# Configuración de modelos
EMBEDDING_MODEL = "text-embedding-3-large"
QUERY_MODEL = "gpt-4o-mini"
GENERATION_MODEL = "gpt-4o"

PDF_LOADER_DOC = "C:\\WorkLabs\\04-Challenge_MELI\\assets\\2025-dbir-data-breach-investigations-report.pdf"
CHROMA_DB_PATH = "C:\\WorkLabs\\04-Challenge_MELI\\chroma_db"

# Configuración del retriever
SEARCH_TYPE = "mmr"
MMR_DIVERSITY_LAMBDA = 0.7
MMR_FETCH_K = 20
SEARCH_K = 2

# Configuracion alternativa para retriever hibrido
ENABLE_HYBRID_SEARCH = True
SIMILARITY_THRESHOLD = 0.70