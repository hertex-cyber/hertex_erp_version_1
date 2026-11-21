from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_permissions
from app.db.session import get_db
from app.modules.identity.models import User
from app.modules.integrations.external_credentials import (
    CredentialMutationRead,
    ExternalConnectionRead,
    ExternalCredentialRotate,
    ExternalCredentialWrite,
    ExternalProviderRead,
    external_credentials_service,
)

router = APIRouter(prefix="/integrations/external")

read_external = require_permissions("integrations.channel.manage", "settings.setting.read")
write_external = require_permissions("integrations.channel.manage", "system.settings.manage")


@router.get(
    "/providers",
    response_model=list[ExternalProviderRead],
    tags=["Integrations · External credentials"],
)
async def list_external_providers(
    user: User = Depends(read_external),
    db: AsyncSession = Depends(get_db),
):
    return await external_credentials_service.list_providers(db, user.tenant_id)


@router.get(
    "/providers/{provider}",
    response_model=ExternalProviderRead,
    tags=["Integrations · External credentials"],
)
async def get_external_provider(
    provider: str,
    user: User = Depends(read_external),
    db: AsyncSession = Depends(get_db),
):
    return await external_credentials_service.get_provider(db, user.tenant_id, provider)


@router.put(
    "/providers/{provider}/credentials",
    response_model=ExternalProviderRead,
    tags=["Integrations · External credentials"],
)
async def replace_external_credentials(
    provider: str,
    payload: ExternalCredentialWrite,
    user: User = Depends(write_external),
    db: AsyncSession = Depends(get_db),
):
    return await external_credentials_service.set_credentials(
        db,
        user,
        provider=provider,
        credentials=payload.credentials,
        reason=payload.reason,
    )


@router.post(
    "/providers/{provider}/credentials/{field}/rotate",
    response_model=CredentialMutationRead,
    tags=["Integrations · External credentials"],
)
async def rotate_external_credential(
    provider: str,
    field: str,
    payload: ExternalCredentialRotate,
    user: User = Depends(write_external),
    db: AsyncSession = Depends(get_db),
):
    return await external_credentials_service.rotate(
        db,
        user,
        provider=provider,
        field=field,
        value=payload.value,
        window_hours=payload.window_hours,
    )


@router.post(
    "/providers/{provider}/credentials/{field}/commit",
    response_model=CredentialMutationRead,
    tags=["Integrations · External credentials"],
)
async def commit_external_credential(
    provider: str,
    field: str,
    user: User = Depends(write_external),
    db: AsyncSession = Depends(get_db),
):
    return await external_credentials_service.commit(
        db, user, provider=provider, field=field
    )


@router.post(
    "/providers/{provider}/credentials/{field}/rollback",
    response_model=CredentialMutationRead,
    tags=["Integrations · External credentials"],
)
async def rollback_external_credential(
    provider: str,
    field: str,
    user: User = Depends(write_external),
    db: AsyncSession = Depends(get_db),
):
    return await external_credentials_service.rollback(
        db, user, provider=provider, field=field
    )


@router.post(
    "/providers/{provider}/test-connection",
    response_model=ExternalConnectionRead,
    tags=["Integrations · External credentials"],
)
async def test_external_connection(
    provider: str,
    user: User = Depends(write_external),
    db: AsyncSession = Depends(get_db),
):
    return await external_credentials_service.test_connection(db, user, provider=provider)
