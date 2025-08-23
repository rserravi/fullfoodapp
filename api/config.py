from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    qdrant_url: str = "http://localhost:6333"
    ollama_url: str = "http://localhost:11434"
    collection_name: str = "recipes"
    embedding_models: str = "mxbai-embed-large,jina-embeddings-v2-base-es"
    log_level: str = "INFO"

settings = Settings()
