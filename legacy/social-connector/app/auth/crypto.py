# Social Connector - Authentication & Encryption

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import os
import hashlib
import secrets

from app.config import get_settings


# Global Fernet instance
_fernet = None


def get_fernet() -> Fernet:
    """Get or create Fernet instance for encryption."""
    global _fernet
    if _fernet is None:
        settings = get_settings()
        key = settings.encryption_key
        
        if not key:
            # Generate a key from the app secret
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'social-connector-salt',  # In production, use unique salt per deployment
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(settings.app_secret.encode()))
        elif isinstance(key, str):
            # Ensure key is 32 bytes
            if len(key) != 32:
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=b'social-connector-salt',
                    iterations=100000,
                )
                key = base64.urlsafe_b64encode(kdf.derive(key.encode()))
            else:
                key = base64.urlsafe_b64encode(key.encode()[:32].ljust(32, b'0'))
        
        _fernet = Fernet(key)
    
    return _fernet


def encrypt_token(token: str) -> str:
    """Encrypt a token for storage."""
    if not token:
        return ""
    fernet = get_fernet()
    return fernet.encrypt(token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a token from storage."""
    if not encrypted_token:
        return ""
    try:
        fernet = get_fernet()
        return fernet.decrypt(encrypted_token.encode()).decode()
    except Exception:
        return ""


def hash_api_key(api_key: str) -> str:
    """Hash an API key for storage."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def generate_state() -> str:
    """Generate a random state for OAuth."""
    return secrets.token_urlsafe(32)


def generate_code_verifier() -> str:
    """Generate PKCE code verifier."""
    return secrets.token_urlsafe(32)


def generate_code_challenge(code_verifier: str) -> str:
    """Generate PKCE code challenge from verifier."""
    digest = hashlib.sha256(code_verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return pwd_context.verify(plain_password, hashed_password)


def generate_api_key() -> str:
    """Generate a secure API key."""
    return f"sc_{secrets.token_urlsafe(32)}"


def create_jwt_token(data: dict, expires_delta: timedelta = None) -> str:
    """Create a JWT token."""
    from datetime import datetime, timedelta
    from jose import jwt
    
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=24))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.app_secret, algorithm="HS256")


def decode_jwt_token(token: str) -> dict:
    """Decode a JWT token."""
    from jose import jwt, JWTError
    
    settings = get_settings()
    try:
        return jwt.decode(token, settings.app_secret, algorithms=["HS256"])
    except JWTError:
        return {}


# Time utilities
from datetime import timedelta