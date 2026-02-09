"""
Simple auth: login (admin/charles) and token validation.
"""
import secrets
from typing import Optional
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyQuery

# In-memory: valid tokens (token -> username)
_auth_tokens: dict[str, str] = {}

# Stored download path (persists for the process)
_download_path: Optional[str] = None

# Credentials (could move to env: ADMIN_USERNAME, ADMIN_PASSWORD)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "charles"

security_bearer = HTTPBearer(auto_error=False)
security_query = APIKeyQuery(name="token", auto_error=False)


def _create_token(username: str) -> str:
    t = secrets.token_urlsafe(32)
    _auth_tokens[t] = username
    return t


def _validate_token(token: str) -> Optional[str]:
    return _auth_tokens.get(token)


def _revoke_token(token: str) -> None:
    _auth_tokens.pop(token, None)


def login(username: str, password: str) -> Optional[str]:
    """If credentials match, return token; else None."""
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        return _create_token(username)
    return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    token_query: Optional[str] = Depends(security_query),
) -> str:
    """Dependency: require valid auth; return username or raise 401."""
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif token_query:
        token = token_query
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    username = _validate_token(token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return username


# Settings store (download path)
def get_download_path() -> Optional[str]:
    return _download_path


def set_download_path(path: Optional[str]) -> None:
    global _download_path
    _download_path = path
