import os, sqlite3, secrets, time
from pathlib import Path
from flask import Flask, render_template, request, jsonify, abort

BASE = Path(__file__).resolve().parent
SHOP_DB = BASE / "shop.db"
APP = Flask(__name__)
APP.secret_key = os.environ.get("FLASK_SECRET", secrets.token_hex(32))

# Prototype only. Keep development mode OFF on a public server.
SHOP_ENV = os.environ.get("SHOP_ENV", "development")
SHOP_API_KEY = os.environ.get("SHOP_API_KEY", "CHANGE_THIS_LONG_RANDOM_SECRET")
ADMIN_KEY = os.environ.get("SHOP_ADMIN_KEY", "CHANGE_THIS_ADMIN_SECRET")

PACKAGES = {
    "100":  {"diamonds": 100,  "price": 10_000},
    "550":  {"diamonds": 550,  "price": 50_000},
    "1200": {"diamonds": 1200, "price": 100_000},
    "2500": {"diamonds": 2500, "price": 200_000},
}

def connect():
    con = sqlite3.connect(SHOP_DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with connect() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            game_id INTEGER NOT NULL,
            diamonds INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            payment_method TEXT NOT NULL DEFAULT 'test',
            payment_ref TEXT UNIQUE,
            created_at INTEGER NOT NULL,
            paid_at INTEGER,
            delivered_at INTEGER
        )
        """)

init_db()

@APP.get("/")
def home():
    return render_template("index.html", packages=PACKAGES)

@APP.post("/api/orders")
def create_order():
    data = request.get_json(silent=True) or {}
    try:
        game_id = int(data.get("game_id", 0))
        package = PACKAGES[str(data.get("package", ""))]
    except (ValueError, KeyError, TypeError):
        return jsonify(error="شناسه بازی یا بسته نامعتبر است."), 400
    if game_id <= 0:
        return jsonify(error="شناسه بازی معتبر نیست."), 400

    order_id = secrets.token_hex(8).upper()
    with connect() as con:
        con.execute(
            "INSERT INTO orders(id,game_id,diamonds,amount,created_at) VALUES(?,?,?,?,?)",
            (order_id, game_id, package["diamonds"], package["price"], int(time.time()))
        )
    return jsonify(order_id=order_id, game_id=game_id,
                   diamonds=package["diamonds"], amount=package["price"],
                   status="pending")

@APP.post("/api/dev/pay/<order_id>")
def dev_pay(order_id):
    if SHOP_ENV != "development":
        abort(404)
    data = request.get_json(silent=True) or {}
    if data.get("admin_key") != ADMIN_KEY:
        abort(403)
    ref = "TEST-" + secrets.token_hex(8)
    with connect() as con:
        cur = con.execute(
            """UPDATE orders SET status='paid', payment_method='test',
               payment_ref=?, paid_at=? WHERE id=? AND status='pending'""",
            (ref, int(time.time()), order_id)
        )
        if cur.rowcount != 1:
            return jsonify(error="سفارش پیدا نشد یا قبلاً پرداخت شده."), 409
    return jsonify(ok=True, message="پرداخت آزمایشی ثبت شد؛ ربات می‌تواند سفارش را دریافت کند.")

@APP.get("/api/orders/<order_id>")
def order_status(order_id):
    with connect() as con:
        row = con.execute(
            "SELECT id,game_id,diamonds,amount,status,created_at,delivered_at FROM orders WHERE id=?",
            (order_id,)
        ).fetchone()
    if not row:
        abort(404)
    return jsonify(dict(row))

@APP.get("/api/bot/paid-orders")
def bot_paid_orders():
    if request.headers.get("X-Shop-Key") != SHOP_API_KEY:
        abort(403)
    with connect() as con:
        rows = con.execute(
            """SELECT id,game_id,diamonds FROM orders
               WHERE status='paid' ORDER BY paid_at LIMIT 50"""
        ).fetchall()
    return jsonify(orders=[dict(r) for r in rows])

@APP.post("/api/bot/ack")
def bot_ack():
    if request.headers.get("X-Shop-Key") != SHOP_API_KEY:
        abort(403)
    data = request.get_json(silent=True) or {}
    order_id = str(data.get("order_id", ""))
    with connect() as con:
        cur = con.execute(
            """UPDATE orders SET status='delivered', delivered_at=?
               WHERE id=? AND status='paid'""",
            (int(time.time()), order_id)
        )
        if cur.rowcount != 1:
            return jsonify(error="سفارش معتبرِ پرداخت‌شده‌ای برای تحویل پیدا نشد."), 409
    return jsonify(ok=True)

if __name__ == "__main__":
    APP.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
