import os
import shutil
import tempfile
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

TEST_DIR = tempfile.mkdtemp(prefix="hertex-tests-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DIR}/test.db"
os.environ["AUTO_CREATE_TABLES"] = "true"
os.environ["AUTO_SEED"] = "true"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["ENVIRONMENT"] = "test"
os.environ["AUTH_RATE_LIMIT_PER_MINUTE"] = "1000"

import app.core.subscribers  # noqa: E402, F401
from app.db.registry import Base  # noqa: E402
from app.db.seed import seed_all  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.modules.identity.models import User  # noqa: E402

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


@pytest_asyncio.fixture
async def approver_auth(client, auth):
    marker = uuid4().hex
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"finance-approver-{marker}@example.com",
            "password": "Quartz!Maple#R8v",
            "full_name": "Finance Approver",
            "tenant_name": f"Finance Approver {marker}",
        },
    )
    assert response.status_code == 201, response.text
    token_data = response.json()
    async with AsyncSessionLocal() as db:
        requester = await db.scalar(select(User).where(User.email == "admin@hertex.dev"))
        approver = await db.scalar(select(User).where(User.email == f"finance-approver-{marker}@example.com"))
        assert requester is not None and approver is not None
        approver.tenant_id = requester.tenant_id
        approver.is_superuser = True
        await db.commit()
    return {"Authorization": f"Bearer {token_data['access_token']}"}


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
