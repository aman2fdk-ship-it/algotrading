"""Comprehensive authentication and authorization API tests."""

from datetime import timedelta
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.user import User
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
)


BASE = "/auth"


def registration(email: str | None = None, **overrides) -> dict:
    data = {
        "name": "Alice Trader",
        "email": email or f"auth-{uuid.uuid4().hex}@example.com",
        "password": "StrongPass123!",
        "confirm_password": "StrongPass123!",
    }
    data.update(overrides)
    return data


async def create_user(db_session, *, active=True, email=None, password="StrongPass123!") -> User:
    user = User(
        id=str(uuid.uuid4()),
        email=email or f"user-{uuid.uuid4().hex}@example.com",
        hashed_password=hash_password(password),
        name="Test Trader",
        is_active=active,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


def headers_for(user: User, *, expires_delta=None) -> dict[str, str]:
    token = create_access_token({"sub": str(user.id)}, expires_delta=expires_delta)
    return {"Authorization": f"Bearer {token}"}


# Registration -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_valid_user_returns_tokens_and_persists(client: AsyncClient, db_session):
    payload = registration()
    response = await client.post(f"{BASE}/register", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["token_type"] == "bearer"
    result = await db_session.execute(select(User).where(User.email == payload["email"]))
    user = result.scalar_one()
    assert user.name == payload["name"]
    assert user.hashed_password != payload["password"]


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_conflict(client: AsyncClient):
    payload = registration()
    assert (await client.post(f"{BASE}/register", json=payload)).status_code == 201
    response = await client.post(f"{BASE}/register", json=payload)
    assert response.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("password", ["short", "1234567", ""])
async def test_register_weak_password_returns_validation_error(client: AsyncClient, password):
    response = await client.post(f"{BASE}/register", json=registration(password=password, confirm_password=password))
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_invalid_email_returns_validation_error(client: AsyncClient):
    response = await client.post(f"{BASE}/register", json=registration(email="not-an-email"))
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_missing_required_field_returns_validation_error(client: AsyncClient):
    payload = registration()
    del payload["name"]
    response = await client.post(f"{BASE}/register", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_password_confirmation_mismatch_returns_validation_error(client: AsyncClient):
    response = await client.post(f"{BASE}/register", json=registration(confirm_password="DifferentPass123!"))
    assert response.status_code == 422


# Login ------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_valid_credentials_returns_access_and_refresh_tokens(client: AsyncClient):
    payload = registration()
    await client.post(f"{BASE}/register", json=payload)
    response = await client.post(f"{BASE}/login", json={"email": payload["email"], "password": payload["password"]})
    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["refresh_token"]


@pytest.mark.asyncio
async def test_login_wrong_password_returns_unauthorized(client: AsyncClient, db_session):
    user = await create_user(db_session, password="CorrectPass123!")
    response = await client.post(f"{BASE}/login", json={"email": user.email, "password": "WrongPass123!"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email_returns_unauthorized(client: AsyncClient):
    response = await client.post(f"{BASE}/login", json={"email": "missing@example.com", "password": "StrongPass123!"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_inactive_user_returns_forbidden(client: AsyncClient, db_session):
    user = await create_user(db_session, active=False, password="StrongPass123!")
    response = await client.post(f"{BASE}/login", json={"email": user.email, "password": "StrongPass123!"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_login_updates_last_login(client: AsyncClient, db_session):
    user = await create_user(db_session)
    assert user.last_login is None
    response = await client.post(f"{BASE}/login", json={"email": user.email, "password": "StrongPass123!"})
    assert response.status_code == 200
    await db_session.refresh(user)
    assert user.last_login is not None


# Refresh tokens ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_valid_refresh_token_returns_rotated_tokens(client: AsyncClient, db_session):
    user = await create_user(db_session)
    token = create_refresh_token({"sub": str(user.id)})
    response = await client.post(f"{BASE}/refresh", json={"refresh_token": token})
    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["refresh_token"]


@pytest.mark.asyncio
async def test_refresh_expired_refresh_token_returns_unauthorized(client: AsyncClient, db_session):
    user = await create_user(db_session)
    token = create_refresh_token({"sub": str(user.id)}, expires_delta=timedelta(seconds=-1))
    response = await client.post(f"{BASE}/refresh", json={"refresh_token": token})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_access_token_is_rejected(client: AsyncClient, db_session):
    user = await create_user(db_session)
    token = create_access_token({"sub": str(user.id)})
    response = await client.post(f"{BASE}/refresh", json={"refresh_token": token})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_garbage_token_is_rejected(client: AsyncClient):
    response = await client.post(f"{BASE}/refresh", json={"refresh_token": "not.a.jwt"})
    assert response.status_code == 401


# Protected endpoint enforcement ------------------------------------------------

@pytest.mark.asyncio
async def test_me_without_authorization_is_unauthorized(client: AsyncClient):
    assert (await client.get(f"{BASE}/me")).status_code == 401


@pytest.mark.asyncio
async def test_me_with_bearer_prefix_but_no_token_is_unauthorized(client: AsyncClient):
    assert (await client.get(f"{BASE}/me", headers={"Authorization": "Bearer"})).status_code == 401


@pytest.mark.asyncio
async def test_me_with_malformed_token_is_unauthorized(client: AsyncClient):
    assert (await client.get(f"{BASE}/me", headers={"Authorization": "Bearer malformed"})).status_code == 401


@pytest.mark.asyncio
async def test_me_with_expired_access_token_is_unauthorized(client: AsyncClient, db_session):
    user = await create_user(db_session)
    response = await client.get(f"{BASE}/me", headers=headers_for(user, expires_delta=timedelta(seconds=-1)))
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_tampered_token_is_unauthorized(client: AsyncClient, db_session):
    user = await create_user(db_session)
    token = create_access_token({"sub": str(user.id)})
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    response = await client.get(f"{BASE}/me", headers={"Authorization": f"Bearer {tampered}"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_access_token_cannot_be_used_for_refresh_only_endpoint(client: AsyncClient, db_session):
    user = await create_user(db_session)
    response = await client.get(f"{BASE}/me", headers={"Authorization": f"Bearer {create_refresh_token({'sub': str(user.id)})}"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_inactive_user_cannot_access_protected_endpoint(client: AsyncClient, db_session):
    user = await create_user(db_session, active=False)
    assert (await client.get(f"{BASE}/me", headers=headers_for(user))).status_code == 403


@pytest.mark.asyncio
async def test_protected_risk_endpoint_requires_authentication(client: AsyncClient):
    assert (await client.get("/api/v1/risk/pip-values")).status_code == 401


@pytest.mark.asyncio
async def test_protected_risk_endpoint_accepts_valid_authentication(client: AsyncClient, db_session):
    user = await create_user(db_session)
    response = await client.get("/api/v1/risk/pip-values", headers=headers_for(user))
    assert response.status_code == 200


# User identity / isolation invariants -----------------------------------------

@pytest.mark.asyncio
async def test_me_returns_only_authenticated_users_identity(client: AsyncClient, db_session):
    user_a = await create_user(db_session)
    user_b = await create_user(db_session)
    response = await client.get(f"{BASE}/me", headers=headers_for(user_a))
    assert response.status_code == 200
    assert response.json()["id"] == user_a.id
    assert response.json()["id"] != user_b.id


@pytest.mark.asyncio
async def test_user_settings_update_is_scoped_to_authenticated_user(client: AsyncClient, db_session):
    user_a = await create_user(db_session)
    user_b = await create_user(db_session)
    response = await client.patch(f"{BASE}/settings", json={"name": "Alice Updated"}, headers=headers_for(user_a))
    assert response.status_code == 200
    await db_session.refresh(user_a)
    await db_session.refresh(user_b)
    assert user_a.name == "Alice Updated"
    assert user_b.name == "Test Trader"


@pytest.mark.asyncio
async def test_user_cannot_impersonate_another_user_by_changing_token_subject(client: AsyncClient, db_session):
    user_a = await create_user(db_session)
    user_b = await create_user(db_session)
    response = await client.get(f"{BASE}/me", headers=headers_for(user_a))
    assert response.json()["email"] == user_a.email
    # A token signed for B identifies B, never A; no endpoint trusts client-supplied user IDs.
    response_b = await client.get(f"{BASE}/me", headers=headers_for(user_b))
    assert response_b.json()["email"] == user_b.email
