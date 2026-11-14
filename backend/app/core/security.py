"""Passphrase hashing, session tokens, account IDs and field encryption.

- Passphrases: Argon2id (memory-hard), never stored or logged as typed.
- Session tokens: 256-bit random; only their SHA-256 is stored, so a
  database leak does not hand out working sessions.
- Optional emails: encrypted with Fernet (AES-128-CBC + HMAC) using
  NIVRA_DATA_KEY; we never store them in plaintext.
"""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

_hasher = PasswordHasher()

# A real Argon2 hash used to spend the same time when an account doesn't
# exist, so response timing doesn't reveal which Nivra IDs are real.
_DUMMY_HASH = _hasher.hash("nivra-timing-equaliser")

# No 0/O or 1/I, so IDs are easy to read back and write down.
_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def hash_passphrase(passphrase: str) -> str:
    return _hasher.hash(passphrase)


def verify_passphrase(stored_hash: str | None, passphrase: str) -> bool:
    try:
        return _hasher.verify(stored_hash or _DUMMY_HASH, passphrase) and stored_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def new_account_code() -> str:
    """A human-friendly Nivra ID, e.g. NV-7K3Q-92XD (about 50 bits of randomness)."""
    pick = lambda n: "".join(secrets.choice(_ALPHABET) for _ in range(n))  # noqa: E731
    return f"NV-{pick(4)}-{pick(4)}"


def normalise_account_code(code: str) -> str:
    return code.strip().upper()


def new_id() -> str:
    return secrets.token_hex(12)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class EncryptionUnavailable(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = get_settings().data_key
    if not key:
        raise EncryptionUnavailable("NIVRA_DATA_KEY is not configured")
    return Fernet(key.encode())


def encrypt_field(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_field(value: str) -> str | None:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, EncryptionUnavailable):
        return None
