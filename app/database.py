from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os

# Load environment variables from the project root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(project_root, '.env')
load_dotenv(env_path)

# Database configuration
DB_URL = os.getenv("DB_URL", "mysql+pymysql://root@localhost/trading_bot")

# Create engine
engine = create_engine(DB_URL)

# Session factory
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Base class for ORM models
Base = declarative_base()

def get_db():
    """Dependency for FastAPI to get database sessions"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
