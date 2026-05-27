import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os


SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "gear@thomascreagh.com")
SMTP_PASS = os.getenv("SMTP_PASS", "")


def send_email(to: str, subject: str, body: str):
    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, to, msg.as_string())
    except Exception as e:
        print(f"Email error: {e}")


def send_account_created(email: str, password: str):
    send_email(
        email,
        "Your Gear Account",
        f"""
        <p>Your account at gear.thomascreagh.com has been created.</p>
        <p><b>Email:</b> {email}<br>
        <b>Password:</b> {password}</p>
        <p>Please log in and change your password.</p>
        """
    )


def send_loan_approved(email: str, locker_code: str, due_date: str, items: list):
    item_list = "".join(f"<li>{i}</li>" for i in items)
    send_email(
        email,
        "Borrow Request Approved",
        f"""
        <p>Your borrow request has been approved.</p>
        <p><b>Locker code:</b> {locker_code}</p>
        <p><b>Due date:</b> {due_date}</p>
        <p><b>Items:</b><ul>{item_list}</ul></p>
        <p>Please take a photo of the locker after collecting your gear.</p>
        """
    )


def send_overdue_notice(email: str, items: list):
    item_list = "".join(f"<li>{i}</li>" for i in items)
    send_email(
        email,
        "Gear Return Overdue",
        f"""
        <p>You have overdue gear. Your account is locked until items are returned.</p>
        <ul>{item_list}</ul>
        <p>Please contact Tom to resolve this.</p>
        """
    )
