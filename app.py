import os
import sqlite3
import smtplib
import imaplib
import email
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import Flask, redirect, render_template, request, session, url_for
from email import message_from_bytes
from classifier import SpamClassifier

app = Flask(__name__)
app.secret_key = "simple-secret-key"
DB_PATH = "./email_app.db"


# --- Database ---

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            email    TEXT UNIQUE,
            password TEXT
        );
        CREATE TABLE IF NOT EXISTS sent_emails (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            sender    TEXT,
            recipient TEXT,
            subject   TEXT,
            body      TEXT
        );
        CREATE TABLE IF NOT EXISTS received_emails (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            message_uid TEXT,
            sender      TEXT,
            recipient   TEXT,
            subject     TEXT,
            body        TEXT,
            label       TEXT,
            score       REAL
        );
    """)
    conn.commit()
    conn.close()


# --- Email helpers ---

def send_email(sender, password, recipient, subject, body):
    msg = MIMEMultipart()
    msg["From"], msg["To"], msg["Subject"] = sender, recipient, subject
    msg.attach(MIMEText(body, "plain"))

    server = smtplib.SMTP(os.environ.get("SMTP_HOST", "smtp.gmail.com"), 587)
    server.starttls()
    server.login(sender, password)
    server.send_message(msg)
    server.quit()

def decode_text(value):
    parts = decode_header(value or "")
    return "".join(
        p.decode(enc or "utf-8", errors="replace") if isinstance(p, bytes) else p
        for p, enc in parts
    )

def get_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode("utf-8", errors="replace")
        return ""
    return (msg.get_payload(decode=True) or b"").decode("utf-8", errors="replace")

def sync_inbox(user_email, password):
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(user_email, password)
    mail.select("inbox")

    _, data = mail.search(None, "ALL")
    uids = data[0].split()[-50:]

    classifier = SpamClassifier()

    with get_conn() as conn:
        for uid in uids:
            uid_str = uid.decode()
            if conn.execute(
                "SELECT 1 FROM received_emails WHERE message_uid=? AND recipient=?",
                (uid_str, user_email)
            ).fetchone():
                continue

            _, raw = mail.fetch(uid, "(RFC822)")
            msg     = message_from_bytes(raw[0][1])
            subject = decode_text(msg.get("Subject", ""))
            body    = get_body(msg)
            label, score = classifier.classify(f"{subject}\n{body}")

            conn.execute(
                "INSERT INTO received_emails (message_uid,sender,recipient,subject,body,label,score) VALUES (?,?,?,?,?,?,?)",
                (uid_str, decode_text(msg.get("From", "")), user_email, subject, body, label, score)
            )

    mail.logout()


# --- Auth helper ---

def logged_in():
    return "user_email" in session


# --- Routes ---

@app.route("/")
def index():
    return redirect(url_for("sent_page" if logged_in() else "login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        with get_conn() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE email=? AND password=?",
                (request.form["email"], request.form["password"])
            ).fetchone()
        if user:
            session["user_email"] = user["email"]
            return redirect(url_for("sent_page"))
        return render_template("login.html", error="Incorrect email or password.")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        try:
            with get_conn() as conn:
                conn.execute("INSERT INTO users (email, password) VALUES (?, ?)",
                             (request.form["email"], request.form["password"]))
        except sqlite3.IntegrityError:
            return render_template("register.html", error="An account with that email already exists.")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/compose", methods=["GET", "POST"])
def compose():
    if not logged_in(): return redirect(url_for("login"))

    if request.method == "POST":
        sender = session["user_email"]
        with get_conn() as conn:
            password = conn.execute("SELECT password FROM users WHERE email=?", (sender,)).fetchone()["password"]
            send_email(sender, password, request.form["recipient"], request.form["subject"], request.form["body"])
            conn.execute(
                "INSERT INTO sent_emails (sender,recipient,subject,body) VALUES (?,?,?,?)",
                (sender, request.form["recipient"], request.form["subject"], request.form["body"])
            )
        return redirect(url_for("sent_page"))

    return render_template("compose.html", user_email=session["user_email"])

@app.route("/sent")
def sent_page():
    if not logged_in(): return redirect(url_for("login"))

    with get_conn() as conn:
        emails = conn.execute(
            "SELECT * FROM sent_emails WHERE sender=? ORDER BY id DESC",
            (session["user_email"],)
        ).fetchall()

    return render_template("sent.html", emails=emails, user_email=session["user_email"])



@app.route("/received")
def received_page():
    if not logged_in(): return redirect(url_for("login"))
    user = session["user_email"]

    with get_conn() as conn:
        password = conn.execute("SELECT password FROM users WHERE email=?", (user,)).fetchone()["password"]

    sync_inbox(user, password)

    with get_conn() as conn:
        emails = conn.execute(
            "SELECT * FROM received_emails WHERE recipient=? AND label='normal' ORDER BY id DESC",
            (user,)
        ).fetchall()

    return render_template("received.html", emails=emails, user_email=user)

@app.route("/spam")
def spam_page():
    if not logged_in(): return redirect(url_for("login"))

    with get_conn() as conn:
        emails = conn.execute(
            "SELECT * FROM received_emails WHERE recipient=? AND label='spam' ORDER BY id DESC",
            (session["user_email"],)
        ).fetchall()

    return render_template("spam.html", emails=emails, user_email=session["user_email"])


if __name__ == "__main__":
    init_db()
    app.run(debug=True)