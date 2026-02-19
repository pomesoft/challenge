# DataSec Challenge

## Javier Montigel

## Objetivo 
Realizar un sistema multiagente que posea las características mencionadas a continuación y
pueda realizar las tareas propuestas para la creación de nuevos mecanismos detectivos:
Sistema: La solución debe ser una arquitectura multiagente compuesta por 3 agentes
específicos que implementen un pipeline secuencial de análisis de vectores de
ataque/riesgos, comparativa con el contexto del ecosistema a evaluar, y generación de un
reporte de detectores prioritarios.

## Arquiectura propuesta

## 🏗 Arquitectura Propuesta

```mermaid
flowchart LR

  %% ===========
  %% Client / UI
  %% ===========
  U[Usuario\n(Ecosystem JSON + Preguntas)] --> ST[Streamlit UI\napp.py]

  %% ==================
  %% Orchestrator Layer
  %% ==================
  ST --> LG[LangGraph Orchestrator\n(StateGraph + checkpoints)]

  %% ===========
  %% Knowledge / RAG
  %% ===========
  subgraph RAG["RAG DBIR 2025"]
    PDF[DBIR 2025 PDF] --> LD[PyPDFLoader + Splitter]
    LD --> VS[(Chroma Vector Store)]
    VS --> RET[Retriever\nMMR + MultiQuery]
  end

  %% ===================
  %% Multi-Agent System
  %% ===================
  subgraph AGENTS["Multi-Agent Workflow"]
    A1[Agente 1: Analyzer\nDetectores + riesgo]
    V1{Validator}
    A2[Agente 2: Classifier\nMITRE ATT&CK]
    V2{Validator}
    A3[Agente 3: Reporter\nReporte Markdown]
    V3{Validator}
  end

  LG --> A1
  A1 --> RET
  RET --> A1
  A1 --> V1
  V1 -->|OK| A2
  V1 -->|Repair| A1

  A2 --> MCP[(MCP MITRE Server)]
  A2 --> V2
  V2 -->|OK| A3
  V2 -->|Repair| A2

  A3 --> V3
  V3 -->|OK| OUT[report.md + json]

```
