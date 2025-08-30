# FullFoodApp (MVP) — API local + Qdrant + Ollama (RAG)

Aplicación MVP para recetas/compra con **FastAPI**, **Qdrant** como vector store y **Ollama** para LLM/embeddings.  
Incluye **RAG híbrido** (mxbai + jina) con **RRF**, compilador de receta neutra → electrodomésticos (*airfryer*, *horno*), y configuración vía **.env**.

---

## 📁 Estructura
fullfoodapp/
├─ api/
│ ├─ main.py # Endpoints FastAPI
│ ├─ config.py # Carga .env (pydantic-settings)
│ ├─ schemas.py # Pydantic models
│ ├─ embeddings.py # Cliente Ollama (embeddings, con fallbacks)
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
- **Ollama** en local (`OLLAMA_URL`, por defecto `http://localhost:11434`)
  - Modelos necesarios (nombres EXACTOS):
    - `mxbai-embed-large`
    - `jina/jina-embeddings-v2-base-es`  ← nota el prefijo `jina/`
    - `llama3.1:8b` (LLM para generación JSON)

```bash
ollama pull mxbai-embed-large
ollama pull jina/jina-embeddings-v2-base-es
ollama pull llama3.1:8b

```

### 🔐 Variables de entorno

- `SERVICE_ENV`: entorno de ejecución (`dev` por defecto). Para producción usar `prod`.
- `JWT_SECRET`: secreto para firmar tokens JWT. Debe cambiarse respecto al valor por defecto y es obligatorio fuera de desarrollo.
- `AUTH_FALLBACK_USER`: usuario alternativo para desarrollo. Se deshabilita automáticamente en producción.
- `AUTH_DEV_PIN`: PIN de desarrollo requerido en `dev` (debe definirse como variable de entorno) y no debe existir en `prod`.
