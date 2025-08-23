from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

class Document(BaseModel):
    id: Optional[str] = None
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class IngestRequest(BaseModel):
    documents: List[Document]

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    vector: str = "auto"  # auto | mxbai | jina

class SearchHit(BaseModel):
    id: str
    score: float
    text: str
    metadata: Dict[str, Any]

class SearchResponse(BaseModel):
    hits: List[SearchHit]

# Para recetas (stub MVP)
class RecipeGenRequest(BaseModel):
    ingredients: List[str]
    portions: int = 2
    appliances: List[str] = ["airfryer"]
    dietary: List[str] = []  # p. ej. ["vegetariano", "sin_gluten"]

class StepGeneric(BaseModel):
    action: str
    description: str
    ingredients: List[str] = []
    tools: List[str] = []
    temperature_c: Optional[int] = None
    time_min: Optional[float] = None
    speed: Optional[str] = None
    notes: Optional[str] = None
    batching: bool = False

class RecipeNeutral(BaseModel):
    title: str
    portions: int
    steps_generic: List[StepGeneric]

class AppliancePlanStep(BaseModel):
    action: str
    temperature_c: Optional[int]
    time_min: Optional[float]
    instructions: str

class CompiledPlan(BaseModel):
    appliance: str
    steps: List[AppliancePlanStep]

class RecipePlan(BaseModel):
    recipe: RecipeNeutral
    plans: List[CompiledPlan]
