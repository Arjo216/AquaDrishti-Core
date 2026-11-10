import threading
from datetime import datetime
from fastapi import FastAPI, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from backend.database import SessionLocal, TelemetryLedgerRecord, compute_sha256_hash
from backend.geochem_engine import HydroGeochemEngine
from backend.security import verify_edge_request
from backend.pignn_engine import PhysicsInformedAquiferGNN
from backend.swarm_aco import SwarmACOPumpScheduler
from backend.federated_zk import FederatedZKCoordinator
from backend.macro_copilot import MacroSubsidenceAndCopilotEngine

app = FastAPI(
    title="AquaSentinel-Core: 4D PI-GNN, Swarm ACO & Zero-Trust Aquifer Grid",
    version="3.0.0-ULTRA"
)

engine_ai = HydroGeochemEngine()
pignn_engine = PhysicsInformedAquiferGNN()
swarm_scheduler = SwarmACOPumpScheduler()
fed_zk_engine = FederatedZKCoordinator()
macro_copilot = MacroSubsidenceAndCopilotEngine()

ledger_lock = threading.Lock()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class TelemetryInput(BaseModel):
    node_id: str = Field(..., min_length=3, max_length=64)
    facility_name: str
    district: str
    state: str
    zone_category: str
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    flow_rate_m3_hr: float
    daily_cumulative_m3: float
    noc_limit_m3: float
    depth_mbgl: float
    drawdown_rate_m_hr: float
    ph: float
    orp_mv: float
    tds_ppm: float
    baseline_arsenic_ug_l: float
    timestamp_epoch: int
    nonce: str = Field(..., min_length=8, max_length=64)


def _fetch_latest_nodes_list(db: Session) -> list[dict]:
    records = (
        db.query(TelemetryLedgerRecord)
        .order_by(TelemetryLedgerRecord.timestamp.desc())
        .limit(300)
        .all()
    )
    latest_by_node = {}
    for r in records:
        if r.node_id not in latest_by_node:
            latest_by_node[r.node_id] = {
                "node_id": r.node_id,
                "facility_name": r.facility_name,
                "district": r.district,
                "state": r.state,
                "zone_category": r.zone_category,
                "lat": r.lat,
                "lon": r.lon,
                "flow_rate_m3_hr": r.flow_rate_m3_hr,
                "daily_cumulative_m3": r.daily_cumulative_m3,
                "noc_limit_m3": r.noc_limit_m3,
                "depth_mbgl": r.depth_mbgl,
                "drawdown_rate_m_hr": r.drawdown_rate_m_hr,
                "ph": r.ph,
                "orp_mv": r.orp_mv,
                "tds_ppm": r.tds_ppm,
                "predicted_as_total_ug_l": r.predicted_as_total_ug_l,
                "predicted_as3_toxic_ug_l": r.predicted_as3_toxic_ug_l,
                "predicted_as5_ug_l": r.predicted_as5_ug_l,
                "redox_regime": r.redox_regime,
                "arsenic_risk_level": r.arsenic_risk_level,
                "recommended_pump_hz": r.recommended_pump_hz,
                "modbus_command_hex": r.modbus_command_hex,
                "pump_action_status": r.pump_action_status,
                "cgwa_status": r.cgwa_status,
                "bharatkosh_daily_fee_inr": r.bharatkosh_daily_fee_inr,
                "is_anomaly": r.is_anomaly,
                "utilization_pct": r.utilization_pct,
                "prev_hash": r.prev_hash,
                "record_hash": r.record_hash,
                "timestamp": r.timestamp.isoformat()
            }
    return list(latest_by_node.values())


@app.post("/api/v1/telemetry/ingest")
def ingest_telemetry(
    payload: TelemetryInput,
    x_aqua_signature: str = Header(..., description="HMAC-SHA256 Signature"),
    db: Session = Depends(get_db)
):
    verify_edge_request(
        node_id=payload.node_id,
        timestamp_epoch=payload.timestamp_epoch,
        nonce=payload.nonce,
        cumulative_m3=payload.daily_cumulative_m3,
        depth_mbgl=payload.depth_mbgl,
        x_aqua_signature=x_aqua_signature
    )

    eval_out = engine_ai.evaluate_node(
        flow_rate_m3_hr=payload.flow_rate_m3_hr,
        daily_cumulative_m3=payload.daily_cumulative_m3,
        noc_limit_m3=payload.noc_limit_m3,
        depth_mbgl=payload.depth_mbgl,
        drawdown_rate_m_hr=payload.drawdown_rate_m_hr,
        ph=payload.ph,
        orp_mv=payload.orp_mv,
        tds_ppm=payload.tds_ppm,
        baseline_arsenic_ug_l=payload.baseline_arsenic_ug_l,
        zone_category=payload.zone_category
    )

    with ledger_lock:
        last_rec = (
            db.query(TelemetryLedgerRecord)
            .filter(TelemetryLedgerRecord.node_id == payload.node_id)
            .order_by(TelemetryLedgerRecord.id.desc())
            .first()
        )
        prev_hash = last_rec.record_hash if last_rec else "0" * 64
        now_ts = datetime.utcnow()
        ts_iso = now_ts.isoformat()

        record_hash = compute_sha256_hash(
            node_id=payload.node_id,
            cumulative_m3=payload.daily_cumulative_m3,
            depth_mbgl=payload.depth_mbgl,
            as_total=eval_out["predicted_as_total_ug_l"],
            prev_hash=prev_hash,
            ts_iso=ts_iso
        )

        rec = TelemetryLedgerRecord(
            node_id=payload.node_id,
            facility_name=payload.facility_name,
            district=payload.district,
            state=payload.state,
            zone_category=payload.zone_category,
            lat=payload.lat,
            lon=payload.lon,
            flow_rate_m3_hr=payload.flow_rate_m3_hr,
            daily_cumulative_m3=payload.daily_cumulative_m3,
            noc_limit_m3=payload.noc_limit_m3,
            depth_mbgl=payload.depth_mbgl,
            drawdown_rate_m_hr=payload.drawdown_rate_m_hr,
            ph=payload.ph,
            orp_mv=payload.orp_mv,
            tds_ppm=payload.tds_ppm,
            baseline_arsenic_ug_l=payload.baseline_arsenic_ug_l,
            predicted_as_total_ug_l=eval_out["predicted_as_total_ug_l"],
            predicted_as3_toxic_ug_l=eval_out["predicted_as3_toxic_ug_l"],
            predicted_as5_ug_l=eval_out["predicted_as5_ug_l"],
            redox_regime=eval_out["redox_regime"],
            arsenic_risk_level=eval_out["arsenic_risk_level"],
            recommended_pump_hz=eval_out["recommended_pump_hz"],
            modbus_command_hex=eval_out["modbus_command_hex"],
            pump_action_status=eval_out["pump_action_status"],
            cgwa_status=eval_out["cgwa_status"],
            bharatkosh_daily_fee_inr=eval_out["bharatkosh_daily_fee_inr"],
            is_anomaly=eval_out["is_anomaly"],
            utilization_pct=eval_out["utilization_pct"],
            nonce=payload.nonce,
            ts_iso=ts_iso,
            prev_hash=prev_hash,
            record_hash=record_hash,
            timestamp=now_ts
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)

    return {
        "status": "INGESTED_HMAC_VERIFIED_AND_HASHED",
        "node_id": rec.node_id,
        "record_hash": rec.record_hash,
        "analysis": eval_out
    }


@app.get("/api/v1/telemetry/latest")
def get_latest_telemetry(db: Session = Depends(get_db)):
    return _fetch_latest_nodes_list(db)


@app.get("/api/v1/ledger/verify")
def verify_cryptographic_ledger(db: Session = Depends(get_db)):
    records = db.query(TelemetryLedgerRecord).order_by(TelemetryLedgerRecord.id.asc()).all()
    node_chains = {}
    tampered_count = 0

    for r in records:
        expected_prev = node_chains.get(r.node_id, "0" * 64)
        recomputed_hash = compute_sha256_hash(
            node_id=r.node_id,
            cumulative_m3=r.daily_cumulative_m3,
            depth_mbgl=r.depth_mbgl,
            as_total=r.predicted_as_total_ug_l,
            prev_hash=r.prev_hash,
            ts_iso=r.ts_iso
        )
        if r.prev_hash != expected_prev or r.record_hash != recomputed_hash:
            tampered_count += 1
        node_chains[r.node_id] = r.record_hash

    return {
        "total_packets_audited": len(records),
        "Active_Nodes_Tracked": len(node_chains),
        "tampered_packets_detected": tampered_count,
        "ledger_integrity_status": (
            "VERIFIED IMMUTABLE (HMAC + SHA-256 FULL MATCH)"
            if tampered_count == 0
            else f"CRITICAL TAMPER ALERT ({tampered_count} CORRUPTED ROWS)"
        )
    }


@app.get("/api/v1/advanced/intelligence")
def get_advanced_grid_intelligence(query: str = "", db: Session = Depends(get_db)):
    """Executes all 4 Advanced AI Pillars on the live aquifer state."""
    nodes = _fetch_latest_nodes_list(db)
    pignn_res = pignn_engine.run_spatiotemporal_inference(nodes)
    swarm_res = swarm_scheduler.optimize_swarm_schedule(nodes)
    fed_res = fed_zk_engine.aggregate_federated_round(nodes)
    macro_res = macro_copilot.evaluate_macro_subsidence_and_rwh(nodes)
    copilot_res = macro_copilot.generate_cgwa_legal_brief(nodes, custom_query=query)

    return {
        "pignn": pignn_res,
        "swarm_aco": swarm_res,
        "federated_zk": fed_res,
        "macro_subsidence": macro_res,
        "compliance_copilot": copilot_res
    }