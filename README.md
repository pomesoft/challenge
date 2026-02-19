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
flowchart LR
  %% ===========
  %% Client / UI
  %% ===========
  U[Usuario\n(Ecosystem JSON + Preguntas)] -->|Chat / Form| ST[Streamlit UI\napp.py]

  %% ==================
  %% Orchestrator Layer
  %% ==================
  ST -->|run_pipeline(ecosystem)| LG[LangGraph Orchestrator\n(StateGraph + checkpoints)]

  %% ===========
  %% Knowledge/RAG
  %% ===========
  subgraph RAG["RAG DBIR 2025 (Base de Conocimiento)"]
    PDF[DBIR 2025 PDF\nassets/2025-dbir-...pdf] --> LD[PyPDFLoader + Splitter\n(chunking)]
    LD --> VS[(Chroma Vector Store\npersist_directory)]
    VS --> RET[Retriever\nMMR + MultiQuery\n(+ Hybrid optional)]
  end

  %% ===================
  %% Multi-Agent Workflow
  %% ===================
  subgraph AGENTS["Multi-Agent System (3 agentes)"]
    A1[Agente 1: Analyzer\nGenera hasta 5 detectores\n+ riesgo H/M/L\n+ evidencia DBIR]
    V1{Validator / Checkpoint\nSchema + reglas}
    A2[Agente 2: Classifier\nMapea detectores a\nMITRE ATT&CK techniques\n+ impacto + prioridad]
    V2{Validator / Checkpoint\nConfianza / tool errors}
    A3[Agente 3: Reporter\nReporte final Markdown\n+ accionables por equipo]
    V3{Validator / Checkpoint\nCompletitud / calidad}
  end

  %% ====================
  %% LLM + Tools Backends
  %% ====================
  LLM[(OpenAI Responses API\nvia ChatOpenAI use_responses_api)]
  MCP[(MCP Server\nMITRE ATT&CK Tools)]

  %% ===========
  %% Data Flow
  %% ===========
  LG --> A1
  A1 -->|consulta DBIR| RET
  RET --> A1
  A1 --> V1
  V1 -->|OK| A2
  V1 -->|Repair| A1

  A2 -->|tool calls| MCP
  MCP --> A2
  A2 --> V2
  V2 -->|OK| A3
  V2 -->|Repair / retry| A2

  A3 --> V3
  V3 -->|OK| OUT[Outputs\nreport.md + json]
  V3 -->|Repair| A3

  %% LLM usage
  A1 --> LLM
  A2 --> LLM
  A3 --> LLM

  %% =====================
  %% Observability / Storage
  %% =====================
  subgraph OBS["Trazabilidad / Observabilidad"]
    LOGS[(Central Store\nruns/<session_id>/\ntrace.json + I/O por agente)]
  end

  LG -->|events + I/O| LOGS
  OUT --> LOGS
  ST -->|mostrar resultados| OUT


