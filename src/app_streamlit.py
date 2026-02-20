import os
import json
import streamlit as st
from pathlib import Path

from pipeline import EcosystemInput, run_pipeline


st.set_page_config(
    page_title="AI - MultiAgent Security Analyzer",
    layout="wide"
)

st.title("🔐  AI - MultiAgent Security Analyzer")
st.markdown("LangGraph + MCP MITRE + OpenAI Responses")

# ========================
# Sidebar - Config
# ========================

st.sidebar.header("⚙️ Configuración")

model = st.sidebar.text_input(
    "Modelo",
    value="gpt-4.1-mini"
)

mitre_url = st.sidebar.text_input(
    "MITRE MCP URL",
    value="http://localhost:8000/mcp"
)

    
if mitre_url:
    os.environ["MITRE_MCP_URL"] = mitre_url

os.environ["MODEL"] = model


# ========================
# Ecosystem Input
# ========================

st.header("📥 Ecosystem Input")

default_json = {
    "org_name": "Acme Retail",
    "industry": "Retail",
    "regions": ["AR"],
    "apps": [
        {"name": "Backoffice", "type": "web", "auth": "password", "exposed": True}
    ],
    "data": [
        {"name": "Customer PII", "sensitivity": "high"}
    ],
    "logging": {"siem": "none", "retention_days": 30},
    "security_controls": [
        {"name": "MFA", "coverage": "partial"}
    ]
}

input_text = st.text_area(
    "Ecosystem JSON",
    value=json.dumps(default_json, indent=4),
    height=350
)

col1, col2 = st.columns([1, 1])

run_clicked = col1.button("🚀 Ejecutar Análisis")
clear_clicked = col2.button("🧹 Limpiar Resultado")


# ========================
# Run Pipeline
# ========================

if clear_clicked:
    st.experimental_rerun()

if run_clicked:
    try:
        ecosystem_dict = json.loads(input_text)
        ecosystem = EcosystemInput.model_validate(ecosystem_dict)

        with st.spinner("Ejecutando agentes..."):
            result = run_pipeline(ecosystem)

        st.success(f"✅ Sesión: {result.session_id}")

        # ========================
        # Tabs
        # ========================
        tab1, tab2, tab3, tab4 = st.tabs(
            ["🔎 Detectores", "🎯 MITRE Mapping", "📄 Reporte", "🧭 Trazabilidad"]
        )

        # ========================
        # Tab 1 - Analyzer
        # ========================
        with tab1:
            if result.analyzer:
                for det in result.analyzer.detectors:
                    with st.expander(f"{det.name} ({det.risk_level})"):
                        st.markdown(f"**Descripción:** {det.description}")
                        st.markdown(f"**Rationale:** {det.rationale}")
                        st.markdown("**Evidencia DBIR:**")
                        for ev in det.dbir_evidence:
                            st.markdown(f"- {ev}")
            else:
                st.warning("No se generaron detectores.")

        # ========================
        # Tab 2 - Classifier
        # ========================
        with tab2:
            if result.classifier:
                for m in result.classifier.mappings:
                    with st.expander(f"{m.detector_name} | Priority: {m.priority}"):
                        st.markdown(f"**Impact:** {m.impact}")
                        st.markdown(f"**Confidence:** {m.confidence:.2f}")

                        if m.techniques:
                            st.markdown("### Técnicas MITRE")
                            for t in m.techniques:
                                st.markdown(f"- {t.id} - {t.name} ({t.tactic})")
                        else:
                            st.warning("Sin técnicas mapeadas.")
            else:
                st.warning("No se generó mapeo MITRE.")

        # ========================
        # Tab 3 - Report
        # ========================
        with tab3:
            if result.reporter:
                st.markdown(result.reporter.report_md)
            else:
                st.warning("No se generó reporte.")

        # ========================
        # Tab 4 - Trace
        # ========================
        with tab4:
            st.json(result.events)

    except Exception as e:
        st.error(f"Error: {e}")
