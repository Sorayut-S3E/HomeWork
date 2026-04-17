import os
import json
import uuid
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, g
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


app = Flask(__name__)
app.config["SECRET_KEY"] = "student-demo-secret-key"
app.config["DATABASE"] = "store.db"
app.config["UPLOAD_FOLDER"] = os.path.join("static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB


# --------------------------
# Database helpers
# --------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(app.config["DATABASE"])
    db.execute("PRAGMA foreign_keys = ON")
    with open("schema.sql", "r", encoding="utf-8") as f:
        db.executescript(f.read())

    count = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if count == 0:
        sample_products = [
            (
                "NVIDIA RTX 4060", "NVIDIA", "การ์ดจอ", 12990, 10,
                "8GB", "RTX 4060", "-", "https://via.placeholder.com/500x300?text=RTX+4060",
                "การ์ดจอสำหรับเล่นเกมและงานกราฟิก", "VRAM 8GB, DLSS, Ray Tracing"
            ),
            (
                "AMD Ryzen 5 7600", "AMD", "CPU", 7990, 12,
                "-", "-", "Ryzen 5 7600", "https://via.placeholder.com/500x300?text=Ryzen+5+7600",
                "ซีพียู 6 คอร์ 12 เธรด เหมาะกับเกมและงานทั่วไป", "6 Cores, 12 Threads, AM5"
            ),
            (
                "Corsair DDR5 16GB", "Corsair", "RAM", 2490, 20,
                "16GB DDR5", "-", "-", "https://via.placeholder.com/500x300?text=DDR5+16GB",
                "แรมสำหรับเครื่องประกอบรุ่นใหม่", "Bus 5600MHz, 16GB x 1"
            ),
            (
                "Intel Core i5-14400F", "Intel", "CPU", 8290, 15,
                "-", "-", "Core i5-14400F", "https://via.placeholder.com/500x300?text=i5-14400F",
                "ซีพียูยอดนิยมสำหรับเกมเมอร์", "10 Cores, 16 Threads, LGA1700"
            ),
            (
                "ASUS RTX 4070 SUPER", "ASUS", "การ์ดจอ", 24990, 5,
                "12GB", "RTX 4070 SUPER", "-", "https://via.placeholder.com/500x300?text=RTX+4070+SUPER",
                "การ์ดจอระดับสูงสำหรับเล่นเกม 2K", "VRAM 12GB, Ray Tracing, DLSS 3"
            ),
        ]

        db.executemany(
            """
            INSERT INTO products
            (name, brand, category, price, stock, ram, gpu, cpu, image_url, description, specs_text, reviews_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [(p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8], p[9], p[10], "[]") for p in sample_products]
        )

    db.commit()
    db.close()


# --------------------------
# Utility functions
# --------------------------
def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if "member_id" not in session:
            flash("กรุณาเข้าสู่ระบบก่อน", "warning")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapped_view


def get_current_member():
    member_id = session.get("member_id")
    if not member_id:
        return None
    db = get_db()
    return db.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()


def parse_json_text(text_value, default_value):
    try:
        return json.loads(text_value) if text_value else default_value
    except json.JSONDecodeError:
        return default_value


def get_product_by_id(product_id):
    db = get_db()
    return db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()


def get_cart():
    if "cart" not in session:
        session["cart"] = {}
    return session["cart"]


def cart_items_with_total():
    db = get_db()
    cart = get_cart()
    items = []
    total = 0

    for product_id, qty in cart.items():
        product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if product:
            subtotal = product["price"] * int(qty)
            total += subtotal
            items.append({
                "product": product,
                "qty": int(qty),
                "subtotal": subtotal
            })
    return items, total


def save_slip_file(file):
    if not file or file.filename == "":
        return None
    filename = secure_filename(file.filename)
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    full_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    file.save(full_path)
    return unique_name


def simulate_payment_gateway(payment_method):
    # ฟังก์ชันจำลองการเชื่อม Payment Gateway
    # โปรเจกต์จริงค่อยเปลี่ยนเป็น API ของ Omise / Stripe / 2C2P ฯลฯ
    if payment_method in ["card", "ewallet"]:
        return True
    return False


@app.context_processor
def inject_cart_count():
    cart = session.get("cart", {})
    count = sum(int(qty) for qty in cart.values())
    return {"cart_count": count}


# --------------------------
# Auth routes
# --------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form["full_name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        db = get_db()
        existing = db.execute("SELECT id FROM members WHERE email = ?", (email,)).fetchone()
        if existing:
            flash("อีเมลนี้ถูกใช้งานแล้ว", "danger")
            return redirect(url_for("register"))

        db.execute(
            "INSERT INTO members (full_name, email, password_hash, wishlist_json) VALUES (?, ?, ?, ?)",
            (full_name, email, generate_password_hash(password), "[]")
        )
        db.commit()
        flash("สมัครสมาชิกสำเร็จ กรุณาเข้าสู่ระบบ", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        db = get_db()
        member = db.execute("SELECT * FROM members WHERE email = ?", (email,)).fetchone()

        if member and check_password_hash(member["password_hash"], password):
            session["member_id"] = member["id"]
            flash("เข้าสู่ระบบสำเร็จ", "success")
            return redirect(url_for("index"))

        flash("อีเมลหรือรหัสผ่านไม่ถูกต้อง", "danger")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("ออกจากระบบแล้ว", "info")
    return redirect(url_for("index"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    reset_link = None
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        token = uuid.uuid4().hex
        expire_time = (datetime.now() + timedelta(minutes=30)).isoformat()

        db = get_db()
        member = db.execute("SELECT * FROM members WHERE email = ?", (email,)).fetchone()

        if member:
            db.execute(
                "UPDATE members SET reset_token = ?, reset_expiry = ? WHERE id = ?",
                (token, expire_time, member["id"])
            )
            db.commit()
            reset_link = url_for("reset_password", token=token, _external=True)
            flash("ตัวอย่างโปรเจกต์นี้จะโชว์ลิงก์รีเซ็ตให้เลย (ไม่ส่งอีเมลจริง)", "info")
        else:
            flash("ไม่พบอีเมลในระบบ", "danger")

    return render_template("forgot_password.html", reset_link=reset_link)


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    db = get_db()
    member = db.execute(
        "SELECT * FROM members WHERE reset_token = ?",
        (token,)
    ).fetchone()

    if not member:
        flash("ลิงก์รีเซ็ตไม่ถูกต้อง", "danger")
        return redirect(url_for("login"))

    if member["reset_expiry"]:
        expire_time = datetime.fromisoformat(member["reset_expiry"])
        if datetime.now() > expire_time:
            flash("ลิงก์รีเซ็ตหมดอายุแล้ว", "danger")
            return redirect(url_for("forgot_password"))

    if request.method == "POST":
        new_password = request.form["password"]

        db.execute(
            """
            UPDATE members
            SET password_hash = ?, reset_token = NULL, reset_expiry = NULL
            WHERE id = ?
            """,
            (generate_password_hash(new_password), member["id"])
        )
        db.commit()
        flash("รีเซ็ตรหัสผ่านสำเร็จ", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html", token=token)


# --------------------------
# Product routes
# --------------------------
@app.route("/")
@app.route("/products")
def index():
    search = request.args.get("search", "").strip()
    brand = request.args.get("brand", "").strip()
    category = request.args.get("category", "").strip()
    min_price = request.args.get("min_price", "").strip()
    max_price = request.args.get("max_price", "").strip()
    ram = request.args.get("ram", "").strip()
    gpu = request.args.get("gpu", "").strip()

    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if search:
        query += " AND (name LIKE ? OR category LIKE ? OR cpu LIKE ? OR gpu LIKE ?)"
        like_text = f"%{search}%"
        params.extend([like_text, like_text, like_text, like_text])

    if brand:
        query += " AND brand LIKE ?"
        params.append(f"%{brand}%")

    if category:
        query += " AND category LIKE ?"
        params.append(f"%{category}%")

    if min_price:
        query += " AND price >= ?"
        params.append(float(min_price))

    if max_price:
        query += " AND price <= ?"
        params.append(float(max_price))

    if ram:
        query += " AND ram LIKE ?"
        params.append(f"%{ram}%")

    if gpu:
        query += " AND gpu LIKE ?"
        params.append(f"%{gpu}%")

    query += " ORDER BY id DESC"

    db = get_db()
    products = db.execute(query, params).fetchall()
    brands = db.execute("SELECT DISTINCT brand FROM products ORDER BY brand").fetchall()
    categories = db.execute("SELECT DISTINCT category FROM products ORDER BY category").fetchall()

    return render_template(
        "index.html",
        products=products,
        brands=brands,
        categories=categories
    )


@app.route("/product/<int:product_id>", methods=["GET", "POST"])
def product_detail(product_id):
    db = get_db()
    product = get_product_by_id(product_id)

    if not product:
        flash("ไม่พบสินค้า", "danger")
        return redirect(url_for("index"))

    if request.method == "POST":
        if "member_id" not in session:
            flash("กรุณาเข้าสู่ระบบก่อนรีวิว", "warning")
            return redirect(url_for("login"))

        rating = int(request.form["rating"])
        comment = request.form["comment"].strip()
        member = get_current_member()

        reviews = parse_json_text(product["reviews_json"], [])
        reviews.append({
            "member_name": member["full_name"],
            "rating": rating,
            "comment": comment,
            "created_at": datetime.now().strftime("%d/%m/%Y %H:%M")
        })

        db.execute(
            "UPDATE products SET reviews_json = ? WHERE id = ?",
            (json.dumps(reviews, ensure_ascii=False), product_id)
        )
        db.commit()

        flash("เพิ่มรีวิวเรียบร้อยแล้ว", "success")
        return redirect(url_for("product_detail", product_id=product_id))

    reviews = parse_json_text(product["reviews_json"], [])
    avg_rating = round(sum(r["rating"] for r in reviews) / len(reviews), 1) if reviews else 0

    related_products = db.execute(
        """
        SELECT * FROM products
        WHERE id != ? AND (category = ? OR brand = ?)
        LIMIT 4
        """,
        (product_id, product["category"], product["brand"])
    ).fetchall()

    wishlist_ids = []
    member = get_current_member()
    if member:
        wishlist_ids = parse_json_text(member["wishlist_json"], [])

    return render_template(
        "product_detail.html",
        product=product,
        reviews=reviews,
        avg_rating=avg_rating,
        related_products=related_products,
        wishlist_ids=wishlist_ids
    )


# --------------------------
# Wishlist routes
# --------------------------
@app.route("/wishlist")
@login_required
def wishlist():
    db = get_db()
    member = get_current_member()
    wishlist_ids = parse_json_text(member["wishlist_json"], [])

    products = []
    if wishlist_ids:
        placeholders = ",".join(["?"] * len(wishlist_ids))
        products = db.execute(
            f"SELECT * FROM products WHERE id IN ({placeholders})",
            wishlist_ids
        ).fetchall()

    return render_template("wishlist.html", products=products)


@app.route("/wishlist/toggle/<int:product_id>")
@login_required
def toggle_wishlist(product_id):
    db = get_db()
    member = get_current_member()
    wishlist_ids = parse_json_text(member["wishlist_json"], [])

    if product_id in wishlist_ids:
        wishlist_ids.remove(product_id)
        flash("ลบออกจากรายการโปรดแล้ว", "info")
    else:
        wishlist_ids.append(product_id)
        flash("เพิ่มในรายการโปรดแล้ว", "success")

    db.execute(
        "UPDATE members SET wishlist_json = ? WHERE id = ?",
        (json.dumps(wishlist_ids, ensure_ascii=False), member["id"])
    )
    db.commit()

    return redirect(request.referrer or url_for("wishlist"))


# --------------------------
# Cart routes
# --------------------------
@app.route("/cart")
def cart():
    items, total = cart_items_with_total()
    return render_template("cart.html", items=items, total=total)


@app.route("/add-to-cart/<int:product_id>")
def add_to_cart(product_id):
    product = get_product_by_id(product_id)
    if not product:
        flash("ไม่พบสินค้า", "danger")
        return redirect(url_for("index"))

    cart = get_cart()
    product_key = str(product_id)
    cart[product_key] = cart.get(product_key, 0) + 1
    session["cart"] = cart
    flash("เพิ่มสินค้าลงตะกร้าแล้ว", "success")
    return redirect(request.referrer or url_for("index"))


@app.route("/update-cart", methods=["POST"])
def update_cart():
    cart = get_cart()

    for key, value in request.form.items():
        if key.startswith("qty_"):
            product_id = key.replace("qty_", "")
            try:
                qty = int(value)
                if qty <= 0:
                    cart.pop(product_id, None)
                else:
                    cart[product_id] = qty
            except ValueError:
                pass

    session["cart"] = cart
    flash("อัปเดตตะกร้าแล้ว", "success")
    return redirect(url_for("cart"))


@app.route("/remove-from-cart/<int:product_id>")
def remove_from_cart(product_id):
    cart = get_cart()
    cart.pop(str(product_id), None)
    session["cart"] = cart
    flash("ลบสินค้าออกจากตะกร้าแล้ว", "info")
    return redirect(url_for("cart"))


# --------------------------
# Checkout / Order routes
# --------------------------
@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    items, total = cart_items_with_total()
    if not items:
        flash("ตะกร้าสินค้ายังว่างอยู่", "warning")
        return redirect(url_for("cart"))

    shipping_fee = 100
    grand_total = total + shipping_fee

    if request.method == "POST":
        shipping_address = request.form["shipping_address"].strip()
        payment_method = request.form["payment_method"]
        slip_file = request.files.get("slip_file")

        slip_filename = None
        status = "รอชำระเงิน"

        if payment_method == "bank_transfer":
            slip_filename = save_slip_file(slip_file)
            status = "รอชำระเงิน"

        if payment_method in ["card", "ewallet"]:
            payment_success = simulate_payment_gateway(payment_method)
            status = "กำลังจัดส่ง" if payment_success else "รอชำระเงิน"

        order_code = "ORD-" + datetime.now().strftime("%Y%m%d%H%M%S")
        order_items = []

        for item in items:
            order_items.append({
                "product_id": item["product"]["id"],
                "name": item["product"]["name"],
                "price": item["product"]["price"],
                "qty": item["qty"],
                "subtotal": item["subtotal"]
            })

        db = get_db()
        db.execute(
            """
            INSERT INTO orders
            (member_id, order_code, items_json, total_price, shipping_fee, grand_total,
             shipping_address, payment_method, slip_filename, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["member_id"],
                order_code,
                json.dumps(order_items, ensure_ascii=False),
                total,
                shipping_fee,
                grand_total,
                shipping_address,
                payment_method,
                slip_filename,
                status
            )
        )
        db.commit()

        session["cart"] = {}
        flash("สั่งซื้อสำเร็จ", "success")
        return redirect(url_for("orders"))

    return render_template(
        "checkout.html",
        items=items,
        total=total,
        shipping_fee=shipping_fee,
        grand_total=grand_total
    )


@app.route("/orders")
@login_required
def orders():
    db = get_db()
    all_orders = db.execute(
        "SELECT * FROM orders WHERE member_id = ? ORDER BY id DESC",
        (session["member_id"],)
    ).fetchall()

    parsed_orders = []
    for order in all_orders:
        parsed_orders.append({
            "id": order["id"],
            "order_code": order["order_code"],
            "items": parse_json_text(order["items_json"], []),
            "grand_total": order["grand_total"],
            "status": order["status"],
            "payment_method": order["payment_method"],
            "created_at": order["created_at"]
        })

    return render_template("orders.html", orders=parsed_orders)


@app.route("/order/<int:order_id>")
@login_required
def order_detail(order_id):
    db = get_db()
    order = db.execute(
        "SELECT * FROM orders WHERE id = ? AND member_id = ?",
        (order_id, session["member_id"])
    ).fetchone()

    if not order:
        flash("ไม่พบคำสั่งซื้อ", "danger")
        return redirect(url_for("orders"))

    parsed_order = dict(order)
    parsed_order["items"] = parse_json_text(order["items_json"], [])

    return render_template("order_detail.html", order=parsed_order)


@app.route("/order/<int:order_id>/confirm-payment")
@login_required
def confirm_payment(order_id):
    db = get_db()
    order = db.execute(
        "SELECT * FROM orders WHERE id = ? AND member_id = ?",
        (order_id, session["member_id"])
    ).fetchone()

    if not order:
        flash("ไม่พบคำสั่งซื้อ", "danger")
        return redirect(url_for("orders"))

    if order["status"] == "รอชำระเงิน":
        db.execute(
            "UPDATE orders SET status = 'กำลังจัดส่ง' WHERE id = ?",
            (order_id,)
        )
        db.commit()
        flash("จำลองการตรวจสอบชำระเงินเรียบร้อย", "success")

    return redirect(url_for("order_detail", order_id=order_id))


@app.route("/order/<int:order_id>/complete")
@login_required
def complete_order(order_id):
    db = get_db()
    order = db.execute(
        "SELECT * FROM orders WHERE id = ? AND member_id = ?",
        (order_id, session["member_id"])
    ).fetchone()

    if not order:
        flash("ไม่พบคำสั่งซื้อ", "danger")
        return redirect(url_for("orders"))

    if order["status"] == "กำลังจัดส่ง":
        db.execute(
            "UPDATE orders SET status = 'ส่งสำเร็จ' WHERE id = ?",
            (order_id,)
        )
        db.commit()
        flash("อัปเดตสถานะเป็นส่งสำเร็จแล้ว", "success")

    return redirect(url_for("order_detail", order_id=order_id))


# --------------------------
# Main
# --------------------------
if __name__ == "__main__":
    if not os.path.exists(app.config["DATABASE"]):
        init_db()
    else:
        # ป้องกันกรณีมีไฟล์ DB แต่ยังไม่มีตาราง
        try:
            db = sqlite3.connect(app.config["DATABASE"])
            db.execute("SELECT 1 FROM products LIMIT 1")
            db.close()
        except sqlite3.OperationalError:
            init_db()

    app.run(debug=True)
