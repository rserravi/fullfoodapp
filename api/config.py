from typing import Dict
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    log_level: str = "INFO"

    # Ollama / LLM
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "llama3.1:8b"
    embedding_models: str = "mxbai-embed-large,jina/jina-embeddings-v2-base-es"
    ollama_timeout_s: int = 180

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    collection_name: str = "recipes"

    # Vector dims (avoid Ollama call on startup)
    vector_dims: str = "mxbai:1024,jina:768"

    # CORS (para frontend en V2)
    cors_allow_origins: str = "*"
    cors_allow_credentials: bool = True
    cors_allow_methods: str = "*"
    cors_allow_headers: str = "*"

    # DB local (SQLite file)
    db_url: str = "sqlite:///./fullfood.db"

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

settings = Settings()
