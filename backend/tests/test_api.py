import sys
import types

import pytest
from fastapi.testclient import TestClient


# Stub auth and database before importing the app module
fake_auth = types.ModuleType("auth")


def _fake_verify_token(token: str) -> dict:
    return {"uid": "test-user"}


fake_auth.verify_token = _fake_verify_token
sys.modules["auth"] = fake_auth


fake_db = types.ModuleType("database")
fake_db.saved_records: list[dict] = []
fake_db.deleted_calls: list[tuple[str, list[str]]] = []


def _fake_save_scan(user_id: str, result: dict) -> dict:
    record = {
        "firebase_uid": user_id,
        "total_value": result["total"],
        "coin_025": result["coins"].get("025", 0),
        "coin_050": result["coins"].get("050", 0),
        "coin_1": result["coins"].get("1", 0),
        "coin_2": result["coins"].get("2", 0),
        "coin_5": result["coins"].get("5", 0),
        "coin_10": result["coins"].get("10", 0),
        "thumb": result.get("thumb"),
    }
    fake_db.saved_records.append(record)
    return record


def _fake_get_history(user_id: str) -> list[dict]:
    # simple in-memory sample history
    return [
        {
            "id": "1",
            "firebase_uid": user_id,
            "total_value": 10.0,
        }
    ]


def _fake_delete_scans(user_id: str, ids: list[str]) -> None:
    fake_db.deleted_calls.append((user_id, ids))


fake_db.save_scan = _fake_save_scan
fake_db.get_history = _fake_get_history
fake_db.delete_scans = _fake_delete_scans
sys.modules["database"] = fake_db


from main import (  # noqa: E402
    ALLOWED_TYPES,
    COIN_VALUES,
    MAX_SIZE,
    app,
)


client = TestClient(app)


def test_predict_rejects_invalid_file_type() -> None:
    resp = client.post(
        "/predict",
        files={
            "image": ("test.txt", b"not-an-image", "text/plain"),
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid file type"


def test_predict_accepts_valid_image_with_stubbed_model(monkeypatch) -> None:
    import main as main_module

    def _fake_run_yolo(image_bytes: bytes) -> dict:
        return {
            "total": 1.0,
            "coins": {k: 0 for k in COIN_VALUES.keys()},
            "boxes": [],
            "annotated_image_base64": "",
            "annotated_image_mime": "image/png",
        }

    monkeypatch.setattr(main_module, "run_yolo", _fake_run_yolo)

    # minimal JPEG-like bytes so filetype detects image/jpeg
    img_bytes = b"\xff\xd8\xff" + b"\x00" * 1024

    resp = client.post(
        "/predict",
        files={
            "image": ("test.jpg", img_bytes, "image/jpeg"),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1.0
    assert body["coins"] == {k: 0 for k in COIN_VALUES.keys()}


def test_predict_rejects_too_large_image() -> None:
    img_bytes = b"\xff\xd8\xff" + b"\x00" * (MAX_SIZE + 1)

    resp = client.post(
        "/predict",
        files={
            "image": ("big.jpg", img_bytes, "image/jpeg"),
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "File too large"


def test_history_requires_auth_header() -> None:
    resp = client.get("/history")
    assert resp.status_code in (401, 403)


def test_save_history_recomputes_total_and_scopes_by_uid() -> None:
    fake_db.saved_records.clear()

    body = {
        "total": 9999.0,
        "coins": {
            "1": 2,
            "2": 1,
            "5": -3,  # should be clamped to 0
            "999": 10,  # unknown key should be ignored
        },
        "thumb": "data:image/png;base64,xxx",
    }

    resp = client.post(
        "/history",
        json=body,
        headers={"Authorization": "Bearer dummy"},
    )
    assert resp.status_code == 200
    assert fake_db.saved_records, "record should be saved"

    record = fake_db.saved_records[-1]
    assert record["firebase_uid"] == "test-user"
    # sanitize coins: unknown keys dropped, negatives clamped to 0
    assert record["coin_1"] == 2
    assert record["coin_2"] == 1
    assert record["coin_5"] == 0

    expected_total = 2 * COIN_VALUES["1"] + 1 * COIN_VALUES["2"]
    assert pytest.approx(record["total_value"], rel=1e-6) == expected_total


def test_get_history_uses_token_uid() -> None:
    resp = client.get(
        "/history",
        headers={"Authorization": "Bearer dummy"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    if body:
        assert body[0]["firebase_uid"] == "test-user"


def test_delete_history_scoped_and_passes_ids() -> None:
    fake_db.deleted_calls.clear()

    resp = client.request(
        "DELETE",
        "/history",
        json={"ids": ["a", "b"]},
        headers={"Authorization": "Bearer dummy"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"deleted_ids": ["a", "b"]}
    assert fake_db.deleted_calls == [("test-user", ["a", "b"])]

