# FullFoodApp (MVP) — API local + Qdrant + Azure OpenAI (RAG)

Aplicación MVP para recetas/compra con **FastAPI**, **Qdrant** como vector store y **Azure OpenAI** para LLM/embeddings.
Incluye **RAG híbrido** (mxbai + jina) con **RRF**, compilador de receta neutra → electrodomésticos (*airfryer*, *horno*), y configuración vía **.env**.


---

## 📁 Estructura
fullfoodapp/
├─ api/
│ ├─ main.py # Endpoints FastAPI
│ ├─ config.py # Carga .env (pydantic-settings)
│ ├─ schemas.py # Pydantic models
│ ├─ embeddings.py # Cliente Azure OpenAI (embeddings)
│ ├─ llm.py # Cliente Ollama (generate format=json)
│ ├─ rag.py # Hybrid retrieve + RRF + context builder
│ ├─ vectorstore.py # Cliente Qdrant (vectores con nombre)
│ ├─ ingest.py # Ingesta de semillas
│ ├─ compiler/
│ │ ├─ rules_airfryer.py
│ │ ├─ rules_oven.py
│ │ └─ compiler.py
│ └─ prompts/
│ └─ recipe_generation.md
├─ seeds/
│ └─ recipes_min.json
├─ docker-compose.yml # Solo Qdrant (API se ejecuta en local)
├─ .env # Configuración local (no se sube a git)
├─ .gitignore
└─ README.md


---

## ✅ Requisitos

- **Python 3.11+** (recomendado venv)
- **Docker** (solo para Qdrant)
- **Ollama** en local (`OLLAMA_URL`, por defecto `http://localhost:11434`) con el modelo:
  - `llama3.1:8b` (LLM para generación JSON)
- **Azure OpenAI** con un deployment de embeddings (por ejemplo `text-embedding-3-large`)

```bash
ollama pull llama3.1:8b
```

## 📦 Redis para rate limiting

El middleware de límite de peticiones usa **Redis** como almacenamiento compartido. Configura en tu `.env`:

```bash
REDIS_URL=redis://localhost:6379/0
REDIS_PASSWORD=tu_password  # opcional
```

### 🔐 Variables de entorno

- `SERVICE_ENV`: entorno de ejecución (`dev` por defecto). Para producción usar `prod`.
- `JWT_SECRET`: secreto para firmar tokens JWT. Debe cambiarse respecto al valor por defecto y es obligatorio fuera de desarrollo.
- `AUTH_FALLBACK_USER`: usuario alternativo para desarrollo. Se deshabilita automáticamente en producción.
- `AUTH_DEV_PIN`: PIN de desarrollo requerido en `dev` (debe definirse como variable de entorno) y no debe existir en `prod`.
