from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from linkedin_tool.setting import Setting

DATABASE_URL = Setting.DATABASE_URL.value

class Base(DeclarativeBase):
    pass

engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)