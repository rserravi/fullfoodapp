from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from .config import settings
from .db import init_db
from .vectorstore import ensure_collection
from .routes.shopping import router as shopping_router
from .routes.appliances import router as appliances_router
from .routes.planner import router as planner_router
from .routes.catalog import router as catalog_router
from .routes.admin import router as admin_router
from .middleware.rate_limit import RateLimitMiddleware
from .errors import install_exception_handlers
from prometheus_fastapi_instrumentator import Instrumentator

TAGS_METADATA = [
    {"name": "planner", "description": "Planificación semanal de comidas y exportación iCal."},
    {"name": "shopping", "description": "Lista de la compra: agregado por semana, CRUD y exportación CSV."},
    {"name": "appliances", "description": "Gestión de electrodomésticos del usuario."},
    {"name": "catalog", "description": "Catálogo de productos y categorías del usuario."},
    {"name": "admin", "description": "Seeds de datos de desarrollo."},
]

app = FastAPI(
    title="FullFoodApp API",
    version="0.1.0",
    description="Backend de FullFoodApp (MVP). RAG local con Qdrant + Ollama, planificador semanal y lista de la compra.",
    default_response_class=ORJSONResponse,
    openapi_tags=TAGS_METADATA,
    contact={"name": "Equipo FullFoodApp", "email": "dev@fullfoodapp.local"},
    license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allow_origins.split(",")] if settings.cors_allow_origins != "*" else ["*"],
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=[m.strip() for m in settings.cors_allow_methods.split(",")] if settings.cors_allow_methods != "*" else ["*"],
    allow_headers=[h.strip() for h in settings.cors_allow_headers.split(",")] if settings.cors_allow_headers != "*" else ["*"],
)

# Rate limiting
app.add_middleware(RateLimitMiddleware)

# Prometheus
instrumentator = Instrumentator().instrument(app)
instrumentator.expose(app, include_in_schema=False, endpoint="/metrics")

# Exception handlers unificados
install_exception_handlers(app)

@app.on_event("startup")
async def startup():
    init_db()
    vector_dims = settings.parsed_vector_dims()
    await ensure_collection(vector_dims)

# Routers
app.include_router(shopping_router)
app.include_router(appliances_router)
app.include_router(planner_router)
app.include_router(catalog_router)
app.include_router(admin_router)

@app.get("/health", tags=["admin"], summary="Healthcheck simple")
async def health():
    return {"status": "ok", "qdrant": settings.qdrant_url, "llm": settings.llm_model}

# --- Inserta 'servers' en OpenAPI ---
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=TAGS_METADATA,
    )
    schema["servers"] = [{"url": settings.server_public_url, "description": f"{settings.service_env}"}]
    app.openapi_schema = schema
    return app.openapi_schema

app.openapi = custom_openapi  # type: ignore[assignment]
