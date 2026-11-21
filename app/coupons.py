"""Thresholds use original amount; percentage coupons apply before fixed reductions."""
from datetime import date
from itertools import combinations
from .prices import cents


def best_coupon(amount, coupons, platform=None, category=None, today=None, warning_days=7):
    today = today or date.today()
    if amount < 0 or warning_days < 0:
        raise ValueError("金额和预警天数不能为负")
    original = cents(amount)
    eligible, warnings, skipped = [], [], []
    for c in coupons:
        days = (date.fromisoformat(c["expires"]) - today).days
        matches = (not c.get("platform") or c["platform"] == platform) and (not c.get("category") or c["category"] == category)
        if 0 <= days <= warning_days:
            warnings.append({**c, "days_left": days})
        if days < 0 or not matches or original < cents(c["threshold"]):
            skipped.append(c["id"])
        else:
            eligible.append(c)
    def evaluate(group):
        payable = original
        for c in sorted(group, key=lambda c: (c["kind"] != "rate", c["id"])):
            if c["kind"] == "rate":
                payable = round(payable * c["value"])
            else:
                payable -= cents(c["value"])
        payable = max(0, payable)
        return {"coupons": [c["id"] for c in group], "payable": payable / 100, "savings": (original - payable) / 100}
    def key(group):
        result = evaluate(group)
        return (result["payable"], tuple(sorted(c["expires"] for c in group)), len(group), tuple(c["id"] for c in group))
    singles = [(c,) for c in eligible]
    groups = [()]
    for size in range(1, len(eligible) + 1):
        groups.extend(g for g in combinations(eligible, size)
                      if (size == 1 or all(c["stackable"] for c in g))
                      and len({c["source"] for c in g}) == size)
    return {"best_single": evaluate(min(singles, key=key)) if singles else None, "best_stack": evaluate(min(groups, key=key)), "expiry_warnings": sorted(warnings, key=lambda c: (c["days_left"], c["id"])), "skipped": skipped}
