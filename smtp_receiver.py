import os
import sqlite3
import time
from email import message_from_bytes
from email.utils import parseaddr
from aiosmtpd.controller import Controller
from classifier import SpamClassifier

DB_PATH = "./email_app.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS received_emails (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            sender     TEXT,
            recipient  TEXT,
            subject    TEXT,
            body       TEXT,
            label      TEXT,
            score      REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def extract_text(msg):
    if msg.is_multipart():
        parts = [
            part.get_payload(decode=True).decode("utf-8", errors="replace")
            for part in msg.walk()
            if part.get_content_type() == "text/plain" and part.get_payload(decode=True)
        ]
        return "\n".join(parts).strip()
    payload = msg.get_payload(decode=True)
    return payload.decode("utf-8", errors="replace").strip() if payload else ""


class Handler:
    def __init__(self):
        self.classifier = SpamClassifier(
            model_path=os.environ.get("SPAM_MODEL_PATH", "spam_model.joblib"),
            vectorizer_path=os.environ.get("VECTORIZER_PATH", "vectorizer.joblib"),
        )

    async def handle_DATA(self, server, session, envelope):
        msg       = message_from_bytes(envelope.original_content or envelope.content)
        sender    = parseaddr(msg.get("From", ""))[1]
        recipient = envelope.rcpt_tos[0] if envelope.rcpt_tos else ""
        subject   = msg.get("Subject", "")
        body      = extract_text(msg)
        label, score = self.classifier.classify(f"{subject}\n{body}")

        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO received_emails (sender,recipient,subject,body,label,score) VALUES (?,?,?,?,?,?)",
            (sender, recipient, subject, body, label, score),
        )
        conn.commit()
        conn.close()
        return "250 OK"


if __name__ == "__main__":
    init_db()
    host = os.environ.get("SMTP_RECEIVER_HOST", "0.0.0.0")
    port = int(os.environ.get("SMTP_RECEIVER_PORT", "8025"))

    controller = Controller(Handler(), hostname=host, port=port)
    controller.start()
    print(f"SMTP receiver running on {host}:{port}")

    while True:
        time.sleep(1)