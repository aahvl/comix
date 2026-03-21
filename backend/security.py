import os
import bcrypt
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

_FERNET_KEY = os.getenv("FERNET_KEY")

if not _FERNET_KEY:
    raise EnvironmentError("FERNET_KEY not found in env")

_fernet = Fernet(_FERNET_KEY.encode())

def encrypt(plain_text: str) -> str:
    return _fernet.encrypt(plain_text.encode()).decode()

def decrypt(cipher_text: str) -> str:
    return _fernet.decrypt(cipher_text.encode()).decode()

def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()

def verify_pin(pin: str, pin_hash: str) -> bool:
    return bcrypt.checkpw(pin.encode(), pin_hash.encode())