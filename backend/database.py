from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 1. Tu URI de conexión a PostgreSQL
URL_BASE_DATOS = "postgresql://postgres:postgres@localhost:5432/cines"

engine = create_engine(URL_BASE_DATOS)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()