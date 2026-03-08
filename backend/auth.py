# backend/auth.py
import json
import os
from pathlib import Path

import firebase_admin
from fastapi import HTTPException
from firebase_admin import auth, credentials

_HERE = Path(__file__).resolve().parent
_LOCAL_KEY = _HERE / "serviceAccountKey.json"
_ROOT_KEY = _HERE.parent / "serviceAccountKey.json"

_json_env = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

if _json_env:
    try:
        _creds_info = json.loads(_json_env)
        cred = credentials.Certificate(_creds_info)
    except Exception as exc:
        raise RuntimeError("Invalid FIREBASE_SERVICE_ACCOUNT_JSON") from exc
elif _LOCAL_KEY.exists():
    cred = credentials.Certificate(str(_LOCAL_KEY))
elif _ROOT_KEY.exists():
    cred = credentials.Certificate(str(_ROOT_KEY))
else:
    raise RuntimeError(
        f"Firebase service account key not found. "
        f"Checked '{_LOCAL_KEY}' and '{_ROOT_KEY}', "
        f"and FIREBASE_SERVICE_ACCOUNT_JSON env."
    )

firebase_admin.initialize_app(cred)

def verify_token(token: str) -> dict:
    try:
        decoded = auth.verify_id_token(token)
        return decoded          # มี uid, email ของ user
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")