import os
import time
import hmac
import hashlib
from collections import deque
from fastapi import Header, HTTPException

# In production, set AQUA_EDGE_SECRET in Codespaces Secrets / .env
EDGE_SHARED_SECRET = os.getenv("AQUA_EDGE_SECRET", "aquasentinel_zero_trust_hmac_key_2026")
MAX_TIMESTAMP_DRIFT_SECONDS = 120

# Bounded in-memory ring buffer of seen nonces to block replay attacks
SEEN_NONCES = deque(maxlen=5000)


def generate_hmac_signature(node_id: str, timestamp_epoch: int, nonce: str, cumulative_m3: float, depth_mbgl: float) -> str:
    """Computes a deterministic HMAC-SHA256 signature over critical telemetry parameters."""
    canonical_msg = f"{node_id}:{timestamp_epoch}:{nonce}:{cumulative_m3:.3f}:{depth_mbgl:.2f}"
    return hmac.new(
        EDGE_SHARED_SECRET.encode("utf-8"),
        canonical_msg.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def verify_edge_request(
    node_id: str,
    timestamp_epoch: int,
    nonce: str,
    cumulative_m3: float,
    depth_mbgl: float,
    x_aqua_signature: str = Header(..., description="HMAC-SHA256 Edge Signature")
) -> bool:
    # 1. Check Timestamp Freshness (Blocks delayed replay attacks)
    current_epoch = int(time.time())
    if abs(current_epoch - timestamp_epoch) > MAX_TIMESTAMP_DRIFT_SECONDS:
        raise HTTPException(
            status_code=401,
            detail="SECURITY_REJECT: Telemetry timestamp outside 120s anti-replay window."
        )

    # 2. Check Nonce Uniqueness (Blocks immediate duplicate packet replay)
    if nonce in SEEN_NONCES:
        raise HTTPException(
            status_code=409,
            detail="SECURITY_REJECT: Duplicate cryptographic nonce detected (Replay Attack Blocked)."
        )

    # 3. Constant-Time HMAC-SHA256 Signature Verification
    expected_sig = generate_hmac_signature(node_id, timestamp_epoch, nonce, cumulative_m3, depth_mbgl)
    if not hmac.compare_digest(expected_sig, x_aqua_signature):
        raise HTTPException(
            status_code=403,
            detail="SECURITY_REJECT: Invalid HMAC-SHA256 Edge Signature (Untrusted Hardware)."
        )

    SEEN_NONCES.append(nonce)
    return True