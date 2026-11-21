"""Risk: quiet renewal within 7 days +40, duplicate category +30, <=1 use/month +30."""
from collections import Counter
from datetime import date


def audit_subscriptions(items, today=None):
    today = today or date.today()
    counts = Counter(i["category"] for i in items)
    results = []
    for item in items:
        divisor = {"monthly": 1, "quarterly": 3, "yearly": 12}[item["period"]]
        monthly = item["cost"] / divisor
        days = (date.fromisoformat(item["renewal_date"]) - today).days
        flags = []
        if item["auto_renew"] and not item["notify"] and 0 <= days <= 7:
            flags.append("静默续费临近")
        if counts[item["category"]] > 1:
            flags.append("同类重复")
        if item["uses_per_month"] <= 1:
            flags.append("很少使用")
        score = sum({"静默续费临近": 40, "同类重复": 30, "很少使用": 30}[f] for f in flags)
        results.append({**item, "monthly_cost": round(monthly, 2), "renewal_in_days": days, "flags": flags, "risk_score": score})
    return {"monthly_total": round(sum(i["cost"] / {"monthly": 1, "quarterly": 3, "yearly": 12}[i["period"]] for i in items), 2), "subscriptions": sorted(results, key=lambda i: -i["risk_score"])}
