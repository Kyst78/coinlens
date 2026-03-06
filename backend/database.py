import os

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")   # ใช้ service_role key ฝั่ง backend
)

def save_scan(user_id: str, result: dict) -> dict:
    data = {
        # firebase uid ของผู้ใช้ เก็บในคอลัมน์ text แยกจาก primary key
        "firebase_uid": user_id,
        "total_value": result["total"],
        "coin_025": result["coins"].get("025", 0),
        "coin_050": result["coins"].get("050", 0),
        "coin_1":  result["coins"].get("1", 0),
        "coin_2":  result["coins"].get("2", 0),
        "coin_5":  result["coins"].get("5", 0),
        "coin_10": result["coins"].get("10", 0),
        # เก็บ data URL ของรูป preview/annotated
        "thumb": result.get("thumb"),
    }
    res = supabase.table("scan_history").insert(data).execute()
    # ส่งแถวที่ถูกสร้างกลับไปให้ API ใช้ต่อ (optimistic update)
    if res and getattr(res, "data", None):
        return res.data[0]
    return data


def get_history(user_id: str) -> list:
    return (
        supabase.table("scan_history")
        .select("*")
        .eq("firebase_uid", user_id)
        .order("scanned_at", desc=True)
        .execute()
        .data
    )


def delete_scans(user_id: str, ids: list[str]) -> None:
    if not ids:
        return
    (
        supabase.table("scan_history")
        .delete()
        .eq("firebase_uid", user_id)
        .in_("id", ids)
        .execute()
    )