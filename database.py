from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

DATABASE_URL = "sqlite:///./operations.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==========================================
# 📊 DATABASE TABLES
# ==========================================

class PasscodeDB(Base):
    __tablename__ = "passcodes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
    passcode_type = Column(String, default="Trial")
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

class WarehouseDB(Base):
    __tablename__ = "warehouses"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(String, unique=True, index=True, nullable=False)
    location = Column(String, nullable=False)
    units_in_stock = Column(Integer, default=0)
    max_capacity = Column(Integer, default=1000)
    x_coord = Column(Float, default=0.0)
    y_coord = Column(Float, default=0.0)

class SimulationLogDB(Base):
    __tablename__ = "simulation_logs"

    id = Column(Integer, primary_key=True, index=True)
    engine_name = Column(String, nullable=False)  # AEGIS, NEXUS, or PHOENIX
    executed_at = Column(DateTime, default=datetime.utcnow)
    parameters_json = Column(Text, nullable=False)
    results_json = Column(Text, nullable=False)

def init_db():
    Base.metadata.create_all(bind=engine)