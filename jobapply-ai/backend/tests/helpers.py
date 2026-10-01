import io
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.services.delivery.base import DeliveryChannel, DeliveryError, OutgoingEmail
from app.services.delivery.registry import register_channel

FIX = Path(__file__).parent / "fixtures"
PASSWORD = "Str0ngPassw0rd!"


def make_pdf(text: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in text.split("\n"):
        c.setFont("Helvetica", 9)
        c.drawString(40, y, line[:110])
        y -= 12
        if y < 40:
            c.showPage()
            y = 800
    c.save()
    return buf.getvalue()


def cv_pdf() -> bytes:
    return make_pdf((FIX / "sample_cv.txt").read_text())


class FakeChannel(DeliveryChannel):
    name = "fake"

    def __init__(self):
        self.sent: list[OutgoingEmail] = []
        self.fail_with: DeliveryError | None = None
        self.fail_times = 0

    def send(self, credentials, message):
        if self.fail_with and self.fail_times != 0:
            self.fail_times -= 1
            raise self.fail_with
        self.sent.append(message)
        return f"msg-{len(self.sent)}"


def install_fake_gmail() -> FakeChannel:
    ch = FakeChannel()
    register_channel("gmail", ch)
    return ch


def register(client, email="rabbi@example.com", verify=True, name="Tarif Ul Haider Rabbi"):
    r = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD, "full_name": name, "accept_terms": True})
    assert r.status_code == 201, r.text
    if verify:
        assert client.post("/api/v1/auth/verify-email", json={"token": r.json()["dev_verification_token"]}).status_code == 200
    t = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert t.status_code == 200, t.text
    return {"Authorization": f"Bearer {t.json()['access_token']}"}, t.json()


def upload_cv(client, headers, data=None, name="cv.pdf"):
    return client.post("/api/v1/resumes/upload", headers=headers, files={"file": (name, data or cv_pdf(), "application/pdf")})


def connect_gmail_account(db, user_email="rabbi@example.com"):
    """Insert a connected Gmail account directly (the OAuth dance needs Google)."""
    import json

    from sqlalchemy import select

    from app.core.crypto import encrypt_str
    from app.models import EmailAccount, User
    from app.models.base import utcnow

    u = db.scalar(select(User).where(User.email == user_email))
    a = EmailAccount(user_id=u.id, provider="gmail", address=user_email, display_name="Tarif", encrypted_credentials=encrypt_str(json.dumps({"refresh_token": "x"})),
                     scopes=["gmail.send"], consent_given_at=utcnow(), is_default=True)
    db.add(a)
    db.commit()
    return a
