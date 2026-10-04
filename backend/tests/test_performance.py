"""Regression checks using an isolated SQLite database, never the server DB.

Run from the repository root: python -m unittest discover -s backend/tests -v
"""
import asyncio
import gzip
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.pop("DATABASE_URL_PATH", None)
os.environ["DATABASE_URL"] = "sqlite://"
os.environ.pop("UPLOAD_DIR_PATH", None)
_uploads = tempfile.TemporaryDirectory()
os.environ["UPLOAD_DIR"] = _uploads.name

from sqlalchemy import event
from fastapi import HTTPException, UploadFile
from database import Base, engine, SessionLocal
import models
import schemas
from middleware import PerformanceMiddleware
from routers import loans, admin
from services.overdue import send_overdue_reminders


class LoanPerformanceTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.create_all(engine)
        self.db = SessionLocal()
        user = models.User(email="test@example.com", password_hash="unused", is_approved=True, auto_approve=True)
        self.db.add(user)
        self.db.flush()
        self.user_id = user.id
        self.db.add_all([models.Item(id=i, name=f"Item {i}", locker="top") for i in range(1, 21)])
        for i in range(1, 13):
            loan = models.Loan(user_id=user.id, item_ids=[1, 2, 3], lockers=["top"], status="active", due_date=datetime.utcnow() - timedelta(days=1))
            loan.photos = [models.LoanPhoto(locker="top", photo_type="return", file_path="test.jpg")]
            self.db.add(loan)
        self.db.commit()
        self.db.expunge_all()
        self.user = self.db.get(models.User, self.user_id)
        self.statements = []
        self.listener = lambda conn, cursor, statement, params, context, many: self.statements.append(statement)
        event.listen(engine, "before_cursor_execute", self.listener)

    def tearDown(self):
        event.remove(engine, "before_cursor_execute", self.listener)
        self.db.close()
        Base.metadata.drop_all(engine)

    def selects(self):
        return [s for s in self.statements if s.lstrip().upper().startswith("SELECT")]

    def test_my_loans_loads_photos_in_two_queries(self):
        result = loans.my_loans(self.db, self.user)
        payload = [schemas.LoanOut.model_validate(loan) for loan in result]
        self.assertEqual(len(payload), 12)
        self.assertTrue(all(len(loan.photos) == 1 for loan in payload))
        self.assertEqual(len(self.selects()), 2)

    def test_admin_list_batches_users_items_and_photos(self):
        result = admin.list_loans(False, self.db, self.user)
        self.assertEqual(len(result), 12)
        self.assertEqual(result[0]["item_names"], ["Item 1", "Item 2", "Item 3"])
        self.assertEqual(result[0]["user_email"], "test@example.com")
        self.assertEqual(len(result[0]["photos"]), 1)
        self.assertEqual(len(self.selects()), 3)

    def test_create_uses_latest_codes_and_separates_door(self):
        self.db.add_all([
            models.LockerCode(locker="top", code="old"),
            models.LockerCode(locker="top", code="new"),
            models.LockerCode(locker="twall_door", code="door"),
        ])
        self.db.commit()
        self.statements.clear()
        loan = loans.create_loan(schemas.LoanCreate(lockers=["top", "bottom"], days=1), self.db, self.user)
        self.assertEqual(loan.locker_codes, {"top": "new"})
        self.assertEqual(loan.door_code, "door")
        self.assertEqual(len([s for s in self.selects() if "FROM locker_codes" in s]), 1)

    def test_edit_batches_item_reads_and_preserves_availability(self):
        self.db.query(models.Item).filter(models.Item.id.in_([1, 2, 3])).update({"available": False})
        self.db.commit()
        self.statements.clear()
        loan = loans.update_loan(1, schemas.LoanUpdate(item_ids=list(range(4, 21))), self.db, self.user)
        self.assertEqual(loan.item_ids, list(range(4, 21)))
        self.assertEqual(len([s for s in self.selects() if "FROM items" in s]), 1)
        for item in self.db.query(models.Item).all():
            self.assertEqual(item.available, item.id < 4)

    def test_unavailable_item_rejects_whole_edit(self):
        self.db.query(models.Item).filter(models.Item.id.in_([1, 2, 3, 4])).update({"available": False})
        self.db.commit()
        with self.assertRaises(HTTPException) as error:
            loans.update_loan(1, schemas.LoanUpdate(item_ids=[4, 5]), self.db, self.user)
        self.assertEqual(error.exception.status_code, 400)
        self.db.rollback()
        self.assertEqual(self.db.get(models.Loan, 1).item_ids, [1, 2, 3])
        self.assertFalse(self.db.get(models.Item, 1).available)
        self.assertTrue(self.db.get(models.Item, 5).available)

    def test_return_batches_updates_and_returns_saved_loan(self):
        self.db.query(models.Item).update({"available": False})
        self.db.get(models.Loan, 1).item_ids = list(range(1, 21))
        self.db.commit()
        self.statements.clear()
        result = loans.return_loan(1, self.db, self.user)
        item_updates = [s for s in self.statements if s.startswith("UPDATE items")]
        self.assertEqual(len(item_updates), 1)
        self.assertEqual(result["loan"].status, "returned")
        self.assertEqual(result["loan"].returned_at, result["returned_at"])
        self.assertEqual(len(result["loan"].photos), 1)
        self.assertTrue(all(item.available for item in self.db.query(models.Item).all()))

    def test_missing_return_photo_still_rejects(self):
        self.db.get(models.Loan, 1).lockers = ["top", "bottom"]
        self.db.commit()
        with self.assertRaises(HTTPException) as error:
            loans.return_loan(1, self.db, self.user)
        self.assertEqual(error.exception.status_code, 400)
        self.db.rollback()
        self.assertEqual(self.db.get(models.Loan, 1).status, "active")

    def test_photo_response_includes_replacement(self):
        result = loans.upload_photo(1, "top", "return", UploadFile(filename="photo.jpg", file=io.BytesIO(b"photo")), self.db, self.user)
        self.assertEqual(len(result["loan"].photos), 1)
        self.assertEqual(result["loan"].photos[0].file_path, result["path"])

    def test_nested_groups_share_children_and_reject_cycles(self):
        leaf = models.GearGroup(name="leaf", item_ids=[1, 2])
        self.db.add(leaf)
        self.db.flush()
        parent = models.GearGroup(name="parent", item_ids=[2, 3], group_ids=[leaf.id])
        self.db.add(parent)
        self.db.flush()
        root = models.GearGroup(name="root", item_ids=[], group_ids=[leaf.id, parent.id])
        self.db.add(root)
        self.db.commit()
        self.assertEqual(loans.expand_gear_group(root, self.db), [1, 2, 3])
        leaf.group_ids = [root.id]
        with self.assertRaises(HTTPException):
            loans.expand_gear_group(root, self.db)

    def test_autoclose_batches_all_items(self):
        self.db.query(models.Loan).update({"loan_type": "twall", "created_at": datetime.utcnow() - timedelta(days=2)})
        self.db.query(models.Item).update({"available": False})
        self.db.commit()
        self.statements.clear()
        closed = loans.run_twall_autoclose(self.db)
        self.assertEqual(len(closed), 12)
        self.assertEqual(len([s for s in self.statements if s.startswith("UPDATE items")]), 1)
        self.assertTrue(self.db.get(models.Item, 1).available)
        self.assertFalse(self.db.get(models.Item, 4).available)

    def test_admin_toggle_preserves_item_availability(self):
        result = loans.admin_toggle_return(1, self.db, self.user)
        self.assertEqual(result["status"], "returned")
        self.assertTrue(self.db.get(models.Item, 1).available)
        result = loans.admin_toggle_return(1, self.db, self.user)
        self.assertEqual(result["status"], "active")
        self.assertFalse(self.db.get(models.Item, 1).available)

    def test_overdue_batches_queries_and_consolidates_mail(self):
        with patch("services.overdue.send_overdue_notice") as mail:
            result = send_overdue_reminders(self.db, self.user_id)
        self.assertEqual(len(self.selects()), 2)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["loan_ids"]), 12)
        mail.assert_called_once()


class MiddlewareTests(unittest.TestCase):
    def test_timing_and_catalogue_compression(self):
        body = b'{"items": "' + b"sample catalogue " * 1000 + b'"}'

        async def request(path):
            messages = []
            async def app(scope, receive, send):
                await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
                await send({"type": "http.response.body", "body": body})
            async def send(message):
                messages.append(message)
            await PerformanceMiddleware(app)({"type": "http", "path": path, "headers": [(b"accept-encoding", b"gzip")]}, None, send)
            return dict(messages[0]["headers"]), messages[1]["body"]

        headers, compressed = asyncio.run(request("/items"))
        self.assertEqual(headers[b"content-encoding"], b"gzip")
        self.assertIn(b"app;dur=", headers[b"server-timing"])
        self.assertEqual(gzip.decompress(compressed), body)
        self.assertLess(len(compressed), len(body) / 10)
        headers, uncompressed = asyncio.run(request("/loans/my"))
        self.assertNotIn(b"content-encoding", headers)
        self.assertEqual(uncompressed, body)


if __name__ == "__main__":
    unittest.main()
