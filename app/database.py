import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:1234@localhost:3306/fastapi_db",
)

engine_options = {"pool_pre_ping": True}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()   


def ensure_schema():
    """Apply the small additive migrations needed by existing local databases."""
    inspector = inspect(engine)
    if "users" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("users")}
        if "coin_balance" not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE users ADD COLUMN coin_balance INTEGER NOT NULL DEFAULT 0")
                )
    if "groups" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("groups")}
        table_name = "`groups`" if engine.dialect.name == "mysql" else '"groups"'
        statements = {
            "quantity": f"ALTER TABLE {table_name} ADD COLUMN quantity INTEGER NULL",
            "region": f"ALTER TABLE {table_name} ADD COLUMN region VARCHAR(100) NOT NULL DEFAULT ''",
            "image_url": f"ALTER TABLE {table_name} ADD COLUMN image_url LONGTEXT NULL",
        }
        with engine.begin() as connection:
            for column, statement in statements.items():
                if column not in columns:
                    if engine.dialect.name == "sqlite" and column == "image_url":
                        statement = "ALTER TABLE groups ADD COLUMN image_url TEXT NULL"
                    connection.execute(text(statement))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()