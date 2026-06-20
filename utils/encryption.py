"""
Token encryption module.

This module provides the TokenEncryptor class to secure sensitive data
(such as OAuth tokens) before storing them in the database using symmetric encryption.
"""
import logging
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

class TokenEncryptor:
    """Utility class to encrypt and decrypt sensitive tokens using Fernet symmetric encryption."""
    
    def __init__(self, key: str | None):
        """Initializes the TokenEncryptor.
        
        Args:
            key (str | None): A base64-encoded 32-byte key for Fernet encryption.
                If None or invalid, encryption will be disabled.
        """
        self.active = False
        if key:
            try:
                self.fernet = Fernet(key.encode("utf-8"))
                self.active = True
            except Exception as e:
                logger.error(f"Invalid TOKEN_ENCRYPTION_KEY provided: {e}")
                self.fernet = None
        else:
            logger.warning("No TOKEN_ENCRYPTION_KEY provided. Tokens will be stored in plain text.")

    def encrypt(self, plain_text: str | None) -> str | None:
        """Encrypts a plaintext string. Returns plaintext if encryption is inactive."""
        if not plain_text:
            return plain_text
        if not self.active:
            return plain_text
        return self.fernet.encrypt(plain_text.encode("utf-8")).decode("utf-8")

    def decrypt(self, encrypted_text: str | None) -> str | None:
        """Decrypts a cipher string. Falls back to returning the string as-is if decryption fails."""
        if not encrypted_text:
            return encrypted_text
        if not self.active:
            return encrypted_text
        
        # If it doesn't look like a Fernet token (which typically starts with gAAAAA...), 
        # try to decrypt it anyway, but it will likely fail and fallback
        try:
            return self.fernet.decrypt(encrypted_text.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            # Token was likely stored in plaintext before encryption was enabled,
            # or the key has changed. Return as-is so legacy plaintext tokens still work.
            return encrypted_text
        except Exception as e:
            logger.error(f"Error decrypting token: {e}")
            return encrypted_text
