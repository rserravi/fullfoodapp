from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, EmailStr
from fastapi import APIRouter, HTTPException, Body

from ..config import settings
from ..security import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    email: EmailStr
    dev_pin: Optional[str] = None

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str

@router.post("/login", response_model=LoginResponse, summary="Login (modo dev) con PIN para emitir JWT")
def login_dev(req: LoginRequest = Body(..., examples={
    "dev": {"summary": "Login con PIN de desarrollo", "value": {"email": "ruben@example.com", "dev_pin": "000000"}}
})):
    pin = req.dev_pin or ""
    if not settings.auth_dev_pin or pin != settings.auth_dev_pin:
        raise HTTPException(status_code=401, detail="Invalid PIN")
    user_id = req.email.lower()
    token = create_access_token(user_id=user_id, expires_minutes=settings.jwt_expire_minutes)
    return LoginResponse(access_token=token, user_id=user_id)
