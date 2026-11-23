"""SQLite persistence layer. Uses only Python's standard library."""
import sqlite3
from pathlib import Path
from uuid import uuid4

DB_PATH = Path(__file__).with_name("warehouse.db")

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with connect() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity >= 0),
            reorder_level INTEGER NOT NULL DEFAULT 5,
            location TEXT NOT NULL
        )""")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer TEXT NOT NULL,
            destination TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            priority INTEGER NOT NULL DEFAULT 3,
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(product_id) REFERENCES products(id)
        )""")
        # Safe, additive migration: preserve all existing order and inventory data.
        existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(orders)").fetchall()}
        if "assigned_vehicle" not in existing_columns:
            conn.execute("ALTER TABLE orders ADD COLUMN assigned_vehicle TEXT")
        if "route_km" not in existing_columns:
            conn.execute("ALTER TABLE orders ADD COLUMN route_km REAL")
        if "assigned_at" not in existing_columns:
            conn.execute("ALTER TABLE orders ADD COLUMN assigned_at TEXT")
        if "order_group_id" not in existing_columns:
            conn.execute("ALTER TABLE orders ADD COLUMN order_group_id TEXT")
        # Give each legacy single-line order its own group identifier.
        conn.execute("UPDATE orders SET order_group_id='ORD-' || printf('%06d', id) WHERE order_group_id IS NULL")
        count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if count == 0:
            sample = [
                ("SKU-1001","Wireless Mouse","Electronics",40,8,"A-01"),
                ("SKU-1002","Keyboard","Electronics",25,5,"A-02"),
                ("SKU-1003","Water Bottle","Lifestyle",60,10,"B-01"),
                ("SKU-1004","Notebook","Stationery",100,15,"B-02"),
                ("SKU-1005","USB-C Cable","Electronics",8,10,"C-01"),
                ("SKU-1006","Desk Lamp","Home",18,5,"C-02"),
            ]
            conn.executemany(
                "INSERT INTO products(sku,name,category,quantity,reorder_level,location) VALUES(?,?,?,?,?,?)",
                sample
            )

def get_products(search=""):
    with connect() as conn:
        if search:
            term = f"%{search}%"
            rows = conn.execute(
                "SELECT * FROM products WHERE sku LIKE ? OR name LIKE ? OR category LIKE ? ORDER BY name",
                (term, term, term)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM products ORDER BY name").fetchall()
        return [dict(r) for r in rows]

def add_product(sku, name, category, quantity, reorder_level, location):
    with connect() as conn:
        conn.execute(
            "INSERT INTO products(sku,name,category,quantity,reorder_level,location) VALUES(?,?,?,?,?,?)",
            (sku.strip(), name.strip(), category, quantity, reorder_level, location.strip().upper())
        )

def update_stock(product_id, quantity):
    with connect() as conn:
        conn.execute("UPDATE products SET quantity=? WHERE id=?", (quantity, product_id))

def delete_product(product_id):
    with connect() as conn:
        linked = conn.execute("SELECT COUNT(*) FROM orders WHERE product_id=?", (product_id,)).fetchone()[0]
        if linked:
            raise ValueError("This product is linked to existing orders and cannot be deleted.")
        conn.execute("DELETE FROM products WHERE id=?", (product_id,))

def create_multi_item_order(customer, destination, items, priority):
    """Create one customer order containing multiple product lines atomically.

    items accepts an iterable of (product_id, quantity) pairs. Every stock
    check happens before any stock is deducted, so a failed order changes nothing.
    Each line remains a normal order row for compatibility with dispatch/analytics.
    """
    customer = customer.strip()
    if not customer:
        raise ValueError("Enter a customer name.")
    normalized = {}
    for product_id, quantity in items:
        product_id, quantity = int(product_id), int(quantity)
        if quantity <= 0:
            raise ValueError("Every item quantity must be at least 1.")
        normalized[product_id] = normalized.get(product_id, 0) + quantity
    if not normalized:
        raise ValueError("Add at least one product to the cart.")

    group_id = f"ORD-{uuid4().hex[:8].upper()}"
    with connect() as conn:
        # Validate all lines before making any database changes.
        product_rows = {}
        for product_id, quantity in normalized.items():
            product = conn.execute(
                "SELECT id, name, quantity FROM products WHERE id=?", (product_id,)
            ).fetchone()
            if product is None:
                raise ValueError(f"Product ID {product_id} was not found.")
            if product["quantity"] < quantity:
                raise ValueError(
                    f"Insufficient stock for {product['name']}. "
                    f"Available: {product['quantity']}, requested: {quantity}."
                )
            product_rows[product_id] = product

        for product_id, quantity in normalized.items():
            conn.execute("UPDATE products SET quantity=quantity-? WHERE id=?", (quantity, product_id))
            conn.execute(
                """INSERT INTO orders(customer,destination,product_id,quantity,priority,order_group_id)
                   VALUES(?,?,?,?,?,?)""",
                (customer, destination, product_id, quantity, int(priority), group_id)
            )
    return group_id


def create_order(customer, destination, product_id, quantity, priority):
    """Backward-compatible helper for placing a single-item order."""
    return create_multi_item_order(customer, destination, [(product_id, quantity)], priority)

def get_orders():
    with connect() as conn:
        rows = conn.execute("""
        SELECT o.*, p.name AS product_name, p.location AS pick_location
        FROM orders o JOIN products p ON p.id=o.product_id
        ORDER BY CASE o.status WHEN 'Pending' THEN 0 WHEN 'Processing' THEN 1 ELSE 2 END,
                 o.priority ASC, o.id ASC
        """).fetchall()
        return [dict(r) for r in rows]

def update_order_status(order_id, status):
    with connect() as conn:
        conn.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))


def update_order_group_status(order_group_id, status):
    """Update every product line belonging to the same customer order."""
    with connect() as conn:
        conn.execute("UPDATE orders SET status=? WHERE order_group_id=?", (status, order_group_id))

def dashboard_stats():
    with connect() as conn:
        products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        units = conn.execute("SELECT COALESCE(SUM(quantity),0) FROM products").fetchone()[0]
        pending = conn.execute("SELECT COUNT(DISTINCT order_group_id) FROM orders WHERE status='Pending'").fetchone()[0]
        completed = conn.execute("SELECT COUNT(DISTINCT order_group_id) FROM orders WHERE status='Delivered'").fetchone()[0]
        low = conn.execute("SELECT COUNT(*) FROM products WHERE quantity <= reorder_level").fetchone()[0]
        return {"products": products, "units": units, "pending": pending, "completed": completed, "low": low}


def save_delivery_assignments(assignments):
    """Persist vehicle and route details for each assigned order."""
    with connect() as conn:
        for vehicle_name, orders in assignments.items():
            for order in orders:
                line_ids = order.get("line_ids") or [int(order["id"])]
                for line_id in line_ids:
                    conn.execute(
                        "UPDATE orders SET assigned_vehicle=?, route_km=?, assigned_at=CURRENT_TIMESTAMP WHERE id=? AND status!='Delivered'",
                        (vehicle_name, float(order["route_km"]), int(line_id))
                    )

def clear_delivery_assignments():
    """Clear assignments for orders that have not been delivered."""
    with connect() as conn:
        conn.execute("UPDATE orders SET assigned_vehicle=NULL, route_km=NULL, assigned_at=NULL WHERE status!='Delivered'")

def analytics_summary():
    """Return compact aggregate metrics directly from SQLite."""
    with connect() as conn:
        status_rows = conn.execute("SELECT status, COUNT(DISTINCT order_group_id) AS total FROM orders GROUP BY status").fetchall()
        priority_rows = conn.execute("SELECT priority, COUNT(DISTINCT order_group_id) AS total FROM orders GROUP BY priority").fetchall()
        daily_rows = conn.execute("SELECT substr(MIN(created_at),1,10) AS day, COUNT(DISTINCT order_group_id) AS orders FROM orders GROUP BY order_group_id ORDER BY day").fetchall()
        category_rows = conn.execute("SELECT category, SUM(quantity) AS units FROM products GROUP BY category ORDER BY units DESC").fetchall()
        destination_rows = conn.execute("SELECT destination, COUNT(DISTINCT order_group_id) AS total FROM orders GROUP BY destination ORDER BY total DESC").fetchall()
        totals = conn.execute("""SELECT COUNT(*) AS total,
            SUM(CASE WHEN status='Delivered' THEN 1 ELSE 0 END) AS delivered,
            AVG(CASE WHEN status='Delivered' THEN 1.0 ELSE 0.0 END) AS delivered_rate
            FROM (SELECT order_group_id, MAX(status='Delivered') AS is_delivered,
                  CASE WHEN MAX(status='Delivered')=1 THEN 'Delivered' ELSE MIN(status) END AS status
                  FROM orders GROUP BY order_group_id)""").fetchone()
        assigned = conn.execute("SELECT COUNT(DISTINCT order_group_id) FROM orders WHERE assigned_vehicle IS NOT NULL AND status!='Delivered'").fetchone()[0]
        return {
            "status": [dict(r) for r in status_rows],
            "priority": [dict(r) for r in priority_rows],
            "daily": [dict(r) for r in daily_rows],
            "category": [dict(r) for r in category_rows],
            "destination": [dict(r) for r in destination_rows],
            "total_orders": totals["total"] or 0,
            "delivered": totals["delivered"] or 0,
            "delivered_rate": round((totals["delivered"] or 0) / (totals["total"] or 1) * 100, 1),
            "assigned": assigned,
        }
