# Token Encryption
# Secure storage for OAuth tokens using Fernet (AES-128-GCM)

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import os
import logging

logger = logging.getLogger(__name__)


class TokenEncryption:
    """Encrypt/decrypt OAuth tokens at rest using Fernet."""
    
    def __init__(self, master_key: bytes = None):
        if master_key:
            self.key = master_key
        else:
            # Derive from environment variable + salt
            password = os.environ.get("TOKEN_ENCRYPTION_PASSWORD", "").encode()
            if not password:
                raise ValueError("TOKEN_ENCRYPTION_PASSWORD environment variable required")
            
            salt = os.environ.get("TOKEN_ENCRYPTION_SALT", "static-salt-change-in-production").encode()
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            self.key = base64.urlsafe_b64encode(kdf.derive(password))
        
        self.cipher = Fernet(self.key)
    
    def encrypt(self, token: str) -> str:
        """Encrypt a token string."""
        if not token:
            return ""
        return self.cipher.encrypt(token.encode()).decode()
    
    def decrypt(self, encrypted: str) -> str:
        """Decrypt a token string."""
        if not encrypted:
            return ""
        try:
            return self.cipher.decrypt(encrypted.encode()).decode()
        except Exception as e:
            logger.error(f"Token decryption failed: {e}")
            raise ValueError("Invalid token or encryption key mismatch")
    
    @classmethod
    def generate_key(cls) -> str:
        """Generate a new Fernet key for initial setup."""
        return Fernet.generate_key().decode()


# Global instance (initialized on first use)
_token_encryption: TokenEncryption = None


def get_token_encryption() -> TokenEncryption:
    """Get or create the global token encryption instance."""
    global _token_encryption
    if _token_encryption is None:
        _token_encryption = TokenEncryption()
    return _token_encryption


def init_token_encryption(master_key: bytes = None) -> TokenEncryption:
    """Initialize the global token encryption with a specific key."""
    global _token_encryption
    _token_encryption = TokenEncryption(master_key)
    return _token_encryption