import math
import numpy as np
from sklearn.ensemble import IsolationForest
import requests


class HydroGeochemEngine:
    def __init__(self):
        rng = np.random.RandomState(42)
        normal_operational_data = np.column_stack([
            rng.normal(loc=6.0, scale=2.0, size=600),    # Flow rate (m3/hr)
            rng.normal(loc=28.0, scale=5.0, size=600),   # Depth (mbgl)
            rng.normal(loc=0.15, scale=0.08, size=600),  # Drawdown velocity (m/hr)
            rng.normal(loc=380.0, scale=60.0, size=600)  # TDS (ppm)
        ])
        self.anomaly_detector = IsolationForest(contamination=0.06, random_state=42)
        self.anomaly_detector.fit(normal_operational_data)

    @staticmethod
    def _generate_modbus_rtu_frame(slave_id: int, target_hz: float) -> str:
        freq_centi_hz = int(round(target_hz * 100))
        frame_bytes = [
            slave_id & 0xFF,
            0x06,
            0x20, 0x00,
            (freq_centi_hz >> 8) & 0xFF,
            freq_centi_hz & 0xFF
        ]
        crc = 0xFFFF
        for b in frame_bytes:
            crc ^= b
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        frame_bytes.append(crc & 0xFF)
        frame_bytes.append((crc >> 8) & 0xFF)
        return " ".join(f"{b:02X}" for b in frame_bytes)

    @staticmethod
    def _validate_sensor_plausibility(flow: float, depth: float, ph: float, orp: float, tds: float) -> tuple[bool, str]:
        """Industrial SCADA Fail-Safe: Detects broken 4-20mA / RS485 sensor wires before actuating pumps."""
        if not (0.0 <= flow <= 250.0):
            return False, "SENSOR FAULT: Flow meter out of physical bounds"
        if not (1.0 <= depth <= 250.0):
            return False, "SENSOR FAULT: Piezometer depth transducer open-circuit"
        if not (3.5 <= ph <= 11.5):
            return False, "SENSOR FAULT: pH glass electrode drift/breakage"
        if not (-600.0 <= orp <= 800.0):
            return False, "SENSOR FAULT: ORP platinum electrode out of bounds"
        if not (10.0 <= tds <= 15000.0):
            return False, "SENSOR FAULT: Conductivity/TDS short-circuit"
        return True, "SENSORS_HEALTHY"

    def evaluate_node(
        self,
        flow_rate_m3_hr: float,
        daily_cumulative_m3: float,
        noc_limit_m3: float,
        depth_mbgl: float,
        drawdown_rate_m_hr: float,
        ph: float,
        orp_mv: float,
        tds_ppm: float,
        baseline_arsenic_ug_l: float,
        zone_category: str
    ) -> dict:
        # 0. Hardware Sensor Plausibility Check (Fail-Safe Guardrail)
        sensors_ok, fault_msg = self._validate_sensor_plausibility(
            flow_rate_m3_hr, depth_mbgl, ph, orp_mv, tds_ppm
        )
        if not sensors_ok:
            # Fail-Safe Mode: Hold pump at safe 35 Hz minimum pressure to prevent water-hammer
            safe_hz = 35.0
            return {
                "is_anomaly": True,
                "predicted_as_total_ug_l": baseline_arsenic_ug_l,
                "predicted_as3_toxic_ug_l": round(baseline_arsenic_ug_l * 0.5, 2),
                "predicted_as5_ug_l": round(baseline_arsenic_ug_l * 0.5, 2),
                "redox_regime": fault_msg,
                "arsenic_risk_level": "HARDWARE SENSOR FAULT (FAIL-SAFE HOLD)",
                "recommended_pump_hz": safe_hz,
                "modbus_command_hex": self._generate_modbus_rtu_frame(1, safe_hz),
                "pump_action_status": f"FAIL-SAFE HOLD ({safe_hz} Hz) - {fault_msg}",
                "cgwa_status": "TELEMETRY MAINTENANCE REQUIRED",
                "bharatkosh_daily_fee_inr": 0.0,
                "utilization_pct": round((daily_cumulative_m3 / max(noc_limit_m3, 1.0)) * 100.0, 1)
            }

        # 1. ML Isolation Forest Anomaly Detection
        features = np.array([[flow_rate_m3_hr, depth_mbgl, drawdown_rate_m_hr, tds_ppm]])
        is_anomaly = bool(self.anomaly_detector.predict(features)[0] == -1)

        # 2. Physics-Informed Soft-Sensor: Arsenic Mobilization & As(III)/As(V) Speciation
        eh_volts = (orp_mv + 200.0) / 1000.0
        drawdown_stress = max(0.0, (depth_mbgl - 18.0) / 30.0) + (max(0.0, drawdown_rate_m_hr - 0.20) * 1.8)
        ph_desorption_boost = 1.35 if (ph > 7.8 or ph < 6.4) else 1.0
        overdraft_ratio = daily_cumulative_m3 / max(noc_limit_m3, 1.0)

        predicted_as_total = baseline_arsenic_ug_l * (
            1.0 + (drawdown_stress * 0.75 * ph_desorption_boost * max(1.0, overdraft_ratio))
        )
        predicted_as_total = round(min(predicted_as_total, 450.0), 2)

        pe = eh_volts / 0.05916
        log_as3_as5_ratio = 19.5 - (2.0 * pe) - (2.0 * ph)
        clamped_log = max(-6.0, min(6.0, log_as3_as5_ratio))
        ratio_as3_to_as5 = math.pow(10.0, clamped_log)
        as3_fraction = ratio_as3_to_as5 / (1.0 + ratio_as3_to_as5)

        predicted_as3 = round(predicted_as_total * as3_fraction, 2)
        predicted_as5 = round(predicted_as_total - predicted_as3, 2)

        if orp_mv < -50.0:
            redox_regime = "REDUCING ANOXIC (Fe-Oxyhydroxide Dissolution -> High As3+)"
        elif drawdown_rate_m_hr > 0.35:
            redox_regime = "RAPID DRAWDOWN O2 INCURSION (Sulfide Oxidation Surge)"
        else:
            redox_regime = "SUB-OXIC EQUILIBRIUM"

        if predicted_as_total >= 50.0 or predicted_as3 >= 25.0:
            arsenic_risk_level = "CRITICAL BIO-HAZARD (As3+ Surge)"
        elif predicted_as_total > 10.0:
            arsenic_risk_level = "ELEVATED (>10 µg/L WHO Limit)"
        else:
            arsenic_risk_level = "SAFE (<10 µg/L)"

        # 3. Closed-Loop VFD Pump Governor with Anti-Water-Hammer Ramp Protection
        utilization_pct = round((daily_cumulative_m3 / max(noc_limit_m3, 1.0)) * 100.0, 1)

        if utilization_pct >= 105.0 or predicted_as_total >= 65.0:
            # Soft-landing ramp command (20 Hz minimum cooling/seal flow before staged shutoff)
            recommended_hz = 20.0
            pump_action = "CRITICAL INTERLOCK: SOFT-RAMP TO 20 Hz (Preventing Hydraulic Water Hammer)"
        elif drawdown_rate_m_hr > 0.30 or predicted_as_total > 15.0 or utilization_pct > 85.0:
            throttle_factor = max(0.56, 1.0 - (drawdown_stress * 0.25))
            recommended_hz = round(50.0 * throttle_factor, 1)
            pump_action = f"ACTIVE THROTTLE: VFD REDUCED TO {recommended_hz} Hz (Stabilizing Cone of Depression)"
        else:
            recommended_hz = 50.0
            pump_action = "NOMINAL OPERATION (50.0 Hz Full Speed)"

        modbus_hex = self._generate_modbus_rtu_frame(slave_id=1, target_hz=recommended_hz)

        # 4. CGWA BhuNeer Compliance & Bharatkosh Fee Calculation
        rate_map = {"Safe": 1.0, "Semi-Critical": 2.0, "Critical": 4.0, "Over-Exploited": 8.0}
        base_rate_inr = rate_map.get(zone_category, 2.0)

        if daily_cumulative_m3 > noc_limit_m3:
            cgwa_status = "VIOLATION: NOC CAP EXCEEDED (+₹10,000/day Environmental Penalty Risk)"
            excess_m3 = daily_cumulative_m3 - noc_limit_m3
            daily_fee = (noc_limit_m3 * base_rate_inr) + (excess_m3 * base_rate_inr * 2.5)
        elif utilization_pct > 85.0:
            cgwa_status = "WARNING: >85% DAILY KLD QUOTA CONSUMED"
            daily_fee = daily_cumulative_m3 * base_rate_inr
        else:
            cgwa_status = "COMPLIANT (BhuNeer Sync Ready)"
            daily_fee = daily_cumulative_m3 * base_rate_inr

        return {
            "is_anomaly": is_anomaly,
            "predicted_as_total_ug_l": predicted_as_total,
            "predicted_as3_toxic_ug_l": predicted_as3,
            "predicted_as5_ug_l": predicted_as5,
            "redox_regime": redox_regime,
            "arsenic_risk_level": arsenic_risk_level,
            "recommended_pump_hz": recommended_hz,
            "modbus_command_hex": modbus_hex,
            "pump_action_status": pump_action,
            "cgwa_status": cgwa_status,
            "bharatkosh_daily_fee_inr": round(daily_fee, 2),
            "utilization_pct": utilization_pct
        }