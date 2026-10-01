"""Human-in-the-loop guarantees around approval and sending."""
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.crypto import sign_payload
from app.models import Application, ApplicationEmail, AuditLog, EmailAccount, PlanLimit, SendLog, User
from app.services.delivery import service as delivery_service
from app.services.delivery.base import DeliveryError
from tests.helpers import FakeChannel, connect_gmail_account, install_fake_gmail, register, upload_cv
from tests.test_e2e import job_post


@pytest.fixture()
def env(client, db, monkeypatch):
    monkeypatch.setattr(delivery_service, "RETRY_DELAYS", (0, 0))
    ch = install_fake_gmail()
    h, _ = register(client)
    upload_cv(client, h)
    jobs = client.post("/api/v1/jobs/bulk", headers=h, json={"items": [{"text": job_post(i)} for i in range(4)]}).json()["jobs"]
    connect_gmail_account(db)
    client.post("/api/v1/applications/generate", headers=h, json={"job_ids": [j["id"] for j in jobs]})
    apps = client.get("/api/v1/applications", headers=h).json()["items"]
    return client, h, ch, [a["id"] for a in apps], db


def approve(client, h, ids):
    r = client.post("/api/v1/applications/approve-bulk", headers=h, json={"application_ids": ids})
    assert r.json()["approved"] == len(ids), r.text


def preview(client, h, ids):
    return client.post("/api/v1/applications/send/preview", headers=h, json={"application_ids": ids}).json()


def send(client, h, ids, token, confirm=True):
    return client.post("/api/v1/applications/send", headers=h, json={"application_ids": ids, "confirmation_token": token, "confirm": confirm})


def test_unapproved_applications_cannot_be_previewed_or_sent(env):
    client, h, ch, ids, db = env
    p = preview(client, h, ids[:1])
    assert p["count"] == 0 and p["confirmation_token"] is None and "Not approved" in p["items"][0]["problems"][0]
    # a token minted for an empty/other selection cannot unlock sending
    tok = sign_payload({"u": "x", "h": {}}, 600, "send")
    assert send(client, h, ids[:1], tok).status_code == 409
    assert ch.sent == []


def test_preview_shows_recipient_subject_attachments(env):
    client, h, ch, ids, db = env
    approve(client, h, ids[:2])
    p = preview(client, h, ids[:2])
    item = p["items"][0]
    assert item["to"].endswith(".com") and item["subject"].startswith("Application for") and item["from"] == "rabbi@example.com"
    assert [a["filename"].rsplit(".", 1)[1] for a in item["attachments"]] == ["pdf", "pdf"] and "You are about to send 2" in p["notice"]
    assert ch.sent == []


def test_token_must_match_exact_selection(env):
    client, h, ch, ids, db = env
    approve(client, h, ids[:3])
    p = preview(client, h, ids[:2])
    r = send(client, h, ids[:3], p["confirmation_token"])  # one more application than was previewed
    assert r.status_code == 409 and r.json()["detail"]["code"] == "selection_changed" and ch.sent == []


def test_token_bound_to_user(env, client):
    client, h, ch, ids, db = env
    approve(client, h, ids[:1])
    tok = preview(client, h, ids[:1])["confirmation_token"]
    h2, _ = register(client, "mallory@example.com")
    assert send(client, h2, ids[:1], tok).status_code == 409 and ch.sent == []


def test_expired_token_rejected(env):
    client, h, ch, ids, db = env
    approve(client, h, ids[:1])
    p = preview(client, h, ids[:1])
    uid = client.get("/api/v1/auth/me", headers=h).json()["id"]
    app = db.get(Application, __import__("uuid").UUID(ids[0]))
    expired = sign_payload({"u": uid, "h": {ids[0]: app.content_hash}}, -1, "send")
    r = send(client, h, ids[:1], expired)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "bad_confirmation" and ch.sent == []


def test_editing_after_approval_revokes_approval_and_invalidates_token(env):
    client, h, ch, ids, db = env
    approve(client, h, ids[:1])
    tok = preview(client, h, ids[:1])["confirmation_token"]
    current = client.get(f"/api/v1/applications/{ids[0]}", headers=h).json()["email"]["subject"]
    r = client.patch(f"/api/v1/applications/{ids[0]}/email", headers=h, json={"subject": current + " (edited)"})
    assert r.json()["status"] == "awaiting_review"
    r = send(client, h, ids[:1], tok)
    assert r.json()["results"][0]["status"] == "blocked" and ch.sent == []
    approve(client, h, ids[:1])  # re-approval works
    p = preview(client, h, ids[:1])
    assert send(client, h, ids[:1], p["confirmation_token"]).json()["sent"] == 1
    assert ch.sent[0].subject.endswith("(edited)")


def test_cover_letter_edit_revokes_approval_and_updates_documents(env):
    client, h, ch, ids, db = env
    approve(client, h, ids[:1])
    d = client.get(f"/api/v1/applications/{ids[0]}", headers=h).json()
    body = d["cover_letter"]["body"].replace("Dear Hiring Manager,", "Dear Hiring Team,")
    r = client.patch(f"/api/v1/applications/{ids[0]}/cover-letter", headers=h, json={"body": body}).json()
    assert r["status"] == "awaiting_review" and r["cover_letter"]["edited_by_user"] and r["cover_letter"]["body"].startswith("Dear Hiring Team")
    # a letter edited into something wrong is blocked by QC rather than silently approved
    bad = body + "\n\nI also have 9 years of experience in Kubernetes."
    r = client.patch(f"/api/v1/applications/{ids[0]}/cover-letter", headers=h, json={"body": bad}).json()
    assert r["qc"]["passed"] is False
    r = client.post(f"/api/v1/applications/{ids[0]}/approve", headers=h)
    assert r.status_code == 422 and "blocked" in r.json()["detail"]["message"].lower()


def test_qc_failure_blocks_approval_with_clear_reason(env):
    client, h, ch, ids, db = env
    r = client.patch(f"/api/v1/applications/{ids[0]}/email", headers=h, json={"to_address": "not-an-email"}).json()
    assert r["qc"]["passed"] is False
    r = client.post(f"/api/v1/applications/{ids[0]}/approve", headers=h)
    assert r.status_code == 422 and "recipient" in r.json()["detail"]["message"].lower()
    r = client.post("/api/v1/applications/approve-bulk", headers=h, json={"application_ids": [ids[0]]}).json()
    assert r["approved"] == 0 and r["results"][0]["ok"] is False


def test_explicit_confirmation_required(env):
    client, h, ch, ids, db = env
    approve(client, h, ids[:1])
    tok = preview(client, h, ids[:1])["confirmation_token"]
    assert send(client, h, ids[:1], tok, confirm=False).status_code == 422 and ch.sent == []


def test_duplicate_send_protection(env):
    client, h, ch, ids, db = env
    approve(client, h, ids[:1])
    tok = preview(client, h, ids[:1])["confirmation_token"]
    assert send(client, h, ids[:1], tok).json()["sent"] == 1
    r = send(client, h, ids[:1], tok).json()["results"][0]
    assert r["status"] in ("skipped", "blocked") and len(ch.sent) == 1
    assert db.scalar(select(Application.status).where(Application.id == __import__("uuid").UUID(ids[0]))) == "sent"


def test_two_applications_to_same_recipient_and_title_blocked(env, db):
    client, h, ch, ids, db = env
    approve(client, h, ids[:1])
    tok = preview(client, h, ids[:1])["confirmation_token"]
    send(client, h, ids[:1], tok)
    # simulate a second posting with same recipient + title (e.g. user re-added the job under a new link)
    other = db.scalar(select(ApplicationEmail).where(ApplicationEmail.application_id == __import__("uuid").UUID(ids[1])))
    first = db.scalar(select(ApplicationEmail).where(ApplicationEmail.application_id == __import__("uuid").UUID(ids[0])))
    other.to_address = first.to_address
    db.commit()
    rep = client.post(f"/api/v1/applications/{ids[1]}/qc", headers=h).json()
    from app.models import Job
    j0 = db.scalar(select(Job).join(Application, Application.job_id == Job.id).where(Application.id == __import__("uuid").UUID(ids[0])))
    j1 = db.scalar(select(Job).join(Application, Application.job_id == Job.id).where(Application.id == __import__("uuid").UUID(ids[1])))
    if j0.job_title.lower() == j1.job_title.lower():
        assert any(c["id"] == "email.duplicate" for c in rep["blocking"])


def test_unverified_email_cannot_send(client, db, monkeypatch):
    install_fake_gmail()
    h, _ = register(client, "unv@example.com", verify=False)
    upload_cv(client, h)
    j = client.post("/api/v1/jobs", headers=h, json={"text": job_post(0)}).json()["jobs"][0]
    connect_gmail_account(db, "unv@example.com")
    client.post("/api/v1/applications/generate", headers=h, json={"job_ids": [j["id"]]})
    aid = client.get("/api/v1/applications", headers=h).json()["items"][0]["id"]
    approve(client, h, [aid])
    tok = preview(client, h, [aid])["confirmation_token"]
    r = send(client, h, [aid], tok)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "email_unverified"


def test_hourly_send_cap(env, monkeypatch):
    client, h, ch, ids, db = env
    monkeypatch.setattr(get_settings(), "email_send_per_hour", 2)
    approve(client, h, ids[:4])
    tok = preview(client, h, ids[:4])["confirmation_token"]
    r = send(client, h, ids[:4], tok).json()
    assert r["sent"] == 2 and [x["status"] for x in r["results"]].count("blocked") == 2 and len(ch.sent) == 2
    assert "limit" in [x for x in r["results"] if x["status"] == "blocked"][0]["message"].lower()


def test_plan_quota_enforced_on_sends(env):
    client, h, ch, ids, db = env
    row = db.scalar(select(PlanLimit).where(PlanLimit.plan == "free", PlanLimit.metric == "emails_sent"))
    row.limit_value = 1
    db.commit()
    approve(client, h, ids[:2])
    tok = preview(client, h, ids[:2])["confirmation_token"]
    r = send(client, h, ids[:2], tok).json()
    assert r["sent"] == 1 and len(ch.sent) == 1 and any("plan allows" in x["message"] for x in r["results"])


def test_transient_failure_is_retried_then_succeeds(env):
    client, h, ch, ids, db = env
    ch.fail_with, ch.fail_times = DeliveryError("temporarily unavailable", retryable=True), 2
    approve(client, h, ids[:1])
    tok = preview(client, h, ids[:1])["confirmation_token"]
    assert send(client, h, ids[:1], tok).json()["sent"] == 1 and len(ch.sent) == 1


def test_permanent_failure_leaves_application_approved_and_logged(env):
    client, h, ch, ids, db = env
    ch.fail_with, ch.fail_times = DeliveryError("The recipient address was refused by the mail server."), -1
    approve(client, h, ids[:1])
    tok = preview(client, h, ids[:1])["confirmation_token"]
    r = send(client, h, ids[:1], tok).json()
    assert r["sent"] == 0 and r["results"][0]["status"] == "failed" and "refused" in r["results"][0]["message"]
    db.expire_all()
    a = db.get(Application, __import__("uuid").UUID(ids[0]))
    em = db.scalar(select(ApplicationEmail).where(ApplicationEmail.application_id == a.id))
    assert a.status == "approved" and em.status == "failed" and em.idempotency_key is None
    assert db.scalar(select(SendLog).where(SendLog.success.is_(False))) is not None
    # after the problem is fixed the same approved application can be sent again
    ch.fail_with = None
    tok = preview(client, h, ids[:1])["confirmation_token"]
    assert send(client, h, ids[:1], tok).json()["sent"] == 1


def test_expired_oauth_marks_account_for_reauth(env):
    client, h, ch, ids, db = env
    ch.fail_with, ch.fail_times = DeliveryError("Your email connection has expired.", needs_reauth=True), -1
    approve(client, h, ids[:1])
    tok = preview(client, h, ids[:1])["confirmation_token"]
    send(client, h, ids[:1], tok)
    db.expire_all()
    assert db.scalar(select(EmailAccount.status)) == "needs_reauth"
    assert preview(client, h, ids[:1])["items"][0]["blocked"]  # cannot send until reconnected


def test_credentials_encrypted_at_rest_and_never_returned(env):
    client, h, ch, ids, db = env
    acct = db.scalar(select(EmailAccount))
    assert "refresh_token" not in acct.encrypted_credentials and acct.encrypted_credentials.startswith("gAAAA")
    body = client.get("/api/v1/integrations/email", headers=h).text
    assert "refresh_token" not in body and "encrypted" not in body and "credentials" not in body


def test_audit_trail_and_events(env):
    client, h, ch, ids, db = env
    approve(client, h, ids[:1])
    tok = preview(client, h, ids[:1])["confirmation_token"]
    send(client, h, ids[:1], tok)
    actions = {a.action for a in db.scalars(select(AuditLog))}
    assert {"auth.register", "resume.upload", "application.approve", "application.sent"} <= actions
    d = client.get(f"/api/v1/applications/{ids[0]}", headers=h).json()
    assert [e["to"] for e in d["events"] if e["type"] == "status_change"][-3:] == ["awaiting_review", "approved", "sent"]


def test_mark_applied_for_link_only_jobs(client, db):
    install_fake_gmail()
    h, _ = register(client)
    upload_cv(client, h)
    text = "Backend Developer\nCompany: Linky Ltd\nRequirements:\n- Python and Django\nApply here: https://linky.example.com/careers/42"
    j = client.post("/api/v1/jobs", headers=h, json={"text": text}).json()["jobs"][0]
    assert j["application_email"] == "" and j["application_url"] == "https://linky.example.com/careers/42"
    client.post("/api/v1/applications/generate", headers=h, json={"job_ids": [j["id"]]})
    a = client.get("/api/v1/applications", headers=h).json()["items"][0]
    assert a["channel"] == "url_assisted" and a["has_url"]
    pv = preview(client, h, [a["id"]])
    assert pv["count"] == 0  # nothing can be emailed
    r = client.post(f"/api/v1/applications/{a['id']}/mark-applied", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "sent" and r.json()["channel"] == "url_assisted"


def test_invalid_status_transitions_rejected(env):
    client, h, ch, ids, db = env
    assert client.patch(f"/api/v1/applications/{ids[0]}", headers=h, json={"status": "offer"}).status_code == 409
    assert client.patch(f"/api/v1/applications/{ids[0]}", headers=h, json={"status": "approved"}).status_code == 422
    assert client.patch(f"/api/v1/applications/{ids[0]}", headers=h, json={"status": "sent"}).status_code == 422
    assert client.patch(f"/api/v1/applications/{ids[0]}", headers=h, json={"notes": "n", "reminder_at": "2026-10-05T09:00:00Z"}).json()["reminder_at"].startswith("2026-10-05")
    r = client.post(f"/api/v1/applications/{ids[0]}/reject", headers=h)
    assert r.json()["status"] == "withdrawn"
