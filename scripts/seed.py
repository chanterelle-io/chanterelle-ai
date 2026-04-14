"""Seed script: creates a sample SQLite DB and registers it as a connection."""

import json
import os
import random
import sqlite3
from datetime import datetime, timedelta

from sqlalchemy import text

from shared.db import get_engine


def create_sample_sqlite(db_path: str = "data/sample.db") -> str:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            signup_date DATE NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            segment TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            order_date DATE NOT NULL,
            amount REAL NOT NULL,
            product_category TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL
        )
    """)

    now = datetime.now()
    segments = ["enterprise", "mid-market", "smb", "individual"]
    categories = ["software", "hardware", "services", "support"]

    # Customers
    customers = []
    for i in range(1, 201):
        days_ago = random.randint(1, 365)
        signup = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        status = random.choices(["active", "inactive"], weights=[75, 25])[0]
        segment = random.choice(segments)
        customers.append((i, f"Customer {i}", f"customer{i}@example.com", signup, status, segment))

    c.execute("DELETE FROM customers")
    c.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?)", customers)

    # Orders
    orders = []
    order_id = 1
    for cust in customers:
        n_orders = random.randint(0, 12)
        for _ in range(n_orders):
            days_ago = random.randint(1, 180)
            order_date = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            amount = round(random.uniform(50, 5000), 2)
            category = random.choice(categories)
            orders.append((order_id, cust[0], order_date, amount, category))
            order_id += 1

    c.execute("DELETE FROM orders")
    c.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", orders)

    # Products
    products = [
        (1, "Analytics Platform", "software", 999),
        (2, "Data Connector", "software", 299),
        (3, "Server Node", "hardware", 4500),
        (4, "Setup & Onboarding", "services", 1500),
        (5, "Premium Support", "support", 200),
    ]
    c.execute("DELETE FROM products")
    c.executemany("INSERT INTO products VALUES (?, ?, ?, ?)", products)

    conn.commit()
    conn.close()

    abs_path = os.path.abspath(db_path)
    print(f"Created sample SQLite at {abs_path}")
    print(f"  {len(customers)} customers, {len(orders)} orders, {len(products)} products")
    return abs_path


def seed_connection(db_path: str) -> None:
    engine = get_engine()

    with engine.connect() as conn:
        existing = conn.execute(
            text("SELECT id FROM connections WHERE name = 'sample_db'")
        ).fetchone()

        if existing:
            conn.execute(
                text("UPDATE connections SET config = :config WHERE name = 'sample_db'"),
                {"config": json.dumps({"path": db_path})},
            )
            conn.commit()
            print("Updated connection 'sample_db'")
        else:
            conn.execute(
                text("""
                    INSERT INTO connections (name, display_name, type, status, config)
                    VALUES ('sample_db', 'Sample Analytics DB', 'sqlite', 'active', :config)
                """),
                {"config": json.dumps({"path": db_path})},
            )
            conn.commit()
            print("Created connection 'sample_db'")


if __name__ == "__main__":
    db_path = create_sample_sqlite()
    seed_connection(db_path)
    print("\nDone. You can now start the services.")
