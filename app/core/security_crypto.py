import base64
import hashlib
from cryptography.fernet import Fernet

# 真实生产环境这个 SECRET_KEY 应该存在环境变量里，绝对不能写在代码里
_ENCRYPTION_KEY = base64.urlsafe_b64encode(hashlib.sha256(b"your-super-secret-key").digest())
cipher_suite = Fernet(_ENCRYPTION_KEY)

def encrypt_api_key(raw_key: str) -> str:
    """加密 API Key"""
    if not raw_key: return ""
    return cipher_suite.encrypt(raw_key.encode()).decode()

def decrypt_api_key(encrypted_key: str) -> str:
    """解密 API Key"""
    if not encrypted_key: return ""
    try:
        return cipher_suite.decrypt(encrypted_key.encode()).decode()
    except Exception:
        return ""