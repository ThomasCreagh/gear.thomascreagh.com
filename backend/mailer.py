import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import read_secret

SMTP_HOST = read_secret("SMTP_HOST", "localhost")
SMTP_PORT = int(read_secret("SMTP_PORT", "587"))
SMTP_USER = read_secret("SMTP_USER", "gear@thomascreagh.com")
SMTP_PASS = read_secret("SMTP_PASS", "")
ADMIN_EMAIL = read_secret("ADMIN_EMAIL", "tom@thomascreagh.com")


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
    send_email(email, "Your Gear Account", f"""
        <p>Your account at gear.thomascreagh.com has been created.</p>
        <p><b>Email:</b> {email}<br><b>Password:</b> {password}</p>
        <p>Please log in and change your password.</p>
    """)


def send_loan_approved(email: str, locker_codes: dict, due_date: str, items: list):
    codes_html = "".join(
        f"<li><b>{k.title()}:</b> {v}</li>" for k, v in locker_codes.items())
    items_html = "".join(f"<li>{i}</li>" for i in items)
    send_email(email, "Borrow Request Approved", f"""
        <p>Your borrow request has been approved.</p>
        <p><b>Due date:</b> {due_date}</p>
        <p><b>Locker codes:</b><ul>{codes_html}</ul></p>
        <p><b>Items:</b><ul>{items_html}</ul></p>
        <p>Please photograph each locker after collecting your gear.</p>
        <p><b>You are responsible for all borrowed gear. Any damage or loss must be reported to Tom immediately.</b></p>
    """)


def send_loan_pending_admin(user_email: str, items: list):
    items_html = "".join(f"<li>{i}</li>" for i in items)
    send_email(ADMIN_EMAIL, "New Gear Borrow Request", f"""
        <p>{user_email} has requested to borrow gear:</p>
        <ul>{items_html}</ul>
        <p>Log in to the admin panel to approve or deny.</p>
    """)


def send_overdue_notice(email: str, items: list):
    items_html = "".join(f"<li>{i}</li>" for i in items)
    send_email(email, "Gear Return Overdue", f"""
        <p>You have overdue gear. Your account is now locked.</p>
        <ul>{items_html}</ul>
        <p>Contact Tom immediately to resolve this.</p>
    """)
