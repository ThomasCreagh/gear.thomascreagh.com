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
        <p>Your gear loan is overdue. Please return it as soon as you can.</p>
        <ul>{items_html}</ul>
        <p><b>How to return your gear:</b></p>
        <ol>
          <li>Log in to <a href="https://gear.thomascreagh.com/myloans.html">My Loans</a>.</li>
          <li>Open this loan and select <b>Get return codes</b>.</li>
          <li>Put all of the gear back in its lockers and follow the return steps shown for that loan, including any required photos.</li>
          <li>Select <b>Return gear</b> to finish the return.</li>
        </ol>
        <p>If you need help returning the gear, please contact Tom.</p>
    """)
