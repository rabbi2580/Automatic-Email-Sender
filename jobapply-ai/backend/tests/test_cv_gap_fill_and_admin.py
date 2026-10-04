from app.core.security import create_access_token, hash_password
from app.models import Admin, Profile, Skill, User
from app.schemas.ai import ProfileExtraction, SkillItem
from app.services.pipeline import apply_extraction


def test_parser_gap_fill_never_erases_user_collections(db):
    user = User(email="gap@example.com", password_hash=hash_password("StrongPass1"), full_name="User")
    db.add(user); db.flush()
    profile = Profile(user_id=user.id, full_name="User", email=user.email)
    db.add(profile); db.flush()
    db.add(Skill(user_id=user.id, profile_id=profile.id, name="Existing", canonical="Existing"))
    db.commit()
    apply_extraction(db, user, ProfileExtraction(skills=[SkillItem(name="Parsed")]), None)
    db.commit(); db.refresh(profile)
    assert [s.name for s in profile.skills] == ["Existing"]


def test_admin_has_independent_login_and_csrf(client, db):
    admin = Admin(email="admin@example.com", password_hash=hash_password("StrongPass1"))
    db.add(admin); db.commit()
    user_token = create_access_token(admin.id, "admin")
    assert client.get("/api/v1/admin/health", headers={"Authorization": f"Bearer {user_token}"}).status_code == 403

    login = client.post("/api/v1/admin/login", json={"email": admin.email, "password": "StrongPass1"})
    assert login.status_code == 200
    data = login.json()
    assert data["access_token"] and data["csrf_token"]
    assert client.get("/api/v1/admin/health", headers={"Authorization": f"Bearer {data['access_token']}"}).status_code == 200
    assert client.get("/api/v1/admin/health").status_code == 403
    assert client.get("/api/v1/admin/health", headers={"X-CSRF-Token": data["csrf_token"]}).status_code == 200
