import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="jobapply-test-")
os.environ.update({
    "ENVIRONMENT": "test", "DATABASE_URL": os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db", "STORAGE_LOCAL_PATH": f"{_tmp}/storage", "TASK_MODE": "inline",
    "AI_PROVIDER": "heuristic", "SECRET_KEY": "test-secret-key-test-secret-key-test-secret-key", "REQUIRE_VERIFIED_EMAIL_TO_SEND": "true",
    "API_BASE_URL": "http://testserver", "PUBLIC_BASE_URL": "http://localhost:3000",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.core.ratelimit import limiter  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.services import storage as storage_mod  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    import app.models  # noqa: F401

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from app.services.usage import seed_plan_limits

    with SessionLocal() as db:
        seed_plan_limits(db)
    storage_mod.reset_storage()
    limiter.reset()
    fastapi_app.state.enforce_rate_limits = False
    yield


@pytest.fixture()
def client():
    with TestClient(fastapi_app) as c:
        yield c


@pytest.fixture()
def db():
    with SessionLocal() as s:
        yield s
