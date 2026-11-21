from datetime import date, timedelta
from math import ceil


def track_inventory(items, today=None):
    today = today or date.today()
    results, reorder = [], []
    for item in items:
        if item["stock"] < 0 or item["daily_usage"] < 0:
            raise ValueError("库存和日用量不能为负")
        days = item["stock"] / item["daily_usage"] if item["daily_usage"] else None
        expiry = (date.fromisoformat(item["expires"]) - today).days if item.get("expires") else None
        critical = item["stock"] == 0 or (expiry is not None and expiry <= 0) or (days is not None and days <= 3)
        soon = (days is not None and days <= 7) or (expiry is not None and expiry <= 7)
        level = "紧急" if critical else "关注" if soon else "充足"
        result = {**item, "days_to_empty": round(days, 2) if days is not None else None, "run_out_date": (today + timedelta(days=ceil(days))).isoformat() if days is not None else None, "expiry_days": expiry, "reminder_level": level}
        results.append(result)
        if level != "充足":
            reorder.append({"name": item["name"], "reason": level, "action": "仅列清单，请确认后自行购买"})
    return {"items": results, "reorder_list": reorder, "auto_order": False}
