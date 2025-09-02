from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
import time
import httpx

from .config import settings
from .db import init_db
from .vectorstore import ensure_collection
from .routes.shopping import router as shopping_router
from .routes.appliances import router as appliances_router
from .routes.planner import router as planner_router
from .routes.catalog import router as catalog_router
from .routes.admin import router as admin_router
from .routes.auth import router as auth_router
from .routes.rag import router as rag_router
from .routes.generate import router as generate_router
from .routes.user_recipes import router as user_recipes_router
from .middleware.rate_limit import RateLimitMiddleware
from .middleware.size_limit import SizeLimitMiddleware
from .errors import install_exception_handlers
from prometheus_fastapi_instrumentator import Instrumentator

TAGS_METADATA = [
    {"name": "auth", "description": "Autenticación JWT (modo dev con PIN)."},
    {"name": "planner", "description": "Planificación semanal de comidas y exportación iCal."},
    {"name": "shopping", "description": "Lista de la compra: agregado por semana, CRUD y exportación CSV."},
    {"name": "appliances", "description": "Gestión de electrodomésticos del usuario."},
    {"name": "catalog", "description": "Catálogo de productos y categorías del usuario."},
    {"name": "admin", "description": "Seeds de datos de desarrollo."},
]

app = FastAPI(
    title="FullFoodApp API",
    version="0.2.0",
    description="Backend de FullFoodApp (MVP). RAG local con Qdrant + Azure OpenAI, planificador semanal y lista de la compra.",
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

# Middlewares
app.add_middleware(SizeLimitMiddleware)     # 413 si Content-Length excede
app.add_middleware(RateLimitMiddleware)     # 429 si exceso RPM

# Prometheus
instrumentator = Instrumentator().instrument(app)
instrumentator.expose(app, include_in_schema=False, endpoint="/metrics")

# Exception handlers
install_exception_handlers(app)

@app.on_event("startup")
async def startup():
    init_db()
    vector_dims = settings.parsed_vector_dims()
    await ensure_collection(vector_dims)

# Routers
app.include_router(auth_router)
app.include_router(shopping_router)
app.include_router(appliances_router)
app.include_router(planner_router)
app.include_router(catalog_router)
app.include_router(admin_router)
app.include_router(rag_router)
app.include_router(generate_router)
app.include_router(user_recipes_router)


@app.get("/health", tags=["admin"], summary="Healthcheck simple")
async def health():
    return {"status": "ok", "qdrant": settings.qdrant_url, "llm": settings.azure_openai_deployment_llm}

@app.get("/health/deep", tags=["admin"], summary="Healthcheck profundo (Qdrant + Azure OpenAI)")
async def health_deep():
    out = {"status": "ok", "checks": {}}

    # Qdrant
    t0 = time.perf_counter()
    q_ok, q_err = True, None
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(settings.qdrant_url.rstrip("/") + "/collections")
            r.raise_for_status()
    except Exception as e:
        q_ok, q_err = False, str(e)
        out["status"] = "degraded"
    out["checks"]["qdrant"] = {"ok": q_ok, "latency_ms": round((time.perf_counter()-t0)*1000, 1), "error": q_err}

    # Azure OpenAI
    t1 = time.perf_counter()
    o_ok, o_err = True, None
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(settings.azure_openai_endpoint.rstrip("/") + "/api/tags")
            r.raise_for_status()
    except Exception as e:
        o_ok, o_err = False, str(e)
        out["status"] = "degraded"
    out["checks"]["azure_openai"] = {"ok": o_ok, "latency_ms": round((time.perf_counter()-t1)*1000, 1), "error": o_err}

    return out

# --- OpenAPI servers ---
from fastapi.openapi.utils import get_openapi
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
app.openapi = custom_openapi  # type: ignore
