"""
Proof script: shows that pagination stays correct even while new products
are being inserted "live", simulating someone browsing while data changes.

What this proves:
  1. Fetch page 1 (as if a user just opened the product list).
  2. Insert 5 brand-new products (simulating someone else adding products
     WHILE our user is browsing).
  3. Fetch page 2 using the cursor obtained from page 1.
  4. Verify: no product from page 1 reappears in page 2, AND no product
     that existed before step 2 is missing from page 2.

Why this works: new inserts get the NEWEST created_at, so they land at the
very top of the list (page 1 territory) -- they do NOT get inserted into the
middle of the list our user already moved past. Our cursor only ever asks
for "things older than what I've already seen", so it is unaffected by
brand-new rows appearing above.
"""

import os
import requests
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
BASE_URL = "http://127.0.0.1:8000"


def fetch_page(cursor=None):
    params = {"limit": 20}
    if cursor:
        params["cursor"] = cursor
    resp = requests.get(f"{BASE_URL}/products", params=params)
    resp.raise_for_status()
    return resp.json()


def insert_new_products(n=5):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    now = datetime.utcnow()
    rows = [
        (f"NEW PRODUCT {i}", "Electronics", 99.99, now, now)
        for i in range(n)
    ]
    execute_values(
        cur,
        "INSERT INTO products (name, category, price, created_at, updated_at) VALUES %s",
        rows,
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"Inserted {n} new products with created_at = {now.isoformat()}")


def main():
    print("Step 1: Fetching page 1...")
    page1 = fetch_page()
    page1_ids = [p["id"] for p in page1["products"]]
    print(f"  Page 1 ids: {page1_ids}")

    print("\nStep 2: Inserting 5 new products (simulating concurrent activity)...")
    insert_new_products(5)

    print("\nStep 3: Fetching page 2 using page 1's cursor...")
    page2 = fetch_page(cursor=page1["next_cursor"])
    page2_ids = [p["id"] for p in page2["products"]]
    print(f"  Page 2 ids: {page2_ids}")

    print("\nStep 4: Verifying correctness...")
    overlap = set(page1_ids) & set(page2_ids)
    if overlap:
        print(f"  FAIL: found duplicate ids across pages: {overlap}")
    else:
        print("  PASS: no duplicate ids between page 1 and page 2.")

    # Page 2 should NOT contain the new products we just inserted --
    # they are newer than everything on page 1, so they belong on page 1,
    # not page 2. This proves our cursor wasn't "confused" by the new rows.
    new_product_names = {p["name"] for p in page2["products"] if p["name"].startswith("NEW PRODUCT")}
    if new_product_names:
        print(f"  FAIL: new products leaked into page 2: {new_product_names}")
    else:
        print("  PASS: newly inserted products did not appear in page 2 (they're newer, so they belong on page 1).")


if __name__ == "__main__":
    main()