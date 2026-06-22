"""
FastAPI backend for browsing products.

KEY DESIGN DECISION: Keyset (cursor-based) pagination instead of OFFSET pagination.

Why not OFFSET?
  SELECT * FROM products ORDER BY created_at DESC LIMIT 20 OFFSET 4000
  - Slow: Postgres has to scan and discard 4000 rows every single call, on every page.
  - Incorrect under writes: if new products are inserted while someone is browsing,
    the "window" shifts. Rows can shift up unexpectedly, causing items to appear
    twice across pages, or be skipped entirely.

Why keyset pagination fixes both:
  - We use the LAST item's (created_at, id) as a "cursor". The next page query is:
      WHERE (created_at, id) < (last_created_at, last_id)
      ORDER BY created_at DESC, id DESC
      LIMIT 20
  - This jumps directly to the right spot using the index -- no scanning/discarding.
  - New inserts elsewhere don't affect this cursor's position, because we're always
    asking for "everything strictly older than this exact point", never "skip N rows".
  - (created_at, id) together (not created_at alone) gives a fully deterministic order
    even when multiple products share the same created_at timestamp.
"""

import base64
import json
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SessionLocal, Product

app = FastAPI(title="Product Browser API")

# Allow a frontend (bonus UI) running on a different origin to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def encode_cursor(created_at: datetime, id: int) -> str:
    """Turns (created_at, id) into an opaque string token to hand to the client."""
    raw = json.dumps({"created_at": created_at.isoformat(), "id": id})
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str):
    """Reverses encode_cursor. Raises if the cursor is malformed/tampered."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        data = json.loads(raw)
        return datetime.fromisoformat(data["created_at"]), data["id"]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid cursor")


@app.get("/products")
def list_products(
    limit: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
):
    """
    Returns products newest-first, optionally filtered by category.

    - First page: call with no `cursor`.
    - Next page: pass the `next_cursor` value returned from the previous call.
    """
    db: Session = next(get_db())
    try:
        query = select(Product)

        if category:
            query = query.where(Product.category == category)

        if cursor:
            cursor_created_at, cursor_id = decode_cursor(cursor)
            # Strict "less than" on the tuple (created_at, id) -- this is the
            # core of keyset pagination: everything strictly after what we've
            # already shown, ordered the same way.
            query = query.where(
                (Product.created_at, Product.id) < (cursor_created_at, cursor_id)
            )

        query = query.order_by(Product.created_at.desc(), Product.id.desc()).limit(limit)

        results = db.execute(query).scalars().all()

        next_cursor = None
        if len(results) == limit:
            last = results[-1]
            next_cursor = encode_cursor(last.created_at, last.id)

        return {
            "products": [
                {
                    "id": p.id,
                    "name": p.name,
                    "category": p.category,
                    "price": float(p.price),
                    "created_at": p.created_at.isoformat(),
                    "updated_at": p.updated_at.isoformat(),
                }
                for p in results
            ],
            "next_cursor": next_cursor,
            "has_more": next_cursor is not None,
        }
    finally:
        db.close()


@app.get("/categories")
def list_categories():
    """Returns the distinct categories available, for building a filter dropdown."""
    db: Session = next(get_db())
    try:
        rows = db.execute(select(Product.category).distinct()).scalars().all()
        return {"categories": sorted(rows)}
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}