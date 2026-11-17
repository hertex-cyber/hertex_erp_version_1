import os
import shutil
import tempfile

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

TEST_DIR = tempfile.mkdtemp(prefix="hertex-tests-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DIR}/test.db"
os.environ["AUTO_CREATE_TABLES"] = "true"
os.environ["AUTO_SEED"] = "true"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["ENVIRONMENT"] = "test"

import app.core.subscribers  # noqa: E402, F401
from app.db.registry import Base  # noqa: E402
from app.db.seed import seed_all  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import create_app  # noqa: E402

app = create_app()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def prepared_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_all()
    yield
    await engine.dispose()
    shutil.rmtree(TEST_DIR, ignore_errors=True)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://hertex.test") as async_client:
        yield async_client


@pytest_asyncio.fixture
async def auth(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@hertex.dev", "password": "Admin@12345"},
    )
    assert response.status_code == 200, response.text
    tokens = response.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
