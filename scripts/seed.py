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


def seed_runtimes() -> None:
    engine = get_engine()
    runtimes = [
        {
            "name": "sql_runtime",
            "display_name": "SQL Runtime",
            "type": "sql",
            "endpoint_url": "http://localhost:8010",
        },
        {
            "name": "python_runtime",
            "display_name": "Python Runtime",
            "type": "python",
            "endpoint_url": "http://localhost:8011",
        },
    ]

    with engine.connect() as conn:
        for rt in runtimes:
            existing = conn.execute(
                text("SELECT id FROM runtimes WHERE name = :name"),
                {"name": rt["name"]},
            ).fetchone()

            if existing:
                conn.execute(
                    text("""
                        UPDATE runtimes SET endpoint_url = :url, type = :type
                        WHERE name = :name
                    """),
                    {"url": rt["endpoint_url"], "type": rt["type"], "name": rt["name"]},
                )
                print(f"Updated runtime '{rt['name']}'")
            else:
                conn.execute(
                    text("""
                        INSERT INTO runtimes (name, display_name, type, endpoint_url, status)
                        VALUES (:name, :display_name, :type, :url, 'active')
                    """),
                    {
                        "name": rt["name"],
                        "display_name": rt["display_name"],
                        "type": rt["type"],
                        "url": rt["endpoint_url"],
                    },
                )
                print(f"Created runtime '{rt['name']}'")
        conn.commit()


def seed_skills() -> None:
    engine = get_engine()

    skills = [
        {
            "name": "sample_db_connector",
            "category": "connector",
            "title": "Sample DB Schema Guide",
            "description": "Knows the schema of the sample analytics database.",
            "scope": json.dumps({
                "level": "connection",
                "connection_names": ["sample_db"],
            }),
            "triggers": json.dumps([
                {"kind": "connection_match", "value": "sample_db", "weight": 1.0},
            ]),
            "instructions": json.dumps({
                "summary": (
                    "The sample_db is a SQLite database with three tables: "
                    "customers (id, name, email, signup_date, status, segment), "
                    "orders (id, customer_id, order_date, amount, product_category), "
                    "products (id, name, category, price). "
                    "Use these tables when the user asks about customers, orders, products, or revenue."
                ),
                "recommended_steps": [
                    "Check which table has the data the user needs",
                    "Write a SQL query joining tables as needed",
                    "Use aggregate functions for summaries",
                ],
                "dos": [
                    "Use proper JOIN syntax when combining tables",
                    "Always alias columns clearly in aggregations",
                    "Use DATE functions for time-based filtering",
                ],
                "donts": [
                    "Don't use SELECT * in production queries — select specific columns",
                    "Don't assume column names — refer to the schema above",
                ],
                "output_expectations": [
                    "Query results should be clean, well-named artifacts",
                    "Include row counts and column descriptions in summaries",
                ],
            }),
            "tags": json.dumps(["sqlite", "analytics", "sample"]),
        },
        {
            "name": "churn_analysis",
            "category": "metric",
            "title": "Customer Churn Analysis",
            "description": "Guidelines for analyzing customer churn patterns.",
            "scope": json.dumps({"level": "global"}),
            "triggers": json.dumps([
                {"kind": "keyword", "value": "churn", "weight": 1.0},
                {"kind": "keyword", "value": "inactive", "weight": 0.8},
                {"kind": "keyword", "value": "retention", "weight": 0.8},
            ]),
            "instructions": json.dumps({
                "summary": (
                    "When analyzing churn, a churned customer has status='inactive' or no orders "
                    "in the last 90 days. Calculate churn rate as inactive/total, ideally broken "
                    "down by segment. Prefer a single query that computes the rate and breakdown "
                    "rather than multiple separate queries."
                ),
                "recommended_steps": [
                    "Write one SQL query that calculates churn rate overall and by segment",
                ],
                "dos": [
                    "Define the churn window clearly (e.g. status='inactive' or 90 days no orders)",
                    "Compare segments (enterprise, mid-market, smb, individual) in a single query",
                ],
                "donts": [
                    "Don't run separate queries for each segment — use GROUP BY instead",
                    "Don't count recently signed-up customers as churned just because they have few orders",
                ],
                "output_expectations": [
                    "A single artifact with churn rate by segment",
                ],
            }),
            "tags": json.dumps(["churn", "retention", "metrics"]),
        },
    ]

    with engine.connect() as conn:
        for skill in skills:
            existing = conn.execute(
                text("SELECT id FROM skills WHERE name = :name"),
                {"name": skill["name"]},
            ).fetchone()

            if existing:
                conn.execute(
                    text("""
                        UPDATE skills
                        SET category = :category, title = :title, description = :description,
                            scope = :scope, triggers = :triggers, instructions = :instructions,
                            tags = :tags
                        WHERE name = :name
                    """),
                    skill,
                )
                print(f"Updated skill '{skill['name']}'")
            else:
                conn.execute(
                    text("""
                        INSERT INTO skills (name, category, title, description, scope, triggers, instructions, tags)
                        VALUES (:name, :category, :title, :description, :scope, :triggers, :instructions, :tags)
                    """),
                    skill,
                )
                print(f"Created skill '{skill['name']}'")
        conn.commit()


def seed_policies() -> None:
    engine = get_engine()

    policies = [
        {
            "name": "deny_python_for_finance",
            "type": "tool_selection",
            "description": "Finance users cannot use Python transforms — SQL only.",
            "scope": json.dumps({"level": "global", "topic_profile_ids": []}),
            "condition": json.dumps({"tool_names": ["python_transform"]}),
            "effect": json.dumps({"denied_tool_names": ["python_transform"]}),
            "priority": 10,
            "tags": json.dumps(["finance", "security"]),
        },
        {
            "name": "large_query_advisory",
            "type": "execution_routing",
            "description": "Flag queries that might return large result sets.",
            "scope": json.dumps({"level": "global"}),
            "condition": json.dumps({"estimated_row_count_above": 10000}),
            "effect": json.dumps({"force_execution_mode": "deferred"}),
            "priority": 5,
            "tags": json.dumps(["performance"]),
        },
    ]

    with engine.connect() as conn:
        for policy in policies:
            existing = conn.execute(
                text("SELECT id FROM policies WHERE name = :name"),
                {"name": policy["name"]},
            ).fetchone()

            if existing:
                conn.execute(
                    text("""
                        UPDATE policies
                        SET type = :type, description = :description,
                            scope = :scope, condition = :condition, effect = :effect,
                            priority = :priority, tags = :tags
                        WHERE name = :name
                    """),
                    policy,
                )
                print(f"Updated policy '{policy['name']}'")
            else:
                conn.execute(
                    text("""
                        INSERT INTO policies (name, type, description, scope, condition, effect, priority, tags)
                        VALUES (:name, :type, :description, :scope, :condition, :effect, :priority, :tags)
                    """),
                    policy,
                )
                print(f"Created policy '{policy['name']}'")
        conn.commit()

    # Now update the finance policy with the actual topic profile ID
    with engine.connect() as conn:
        finance_profile = conn.execute(
            text("SELECT id FROM topic_profiles WHERE name = 'finance_analysis'")
        ).fetchone()
        if finance_profile:
            scope = json.dumps({
                "level": "global",
                "topic_profile_ids": [str(finance_profile[0])],
            })
            conn.execute(
                text("UPDATE policies SET scope = :scope WHERE name = 'deny_python_for_finance'"),
                {"scope": scope},
            )
            conn.commit()
            print("Linked policy 'deny_python_for_finance' to finance_analysis topic")


def seed_topic_profiles() -> None:
    engine = get_engine()

    # First, look up skill IDs for linking
    with engine.connect() as conn:
        skills_map = {}
        rows = conn.execute(text("SELECT id, name FROM skills")).fetchall()
        for row in rows:
            skills_map[row[1]] = str(row[0])

    connector_skill_id = skills_map.get("sample_db_connector", "")
    churn_skill_id = skills_map.get("churn_analysis", "")

    profiles = [
        {
            "name": "finance_analysis",
            "display_name": "Finance Analysis",
            "description": "Scoped to financial queries on the sample DB. SQL only, no Python transforms.",
            "allowed_tool_names": json.dumps(["query_sql_source", "inspect_artifact"]),
            "allowed_connection_names": json.dumps(["sample_db"]),
            "allowed_runtime_types": json.dumps(["sql"]),
            "active_skill_ids": json.dumps([connector_skill_id] if connector_skill_id else []),
            "active_policy_ids": json.dumps([]),
            "domains": json.dumps(["finance"]),
            "tags": json.dumps(["finance", "restricted"]),
        },
        {
            "name": "general_exploration",
            "display_name": "General Exploration",
            "description": "Full access to all tools and connections for exploratory analysis.",
            "allowed_tool_names": json.dumps(["query_sql_source", "transform_with_python", "inspect_artifact"]),
            "allowed_connection_names": json.dumps(["sample_db"]),
            "allowed_runtime_types": json.dumps(["sql", "python"]),
            "active_skill_ids": json.dumps(
                [sid for sid in [connector_skill_id, churn_skill_id] if sid]
            ),
            "active_policy_ids": json.dumps([]),
            "domains": json.dumps([]),
            "tags": json.dumps(["exploration", "full-access"]),
        },
    ]

    with engine.connect() as conn:
        for profile in profiles:
            existing = conn.execute(
                text("SELECT id FROM topic_profiles WHERE name = :name"),
                {"name": profile["name"]},
            ).fetchone()

            if existing:
                conn.execute(
                    text("""
                        UPDATE topic_profiles
                        SET display_name = :display_name, description = :description,
                            allowed_tool_names = :allowed_tool_names,
                            allowed_connection_names = :allowed_connection_names,
                            allowed_runtime_types = :allowed_runtime_types,
                            active_skill_ids = :active_skill_ids,
                            active_policy_ids = :active_policy_ids,
                            domains = :domains, tags = :tags
                        WHERE name = :name
                    """),
                    profile,
                )
                print(f"Updated topic profile '{profile['name']}'")
            else:
                conn.execute(
                    text("""
                        INSERT INTO topic_profiles
                            (name, display_name, description, allowed_tool_names,
                             allowed_connection_names, allowed_runtime_types,
                             active_skill_ids, active_policy_ids, domains, tags)
                        VALUES (:name, :display_name, :description, :allowed_tool_names,
                                :allowed_connection_names, :allowed_runtime_types,
                                :active_skill_ids, :active_policy_ids, :domains, :tags)
                    """),
                    profile,
                )
                print(f"Created topic profile '{profile['name']}'")
        conn.commit()

    # Seed user-topic assignments
    assignments = [
        {"user_id": "finance-user", "topic_name": "finance_analysis"},
        {"user_id": "analyst-user", "topic_name": "general_exploration"},
    ]

    with engine.connect() as conn:
        for assignment in assignments:
            # Look up topic profile ID
            profile_row = conn.execute(
                text("SELECT id FROM topic_profiles WHERE name = :name"),
                {"name": assignment["topic_name"]},
            ).fetchone()
            if not profile_row:
                print(f"Topic profile '{assignment['topic_name']}' not found, skipping assignment")
                continue

            profile_id = str(profile_row[0])

            existing = conn.execute(
                text("""
                    SELECT id FROM user_topic_assignments
                    WHERE user_id = :user_id AND topic_profile_id = :profile_id
                """),
                {"user_id": assignment["user_id"], "profile_id": profile_id},
            ).fetchone()

            if existing:
                print(f"Assignment {assignment['user_id']} → {assignment['topic_name']} already exists")
            else:
                conn.execute(
                    text("""
                        INSERT INTO user_topic_assignments (user_id, topic_profile_id, status)
                        VALUES (:user_id, :profile_id, 'active')
                    """),
                    {"user_id": assignment["user_id"], "profile_id": profile_id},
                )
                print(f"Assigned user '{assignment['user_id']}' → topic '{assignment['topic_name']}'")
        conn.commit()


if __name__ == "__main__":
    db_path = create_sample_sqlite()
    seed_connection(db_path)
    seed_runtimes()
    seed_skills()
    seed_topic_profiles()  # Must be before policies (policies reference profiles)
    seed_policies()
    print("\nDone. You can now start the services.")
