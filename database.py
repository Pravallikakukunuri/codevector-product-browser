import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Numeric, DateTime, Index
from sqlalchemy.orm import declarative_base, sessionmaker

# Load DATABASE_URL from .env file
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# The engine manages the actual connection pool to Postgres
engine = create_engine(DATABASE_URL)

# SessionLocal is how we'll talk to the DB in each request
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class our table models inherit from
Base = declarative_base()


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False, index=True)
    price = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    # Composite indexes for fast keyset pagination.
    # (created_at DESC, id DESC) -> fast "newest first" pagination overall
    # (category, created_at DESC, id DESC) -> fast pagination WITHIN a category filter
    __table_args__ = (
        Index("idx_products_pagination", created_at.desc(), id.desc()),
        Index("idx_products_category_pagination", category, created_at.desc(), id.desc()),
    )


def init_db():
    """Creates the products table (and indexes) in Postgres if they don't exist yet."""
    Base.metadata.create_all(bind=engine)