
from __future__ import annotations

import argparse
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError, field_validator

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser

from langgraph.graph import StateGraph, END
from langgraph.types import RetryPolicy
from langgraph.checkpoint.memory import MemorySaver

# =========================
# 1) Schemas (contracts)
# =========================

RiskLevel = Literal["High", "Medium", "Low"]


class EcosystemInput(BaseModel):
    """Minimal template. Extend freely for your challenge."""
    org_name: str
    industry: str
    regions: List[str] = Field(default_factory=list)

    apps: List[Dict[str, Any]] = Field(default_factory=list)       # e.g., {"name": "...", "type": "web", "auth": "..."}
    data: List[Dict[str, Any]] = Field(default_factory=list)       # e.g., {"name": "...", "sensitivity": "high"}
    logging: Dict[str, Any] = Field(default_factory=dict)          # e.g., {"siem": "splunk", "retention_days": 90}
    security_controls: List[Dict[str, Any]] = Field(default_factory=list)  # e.g., {"name": "MFA", "coverage": "partial"}

    @field_validator("org_name", "industry")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field must be non-empty")
        return v


class Detector(BaseModel):
    name: str
    description: str
    rationale: str
    dbir_evidence: List[str] = Field(default_factory=list)  # store excerpts / references
    risk_level: RiskLevel
    likelihood: RiskLevel


class AnalyzerOutput(BaseModel):
    detectors: List[Detector] = Field(max_length=5)

    @field_validator("detectors")
    @classmethod
    def _max_5(cls, v: List[Detector]) -> List[Detector]:
        return v[:5]


class MitreTechnique(BaseModel):
    id: str
    name: str
    tactic: Optional[str] = None


class DetectorMitreMapping(BaseModel):
    detector_name: str
    techniques: List[MitreTechnique] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    impact: RiskLevel
    priority: int = Field(ge=1, le=100)


class ClassifierOutput(BaseModel):
    mappings: List[DetectorMitreMapping]


class ReporterOutput(BaseModel):
    report_md: str


# =========================
# 2) LangGraph State
# =========================

class GraphState(BaseModel):
    session_id: str
    ecosystem: EcosystemInput

    analyzer: Optional[AnalyzerOutput] = None
    classifier: Optional[ClassifierOutput] = None
    reporter: Optional[ReporterOutput] = None

    # validation / control
    last_error: Optional[str] = None
    repair_count: int = 0
    max_repairs: int = 2
    validation_route: Optional[str] = None

    # traces
    events: List[Dict[str, Any]] = Field(default_factory=list)


# =========================
# 3) Utilities: logging & persistence
# =========================

def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def log_event(state: GraphState, stage: str, payload: Dict[str, Any]) -> GraphState:
    state.events.append({"ts": now_iso(), "stage": stage, **payload})
    return state


def ensure_run_dir(out_dir: Path, session_id: str) -> Path:
    run_dir = out_dir / session_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_json(run_dir: Path, name: str, obj: Any) -> None:
    (run_dir / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def write_text(run_dir: Path, name: str, text: str) -> None:
    (run_dir / name).write_text(text, encoding="utf-8")


# =========================
# 4) LLM: OpenAI Responses via ChatOpenAI
# =========================
# LangChain will route to Responses API when use_responses_api=True. :contentReference[oaicite:0]{index=0}

def make_llm() -> ChatOpenAI:
    model = os.getenv("MODEL", "gpt-4.1-mini")
    return ChatOpenAI(
        model=model,
        temperature=0.2,
        use_responses_api=True,
        # use_previous_response_id=True,  # optional: if you manage state via previous_response_id
    )


# =========================
# 5) MCP (MITRE) hookup
# =========================
# Two options:
# A) OpenAI "remote MCP" tool through bind_tools (lowest code) :contentReference[oaicite:1]{index=1}
# B) LangChain MCP Adapters (if you run local stdio servers, multi-server, interceptors) :contentReference[oaicite:2]{index=2}
#
# This baseline uses A) to keep code minimal.
#
# You must provide your MITRE MCP server URL (SSE endpoint) via env:
#   export MITRE_MCP_URL="http://mitre-mcp:3000/sse"   (example)
#
# NOTE: The exact URL path depends on the MCP server you choose.

def bind_mitre_mcp(llm: ChatOpenAI) -> ChatOpenAI:
    mitre_url = os.getenv("MITRE_MCP_URL", "").strip()
    if not mitre_url:
        # Let the graph run but classifier will fail fast with a clear error.
        return llm

    return llm.bind_tools(
        [
            {
                "type": "mcp",
                "server_label": "mitre_attack",
                "server_url": mitre_url,
                "require_approval": "never",
            }
        ]
    )


# =========================
# 6) Agent Nodes
# =========================

def _ensure_analyzer_output(parsed: Any) -> AnalyzerOutput:
    if isinstance(parsed, AnalyzerOutput):
        return parsed
    if isinstance(parsed, list):
        return AnalyzerOutput.model_validate({"detectors": parsed})
    if isinstance(parsed, dict):
        return AnalyzerOutput.model_validate(parsed)
    raise ValueError(f"Unexpected analyzer output type: {type(parsed)}")


def _ensure_classifier_output(parsed: Any) -> ClassifierOutput:
    if isinstance(parsed, ClassifierOutput):
        return parsed
    if isinstance(parsed, list):
        return ClassifierOutput.model_validate({"mappings": parsed})
    if isinstance(parsed, dict):
        return ClassifierOutput.model_validate(parsed)
    raise ValueError(f"Unexpected classifier output type: {type(parsed)}")


def _ensure_reporter_output(parsed: Any) -> ReporterOutput:
    if isinstance(parsed, ReporterOutput):
        return parsed
    if isinstance(parsed, str):
        return ReporterOutput.model_validate({"report_md": parsed})
    if isinstance(parsed, dict):
        return ReporterOutput.model_validate(parsed)
    raise ValueError(f"Unexpected reporter output type: {type(parsed)}")

def analyzer_node(state: GraphState) -> GraphState:
    llm = make_llm()
    parser = JsonOutputParser(pydantic_object=AnalyzerOutput)

    sys = SystemMessage(
        content=(
            "You are Agent 1 (Analyzer). Given an ecosystem JSON, propose up to 5 security detectors.\n"
            "Each detector must include: name, description, rationale, dbir_evidence (short excerpts), "
            "risk_level (High/Medium/Low), likelihood (High/Medium/Low).\n"
            "Use DBIR 2025 assumptions as baseline (credential abuse, web app attacks, ransomware, etc.).\n"
            "Return STRICT JSON matching the provided schema."
        )
    )

    user = HumanMessage(
        content=(
            "Ecosystem:\n"
            f"{state.ecosystem.model_dump_json(indent=2)}\n\n"
            "Output JSON only."
        )
    )

    try:
        raw = llm.invoke([sys, user])
        # Compatible con Responses API
        if isinstance(raw.content, list):
            text_output = "".join(
                block.get("text", "")
                for block in raw.content
                if isinstance(block, dict)
            )
        else:
            text_output = raw.content

        
        parsed = parser.parse(text_output)
        # Si el modelo devolvió solo lista → envolverla
        if isinstance(parsed, list):
            parsed = {"detectors": parsed}
        out = AnalyzerOutput.model_validate(parsed)
        state.analyzer = out
        
        state.last_error = None
        return log_event(state, "analyzer", {"ok": True, "detectors": len(out.detectors)})
    except Exception as e:
        state.last_error = f"Analyzer failed: {e}"
        return log_event(state, "analyzer", {"ok": False, "error": state.last_error})


def classifier_node(state: GraphState) -> GraphState:
    print(f"Inicia classifier_node. Estado actual: {state.model_dump_json(indent=4)} ")
    if not state.analyzer:
        state.last_error = "Classifier called without analyzer output."
        return log_event(state, "classifier", {"ok": False, "error": state.last_error})

    llm = bind_mitre_mcp(make_llm())
    parser = JsonOutputParser(pydantic_object=ClassifierOutput)

    mitre_url = os.getenv("MITRE_MCP_URL", "").strip()
    if not mitre_url:
        state.last_error = "MITRE_MCP_URL is not set. Cannot call MCP for MITRE mapping."
        return log_event(state, "classifier", {"ok": False, "error": state.last_error})

    sys = SystemMessage(
        content=(
            "You are Agent 2 (Classifier). Map each detector to MITRE ATT&CK techniques.\n"
            "You have access to an MCP server labeled 'mitre_attack'. Use it to look up techniques.\n"
            "For each detector, return:\n"
            "- detector_name\n"
            "- techniques: list of {id,name,tactic}\n"
            "- confidence (0..1)\n"
            "- impact (High/Medium/Low)\n"
            "- priority (1..100, 1 = highest)\n"
            "Return STRICT JSON matching the schema."
        )
    )
    print(f"Classifier system message preparado. {sys.content} ")

    user = HumanMessage(
        content=(
            "Detectors:\n"
            f"{state.analyzer.model_dump_json(indent=2)}\n\n"
            "Use the MCP tools to ground technique IDs/names. Output JSON only."
        )
    )
    print(f"Classifier user message preparado. {user.content} ")

    try:
        raw = llm.invoke([sys, user])
        # Compatible con Responses API
        if isinstance(raw.content, list):
            text_output = "".join(
                block.get("text", "")
                for block in raw.content
                if isinstance(block, dict)
            )
        else:
            text_output = raw.content
        
        parsed = parser.parse(text_output)
        # Si el modelo devolvió solo lista → envolverla
        if isinstance(parsed, list):
            parsed = {"detectors": parsed}
        out = AnalyzerOutput.model_validate(parsed)
        state.classifier = out
        
        state.last_error = None
        return log_event(state, "classifier", {"ok": True, "mappings": len(out.mappings)})
    except Exception as e:
        state.last_error = f"Classifier failed: {e}"
        return log_event(state, "classifier", {"ok": False, "error": state.last_error})


def reporter_node(state: GraphState) -> GraphState:
    print(f"Inicia reporter_node. Estado actual: {state.model_dump_json(indent=4)} ")
    if not state.analyzer or not state.classifier:
        state.last_error = "Reporter called without analyzer/classifier outputs."
        return log_event(state, "reporter", {"ok": False, "error": state.last_error})

    llm = make_llm()
    parser = JsonOutputParser(pydantic_object=ReporterOutput)

    sys = SystemMessage(
        content=(
            "You are Agent 3 (Reporting). Produce a concise but actionable security report in Markdown.\n"
            "Include: Executive Summary, Top detectors, MITRE mappings, prioritized actions by team (IAM/AppSec/SOC/SecEng).\n"
            "Keep it readable; include a small 'Next 7 days / 30 days' plan.\n"
            "Return STRICT JSON: {\"report_md\": \"...\"}"
        )
    )

    user = HumanMessage(
        content=(
            "Ecosystem:\n"
            f"{state.ecosystem.model_dump_json(indent=2)}\n\n"
            "Analyzer output:\n"
            f"{state.analyzer.model_dump_json(indent=2)}\n\n"
            "MITRE mappings:\n"
            f"{state.classifier.model_dump_json(indent=2)}\n"
        )
    )

    try:
        raw = llm.invoke([sys, user])
        # Compatible con Responses API
        if isinstance(raw.content, list):
            text_output = "".join(
                block.get("text", "")
                for block in raw.content
                if isinstance(block, dict)
            )
        else:
            text_output = raw.content
        
        parsed = parser.parse(text_output)
        # Si el modelo devolvió solo lista → envolverla
        if isinstance(parsed, list):
            parsed = {"detectors": parsed}
        out = AnalyzerOutput.model_validate(parsed)
        
        state.reporter = out
        state.last_error = None
        return log_event(state, "reporter", {"ok": True, "chars": len(out.report_md)})
    except Exception as e:
        state.last_error = f"Reporter failed: {e}"
        return log_event(state, "reporter", {"ok": False, "error": state.last_error})


# =========================
# 7) Validators + repair loops (non-linear checkpoints)
# =========================

def validate_analyzer_node(state: GraphState) -> GraphState:
    print(f"Inicia validate_analyzer_node. Estado actual: {state.model_dump_json(indent=4)} ")
    
    if not state.analyzer:
        state.last_error = "Analyzer missing output"
        state.validation_route = "repair_analyzer"
    else:
        state.validation_route = "ok"
    return state



def validate_classifier_node(state: GraphState) -> Tuple[str, GraphState]:
    if not state.classifier:
        state.validation_route = "repair_classifier"
    else:
        state.validation_route = "ok"

    return state



def validate_reporter_node(state: GraphState) -> Tuple[str, GraphState]:
    if not state.reporter:
        return "repair_reporter", log_event(state, "validate_reporter", {"ok": False, "reason": "missing"})
    if len(state.reporter.report_md.strip()) < 200:
        return "repair_reporter", log_event(state, "validate_reporter", {"ok": False, "reason": "too_short"})
    return "ok", log_event(state, "validate_reporter", {"ok": True})


def repair_analyzer_node(state: GraphState) -> GraphState:
    # simplest: just re-run analyzer with an error hint
    hint = state.last_error or "Validation failed"
    state = log_event(state, "repair_analyzer", {"hint": hint})
    return analyzer_node(state)


def repair_classifier_node(state: GraphState) -> GraphState:
    hint = state.last_error or "Validation failed (low confidence or missing)."
    state = log_event(state, "repair_classifier", {"hint": hint})
    return classifier_node(state)


def repair_reporter_node(state: GraphState) -> GraphState:
    hint = state.last_error or "Validation failed (report too short or missing)."
    state = log_event(state, "repair_reporter", {"hint": hint})
    return reporter_node(state)


# =========================
# 8) Build LangGraph
# =========================

def build_graph():
    builder = StateGraph(GraphState)
    print(f"Inicia build_graph.")

    # Nodes
    builder.add_node("analyzer", analyzer_node, retry_policy=RetryPolicy())
    builder.add_node("validate_analyzer", validate_analyzer_node)
    builder.add_node("repair_analyzer", repair_analyzer_node, retry_policy=RetryPolicy(max_attempts=2))

    builder.add_node("classifier", classifier_node, retry_policy=RetryPolicy())
    builder.add_node("validate_classifier", validate_classifier_node)
    builder.add_node("repair_classifier", repair_classifier_node, retry_policy=RetryPolicy(max_attempts=2))

    builder.add_node("reporter", reporter_node, retry_policy=RetryPolicy())
    builder.add_node("validate_reporter", validate_reporter_node)
    builder.add_node("repair_reporter", repair_reporter_node, retry_policy=RetryPolicy(max_attempts=2))

    # Flow
    builder.set_entry_point("analyzer")
    builder.add_edge("analyzer", "validate_analyzer")
    
    builder.add_conditional_edges(
        "validate_analyzer",
        lambda state: state.validation_route,
        {
            "ok": "classifier",
            "repair_analyzer": "repair_analyzer",
        },
    )

    
    builder.add_edge("repair_analyzer", "validate_analyzer")

    builder.add_edge("classifier", "validate_classifier")
    builder.add_conditional_edges(
        "validate_classifier",
        lambda state: state.validation_route,
        {
            "ok": "reporter",
            "repair_classifier": "repair_classifier",
        },
    )
    builder.add_edge("repair_classifier", "validate_classifier")

    builder.add_edge("reporter", "validate_reporter")
    builder.add_conditional_edges(
        "validate_reporter",
        lambda state: state.validation_route,
        {
            "ok": END,
            "repair_reporter": "repair_reporter",
        },
    )
    builder.add_edge("repair_reporter", "validate_reporter")

    # Checkpointing (in-memory baseline; swap to Postgres/Redis later)
    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)


# =========================
# 9) CLI runner
# =========================

def load_ecosystem(path: Path) -> EcosystemInput:
    data = json.loads(path.read_text(encoding="utf-8"))
    return EcosystemInput.model_validate(data)



# def main():
#     ap = argparse.ArgumentParser()
#     ap.add_argument("--ecosystem", required=True, help="Path to ecosystem JSON")
#     ap.add_argument("--out", default="runs", help="Output runs directory")
#     args = ap.parse_args()

#     out_dir = Path(args.out)
#     out_dir.mkdir(parents=True, exist_ok=True)

#     session_id = str(uuid.uuid4())
#     eco = load_ecosystem(Path(args.ecosystem))

#     state = GraphState(session_id=session_id, ecosystem=eco)
#     graph = build_graph()

#     # invoke with a thread_id so checkpointer can track a thread
#     result: GraphState = graph.invoke(state, config={"configurable": {"thread_id": session_id}})

#     run_dir = ensure_run_dir(out_dir, session_id)
#     write_json(run_dir, "00_input.json", result.ecosystem.model_dump())
#     write_json(run_dir, "10_analyzer.json", result.analyzer.model_dump() if result.analyzer else None)
#     write_json(run_dir, "20_classifier.json", result.classifier.model_dump() if result.classifier else None)
#     write_text(run_dir, "30_report.md", result.reporter.report_md if result.reporter else "")
#     write_json(run_dir, "trace.json", result.events)

#     print(f"✅ Done. Session: {session_id}")
#     print(f"📁 Outputs: {run_dir}")


# if __name__ == "__main__":
#     main()

from pathlib import Path
import json

def run_pipeline(ecosystem: EcosystemInput) -> GraphState:
    session_id = str(uuid.uuid4())
    print(f"Inicia pipeline con session_id={session_id}")
    
    state = GraphState(session_id=session_id, ecosystem=ecosystem)
    print(f"Estado inicial: {state.model_dump_json(indent=4)}  ")
    
    graph = build_graph()
    print("LangGraph construido. Iniciando ejecución...")
    
    result: GraphState = graph.invoke(
        state,
        config={"configurable": {"thread_id": session_id}}
    )
    print(f"LangGraph ejecución finalizada. Resultado: {result.model_dump_json(indent=4)}  ")

    # Persist outputs automatically
    print("Persistiendo resultados...")
    run_dir = Path("runs") / session_id
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "input.json").write_text(ecosystem.model_dump_json(indent=2))
    if result.analyzer:
        (run_dir / "analyzer.json").write_text(result.analyzer.model_dump_json(indent=2))
    if result.classifier:
        (run_dir / "classifier.json").write_text(result.classifier.model_dump_json(indent=2))
    if result.reporter:
        (run_dir / "report.md").write_text(result.reporter.report_md)
    (run_dir / "trace.json").write_text(json.dumps(result.events, indent=2))

    return result
