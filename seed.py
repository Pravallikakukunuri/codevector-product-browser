"""
Seed script: generates 200,000 fake products and inserts them into Postgres.

KEY DECISION: we use bulk inserts (psycopg2's execute_values) in batches of 5,000,
instead of one INSERT per row. Looping with individual INSERTs means 200,000 separate
round-trips to the database -- painfully slow (can take 10-20+ minutes).
Bulk insert sends many rows in a single statement, cutting this down to seconds.
"""

import os
import random
from datetime import datetime, timedelta

from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values
from faker import Faker

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

fake = Faker()

TOTAL_PRODUCTS = 200_000
BATCH_SIZE = 5_000

CATEGORIES = [
    "Electronics", "Clothing", "Home & Kitchen", "Books", "Toys",
    "Sports", "Beauty", "Garden", "Automotive", "Groceries",
]


def generate_batch(batch_size: int, start_time: datetime):
    """Generates a list of product tuples ready for bulk insert."""
    rows = []
    for i in range(batch_size):
        # Spread created_at times slightly so ordering/pagination has realistic variety
        created_at = start_time - timedelta(seconds=random.randint(0, 60))
        updated_at = created_at
        rows.append((
            fake.word().capitalize() + " " + fake.word().capitalize(),  # name
            random.choice(CATEGORIES),                                   # category
            round(random.uniform(5, 500), 2),                            # price
            created_at,
            updated_at,
        ))
    return rows


def seed():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    print(f"Seeding {TOTAL_PRODUCTS} products in batches of {BATCH_SIZE}...")

    inserted = 0
    base_time = datetime.utcnow()

    while inserted < TOTAL_PRODUCTS:
        batch_size = min(BATCH_SIZE, TOTAL_PRODUCTS - inserted)
        # Each batch gets progressively older timestamps, so the very last
        # batch inserted ends up with the oldest created_at, and the data
        # still makes sense as "newest first" once fully loaded.
        batch_time = base_time - timedelta(seconds=inserted)
        rows = generate_batch(batch_size, batch_time)

        execute_values(
            cur,
            """
            INSERT INTO products (name, category, price, created_at, updated_at)
            VALUES %s
            """,
            rows,
        )
        conn.commit()

        inserted += batch_size
        print(f"  Inserted {inserted}/{TOTAL_PRODUCTS}")

    cur.close()
    conn.close()
    print("Done seeding.")


if __name__ == "__main__":
    seed()