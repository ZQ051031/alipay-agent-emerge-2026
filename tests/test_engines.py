from datetime import date
from itertools import product
import pytest
from fastapi.testclient import TestClient
from app.main import app, DATA, TODAY
from app.prices import compare_grocery_prices
from app.coupons import best_coupon
from app.inventory import track_inventory
from app.subscriptions import audit_subscriptions


def market(minimum=0, fee=0, free=999):
    return {
        "platforms": [
            {"id": "a", "name": "甲", "minimum_order": minimum, "delivery_fee": fee, "free_delivery_at": free},
            {"id": "b", "name": "乙", "minimum_order": minimum, "delivery_fee": fee, "free_delivery_at": free},
        ],
        "groceries": [
            {"name": "米", "prices": {"a": 3, "b": 10}},
            {"name": "油", "prices": {"a": 10, "b": 4}},
        ],
    }


def basket():
    return [{"name": "米"}, {"name": "油"}]


def test_price_ranking_split_savings():
    result = compare_grocery_prices(basket(), market(), TODAY)
    assert [b["total"] for b in result["ranked_baskets"]] == [13, 14]
    assert result["best_split"]["total"] == 7
    assert result["savings"] == 7


def test_delivery_and_minimum_order_exact_partition():
    # Cheapest per-item assignment is invalid: true optimum buys both from A.
    result = compare_grocery_prices(basket(), market(minimum=8, fee=2), TODAY)
    assert result["best_split"]["total"] == 15
    assert len(result["best_split"]["orders"]) == 1
    assert compare_grocery_prices(basket(), market(fee=20), TODAY)["best_split"]["total"] == 33
    assert compare_grocery_prices(basket(), market(fee=20, free=13), TODAY)["best_split"]["total"] == 13
    assert compare_grocery_prices(basket(), market(minimum=20), TODAY)["best_split"] is None


def test_split_matches_exhaustive_assignments():
    data = market(minimum=4, fee=2, free=15)
    data["groceries"].append({"name": "菜", "prices": {"a": 7, "b": 2}})
    lines = basket() + [{"name": "菜"}]
    totals = []
    for assignment in product("ab", repeat=3):
        total = 0
        valid = True
        for p in data["platforms"]:
            subtotal = sum(data["groceries"][i]["prices"][pid] for i, pid in enumerate(assignment) if pid == p["id"])
            if not subtotal:
                continue
            if subtotal < p["minimum_order"]:
                valid = False
            total += subtotal + (0 if subtotal >= p["free_delivery_at"] else p["delivery_fee"])
        if valid:
            totals.append(total)
    assert compare_grocery_prices(lines, data, TODAY)["best_split"]["total"] == min(totals)


def test_missing_partial_empty_and_quantity():
    data = market()
    data["groceries"][0]["prices"]["b"] = None
    result = compare_grocery_prices(basket(), data, TODAY)
    assert result["unavailable"]["b"] == ["米"]
    assert len(result["ranked_baskets"]) == 1
    assert compare_grocery_prices([{"name": "未知"}], data, TODAY)["missing_items"] == ["未知"]
    data["groceries"][0]["prices"]["a"] = None
    assert compare_grocery_prices(basket(), data, TODAY)["missing_items"] == ["米"]
    assert compare_grocery_prices([], data, TODAY)["best_split"] is None
    assert compare_grocery_prices([{"name": "米", "quantity": 2}], market(), TODAY)["best_split"]["total"] == 6
    with pytest.raises(ValueError):
        compare_grocery_prices([{"name": "米", "quantity": -1}], data, TODAY)
    with pytest.raises(ValueError):
        compare_grocery_prices(basket() * 6, data, TODAY)


def coupon(id, value=10, **kwargs):
    return {"id": id, "name": id, "kind": "fixed", "value": value,
            "threshold": 0, "stackable": True, "source": "平台满减券", "expires": "2026-12-01", **kwargs}


def test_coupon_single_stack_expired_and_restrictions():
    coupons = [coupon("a"), coupon("b", 0.8, kind="rate", source="品类折扣券"), coupon("expired", 90, expires="2026-11-21"),
               coupon("exclusive", 25, stackable=False), coupon("restricted", 80, platform="p1", category="生鲜"),
               coupon("threshold", 100, threshold=101)]
    result = best_coupon(100, coupons, today=TODAY)
    assert result["best_single"]["coupons"] == ["exclusive"]
    assert result["best_stack"]["payable"] == 70
    assert result["best_stack"]["coupons"] == ["a", "b"]
    assert set(result["skipped"]) == {"expired", "restricted", "threshold"}
    assert best_coupon(100, coupons, "p1", "生鲜", TODAY)["best_stack"]["payable"] == 0


def test_coupon_one_per_source_and_demo_stack():
    coupons = [coupon("a", 12), coupon("b", 10),
               coupon("pay", 3, source="支付宝支付券")]
    result = best_coupon(80, coupons, today=TODAY)
    assert result["best_stack"]["coupons"] == ["a", "pay"]
    assert result["best_stack"]["payable"] == 65
    demo = best_coupon(80, DATA["coupons"], "p1", "生鲜", TODAY)
    assert demo["best_stack"]["coupons"] == ["c2", "c5", "c8"]
    assert demo["best_stack"]["payable"] == 61
    sources = {c["id"]: c["source"] for c in DATA["coupons"]}
    selected = demo["best_stack"]["coupons"]
    assert len({sources[c] for c in selected}) == len(selected)


def test_coupon_expiry_tie_warning_boundaries_empty_errors():
    coupons = [coupon("later"), coupon("soon", expires="2026-11-22", stackable=False),
               coupon("edge", 1, expires="2026-11-29"), coupon("old", expires="2026-11-21")]
    result = best_coupon(20, coupons, today=TODAY)
    assert result["best_single"]["coupons"] == ["soon"]
    assert [c["id"] for c in result["expiry_warnings"]] == ["soon", "edge"]
    assert best_coupon(0, [], today=TODAY)["best_stack"]["payable"] == 0
    assert best_coupon(10, [], today=TODAY)["best_single"] is None
    with pytest.raises(ValueError):
        best_coupon(-1, [], today=TODAY)


def test_inventory_math_dates_expiry_and_zero_usage():
    items = [{"name": "米", "stock": 5, "daily_usage": 2, "expires": "2027-01-01"},
             {"name": "药", "stock": 3, "daily_usage": 0, "expires": "2026-11-21"},
             {"name": "纸", "stock": 0, "daily_usage": 0}]
    result = track_inventory(items, TODAY)
    assert result["items"][0]["days_to_empty"] == 2.5
    assert result["items"][0]["run_out_date"] == "2026-11-25"
    assert result["items"][1]["run_out_date"] is None
    assert result["items"][1]["expiry_days"] == -1
    assert len(result["reorder_list"]) == 3
    assert result["auto_order"] is False
    assert track_inventory([], TODAY)["items"] == []
    with pytest.raises(ValueError):
        track_inventory([{"stock": -1, "daily_usage": 1}], TODAY)


def test_subscriptions_normalisation_and_flags():
    def sub(name, period, cost, **kwargs):
        return {"name": name, "period": period, "cost": cost, "category": "影音",
                "renewal_date": "2026-11-25", "auto_renew": True, "notify": False,
                "uses_per_month": 0, **kwargs}
    items = [sub("a", "monthly", 10), sub("b", "quarterly", 60), sub("c", "yearly", 120, notify=True)]
    result = audit_subscriptions(items, TODAY)
    assert result["monthly_total"] == 40
    assert result["subscriptions"][0]["risk_score"] == 100
    assert set(result["subscriptions"][0]["flags"]) == {"静默续费临近", "同类重复", "很少使用"}
    assert result["subscriptions"][2]["risk_score"] == 60
    clean = audit_subscriptions([sub("d", "monthly", 10, renewal_date="2026-11-21", uses_per_month=2)], TODAY)
    assert clean["subscriptions"][0]["flags"] == []
    assert audit_subscriptions([], TODAY)["monthly_total"] == 0


client = TestClient(app)


@pytest.mark.parametrize("path", ["/", "/style.css", "/app.js", "/api/health", "/api/data",
    "/api/data/platforms", "/api/data/groceries", "/api/data/coupons", "/api/data/inventory",
    "/api/data/subscriptions", "/api/track_inventory", "/api/audit_subscriptions"])
def test_get_api(path):
    assert client.get(path).status_code == 200


def test_api_posts_validation_and_sample_labels():
    assert client.get("/api/health").json()["demo_date"] == "2026-11-22"
    assert "示例数据" in client.get("/").text
    assert "示例数据" in client.get("/api/data").json()["_note"]
    result = client.post("/api/compare_grocery_prices", json={"items": [{"name": "大米"}]})
    assert result.status_code == 200 and result.json()["best_split"]
    assert client.post("/api/best_coupon", json={"amount": 80}).json()["best_stack"]["savings"] > 0
    assert client.post("/api/compare_grocery_prices", json={"items": []}).json()["best_split"] is None
    assert client.post("/api/compare_grocery_prices", json={"items": [{"name": "未知"}]}).json()["missing_items"] == ["未知"]
    assert client.post("/api/best_coupon", json={"amount": -1}).status_code == 422
    assert client.post("/api/compare_grocery_prices", json={"items": [{"name": "米", "quantity": 0}]}).status_code == 422
    assert client.post("/api/compare_grocery_prices", json={"items": [{"name": "米"}] * 11}).status_code == 422
    assert client.get("/api/data/unknown").status_code == 404
