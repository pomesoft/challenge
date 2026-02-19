# DataSec Challenge

## Javier Montigel

## Objetivo 
Realizar un sistema multiagente que posea las características mencionadas a continuación y
pueda realizar las tareas propuestas para la creación de nuevos mecanismos detectivos:
Sistema: La solución debe ser una arquitectura multiagente compuesta por 3 agentes
específicos que implementen un pipeline secuencial de análisis de vectores de
ataque/riesgos, comparativa con el contexto del ecosistema a evaluar, y generación de un
reporte de detectores prioritarios.

## 🏗 Enterprise Architecture Overview

```mermaid
flowchart TB

    %% ===============================
    %% Capa de Presentación
    %% ===============================
    subgraph P["Presentation Layer"]
        U["Usuario<br/>Ecosystem JSON"]
        UI["Streamlit UI<br/>app.py"]
        U --> UI
    end

    %% ===============================
    %% Orquestación
    %% ===============================
    subgraph O["Orchestration Layer"]
        LG["LangGraph Orchestrator<br/>StateGraph + Checkpoints"]
    end

    %% ===============================
    %% Agentes
    %% ===============================
    subgraph I["Intelligence Layer (Multi-Agent)"]
        direction LR
        A1["Analyzer<br/>Detectores + Riesgo"]
        V1{"Validator"}
        A2["Classifier<br/>MITRE Mapping"]
        V2{"Validator"}
        A3["Reporter<br/>Markdown Report"]
        V3{"Validator"}

        A1 --> V1 --> A2 --> V2 --> A3 --> V3
    end

    %% ===============================
    %% Base de conocimeinto / Contexto
    %% ===============================
    subgraph K["Knowledge Layer"]
        PDF["DBIR 2025 PDF"]
        VS["Chroma Vector Store"]
        RET["Retriever<br/>MMR + MultiQuery"]
        PDF --> VS --> RET
    end

    %% ===============================
    %% HErramientas Externas
    %% ===============================
    subgraph T["External Tools"]
        MCP["MCP Server<br/>MITRE ATT&CK"]
        LLM["OpenAI Responses API"]
    end

    %% ===============================
    %% Observabilidad
    %% ===============================
    subgraph OBS["Observability & Storage"]
        LOGS["runs/<session_id><br/>trace.json<br/>agent_outputs"]
    end

    %% ===============================
    %% Connections
    %% ===============================

    UI --> LG
    LG --> A1
    RET --> A1
    A2 --> MCP

    A1 --> LLM
    A2 --> LLM
    A3 --> LLM

    V3 --> LOGS
    LG --> LOGS
```


La arquitectura está diseñada en capas desacopladas: Presentation, Orchestration, Intelligence, Knowledge y Tools.
LangGraph controla el flujo con checkpoints y validaciones no lineales.
El RAG provee grounding en DBIR 2025 y el MCP conecta dinámicamente con MITRE ATT&CK sin hardcodear técnicas.
Toda ejecución es trazable por session_id para reproducibilidad.


### Instalación

```bash
pip install -r requirements.txt

```

### Ejecución

Cargar base de datos vectorial ChromaDB
```bash
python vector_stores.py
```

Interfaz grafica con Streamlit
```bash
cd src
streamlit run app_streamlit.py
```