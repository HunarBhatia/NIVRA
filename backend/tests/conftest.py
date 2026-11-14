import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

# Configure BEFORE the app is imported: settings are read once.
_tmp = Path(tempfile.mkdtemp(prefix="nivra-test-"))
os.environ["NIVRA_ENVIRONMENT"] = "test"
os.environ["NIVRA_DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["NIVRA_DATA_KEY"] = Fernet.generate_key().decode()
os.environ["NIVRA_AUTH_RATE_LIMIT"] = "1000"
os.environ["NIVRA_INLINE_WORKER"] = "false"
os.environ["NIVRA_AGENT_CHECKPOINT_PATH"] = (_tmp / "agents.db").as_posix()

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.deps import auth_limiter  # noqa: E402
from app.core.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

PASS = "a long test passphrase"


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    auth_limiter.reset()
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def register(client: TestClient, passphrase: str = PASS) -> str:
    r = client.post("/api/auth/register", json={"passphrase": passphrase})
    assert r.status_code == 201, r.text
    return r.json()["account_code"]


@pytest.fixture
def user_client(client: TestClient) -> TestClient:
    """A client that is logged in to a fresh account."""
    client.account_code = register(client)  # type: ignore[attr-defined]
    return client
