from __future__ import annotations

from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from ..db import get_session
from ..security import get_current_user
from ..errors import ErrorResponse
from ..models_user_recipes import UserRecipe
from ..schemas_user_recipes import UserRecipeCreate, UserRecipeUpdate, UserRecipeOut
from ..services.recipe_text import recipe_to_text
from ..schemas import RecipeNeutral
from ..embeddings import embed_dual
from ..vectorstore import upsert_documents, delete_user_recipe_vectors

router = APIRouter(prefix="/user-recipes", tags=["user-recipes"])


def _payload_for_qdrant(user_id: str, ur: UserRecipe) -> Dict[str, Any]:
    return {
        "kind": "user_recipe",
        "user_id": user_id,
        "recipe_id": ur.id,
        "title": ur.title,
        "portions": ur.portions,
        "tags": ur.tags,
        "appliances": ur.appliances,
        "recipe": ur.recipe,  # guardamos la receta completa para recuperación directa
        "source": ur.source,
        "public": ur.public,
        "created_at": ur.created_at.isoformat(),
        "updated_at": ur.updated_at.isoformat(),
    }


async def _vectorize_user_recipe(session: Session, user_id: str, ur: UserRecipe) -> None:
    # ur.recipe en DB es un dict -> conviértelo a RecipeNeutral para aplanarlo
    rn = RecipeNeutral(**ur.recipe) if isinstance(ur.recipe, dict) else ur.recipe
    text = recipe_to_text(ur.title, rn)
    embs = await embed_dual([text])  # usa modelos por defecto de settings
    payloads = [_payload_for_qdrant(user_id, ur)]
    # upsert_documents es sincrona en tu código
    upsert_documents([text], payloads, embs)


@router.post(
    "",
    response_model=UserRecipeOut,
    summary="Crear/guardar una receta del usuario (vectoriza para RAG)",
    responses={400: {"model": ErrorResponse}},
)
async def create_user_recipe(
    data: UserRecipeCreate,
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    ur = UserRecipe(
        user_id=user_id,
        title=data.title,
        portions=data.portions,
        tags=data.tags,
        appliances=data.appliances,
        recipe=data.recipe.model_dump(),  # persistimos dict
        source=data.source,
        public=data.public,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(ur)
    session.commit()
    session.refresh(ur)

    # Vectorizar
    await _vectorize_user_recipe(session, user_id, ur)

    return UserRecipeOut(
        id=ur.id,
        user_id=user_id,
        title=ur.title,
        portions=ur.portions,
        tags=ur.tags,
        appliances=ur.appliances,
        recipe=data.recipe,
        source=ur.source,
        public=ur.public,
        created_at=ur.created_at,
        updated_at=ur.updated_at,
    )


@router.get(
    "",
    response_model=List[UserRecipeOut],
    summary="Listar recetas del usuario",
)
def list_user_recipes(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    stmt = (
        select(UserRecipe)
        .where(UserRecipe.user_id == user_id)
        .order_by(UserRecipe.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = session.exec(stmt).all()
    res: List[UserRecipeOut] = []
    for r in rows:
        res.append(
            UserRecipeOut(
                id=r.id,
                user_id=user_id,
                title=r.title,
                portions=r.portions,
                tags=r.tags,
                appliances=r.appliances,
                recipe=r.recipe,  # se valida contra RecipeNeutral
                source=r.source,
                public=r.public,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )
    return res


@router.get(
    "/{recipe_id}",
    response_model=UserRecipeOut,
    summary="Obtener una receta del usuario por id",
    responses={404: {"model": ErrorResponse}},
)
def get_user_recipe(
    recipe_id: str,
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    r = session.get(UserRecipe, recipe_id)
    if not r or r.user_id != user_id:
        raise HTTPException(status_code=404, detail="Receta no encontrada")
    return UserRecipeOut(
        id=r.id,
        user_id=user_id,
        title=r.title,
        portions=r.portions,
        tags=r.tags,
        appliances=r.appliances,
        recipe=r.recipe,
        source=r.source,
        public=r.public,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.put(
    "/{recipe_id}",
    response_model=UserRecipeOut,
    summary="Actualizar una receta del usuario (revectoriza para RAG)",
    responses={404: {"model": ErrorResponse}},
)
async def update_user_recipe(
    recipe_id: str,
    data: UserRecipeUpdate,
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    r = session.get(UserRecipe, recipe_id)
    if not r or r.user_id != user_id:
        raise HTTPException(status_code=404, detail="Receta no encontrada")

    # apply changes
    if data.title is not None:
        r.title = data.title
    if data.portions is not None:
        r.portions = data.portions
    if data.tags is not None:
        r.tags = data.tags
    if data.appliances is not None:
        r.appliances = data.appliances
    if data.recipe is not None:
        r.recipe = data.recipe.model_dump()
    if data.public is not None:
        r.public = data.public
    r.updated_at = datetime.utcnow()

    session.add(r)
    session.commit()
    session.refresh(r)

    # Re-vectorizar: borramos embeddings anteriores por filtro y reinsertamos
    delete_user_recipe_vectors(user_id=user_id, recipe_id=recipe_id)
    await _vectorize_user_recipe(session, user_id, r)

    return UserRecipeOut(
        id=r.id,
        user_id=user_id,
        title=r.title,
        portions=r.portions,
        tags=r.tags,
        appliances=r.appliances,
        recipe=r.recipe,
        source=r.source,
        public=r.public,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.delete(
    "/{recipe_id}",
    summary="Eliminar una receta del usuario (borra embeddings del RAG)",
    responses={200: {"description": "Eliminada"}, 404: {"model": ErrorResponse}},
)
def delete_user_recipe(
    recipe_id: str,
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    r = session.get(UserRecipe, recipe_id)
    if not r or r.user_id != user_id:
        raise HTTPException(status_code=404, detail="Receta no encontrada")

    # borra embeddings
    delete_user_recipe_vectors(user_id=user_id, recipe_id=recipe_id)

    session.delete(r)
    session.commit()
    return {"status": "ok", "deleted_id": recipe_id}
