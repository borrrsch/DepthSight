# tests/test_password_recovery.py

import pytest
from httpx import AsyncClient
from unittest.mock import patch
from api import models, security
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_forgot_password_flow(
    test_client: AsyncClient, db_session: AsyncSession, test_user: models.User
):
    """Tests password recovery request."""
    # Mock email sending in the correct module
    with patch("api.email_utils.send_email") as mock_send_email:
        mock_send_email.return_value = None

        # Request for an existing user
        response = await test_client.post(
            "/api/v1/auth/forgot-password", json={"email": test_user.email}
        )
        assert response.status_code == 200
        data = response.json()
        assert "password reset link has been sent" in data["data"]["message"]

        # Request for a non-existent user (should return the same text for security)
        response = await test_client.post(
            "/api/v1/auth/forgot-password", json={"email": "nonexistent@example.com"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "password reset link has been sent" in data["data"]["message"]


@pytest.mark.asyncio
async def test_reset_password_success(
    test_client: AsyncClient, db_session: AsyncSession, test_user: models.User
):
    """Tests successful password reset with a valid token."""
    # Generate a valid token
    token = security.password_reset_serializer.dumps(
        test_user.email, salt=security.PASSWORD_RESET_SALT
    )

    new_password = "new_secret_password_123"
    response = await test_client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": new_password},
    )

    assert response.status_code == 200
    data = response.json()
    assert "reset successfully" in data["data"]["message"]

    # Check that the password has actually been updated
    await db_session.refresh(test_user)
    assert security.verify_password(new_password, test_user.hashed_password)


@pytest.mark.asyncio
async def test_reset_password_invalid_token(test_client: AsyncClient):
    """Tests password reset with an invalid token."""
    response = await test_client.post(
        "/api/v1/auth/reset-password",
        json={"token": "invalid_token_here", "new_password": "some_password"},
    )
    assert response.status_code == 400
    # API returns error instead of detail
    response_data = response.json()
    assert response_data.get("error") is not None
    assert "invalid or has expired" in response_data["error"]


@pytest.mark.asyncio
async def test_reset_password_short_password(
    test_client: AsyncClient, test_user: models.User
):
    """Tests reset with a password that is too short (pydantic validation)."""
    token = security.password_reset_serializer.dumps(
        test_user.email, salt=security.PASSWORD_RESET_SALT
    )

    response = await test_client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": token,
            "new_password": "123",  # Too short
        },
    )
    # Should be a 422 validation error
    assert response.status_code == 422
