from database import save_scan, get_history

# ทดสอบ save
print("=== ทดสอบ save ===")
save_scan(
    user_id="550e8400-e29b-41d4-a716-446655440000" ,
    result={
        "total": 47,
        "coins": {"1": 3, "2": 2, "5": 4, "10": 2}
    }
)
print("save สำเร็จ!")

# ทดสอบ get
print("\n=== ทดสอบ get ===")
history = get_history("550e8400-e29b-41d4-a716-446655440000")
print(f"พบข้อมูล {len(history)} รายการ")
print(history)