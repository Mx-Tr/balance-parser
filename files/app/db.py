from sqlalchemy import create_engine, Column, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

engine = create_engine("sqlite:///balances.db", echo=False, connect_args={"check_same_thread": False})
Base = declarative_base()

class Balance(Base):
    __tablename__ = "balances"
    id          = Column(String, primary_key=True)
    source      = Column(String)             # megafon / yandex
    account     = Column(String)
    value       = Column(Float)
    updated_at  = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
