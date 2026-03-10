# backend/main.py

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import filetype
import io
import base64
from pathlib import Path

from PIL import Image
from ultralytics import YOLO

limiter = Limiter(key_func=get_remote_address)

class ScanResult(BaseModel):
    total: float
    coins: dict[str, int]
    thumb: str | None = None


class DeleteHistoryRequest(BaseModel):
    ids: list[str]

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    lambda req, exc: __import__("fastapi").responses.JSONResponse(
        {"error": "Too many requests"}, 429
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://coinlens-gules.vercel.app",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "localhost",
        "127.0.0.1",
        "*.railway.app",
        "*.up.railway.app",
        "coinlens-production.up.railway.app",
    ],
)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_SIZE = 10 * 1024 * 1024

COIN_VALUES = {
    "025": 0.25,
    "050": 0.50,
    "1": 1.0,
    "2": 2.0,
    "5": 5.0,
    "10": 10.0,
}

_HERE = Path(__file__).resolve().parent
_MODEL_PATH = _HERE / "best.pt"
if not _MODEL_PATH.exists():
    _MODEL_PATH = _HERE.parent / "best.pt"

# ── Lazy model loading ──────────────────────────────────────────────────────
# ไม่โหลดตอน startup — โหลดครั้งแรกที่มีคนเรียก /predict เท่านั้น
# ทำให้ server ใช้ RAM น้อยตอน idle และไม่ถูก Railway kill
_model = None

def get_model() -> YOLO:
    global _model
    if _model is None:
        _model = YOLO(str(_MODEL_PATH))
    return _model
# ───────────────────────────────────────────────────────────────────────────

async def validate_image(file: UploadFile) -> bytes:
    contents = await file.read()
    if len(contents) > MAX_SIZE:
        raise HTTPException(400, "File too large")
    kind = filetype.guess(contents)
    if kind is None or kind.mime not in ALLOWED_TYPES:
        raise HTTPException(400, "Invalid file type")
    return contents


def run_yolo(image_bytes: bytes) -> dict:
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        results = get_model()(image, conf=0.5,iou=0.9)[0]   # ← โหลด model เฉพาะตอนนี้
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Failed to process image")

    counts = {k: 0 for k in COIN_VALUES.keys()}
    total_value = 0.0
    boxes = []

    names = results.names or {}
    xywh = results.boxes.xywh.cpu().tolist() if results.boxes.xywh is not None else []
    classes = results.boxes.cls.cpu().tolist() if results.boxes.cls is not None else []

    for (x_c, y_c, w, h), cls_idx in zip(xywh, classes):
        class_name = names.get(int(cls_idx))
        if not class_name:
            continue
        if class_name not in COIN_VALUES:
            continue

        counts[class_name] += 1
        total_value += float(COIN_VALUES[class_name])

        boxes.append({"x": x_c, "y": y_c, "w": w, "h": h, "class": class_name})

    plotted = results.plot(labels=True, conf=False)
    annotated_rgb = Image.fromarray(plotted[:, :, ::-1])
    buf = io.BytesIO()
    annotated_rgb.save(buf, format="PNG")
    annotated_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    return {
        "total": round(float(total_value), 2),
        "coins": counts,
        "boxes": boxes,
        "annotated_image_base64": annotated_b64,
        "annotated_image_mime": "image/png",
    }

@app.post("/predict")
@limiter.limit("10/minute")
async def predict(request: Request, image: UploadFile = File(...)):
    contents = await validate_image(image)
    result = run_yolo(contents)
    return result


security = HTTPBearer()

@app.post("/history")
async def save_history_endpoint(
    result: ScanResult,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    from auth import verify_token
    from database import save_scan

    payload = verify_token(credentials.credentials)
    clean_coins: dict[str, int] = {k: 0 for k in COIN_VALUES.keys()}
    for k, v in (result.coins or {}).items():
        if k in clean_coins:
            try:
                iv = int(v)
            except (TypeError, ValueError):
                iv = 0
            if iv < 0:
                iv = 0
            clean_coins[k] = iv

    recomputed_total = 0.0
    for coin, count in clean_coins.items():
        recomputed_total += COIN_VALUES[coin] * float(count)

    safe_result = {
        "total": round(float(recomputed_total), 2),
        "coins": clean_coins,
        "thumb": result.thumb,
    }
    created = save_scan(payload["uid"], safe_result)
    return created


@app.get("/history")
async def get_history_endpoint(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    from auth import verify_token
    from database import get_history

    payload = verify_token(credentials.credentials)
    records = get_history(payload["uid"])
    return records


@app.delete("/history")
async def delete_history_endpoint(
    body: DeleteHistoryRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    from auth import verify_token
    from database import delete_scans

    payload = verify_token(credentials.credentials)
    delete_scans(payload["uid"], body.ids or [])
    return {"deleted_ids": body.ids}