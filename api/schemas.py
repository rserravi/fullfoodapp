from typing import Any, Dict, List, Optional
from typing_extensions import Literal
from pydantic import BaseModel, Field, field_validator

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

# === Recetas ===

ActionLiteral = Literal["prep", "season", "preheat", "cook", "flip", "rest", "serve"]

class RecipeGenRequest(BaseModel):
    ingredients: List[str]
    portions: int = 2
    appliances: List[str] = ["airfryer"]
    dietary: List[str] = []  # p. ej. ["vegetariano", "sin_gluten"]

class StepGeneric(BaseModel):
    action: ActionLiteral
    description: str
    ingredients: List[str] = []
    tools: List[str] = []
    temperature_c: Optional[int] = None
    time_min: Optional[float] = None
    speed: Optional[str] = None
    notes: Optional[str] = None
    batching: bool = False

    @field_validator("time_min")
    @classmethod
    def _time_positive(cls, v):
        if v is not None and v <= 0:
            raise ValueError("time_min debe ser > 0")
        return v

    @field_validator("temperature_c")
    @classmethod
    def _temp_reasonable(cls, v):
        if v is not None and not (0 <= v <= 300):
            raise ValueError("temperature_c fuera de rango razonable (0..300°C)")
        return v

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
