# backend/auth.py
import firebase_admin
from fastapi import HTTPException
from firebase_admin import credentials, auth
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_LOCAL_KEY = _HERE / "serviceAccountKey.json"
_ROOT_KEY = _HERE.parent / "serviceAccountKey.json"
if _LOCAL_KEY.exists():
    _KEY_PATH = _LOCAL_KEY
elif _ROOT_KEY.exists():
    _KEY_PATH = _ROOT_KEY
else:
    raise RuntimeError(
        f"Firebase service account key not found. "
        f"Checked '{_LOCAL_KEY}' and '{_ROOT_KEY}'."
    )

cred = credentials.Certificate(str(_KEY_PATH))
firebase_admin.initialize_app(cred)

def verify_token(token: str) -> dict:
    try:
        decoded = auth.verify_id_token(token)
        return decoded          # มี uid, email ของ user
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")