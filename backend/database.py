from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# URL de conexión directa a tu proyecto en Supabase
URL_BASE_DATOS = "postgresql://postgres.pumgpjfvogqgmpdurnhp:qwBLq70Mg8Ju3Jpu@aws-0-us-east-1.pooler.supabase.com:5432/postgres"

# Conectamos con el engine. pool_pre_ping=True asegura que las conexiones caídas se descarten
engine = create_engine(URL_BASE_DATOS, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()