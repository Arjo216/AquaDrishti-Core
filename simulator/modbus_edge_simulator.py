import os
import json
import time
import uuid
import random
import requests
from backend.security import generate_hmac_signature

API_ENDPOINT = "http://127.0.0.1:8000/api/v1/telemetry/ingest"
SPOOL_FILE = "edge_outbox_spool.jsonl"

NODES = [
    {
        "node_id": "WB-HGL-SER-01",
        "facility_name": "Serampore Textile & Yarn Dyeing Works",
        "district": "Hooghly",
        "state": "West Bengal",
        "zone_category": "Semi-Critical",
        "lat": 22.7520,
        "lon": 88.3420,
        "noc_limit_m3": 90.0,
        "base_depth": 27.5,
        "base_as": 16.0,
        "base_orp": -35.0
    },
    {
        "node_id": "WB-N24-BKP-02",
        "facility_name": "Barrackpore Beverage & Cold-Chain Park",
        "district": "North 24 Parganas",
        "state": "West Bengal",
        "zone_category": "Critical",
        "lat": 22.7674,
        "lon": 88.3883,
        "noc_limit_m3": 120.0,
        "base_depth": 33.0,
        "base_as": 36.0,
        "base_orp": -85.0
    },
    {
        "node_id": "WB-NAD-CHK-03",
        "facility_name": "Chakdaha Municipal AIRP & Rural Grid",
        "district": "Nadia",
        "state": "West Bengal",
        "zone_category": "Critical",
        "lat": 23.0800,
        "lon": 88.5200,
        "noc_limit_m3": 160.0,
        "base_depth": 38.5,
        "base_as": 58.0,
        "base_orp": -115.0
    },
    {
        "node_id": "WB-MLD-KLC-04",
        "facility_name": "Kaliachak Agro-Processing & Food Cluster",
        "district": "Malda",
        "state": "West Bengal",
        "zone_category": "Critical",
        "lat": 24.8667,
        "lon": 88.0167,
        "noc_limit_m3": 110.0,
        "base_depth": 35.0,
        "base_as": 64.0,
        "base_orp": -130.0
    },
    {
        "node_id": "WB-PMD-HLD-05",
        "facility_name": "Haldia Petrochemical Polymer Utility",
        "district": "Purba Medinipur",
        "state": "West Bengal",
        "zone_category": "Semi-Critical",
        "lat": 22.0667,
        "lon": 88.0698,
        "noc_limit_m3": 260.0,
        "base_depth": 42.0,
        "base_as": 7.5,
        "base_orp": 45.0
    },
    {
        "node_id": "PB-LDH-IND-06",
        "facility_name": "Ludhiana Electroplating & Alloy Hub",
        "district": "Ludhiana",
        "state": "Punjab",
        "zone_category": "Over-Exploited",
        "lat": 30.9010,
        "lon": 75.8573,
        "noc_limit_m3": 180.0,
        "base_depth": 58.0,
        "base_as": 12.5,
        "base_orp": 20.0
    }
]


def spool_packet_offline(payload: dict):
    """Saves telemetry packet to local non-volatile disk if cellular/cloud network drops."""
    with open(SPOOL_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")
    print(f"⚠️ [STORE-AND-FORWARD] Network unreachable. Packet spooled to {SPOOL_FILE}")


def flush_offline_spool():
    """Flushes any buffered offline packets with freshly signed timestamps upon reconnection."""
    if not os.path.exists(SPOOL_FILE):
        return
    with open(SPOOL_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    if not lines:
        return

    print(f"🔄 Reconnected! Flushing {len(lines)} buffered packets from local outbox...")
    remaining = []
    for line in lines:
        pkt = json.loads(line)
        pkt["timestamp_epoch"] = int(time.time())
        pkt["nonce"] = uuid.uuid4().hex
        sig = generate_hmac_signature(
            pkt["node_id"], pkt["timestamp_epoch"], pkt["nonce"],
            pkt["daily_cumulative_m3"], pkt["depth_mbgl"]
        )
        try:
            r = requests.post(API_ENDPOINT, json=pkt, headers={"X-Aqua-Signature": sig}, timeout=4)
            if r.status_code != 200:
                remaining.append(line)
        except Exception:
            remaining.append(line)

    if remaining:
        with open(SPOOL_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(remaining) + "\n")
    else:
        os.remove(SPOOL_FILE)
        print("✅ All buffered offline telemetry packets synced to cloud ledger!")


def stream_telemetry(batches: int = 5):
    print("🔐 Starting Zero-Trust HMAC-Signed Modbus-RTU Edge Simulator...")
    for b in range(batches):
        flush_offline_spool()
        print(f"\n--- Ingesting Signed Telemetry Batch {b + 1}/{batches} ---")
        for node in NODES:
            surge = random.random() < 0.30
            flow = round(random.uniform(4.2, 10.5) if not surge else random.uniform(13.5, 21.0), 2)
            cum_m3 = round(node["noc_limit_m3"] * random.uniform(0.68, 1.16), 2)
            depth = round(node["base_depth"] + random.uniform(-1.0, 4.8), 2)
            drawdown_rate = round(random.uniform(0.08, 0.25) if not surge else random.uniform(0.32, 0.65), 2)
            ph = round(random.uniform(6.6, 8.1), 2)
            orp = round(node["base_orp"] + random.uniform(-25.0, 25.0), 1)
            tds = round(random.uniform(310.0, 640.0), 1)

            ts_epoch = int(time.time())
            nonce = uuid.uuid4().hex

            payload = {
                "node_id": node["node_id"],
                "facility_name": node["facility_name"],
                "district": node["district"],
                "state": node["state"],
                "zone_category": node["zone_category"],
                "lat": node["lat"],
                "lon": node["lon"],
                "flow_rate_m3_hr": flow,
                "daily_cumulative_m3": cum_m3,
                "noc_limit_m3": node["noc_limit_m3"],
                "depth_mbgl": depth,
                "drawdown_rate_m_hr": drawdown_rate,
                "ph": ph,
                "orp_mv": orp,
                "tds_ppm": tds,
                "baseline_arsenic_ug_l": node["base_as"],
                "timestamp_epoch": ts_epoch,
                "nonce": nonce
            }

            signature = generate_hmac_signature(
                node_id=node["node_id"],
                timestamp_epoch=ts_epoch,
                nonce=nonce,
                cumulative_m3=cum_m3,
                depth_mbgl=depth
            )

            try:
                res = requests.post(
                    API_ENDPOINT,
                    json=payload,
                    headers={"X-Aqua-Signature": signature},
                    timeout=5
                )
                if res.status_code == 200:
                    body = res.json()
                    ans = body["analysis"]
                    print(
                        f"✅ [{node['node_id']}] HMAC:OK | As(Total): {ans['predicted_as_total_ug_l']} µg/L "
                        f"(As3+: {ans['predicted_as3_toxic_ug_l']} µg/L) | "
                        f"VFD: {ans['recommended_pump_hz']} Hz | SHA256: {body['record_hash'][:10]}..."
                    )
                else:
                    print(f"🚨 Security Reject ({res.status_code}): {res.text}")
            except Exception:
                spool_packet_offline(payload)
        time.sleep(1.5)


if __name__ == "__main__":
    stream_telemetry(batches=5)