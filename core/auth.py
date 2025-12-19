from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .config import settings
from .database import get_db
from .dev_config import DEV_MODE, MOCK_USER_ID, MOCK_TOKEN
from models import User
import uuid

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    # DEV_MODE: Accept mock token
    if DEV_MODE and credentials.credentials == MOCK_TOKEN:
        return MOCK_USER_ID
    
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=[settings.algorithm])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user_id
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_current_user(user_id: str = Depends(verify_token), db: Session = Depends(get_db)):
    # DEV_MODE: Create or get mock user
    if DEV_MODE and user_id == MOCK_USER_ID:
        mock_user = db.query(User).filter(User.id == MOCK_USER_ID).first()
        if not mock_user:
            # Create mock user if doesn't exist
            mock_user = User(
                id=MOCK_USER_ID,
                name="นักพัฒนา",
                username="developer",
                email="dev@example.com",
                password_hash=get_password_hash("dev123"),
                is_active=True,
            )
            db.add(mock_user)
            db.commit()
            db.refresh(mock_user)
            print("🔧 DEV_MODE: Created mock user in database")
        return mock_user
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    return user

def authenticate_user(db: Session, username_or_email: str, password: str):
    user = db.query(User).filter(
        (User.username == username_or_email) | (User.email == username_or_email)
    ).first()
    if not user:
        return False
    if not verify_password(password, user.password_hash):
        return False
    return user

