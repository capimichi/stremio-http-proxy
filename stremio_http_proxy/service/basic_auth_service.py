import secrets

from fastapi import HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials


class BasicAuthService:
    def __init__(self, username: str | None = None, password: str | None = None):
        self.username = username or None
        self.password = password or None
        self.security = HTTPBasic(auto_error=False)

    def require_auth(self, credentials: HTTPBasicCredentials | None = None) -> None:
        if not self.is_enabled():
            return
        if credentials is None:
            self._raise_unauthorized()
        provided_username = credentials.username.encode("utf-8")
        provided_password = credentials.password.encode("utf-8")
        expected_username = self.username.encode("utf-8")
        expected_password = self.password.encode("utf-8")
        if not secrets.compare_digest(provided_username, expected_username) or not secrets.compare_digest(
            provided_password,
            expected_password,
        ):
            self._raise_unauthorized()

    def is_enabled(self) -> bool:
        return bool(self.username and self.password)

    def _raise_unauthorized(self) -> None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
