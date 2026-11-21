import json
from datetime import date
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .prices import compare_grocery_prices
from .coupons import best_coupon
from .inventory import track_inventory
from .subscriptions import audit_subscriptions

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "data/demo.json").read_text())
TODAY = date(2026, 11, 22)
app = FastAPI(title="省钱精算管家 · 示例数据")


class ShoppingLine(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    quantity: int = Field(default=1, ge=1, le=100, strict=True)


class Basket(BaseModel):
    items: list[ShoppingLine] = Field(max_length=10)


class Order(BaseModel):
    amount: float = Field(ge=0, le=1000000, allow_inf_nan=False)
    platform: str | None = None
    category: str | None = None
    warning_days: int = Field(default=7, ge=0, le=365)


@app.get("/api/health")
def health():
    return {"status": "ok", "_note": "示例数据", "demo_date": TODAY.isoformat()}


@app.get("/api/data")
def mock_data():
    return DATA


@app.get("/api/data/{section}")
def section_data(section: str):
    if section not in ("platforms", "groceries", "coupons", "inventory", "subscriptions"):
        raise HTTPException(404, "没有这类示例数据")
    return {"_note": DATA["_note"], "items": DATA[section]}


@app.post("/api/compare_grocery_prices")
def compare(body: Basket):
    return compare_grocery_prices([i.model_dump() for i in body.items], DATA, today=TODAY)


@app.post("/api/best_coupon")
def coupons(body: Order):
    return best_coupon(body.amount, DATA["coupons"], body.platform, body.category, TODAY, body.warning_days)


@app.get("/api/track_inventory")
def inventory():
    return track_inventory(DATA["inventory"], TODAY)


@app.get("/api/audit_subscriptions")
def subscriptions():
    return audit_subscriptions(DATA["subscriptions"], TODAY)


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
