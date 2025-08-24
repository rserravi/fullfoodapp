from typing import Dict, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    log_level: str = "INFO"
    service_env: str = "dev"  # dev|prod
    server_public_url: str = "http://localhost:8000"  # usado en OpenAPI.servers

    # Ollama / LLM
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "llama3.1:8b"
    embedding_models: str = "mxbai-embed-large,jina/jina-embeddings-v2-base-es"
    ollama_timeout_s: int = 180
    llm_timeout_s: int = 45
    llm_max_concurrency: int = 3

    # RAG (Qdrant)
    qdrant_url: str = "http://localhost:6333"
    collection_name: str = "recipes"
    rag_timeout_s: int = 10

    # Vector dims
    vector_dims: str = "mxbai:1024,jina:768"

    # CORS
    cors_allow_origins: str = "*"
    cors_allow_credentials: bool = True
    cors_allow_methods: str = "*"
    cors_allow_headers: str = "*"

    # DB
    db_url: str = "sqlite:///./fullfood.db"

    # Auth / multiusuario
    api_keys: str = "default:demo123"
    auth_fallback_user: Optional[str] = "default"

    # Rate limiting
    rate_limit_rpm: int = 60
    rate_limit_burst: int = 60

    def parsed_embedding_models(self) -> list[str]:
        return [m.strip() for m in self.embedding_models.split(",") if m.strip()]

    def parsed_vector_dims(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for pair in self.vector_dims.split(","):
            if not pair.strip():
                continue
            k, v = pair.split(":")
            out[k.strip()] = int(v)
        return out

    def parsed_api_keys(self) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for pair in [p.strip() for p in self.api_keys.split(",") if p.strip()]:
            if ":" not in pair:
                continue
            user, token = pair.split(":", 1)
            mapping[token.strip()] = user.strip()
        return mapping

settings = Settings()
