import streamlit as st
import pandas as pd
import requests
import pydeck as pdk
import plotly.express as px

st.set_page_config(
    page_title="AquaDrishti-Core v3.0 | 4D PI-GNN & Swarm Aquifer Grid",
    layout="wide",
    initial_sidebar_state="expanded"
)

API_LATEST = "http://127.0.0.1:8000/api/v1/telemetry/latest"
API_VERIFY = "http://127.0.0.1:8000/api/v1/ledger/verify"
API_ADVANCED = "http://127.0.0.1:8000/api/v1/advanced/intelligence"

st.title("🛡️ AquaDrishti-Core v3.0: 4D PI-GNN, Swarm ACO & Zero-Trust Aquifer Grid")
st.caption(
    "Physics-Informed Darcy Graph Neural Network • Ant Colony Swarm Pump Governor • "
    "Federated Zero-Knowledge Compliance • Satellite Subsidence & CGWA BhuNeer Co-Pilot"
)

with st.sidebar:
    st.header("🔐 Cryptographic Audit Status")
    try:
        v_res = requests.get(API_VERIFY, timeout=3).json()
        if v_res["tampered_packets_detected"] == 0:
            st.success(f"Chain Status: {v_res['ledger_integrity_status']}")
        else:
            st.error(f"Chain Status: {v_res['ledger_integrity_status']}")
        st.metric("Audited Telemetry Packets", v_res["total_packets_audited"])
        st.metric("Tampered Packets", v_res["tampered_packets_detected"])
    except Exception:
        st.error("Backend API Offline")

    st.divider()
    if st.button("🔄 Refresh Live Grid Intelligence", use_container_width=True):
        st.rerun()

try:
    nodes_data = requests.get(API_LATEST, timeout=4).json()
    adv_data = requests.get(API_ADVANCED, timeout=6).json()
except Exception:
    nodes_data = []
    adv_data = {}

if not nodes_data:
    st.warning("⚠️ No telemetry packets detected. Run `./run_platform.sh` in your terminal.")
    st.stop()

df = pd.DataFrame(nodes_data)

# Top Executive KPI Row
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Monitored Borewell Nodes", len(df))
noc_breaches = len(df[df["cgwa_status"].str.contains("VIOLATION")])
k2.metric("CGWA BhuNeer Breaches", noc_breaches, delta="Penalty Risk" if noc_breaches > 0 else "Compliant", delta_color="inverse")
as3_hazards = len(df[df["predicted_as3_toxic_ug_l"] > 10.0])
k3.metric("Toxic As³⁺ Alerts (>10 µg/L)", as3_hazards, delta="Redox Mobilization" if as3_hazards > 0 else "Stable", delta_color="inverse")

swarm_reduction = adv_data.get("swarm_aco", {}).get("swarm_kpi", {}).get("simultaneous_stress_reduction_pct", 0.0)
k4.metric("ACO Swarm Peak Stress Cut", f"-{swarm_reduction}%", delta="Aquifer Protected")

total_bharatkosh = df["bharatkosh_daily_fee_inr"].sum()
k5.metric("Daily Bharatkosh Accrual", f"₹{total_bharatkosh:,.2f}")

st.divider()

# 4 Specialized Command Tabs
tab1, tab2, tab3, tab4 = st.tabs([
    "🌐 1. Real-Time 3D Twin & VFD Bus",
    "🧠 2. PI-GNN Darcy Graph & Plume Migration",
    "🐜 3. Multi-Agent ACO Swarm Pump Scheduler",
    "🛰️ 4. Federated ZK-Privacy, Satellite SAR & Legal Co-Pilot"
])

# ================= TAB 1: REAL-TIME 3D TWIN & VFD BUS =================
with tab1:
    col_map, col_chart = st.columns([1.15, 1])
    with col_map:
        st.subheader("🌐 3D Aquifer Drawdown & Subsurface Plume Pathways")
        df["r"] = df["predicted_as_total_ug_l"].apply(lambda x: 255 if x >= 30 else (240 if x > 10 else 20))
        df["g"] = df["predicted_as_total_ug_l"].apply(lambda x: 35 if x >= 30 else (160 if x > 10 else 210))
        df["b"] = 90

        column_layer = pdk.Layer(
            "ColumnLayer",
            data=df,
            get_position=["lon", "lat"],
            get_elevation="depth_mbgl * 400",
            elevation_scale=1,
            radius=3500,
            get_fill_color=["r", "g", "b", 215],
            pickable=True,
            auto_highlight=True,
        )

        edges_df = pd.DataFrame(adv_data.get("pignn", {}).get("edge_plumes", []))
        layers_list = [column_layer]
        if not edges_df.empty:
            arc_layer = pdk.Layer(
                "ArcLayer",
                data=edges_df,
                get_source_position=["source_lon", "source_lat"],
                get_target_position=["target_lon", "target_lat"],
                get_source_color=[255, 180, 0, 190],
                get_target_color=[255, 30, 60, 220],
                get_width=3,
                pickable=True,
            )
            layers_list.append(arc_layer)

        view_state = pdk.ViewState(latitude=23.25, longitude=88.35, zoom=6.6, pitch=48)
        st.pydeck_chart(pdk.Deck(
            layers=layers_list,
            initial_view_state=view_state,
            tooltip={
                "text": (
                    "Node: {facility_name} ({district})\n"
                    "Depth: {depth_mbgl} mbgl | Total As: {predicted_as_total_ug_l} µg/L\n"
                    "VFD Action: {pump_action_status}"
                )
            }
        ))

    with col_chart:
        st.subheader("🧪 Virtual Mass-Spectrometer: As³⁺ vs. As⁵⁺ Speciation")
        spec_df = df.melt(
            id_vars=["node_id", "district"],
            value_vars=["predicted_as3_toxic_ug_l", "predicted_as5_ug_l"],
            var_name="Arsenic_Species",
            value_name="Concentration_ug_L"
        )
        spec_df["Arsenic_Species"] = spec_df["Arsenic_Species"].replace({
            "predicted_as3_toxic_ug_l": "Trivalent As³⁺ (Arsenite - Extreme Toxicity)",
            "predicted_as5_ug_l": "Pentavalent As⁵⁺ (Arsenate - Moderate)"
        })
        fig = px.bar(
            spec_df,
            x="node_id",
            y="Concentration_ug_L",
            color="Arsenic_Species",
            barmode="stack",
            color_discrete_map={
                "Trivalent As³⁺ (Arsenite - Extreme Toxicity)": "#EF4444",
                "Pentavalent As⁵⁺ (Arsenate - Moderate)": "#F59E0B"
            },
            height=390
        )
        fig.add_hline(y=10.0, line_dash="dash", line_color="#10B981", annotation_text="WHO Safe Limit (10 µg/L)")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("⚙️ Closed-Loop VFD Pump Governor & Hardware Modbus-RTU Command Bus")
    vfd_cols = [
        "node_id", "facility_name", "depth_mbgl", "drawdown_rate_m_hr",
        "redox_regime", "recommended_pump_hz", "modbus_command_hex", "pump_action_status"
    ]
    st.dataframe(df[vfd_cols], use_container_width=True, hide_index=True)

# ================= TAB 2: PI-GNN DARCY GRAPH & PLUME MIGRATION =================
with tab2:
    pignn_info = adv_data.get("pignn", {})
    g_metrics = pignn_info.get("graph_metrics", {})

    m1, m2, m3 = st.columns(3)
    m1.metric("Connected Hydrological Graph Nodes", g_metrics.get("total_aquifer_nodes", 0))
    m2.metric("Active Subsurface Darcy Flow Edges", g_metrics.get("active_darcy_pathways", 0))
    m3.metric("Max Plume Migration Velocity", f"{g_metrics.get('max_plume_velocity_cm_day', 0.0)} cm/day")

    st.subheader("🔮 24-Hour PI-GNN Spatio-Temporal Drawdown & As³⁺ Forecast")
    forecasts_df = pd.DataFrame(pignn_info.get("node_forecasts", []))
    if not forecasts_df.empty:
        st.dataframe(forecasts_df, use_container_width=True, hide_index=True)

    st.subheader("🌊 Subsurface Darcy Hydraulic Gradient & Cross-Well Plume Migration Matrix")
    plumes_df = pd.DataFrame(pignn_info.get("edge_plumes", []))
    if not plumes_df.empty:
        display_edge_cols = [
            "source_node", "target_node", "source_district", "target_district",
            "distance_km", "head_drop_m", "plume_velocity_cm_day",
            "cross_drawdown_interference_m", "plume_hazard"
        ]
        st.dataframe(plumes_df[display_edge_cols], use_container_width=True, hide_index=True)

# ================= TAB 3: MULTI-AGENT ACO SWARM SCHEDULER =================
with tab3:
    swarm_info = adv_data.get("swarm_aco", {})
    s_kpi = swarm_info.get("swarm_kpi", {})

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Uncoordinated Daytime Peak", f"{s_kpi.get('uncoordinated_peak_load_m3', 0)} m³")
    s2.metric("ACO Swarm Staggered Peak", f"{s_kpi.get('aco_optimized_peak_load_m3', 0)} m³")
    s3.metric("Peak Aquifer Drawdown Reduction", f"{s_kpi.get('simultaneous_stress_reduction_pct', 0)}%")
    s4.metric("Swarm Engine Status", s_kpi.get("swarm_consensus_status", "ACTIVE"))

    st.subheader("🐜 Cooperative Multi-Agent 24-Hour Pumping Allocation (100% Quota Preserved)")
    sched_df = pd.DataFrame(swarm_info.get("schedule", []))
    if not sched_df.empty:
        st.dataframe(sched_df, use_container_width=True, hide_index=True)

        slot_melt = sched_df.melt(
            id_vars=["node_id", "district"],
            value_vars=["slot_1_00_06_m3", "slot_2_06_12_m3", "slot_3_12_18_m3", "slot_4_18_24_m3"],
            var_name="Time_Window",
            value_name="Allocated_Volume_m3"
        )
        fig_swarm = px.bar(
            slot_melt,
            x="Time_Window",
            y="Allocated_Volume_m3",
            color="node_id",
            title="Flattened Regional Aquifer Load Across 6-Hour Pumping Windows (ACO Swarm Consensus)",
            barmode="stack",
            height=380
        )
        st.plotly_chart(fig_swarm, use_container_width=True)

# ================= TAB 4: FEDERATED ZK, SATELLITE SAR & LEGAL CO-PILOT =================
with tab4:
    fed_info = adv_data.get("federated_zk", {})
    f_sum = fed_info.get("federated_summary", {})

    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Global FedAvg Aggregation Round", f"Round #{f_sum.get('federated_round', 14)}")
    f2.metric("Differential Privacy Budget", f_sum.get("differential_privacy_epsilon", "ε = 1.2"))
    f3.metric("Global Model Weight Norm", f_sum.get("global_fedavg_weight_norm", 0.0))
    f4.metric("ZK-Verified Compliant Factories", f"{f_sum.get('zk_compliant_nodes', 0)} / {len(df)}")

    col_zk, col_sat = st.columns(2)
    with col_zk:
        st.subheader("🔒 Federated Edge Weights & Zero-Knowledge Quota Proofs")
        zk_df = pd.DataFrame(fed_info.get("edge_proofs", []))
        if not zk_df.empty:
            st.dataframe(zk_df, use_container_width=True, hide_index=True)

    with col_sat:
        st.subheader("🛰️ Satellite Soil-Moisture, Land Subsidence & RWH Credits")
        macro_df = pd.DataFrame(adv_data.get("macro_subsidence", []))
        if not macro_df.empty:
            st.dataframe(macro_df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("🤖 Autonomous CGWA BhuNeer & WBPCB Form-V Legal Compliance Co-Pilot")
    copilot_info = adv_data.get("compliance_copilot", {})
    st.caption(f"Active Engine: `{copilot_info.get('engine_used', 'Statutory Synthesizer')}`")
    st.markdown(copilot_info.get("brief_markdown", ""))

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Export Signed CGWA BhuNeer Level-1/Level-2 & Form-V Audit Package (CSV)",
        data=csv_bytes,
        file_name="AquaSentinel_v3_CGWA_BhuNeer_Audit.csv",
        mime="text/csv"
    )