from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import User, UserPreferences
from app.schemas import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from app.services.auth import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _is_guest(user: User) -> bool:
    return user.password_hash is None


def _auth_response(user: User) -> AuthResponse:
    is_guest = _is_guest(user)
    email = user.email or "guest"
    token = create_access_token(user.id, email)
    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user_id=user.id,
        email=email,
        is_guest=is_guest,
    )


@router.post("/register", response_model=AuthResponse)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    await db.flush()
    db.add(UserPreferences(user_id=user.id))
    await db.commit()
    await db.refresh(user)
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return _auth_response(user)


@router.post("/guest", response_model=AuthResponse)
async def guest(db: AsyncSession = Depends(get_db)):
    user = User(email=None, password_hash=None)
    db.add(user)
    await db.flush()
    db.add(UserPreferences(user_id=user.id))
    await db.commit()
    await db.refresh(user)
    return _auth_response(user)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        user_id=current_user.id,
        email=current_user.email or "guest",
        is_guest=_is_guest(current_user),
    )