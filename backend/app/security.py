from hashlib import sha256
from secrets import token_urlsafe

from pwdlib import PasswordHash


password_hash = PasswordHash.recommended()
_dummy_password_hash = password_hash.hash("invalid-user-password-check")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, stored_hash: str | None) -> bool:
    hash_to_check = stored_hash if stored_hash is not None else _dummy_password_hash
    try:
        valid = password_hash.verify(password, hash_to_check)
    except Exception:
        # A malformed stored hash should fail authentication instead of surfacing a server error.
        return False
    return valid and stored_hash is not None


def create_session_token() -> str:
    return token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()
