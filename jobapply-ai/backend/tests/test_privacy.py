import json
from pathlib import Path

from sqlalchemy import func, select

from app.core.config import get_settings
from app.models import (
    Application, ApplicationDocument, AuditLog, EmailAccount, Job, JobMatch, Profile, RefreshToken, Resume, Skill, Subscription, UsageRecord, User, Experience, Education,
)
from tests.helpers import PASSWORD, connect_gmail_account, install_fake_gmail, register, upload_cv
from tests.test_e2e import job_post


def populate(client, db, email="priv@example.com"):
    install_fake_gmail()
    h, _ = register(client, email)
    upload_cv(client, h)
    j = client.post("/api/v1/jobs", headers=h, json={"text": job_post(0)}).json()["jobs"][0]
    connect_gmail_account(db, email)
    client.post("/api/v1/applications/generate", headers=h, json={"job_ids": [j["id"]]})
    return h


def storage_files(uid):
    root = Path(get_settings().storage_local_path) / "u" / str(uid)
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def test_export_contains_user_data_but_no_secrets(client, db):
    h = populate(client, db)
    r = client.get("/api/v1/privacy/export", headers=h)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    data = json.loads(r.text)
    assert data["account"]["email"] == "priv@example.com" and data["profile"]["full_name"] == "Tarif Ul Haider Rabbi"
    assert data["jobs"] and data["applications"][0]["cover_letter"] and data["tailored_cvs"] and data["resumes"][0]["extracted_text"]
    blob = r.text
    for forbidden in ("refresh_token", "password_hash", "$argon2", "encrypted_credentials", "storage_key", "u/", "gAAAA"):
        assert forbidden not in blob, forbidden


def test_delete_resume_removes_file_and_text(client, db):
    h = populate(client, db)
    rid = client.get("/api/v1/resumes", headers=h).json()[0]["id"]
    uid = db.scalar(select(User.id))
    key = db.scalar(select(Resume.storage_key))
    before = len(storage_files(uid))
    assert client.delete(f"/api/v1/resumes/{rid}", headers=h).status_code == 204
    db.expire_all()
    r = db.scalar(select(Resume))
    assert r.extracted_text == "" and r.deleted_at is not None
    assert not (Path(get_settings().storage_local_path) / key).exists() and len(storage_files(uid)) == before - 1
    assert client.get(f"/api/v1/resumes/{rid}", headers=h).status_code == 404
    # structured profile is separate: kept unless the user asks to remove it too
    assert client.get("/api/v1/profile", headers=h).json()["skills"]


def test_delete_resume_with_profile_data(client, db):
    h = populate(client, db)
    rid = client.get("/api/v1/resumes", headers=h).json()[0]["id"]
    client.delete(f"/api/v1/resumes/{rid}?delete_profile_data=true", headers=h)
    p = client.get("/api/v1/profile", headers=h).json()
    assert p["skills"] == [] and p["experiences"] == [] and p["educations"] == [] and p["projects"] == []


def test_delete_application_history(client, db):
    h = populate(client, db)
    uid = db.scalar(select(User.id))
    assert db.scalar(select(func.count()).select_from(Application)) == 1 and storage_files(uid)
    assert client.delete("/api/v1/privacy/application-history", headers=h).status_code == 204
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Application)) == 0 and db.scalar(select(func.count()).select_from(ApplicationDocument)) == 0
    assert not [f for f in storage_files(uid) if "/docs/" in str(f)]
    assert db.scalar(select(func.count()).select_from(Job)) == 1  # jobs and profile are kept
    assert client.get("/api/v1/profile", headers=h).json()["skills"]


def test_account_deletion_removes_everything(client, db):
    h = populate(client, db)
    uid = db.scalar(select(User.id))
    assert storage_files(uid)
    # needs the exact phrase and the password
    assert client.request("DELETE", "/api/v1/privacy/account", headers=h, json={"confirm": "yes", "password": PASSWORD}).status_code == 422
    assert client.request("DELETE", "/api/v1/privacy/account", headers=h, json={"confirm": "DELETE MY ACCOUNT", "password": "wrong"}).status_code == 403
    assert client.request("DELETE", "/api/v1/privacy/account", headers=h, json={"confirm": "DELETE MY ACCOUNT", "password": PASSWORD}).status_code == 204
    db.expire_all()
    for model in (User, Profile, Skill, Experience, Education, Resume, Job, JobMatch, Application, ApplicationDocument, EmailAccount, RefreshToken, Subscription, UsageRecord):
        assert db.scalar(select(func.count()).select_from(model)) == 0, model.__name__
    assert storage_files(uid) == []
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "priv@example.com", "password": PASSWORD}).status_code == 401
    # audit log keeps an anonymised deletion record only
    rec = db.scalar(select(AuditLog).where(AuditLog.action == "account.deleted"))
    assert rec is not None and rec.user_id is None and "priv@example.com" not in json.dumps(rec.meta)


def test_account_deletion_does_not_touch_other_users(client, db):
    h1 = populate(client, db, "one@example.com")
    h2 = populate(client, db, "two@example.com")
    uid2 = db.scalar(select(User.id).where(User.email == "two@example.com"))
    n2 = len(storage_files(uid2))
    client.request("DELETE", "/api/v1/privacy/account", headers=h1, json={"confirm": "DELETE MY ACCOUNT", "password": PASSWORD})
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Job).where(Job.user_id == uid2)) == 1 and len(storage_files(uid2)) == n2
    assert client.get("/api/v1/profile", headers=h2).json()["skills"]


def test_ai_training_is_opt_in_and_logged(client, db):
    h, _ = register(client)
    assert client.get("/api/v1/auth/me", headers=h).json()["ai_training_opt_in"] is False
    assert client.put("/api/v1/privacy/ai-training", headers=h, json={"opt_in": True}).json()["ai_training_opt_in"] is True
    assert any(a["action"] == "privacy.ai_training" for a in client.get("/api/v1/privacy/audit-log", headers=h).json())


def test_ai_request_logs_never_contain_content(client, db, monkeypatch):
    from app.models import AIRequestLog

    h = populate(client, db)
    cols = {c.name for c in AIRequestLog.__table__.columns}
    assert not ({"prompt", "response", "content", "input", "output", "text"} & cols)


def test_disconnect_email_deletes_credentials(client, db):
    h = populate(client, db)
    aid = client.get("/api/v1/integrations/email", headers=h).json()[0]["id"]
    assert client.delete(f"/api/v1/integrations/email/{aid}", headers=h).status_code == 204
    db.expire_all()
    a = db.scalar(select(EmailAccount))
    assert a.encrypted_credentials == "" and a.status == "revoked"
    assert client.get("/api/v1/integrations/email", headers=h).json() == []


def test_oauth_connect_requires_consent_and_state(client, db, monkeypatch):
    h, _ = register(client)
    assert client.post("/api/v1/integrations/email/connect", headers=h, json={"provider": "gmail", "consent": False}).status_code == 422
    assert client.post("/api/v1/integrations/email/connect", headers=h, json={"provider": "gmail", "consent": True}).status_code == 501  # not configured
    monkeypatch.setattr(get_settings(), "google_client_id", "cid")
    url = client.post("/api/v1/integrations/email/connect", headers=h, json={"provider": "gmail", "consent": True}).json()["authorization_url"]
    assert "gmail.send" in url and "access_type=offline" in url and "state=" in url and "gmail.readonly" not in url and "mail.google.com" not in url  # least privilege
    assert client.get("/api/v1/integrations/email/callback/gmail?code=x&state=forged").status_code == 400
