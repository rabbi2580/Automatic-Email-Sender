"""Every id-addressed route must treat another tenant's objects exactly like missing ones (404)."""
import uuid

from sqlalchemy import select

from app.core.crypto import sign_payload
from app.models import Application, ApplicationDocument, EmailAccount, Job, Resume
from app.services.storage import signed_download_token, verify_download_token
from tests.helpers import connect_gmail_account, install_fake_gmail, register, upload_cv
from tests.test_e2e import job_post


def setup_two(client, db):
    install_fake_gmail()
    ha, _ = register(client, "alice@example.com", name="Alice Example")
    hb, _ = register(client, "bob@example.com", name="Bob Example")
    assert upload_cv(client, ha).status_code == 201
    rid = client.get("/api/v1/resumes", headers=ha).json()[0]["id"]
    jid = client.post("/api/v1/jobs", headers=ha, json={"text": job_post(0)}).json()["jobs"][0]["id"]
    acct = connect_gmail_account(db, "alice@example.com")
    client.post("/api/v1/applications/generate", headers=ha, json={"job_ids": [jid]})
    app_id = client.get("/api/v1/applications", headers=ha).json()["items"][0]["id"]
    doc = db.scalar(select(ApplicationDocument).where(ApplicationDocument.application_id == uuid.UUID(app_id)))
    return ha, hb, dict(resume=rid, job=jid, app=app_id, doc=str(doc.id), acct=str(acct.id))


def test_b_cannot_touch_a_objects(client, db):
    ha, hb, ids = setup_two(client, db)
    R, J, A, D, E = ids["resume"], ids["job"], ids["app"], ids["doc"], ids["acct"]
    checks = [
        ("GET", f"/api/v1/resumes/{R}"), ("POST", f"/api/v1/resumes/{R}/reparse"), ("GET", f"/api/v1/resumes/{R}/download"), ("DELETE", f"/api/v1/resumes/{R}"),
        ("GET", f"/api/v1/jobs/{J}"), ("PATCH", f"/api/v1/jobs/{J}"), ("DELETE", f"/api/v1/jobs/{J}"), ("POST", f"/api/v1/jobs/{J}/retry"), ("POST", f"/api/v1/jobs/{J}/not-duplicate"),
        ("GET", f"/api/v1/matches/{J}"),
        ("GET", f"/api/v1/applications/{A}"), ("PATCH", f"/api/v1/applications/{A}"), ("POST", f"/api/v1/applications/{A}/approve"), ("POST", f"/api/v1/applications/{A}/reject"),
        ("POST", f"/api/v1/applications/{A}/qc"), ("POST", f"/api/v1/applications/{A}/regenerate"), ("PATCH", f"/api/v1/applications/{A}/cover-letter"),
        ("PATCH", f"/api/v1/applications/{A}/email"), ("POST", f"/api/v1/applications/{A}/mark-applied"), ("GET", f"/api/v1/applications/{A}/documents/{D}/url"),
        ("DELETE", f"/api/v1/integrations/email/{E}"), ("POST", f"/api/v1/integrations/email/{E}/default"),
    ]
    bodies = {"PATCH": {"notes": "hacked", "body": "x" * 30, "subject": "x"}, "POST": {}}
    for method, url in checks:
        r = client.request(method, url, headers=hb, json=bodies.get(method) if method != "GET" and method != "DELETE" else None)
        assert r.status_code == 404, (method, url, r.status_code, r.text)
    # ...and nothing was modified
    assert client.get(f"/api/v1/applications/{A}", headers=ha).json()["notes"] == ""
    assert client.get(f"/api/v1/resumes/{R}", headers=ha).status_code == 200


def test_lists_and_aggregates_do_not_leak(client, db):
    ha, hb, ids = setup_two(client, db)
    for url in ("/api/v1/resumes", "/api/v1/jobs", "/api/v1/matches", "/api/v1/applications", "/api/v1/integrations/email", "/api/v1/notifications", "/api/v1/resumes/versions"):
        r = client.get(url, headers=hb)
        body = r.json()
        assert (body if isinstance(body, list) else body.get("items", body)) in ([], {}) or body.get("total") == 0, url
    an = client.get("/api/v1/analytics", headers=hb).json()["cards"]
    assert an["jobs_added"] == 0 and an["applications_sent"] == 0
    prof = client.get("/api/v1/profile", headers=hb).json()
    assert prof["full_name"] == "Bob Example" and prof["skills"] == [] and prof["experiences"] == []
    exp = client.get("/api/v1/privacy/export", headers=hb).text
    assert "Alice" not in exp and "Innovative Techworks" not in exp


def test_b_cannot_generate_or_send_for_a_jobs(client, db):
    ha, hb, ids = setup_two(client, db)
    r = client.post("/api/v1/applications/generate", headers=hb, json={"job_ids": [ids["job"]]})
    assert r.status_code == 404
    r = client.post("/api/v1/applications/send/preview", headers=hb, json={"application_ids": [ids["app"]]})
    assert r.json()["count"] == 0 and r.json()["items"][0]["blocked"] and r.json()["confirmation_token"] is None
    r = client.post("/api/v1/applications/approve-bulk", headers=hb, json={"application_ids": [ids["app"]]})
    assert r.json()["approved"] == 0
    r = client.post("/api/v1/applications/send", headers=hb, json={"application_ids": [ids["app"]], "confirmation_token": "x", "confirm": True})
    assert r.status_code == 409
    # B cannot attach A's email account / documents to B's own application
    client.post("/api/v1/profile/structured", headers=hb, json={})  # no-op
    r = client.patch(f"/api/v1/applications/{ids['app']}/email", headers=hb, json={"email_account_id": ids["acct"]})
    assert r.status_code == 404


def test_signed_urls_are_user_bound_and_expire(client, db):
    ha, hb, ids = setup_two(client, db)
    url = client.get(f"/api/v1/applications/{ids['app']}/documents/{ids['doc']}/url", headers=ha).json()["url"]
    token = url.rsplit("/", 1)[1]
    assert client.get(f"/api/v1/files/{token}").status_code == 200  # valid link works without auth header (that is the point of a signed URL)
    r = client.get(f"/api/v1/files/{token}")
    assert r.headers["content-type"].startswith("application/") and "attachment" in r.headers["content-disposition"] and r.headers["x-content-type-options"] == "nosniff"
    # tampering
    assert client.get(f"/api/v1/files/{token[:-3]}abc").status_code == 403
    assert client.get("/api/v1/files/not-a-token").status_code == 403
    # a token for another user's key prefix, even if correctly signed, is refused
    uid_b = client.get("/api/v1/auth/me", headers=hb).json()["id"]
    key_a = db.scalar(select(ApplicationDocument.storage_key))
    forged = sign_payload({"u": uid_b, "k": key_a, "f": "x.pdf", "t": "application/pdf"}, 300, "download")
    assert verify_download_token(forged) is None and client.get(f"/api/v1/files/{forged}").status_code == 403
    # expired
    expired = sign_payload({"u": "u", "k": "u/u/docs/x.pdf", "f": "x", "t": "x"}, -5, "download")
    assert verify_download_token(expired) is None
    # tokens signed for another purpose cannot be replayed as downloads
    other = sign_payload({"u": uid_b, "k": f"u/{uid_b}/docs/x.pdf", "f": "x", "t": "x"}, 300, "send")
    assert verify_download_token(other) is None


def test_storage_rejects_path_traversal():
    from app.services.storage import LocalStorage
    import tempfile
    import pytest

    s = LocalStorage(tempfile.mkdtemp())
    for bad in ("../etc/passwd", "/abs/path", "u/x/../../y", "a b", "u/x/\x00"):
        with pytest.raises(ValueError):
            s.put(bad, b"x")


def test_deleted_objects_are_gone_for_owner_too(client, db):
    ha, hb, ids = setup_two(client, db)
    assert client.delete(f"/api/v1/jobs/{ids['job']}", headers=ha).status_code == 204
    assert client.get(f"/api/v1/jobs/{ids['job']}", headers=ha).status_code == 404
    assert client.get(f"/api/v1/applications/{ids['app']}", headers=ha).status_code in (200, 404)
    assert client.get("/api/v1/applications", headers=ha).json()["total"] == 0
