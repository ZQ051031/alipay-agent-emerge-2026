"""Exact partition DP: each shopping line goes to one platform; no filler purchases."""
from decimal import Decimal, ROUND_HALF_UP


def cents(value):
    return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def compare_grocery_prices(items, data, today=None):
    if len(items) > 10:
        raise ValueError("精确拆单最多支持10行商品，请分批比较")
    catalog = {x["name"]: x for x in data["groceries"]}
    merged = {}
    for line in items:
        name, qty = line["name"], line.get("quantity", 1)
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1 or qty > 100:
            raise ValueError("数量须为1至100的整数")
        merged[name] = merged.get(name, 0) + qty
    lines = list(merged.items())
    missing = [n for n, q in lines if n not in catalog or not any(v is not None for v in catalog[n]["prices"].values())]
    unavailable = {p["id"]: [n for n, q in lines if catalog.get(n, {}).get("prices", {}).get(p["id"]) is None] for p in data["platforms"]}
    if not lines or missing:
        return {"ranked_baskets": [], "best_split": None, "savings": None, "missing_items": missing, "unavailable": unavailable}
    n = len(lines)
    full = (1 << n) - 1
    costs = {}
    ranked = []
    for p in data["platforms"]:
        table = {0: (0, 0)}
        for mask in range(1, full + 1):
            selected = [(name, qty) for i, (name, qty) in enumerate(lines) if mask & (1 << i)]
            if any(catalog[name]["prices"].get(p["id"]) is None for name, qty in selected):
                continue
            subtotal = sum(cents(catalog[name]["prices"][p["id"]]) * qty for name, qty in selected)
            if subtotal < cents(p["minimum_order"]):
                continue
            fee = 0 if subtotal >= cents(p["free_delivery_at"]) else cents(p["delivery_fee"])
            table[mask] = (subtotal + fee, fee)
        costs[p["id"]] = table
        if full in table:
            total, fee = table[full]
            ranked.append({"platform": p["name"], "platform_id": p["id"], "total": total / 100, "delivery_fee": fee / 100})
    ranked.sort(key=lambda x: (x["total"], x["platform_id"]))
    dp = {0: (0, [])}
    for p in data["platforms"]:
        next_dp = dict(dp)
        for used, (cost, allocation) in dp.items():
            remaining = full ^ used
            sub = remaining
            while sub:
                if sub in costs[p["id"]]:
                    total, fee = costs[p["id"]][sub]
                    key = used | sub
                    if key not in next_dp or cost + total < next_dp[key][0]:
                        group = {"platform": p["name"], "items": [{"name": name, "quantity": qty} for i, (name, qty) in enumerate(lines) if sub & (1 << i)], "total": total / 100, "delivery_fee": fee / 100}
                        next_dp[key] = (cost + total, allocation + [group])
                sub = (sub - 1) & remaining
        dp = next_dp
    split = {"total": dp[full][0] / 100, "orders": dp[full][1]} if full in dp else None
    return {"ranked_baskets": ranked, "best_split": split, "savings": round(ranked[-1]["total"] - split["total"], 2) if ranked and split else None, "missing_items": missing, "unavailable": unavailable}
