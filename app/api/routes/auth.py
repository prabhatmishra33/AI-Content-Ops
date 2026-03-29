from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import get_current_user
from app.schemas.common import ApiResponse
from app.services.auth_service import authenticate_user, create_access_token


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login", response_model=ApiResponse)
def login(payload: LoginRequest):
    user = authenticate_user(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(user)
    return ApiResponse(data={"access_token": token, "token_type": "bearer", "role": user.role, "username": user.username})


@router.get("/me", response_model=ApiResponse)
def me(user=Depends(get_current_user)):
    return ApiResponse(data={"username": user.username, "role": user.role})

