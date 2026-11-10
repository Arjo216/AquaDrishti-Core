import hashlib
import os
from datetime import datetime

from sqlalchemy import (  # type: ignore[reportMissingImports]
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    create_engine,
    event,
)
from sqlalchemy.orm import (  # type: ignore[reportMissingImports]
    declarative_base,
    sessionmaker,
)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./aquasentinel_ledger.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 15} if "sqlite" in DATABASE_URL else {},
    pool_pre_ping=True
)

# Enable Write-Ahead Logging (WAL) & Synchronous NORMAL for crash-resilient high concurrency on SQLite
if "sqlite" in DATABASE_URL:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class TelemetryLedgerRecord(Base):
    __tablename__ = "telemetry_ledger"

    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(String, index=True)
    facility_name = Column(String)
    district = Column(String, index=True)
    state = Column(String)
    zone_category = Column(String)
    lat = Column(Float)
    lon = Column(Float)

    # Physical Sensor Telemetry
    flow_rate_m3_hr = Column(Float)
    daily_cumulative_m3 = Column(Float)
    noc_limit_m3 = Column(Float)
    depth_mbgl = Column(Float)
    drawdown_rate_m_hr = Column(Float)
    ph = Column(Float)
    orp_mv = Column(Float)
    tds_ppm = Column(Float)
    baseline_arsenic_ug_l = Column(Float)

    # Physics-Informed Geochemical Soft-Sensor Outputs
    predicted_as_total_ug_l = Column(Float)
    predicted_as3_toxic_ug_l = Column(Float)
    predicted_as5_ug_l = Column(Float)
    redox_regime = Column(String)
    arsenic_risk_level = Column(String)

    # Closed-Loop VFD Pump Governor & CGWA Compliance Outputs
    recommended_pump_hz = Column(Float)
    modbus_command_hex = Column(String)
    pump_action_status = Column(String)
    cgwa_status = Column(String)
    bharatkosh_daily_fee_inr = Column(Float)
    is_anomaly = Column(Boolean)
    utilization_pct = Column(Float)

    # SHA-256 Tamper-Evident Audit Chain
    nonce = Column(String, unique=True, index=True)
    ts_iso = Column(String)
    prev_hash = Column(String)
    record_hash = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


def compute_sha256_hash(node_id: str, cumulative_m3: float, depth_mbgl: float, as_total: float, prev_hash: str, ts_iso: str) -> str:
    payload_str = f"{node_id}|{cumulative_m3:.3f}|{depth_mbgl:.2f}|{as_total:.2f}|{prev_hash}|{ts_iso}"
    return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()


Base.metadata.create_all(bind=engine)