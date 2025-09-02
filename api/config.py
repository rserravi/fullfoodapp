from typing import Dict, Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    prompts_dir: str = "api/prompts"
    
    # Core
    log_level: str = "INFO"
    service_env: str = "dev"  # dev|prod
    server_public_url: str = "http://localhost:8000"

    # Azure OpenAI
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2025-01-01-preview"
    azure_openai_llm_deployment: str = "fullfood-recipes-v1"
    azure_openai_embedding_deployment: Optional[str] = None
    llm_timeout_s: int = 45
    llm_max_concurrency: int = 3

    # RAG (Qdrant)
    qdrant_url: str = "http://localhost:6333"
    collection_name: str = "recipes"
    rag_timeout_s: int = 10

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
    jwt_secret: str = "change-me-dev"
    jwt_expire_minutes: int = 120
    auth_dev_pin: Optional[str] = None

    # Rate limiting
    rate_limit_rpm: int = 60
    rate_limit_burst: int = 60

    # Redis (rate limiting)
    redis_url: Optional[str] = None
    redis_password: Optional[str] = None

    # Size limit
    max_body_bytes: int = 262144  # 256KB

    def parsed_embedding_models(self) -> list[str]:
        if self.azure_openai_embedding_deployment:
            return [self.azure_openai_embedding_deployment]
        return []

    def parsed_vector_dims(self) -> Dict[str, int]:
        if not self.azure_openai_embedding_deployment:
            return {}
        model = self.azure_openai_embedding_deployment
        # Dimensiones fijas para los modelos de Azure OpenAI más comunes.
        if "large" in model:
            dim = 3072
        elif "small" in model:
            dim = 1536
        else:
            # Valor por defecto si no podemos inferirlo del nombre.
            dim = 1536
        return {model: dim}

    def parsed_api_keys(self) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for pair in [p.strip() for p in self.api_keys.split(",") if p.strip()]:
            if ":" not in pair:
                continue
            user, token = pair.split(":", 1)
            mapping[token.strip()] = user.strip()
        return mapping

    @model_validator(mode="after")
    def _validate_security(self) -> "Settings":
        if self.service_env != "dev":
            if self.jwt_secret == "change-me-dev":
                raise ValueError("jwt_secret must be set via environment variable in non-dev environments")
            if self.auth_dev_pin is not None:
                raise ValueError("auth_dev_pin is only allowed in development")
            if self.service_env == "prod":
                self.auth_fallback_user = None
        else:
            if not self.auth_dev_pin:
                raise ValueError("auth_dev_pin must be defined via environment variable in development")
        return self

settings = Settings()
