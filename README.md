# DataSec Challenge

## Javier Montigel

## Objetivo 
Realizar un sistema multiagente que posea las características mencionadas a continuación y
pueda realizar las tareas propuestas para la creación de nuevos mecanismos detectivos:
Sistema: La solución debe ser una arquitectura multiagente compuesta por 3 agentes
específicos que implementen un pipeline secuencial de análisis de vectores de
ataque/riesgos, comparativa con el contexto del ecosistema a evaluar, y generación de un
reporte de detectores prioritarios.

## 🏗 Arquitectura Propuesta

```mermaid
flowchart LR

    U["Usuario<br/>Ecosystem JSON y preguntas"]
    ST["Streamlit UI<br/>app.py"]
    LG["LangGraph Orchestrator<br/>StateGraph + checkpoints"]

    subgraph RAG["RAG DBIR 2025"]
        PDF["DBIR 2025 PDF"]
        LD["Loader + Splitter"]
        VS["Chroma Vector Store"]
        RET["Retriever MMR MultiQuery"]
        PDF --> LD --> VS --> RET
    end

    subgraph AGENTS["Multi-Agent Workflow"]
        A1["Agente 1 Analyzer<br/>Detectores y riesgo"]
        V1{"Validator 1"}
        A2["Agente 2 Classifier<br/>MITRE ATTACK mapping"]
        V2{"Validator 2"}
        A3["Agente 3 Reporter<br/>Reporte Markdown"]
        V3{"Validator 3"}
    end

    MCP["MCP Server MITRE"]
    OUT["Outputs<br/>report.md y json"]

    U --> ST
    ST --> LG
    LG --> A1
    A1 --> RET
    RET --> A1
    A1 --> V1
    V1 -->|OK| A2
    V1 -->|Repair| A1
    A2 --> MCP
    A2 --> V2
    V2 -->|OK| A3
    V2 -->|Repair| A2
    A3 --> V3
    V3 -->|OK| OUT
```
