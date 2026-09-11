"""Token authentication (mock for demo).

The customer App calls the backend with an existing token
(`Authorization: Bearer <token>`). The backend validates the token and resolves
it to a business AccountId.

This module ships a MOCK verifier with a small in-memory token->account map so
the full binding flow is testable end-to-end without an external IdP. Swap
`verify_token` for real JWT/OIDC validation in production (see notes below).
"""
import os
from typing import Optional

from fastapi import Header, HTTPException, status


# Demo token registry: token -> AccountId.
# In production, replace with JWT signature + claims validation against your IdP
# (e.g., verify RS256 signature via JWKS, read `sub`/custom claim as AccountId).
_MOCK_TOKENS = {
    "demo-token-alice": "acct-alice-001",
    "demo-token-bob": "acct-bob-002",
    "demo-token-carol": "acct-carol-003",
}

# Allow adding extra tokens via env (comma-separated `token:account`), handy for CI.
for pair in os.getenv("MOCK_TOKENS", "").split(","):
    pair = pair.strip()
    if ":" in pair:
        tok, acct = pair.split(":", 1)
        _MOCK_TOKENS[tok.strip()] = acct.strip()


def verify_token(token: str) -> Optional[str]:
    """Return AccountId for a valid token, or None if invalid."""
    return _MOCK_TOKENS.get(token)


def require_account(authorization: str = Header(default="")) -> str:
    """FastAPI dependency: extract Bearer token, validate, return AccountId.

    Raises 401 on missing/invalid token."""
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header (expected 'Bearer <token>').",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization[7:].strip()
    account_id = verify_token(token)
    if not account_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return account_id
