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

    # Azure OpenAI / LLM
    azure_openai_endpoint: str = "http://localhost:11434"
    azure_openai_api_key: Optional[str] = None

    azure_openai_deployment_llm: str = "gpt-4o-mini"
    azure_openai_timeout_s: int = 180
    azure_openai_api_version: str = "2024-02-15-preview"

    llm_timeout_s: int = 45
    llm_max_concurrency: int = 3


    # RAG (Qdrant)
    qdrant_url: str = "http://localhost:6333"
    collection_name: str = "recipes"
    rag_timeout_s: int = 10

    # Vector dims
    vector_dims: str = "text-embedding-3-large:3072"

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
        return list(self.parsed_vector_dims().keys())


    def parsed_vector_dims(self) -> Dict[str, int]:
        mapping: Dict[str, int] = {}
        for pair in [p.strip() for p in self.vector_dims.split(",") if p.strip()]:
            if ":" not in pair:
                continue
            name, dim = pair.split(":", 1)
            try:
                mapping[name.strip()] = int(dim.strip())

            except ValueError:
                continue
        return mapping

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
