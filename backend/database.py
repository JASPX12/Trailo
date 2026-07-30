from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

URL_BASE_DATOS = "postgresql://postgres.pumgpjfvogqgmpdurnhp:qwBLq70Mg8Ju3Jpu@aws-0-us-east-1.pooler.supabase.com:5432/postgres"

engine = create_engine(URL_BASE_DATOS, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()