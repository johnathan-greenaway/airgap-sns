from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
import os, base64, secrets

# Key derivation with proper scrypt parameters
def derive_key(password: bytes, salt: bytes = None) -> tuple[bytes, bytes]:
    salt = salt or secrets.token_bytes(16)
    kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
    key = kdf.derive(password)
    return (key, salt)

# AES-256-GCM encryption/decryption
def encrypt(msg: str, password: str) -> str:
    msg_bytes = msg.encode('utf-8')
    key, salt = derive_key(password.encode())
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ct = aesgcm.encrypt(nonce, msg_bytes, None)
    return base64.urlsafe_b64encode(salt + nonce + ct).decode()

def decrypt(token: str, password: str) -> str:
    data = base64.urlsafe_b64decode(token)
    salt = data[:16]
    nonce = data[16:28]
    ct = data[28:]
    key, _ = derive_key(password.encode(), salt)
    aesgcm = AESGCM(key)
    pt = aesgcm.decrypt(nonce, ct, None)
    return pt.decode('utf-8')