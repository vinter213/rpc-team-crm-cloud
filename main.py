from datetime import datetime, timedelta
import os
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import User, Order, Task

APP_NAME = "RPC Team CRM Server"
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_THIS_SECRET_KEY_IN_PRODUCTION_RPC_2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

Base.metadata.create_all(bind=engine)

app = FastAPI(title=APP_NAME, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

class RegisterIn(BaseModel):
    name: str
    username: str
    password: str
    role: str = "worker"

class LoginIn(BaseModel):
    username: str
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class TaskIn(BaseModel):
    title: str
    description: str = ""
    assignee_id: Optional[int] = None
    deadline: str = ""
    priority: str = "normal"
    order_id: Optional[int] = None

class TaskStatusIn(BaseModel):
    status: str

class OrderIn(BaseModel):
    client_name: str
    contact: str = ""
    service: str
    price: float = 0
    prepaid: float = 0
    status: str = "new"
    worker_id: Optional[int] = None
    deadline: str = ""
    notes: str = ""

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)

def create_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def user_dict(user: User):
    return {"id": user.id, "name": user.name, "username": user.username, "role": user.role}

def task_dict(t: Task):
    return {
        "id": t.id,
        "title": t.title,
        "description": t.description,
        "status": t.status,
        "priority": t.priority,
        "deadline": t.deadline,
        "assignee_id": t.assignee_id,
        "order_id": t.order_id,
        "created_at": t.created_at.isoformat() if t.created_at else "",
    }

def order_dict(o: Order):
    return {
        "id": o.id,
        "client_name": o.client_name,
        "contact": o.contact,
        "service": o.service,
        "price": o.price,
        "prepaid": o.prepaid,
        "rest": max(0, (o.price or 0) - (o.prepaid or 0)),
        "status": o.status,
        "worker_id": o.worker_id,
        "deadline": o.deadline,
        "notes": o.notes,
        "created_at": o.created_at.isoformat() if o.created_at else "",
    }

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def require_owner_or_manager(user: User):
    if user.role not in ["owner", "manager"]:
        raise HTTPException(status_code=403, detail="Only owner/manager can do this")

@app.get("/")
def root():
    return {"app": APP_NAME, "status": "online", "docs": "/docs"}

@app.post("/auth/register", response_model=TokenOut)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    if len(data.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 symbols")
    if len(data.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password is too long. Use up to 72 bytes / about 36-72 symbols")
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    users_count = db.query(User).count()
    role = data.role.lower().strip()
    if users_count == 0:
        role = "owner"
    elif role not in ["worker", "manager"]:
        role = "worker"
    user = User(name=data.name, username=data.username, password_hash=hash_password(data.password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_token({"sub": str(user.id), "role": user.role})
    return {"access_token": token, "user": user_dict(user)}

@app.post("/auth/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong login or password")
    token = create_token({"sub": str(user.id), "role": user.role})
    return {"access_token": token, "user": user_dict(user)}

@app.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_dict(user)

@app.get("/users")
def list_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner_or_manager(user)
    return [user_dict(u) for u in db.query(User).order_by(User.id.desc()).all()]

@app.post("/tasks")
def create_task(data: TaskIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner_or_manager(user)
    task = Task(**data.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task_dict(task)

@app.get("/tasks")
def list_tasks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Task).order_by(Task.id.desc())
    if user.role == "worker":
        q = q.filter(Task.assignee_id == user.id)
    return [task_dict(t) for t in q.all()]

@app.patch("/tasks/{task_id}/status")
def update_task_status(task_id: int, data: TaskStatusIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if user.role == "worker" and task.assignee_id != user.id:
        raise HTTPException(status_code=403, detail="This is not your task")
    task.status = data.status
    db.commit()
    db.refresh(task)
    return task_dict(task)

@app.post("/orders")
def create_order(data: OrderIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner_or_manager(user)
    order = Order(**data.model_dump())
    db.add(order)
    db.commit()
    db.refresh(order)
    return order_dict(order)

@app.get("/orders")
def list_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Order).order_by(Order.id.desc())
    if user.role == "worker":
        q = q.filter(Order.worker_id == user.id)
    return [order_dict(o) for o in q.all()]
