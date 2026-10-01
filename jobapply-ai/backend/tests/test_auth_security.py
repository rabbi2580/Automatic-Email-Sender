import time
import uuid

import jwt
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.ratelimit import limiter
from app.core.security import create_access_token
from app.models import RefreshToken, User
from tests.helpers import PASSWORD, register


def test_registration_validation(client):
    base = {"email": "a@example.com", "password": PASSWORD, "full_name": "A", "accept_terms": True}
    assert client.post("/api/v1/auth/register", json={**base, "password": "short"}).status_code == 422
    assert client.post("/api/v1/auth/register", json={**base, "password": "alllowercase123"}).status_code == 422
    assert client.post("/api/v1/auth/register", json={**base, "password": "NoDigitsHereAtAll"}).status_code == 422
    assert client.post("/api/v1/auth/register", json={**base, "accept_terms": False}).status_code == 422
    assert client.post("/api/v1/auth/register", json={**base, "email": "not-an-email"}).status_code == 422
    assert client.post("/api/v1/auth/register", json=base).status_code == 201
    assert client.post("/api/v1/auth/register", json={**base, "email": "A@Example.com"}).status_code == 409  # case-insensitive uniqueness


def test_password_is_hashed_with_argon2id(client, db):
    register(client, "h@example.com")
    u = db.scalar(select(User).where(User.email == "h@example.com"))
    assert u.password_hash.startswith("$argon2id$") and PASSWORD not in u.password_hash


def test_login_errors_are_generic(client):
    register(client, "g@example.com")
    r1 = client.post("/api/v1/auth/login", json={"email": "g@example.com", "password": "WrongPassw0rd!"})
    r2 = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "WrongPassw0rd!"})
    assert r1.status_code == r2.status_code == 401 and r1.json() == r2.json()


def test_account_lockout_after_repeated_failures(client):
    register(client, "l@example.com")
    for _ in range(10):
        assert client.post("/api/v1/auth/login", json={"email": "l@example.com", "password": "WrongPassw0rd!"}).status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": "l@example.com", "password": PASSWORD})  # even the right password is refused while locked
    assert r.status_code == 429 and "Retry-After" in r.headers
    limiter.reset()
    assert client.post("/api/v1/auth/login", json={"email": "l@example.com", "password": PASSWORD}).status_code == 200


def test_refresh_rotation_and_reuse_detection(client, db):
    _, t = register(client, "r@example.com")
    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": t["refresh_token"]})
    assert r1.status_code == 200 and r1.json()["refresh_token"] != t["refresh_token"]
    # replaying the old (rotated) token is treated as theft: whole family revoked
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": t["refresh_token"]}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": r1.json()["refresh_token"]}).status_code == 401
    assert all(rt.revoked_at for rt in db.scalars(select(RefreshToken)))


def test_refresh_tokens_stored_hashed(client, db):
    _, t = register(client, "s@example.com")
    assert db.scalar(select(RefreshToken).where(RefreshToken.token_hash == t["refresh_token"])) is None


def test_logout_revokes(client):
    _, t = register(client, "o@example.com")
    assert client.post("/api/v1/auth/logout", json={"refresh_token": t["refresh_token"]}).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": t["refresh_token"]}).status_code == 401


@pytest.mark.parametrize("make", [
    lambda uid: "garbage",
    lambda uid: jwt.encode({"sub": uid, "type": "access", "exp": int(time.time()) + 600}, "wrong-secret-wrong-secret-wrong-secret", algorithm="HS256"),
    lambda uid: jwt.encode({"sub": uid, "type": "access", "exp": int(time.time()) - 10}, get_settings().secret_key, algorithm="HS256"),
    lambda uid: jwt.encode({"sub": uid, "type": "refresh", "exp": int(time.time()) + 600}, get_settings().secret_key, algorithm="HS256"),
    lambda uid: jwt.encode({"sub": uid, "type": "access"}, None, algorithm="none"),
])
def test_bad_tokens_rejected(client, make):
    headers, _ = register(client, "t@example.com")
    uid = client.get("/api/v1/auth/me", headers=headers).json()["id"]
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {make(uid)}"})
    assert r.status_code == 401


def test_unauthenticated_access_denied_everywhere(client):
    from app.main import app as a

    spec = a.openapi()["paths"]
    public = {"/api/v1/auth/register", "/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/auth/logout", "/api/v1/auth/verify-email",
              "/api/v1/auth/forgot-password", "/api/v1/auth/reset-password", "/api/v1/auth/google/login", "/api/v1/auth/google/callback",
              "/api/v1/files/{token}", "/api/v1/integrations/email/callback/{provider}"}
    for path, methods in spec.items():
        if path in public:
            continue
        for m in methods:
            if m not in ("get", "post", "put", "patch", "delete"):
                continue
            url = path.replace("{", "").replace("}", "")
            url = url.replace("app_id", str(uuid.uuid4())).replace("job_id", str(uuid.uuid4())).replace("doc_id", str(uuid.uuid4()))
            r = client.request(m.upper(), url, json={})
            assert r.status_code in (401, 403, 404, 405, 422) and r.status_code != 200, (m, path, r.status_code)
            if r.status_code != 404 and r.status_code != 405:
                assert r.status_code in (401, 403, 422), (m, path, r.status_code)
            assert r.status_code != 200


def test_token_of_deleted_or_disabled_user_rejected(client, db):
    headers, _ = register(client, "d@example.com")
    u = db.scalar(select(User).where(User.email == "d@example.com"))
    u.is_active = False
    db.commit()
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_change_password_signs_out_everywhere(client):
    headers, t = register(client, "c@example.com")
    r = client.post("/api/v1/auth/change-password", headers=headers, json={"current_password": PASSWORD, "new_password": "An0therStrongPass!"})
    assert r.status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": t["refresh_token"]}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "c@example.com", "password": PASSWORD}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "c@example.com", "password": "An0therStrongPass!"}).status_code == 200
    assert client.post("/api/v1/auth/change-password", headers=headers, json={"current_password": "bad", "new_password": "An0therStrongPass!2"}).status_code == 400


def test_forgot_and_reset_password_flow(client, db):
    register(client, "fp@example.com")
    r = client.post("/api/v1/auth/forgot-password", json={"email": "fp@example.com"})
    assert r.status_code == 200 and r.json()["sent"] is True and "dev_reset_token" in r.json()

    u = db.scalar(select(User).where(User.email == "fp@example.com"))
    assert u.password_reset_token_hash is not None and u.password_reset_expires_at is not None

    token = r.json()["dev_reset_token"]
    rr = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "FreshStrongPass!2"})
    assert rr.status_code == 200 and rr.json()["reset"] is True
    assert client.post("/api/v1/auth/login", json={"email": "fp@example.com", "password": PASSWORD}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "fp@example.com", "password": "FreshStrongPass!2"}).status_code == 200
    db.expire_all()
    u = db.scalar(select(User).where(User.email == "fp@example.com"))
    assert u.password_reset_token_hash is None and u.password_reset_expires_at is None


def test_security_headers_and_no_store(client):
    headers, _ = register(client, "hd@example.com")
    r = client.get("/api/v1/auth/me", headers=headers)
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Frame-Options"] == "DENY" and "no-store" in r.headers["Cache-Control"]
    assert r.headers["X-Request-ID"]


def test_admin_endpoints_require_admin_role(client, db):
    headers, _ = register(client, "u@example.com")
    for path in ("/health", "/users", "/usage", "/ai", "/limits", "/feature-flags", "/delivery-failures", "/audit-log", "/errors", "/integrations"):
        assert client.get(f"/api/v1/admin{path}", headers=headers).status_code == 403, path
    u = db.scalar(select(User).where(User.email == "u@example.com"))
    u.role = "admin"
    db.commit()
    h2 = {"Authorization": f"Bearer {create_access_token(u.id, 'admin')}"}
    assert client.get("/api/v1/admin/health", headers=h2).json()["database"] is True


def test_admin_api_never_exposes_private_content(client, db):
    from tests.helpers import upload_cv

    headers, _ = register(client, "p@example.com")
    upload_cv(client, headers)
    client.post("/api/v1/jobs", headers=headers, json={"text": "Junior Software Engineer\nCompany: Secret Corp Ltd\nRequirements: Python\nSend CV to hr@secret.com"})
    admin = db.scalar(select(User).where(User.email == "p@example.com"))
    admin.role = "admin"
    db.commit()
    h = {"Authorization": f"Bearer {create_access_token(admin.id, 'admin')}"}
    blob = ""
    for path in ("/health", "/users", "/usage", "/ai", "/delivery-failures", "/audit-log", "/errors", "/integrations"):
        blob += client.get(f"/api/v1/admin{path}", headers=h).text
    for secret in ("Secret Corp", "hr@secret.com", "Tarif", "Innovative Techworks", "Blood-Connect", "PyTorch model"):
        assert secret not in blob, secret


def test_rate_limiting_enforced_when_enabled(client):
    from app.main import app as a

    a.state.enforce_rate_limits = True
    codes = [client.post("/api/v1/auth/login", json={"email": "x@example.com", "password": "WrongPassw0rd!"}).status_code for _ in range(14)]
    assert 429 in codes and codes[0] == 401
