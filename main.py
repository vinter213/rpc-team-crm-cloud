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
from sqlalchemy import inspect, text

from database import Base, engine, get_db
from models import User, Order, Task

APP_NAME = "RPC Team CRM Server"
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_THIS_SECRET_KEY_IN_PRODUCTION_RPC_2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

Base.metadata.create_all(bind=engine)

def ensure_schema():
    """Small safe SQLite migration for users that installed older builds."""
    try:
        inspector = inspect(engine)
        if "users" in inspector.get_table_names():
            columns = {c["name"] for c in inspector.get_columns("users")}
            with engine.begin() as conn:
                if "approved" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN approved BOOLEAN DEFAULT 0"))
                    conn.execute(text("UPDATE users SET approved = 1 WHERE role = 'owner'"))
                if "is_active" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1"))
    except Exception:
        pass

ensure_schema()

app = FastAPI(title=APP_NAME, version="1.2.0")
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

class UserApproveIn(BaseModel):
    approved: bool = True

class UserActiveIn(BaseModel):
    is_active: bool = True

class UserRoleIn(BaseModel):
    role: str

class OrderStatusIn(BaseModel):
    status: str

def hash_password(password: str) -> str:
    return pwd_context.hash(password[:72])

def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password[:72], password_hash)

def create_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def user_dict(user: User):
    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "role": user.role,
        "approved": bool(getattr(user, "approved", False)),
        "is_active": bool(getattr(user, "is_active", True)),
        "created_at": user.created_at.isoformat() if user.created_at else "",
    }

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
    if not bool(getattr(user, "is_active", True)):
        raise HTTPException(status_code=403, detail="Account disabled")
    if user.role != "owner" and not bool(getattr(user, "approved", False)):
        raise HTTPException(status_code=403, detail="Account is waiting for owner approval")
    return user

async def get_current_user_unchecked(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def require_owner(user: User):
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Only owner can do this")

def require_owner_or_manager(user: User):
    if user.role not in ["owner", "manager"]:
        raise HTTPException(status_code=403, detail="Only owner/manager can do this")

@app.get("/")
def root():
    return {"app": APP_NAME, "status": "online", "version": "1.2.0", "docs": "/docs"}

@app.post("/auth/register", response_model=TokenOut)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    if len(data.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 symbols")
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    users_count = db.query(User).count()
    role = data.role.lower().strip()
    approved = False
    if users_count == 0:
        role = "owner"
        approved = True
    elif role not in ["worker", "manager"]:
        role = "worker"
    user = User(
        name=data.name.strip() or data.username.strip(),
        username=data.username.strip(),
        password_hash=hash_password(data.password),
        role=role,
        approved=approved,
        is_active=True,
    )
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
    if not bool(getattr(user, "is_active", True)):
        raise HTTPException(status_code=403, detail="Account disabled")
    token = create_token({"sub": str(user.id), "role": user.role})
    return {"access_token": token, "user": user_dict(user)}

@app.get("/me")
def me(user: User = Depends(get_current_user_unchecked)):
    return user_dict(user)

@app.get("/users")
def list_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner_or_manager(user)
    q = db.query(User).order_by(User.id.desc())
    if user.role == "manager":
        q = q.filter(User.role != "owner")
    return [user_dict(u) for u in q.all()]

@app.patch("/users/{user_id}/approve")
def approve_user(user_id: int, data: UserApproveIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner(user)
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.role == "owner" and target.id != user.id:
        raise HTTPException(status_code=403, detail="Cannot change another owner")
    target.approved = data.approved
    db.commit()
    db.refresh(target)
    return user_dict(target)

@app.patch("/users/{user_id}/active")
def set_user_active(user_id: int, data: UserActiveIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner(user)
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="You cannot disable yourself")
    target.is_active = data.is_active
    db.commit()
    db.refresh(target)
    return user_dict(target)

@app.patch("/users/{user_id}/role")
def set_user_role(user_id: int, data: UserRoleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner(user)
    role = data.role.lower().strip()
    if role not in ["owner", "manager", "worker"]:
        raise HTTPException(status_code=400, detail="Bad role")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == user.id and role != "owner":
        raise HTTPException(status_code=400, detail="You cannot remove owner role from yourself")
    target.role = role
    if role == "owner":
        target.approved = True
    db.commit()
    db.refresh(target)
    return user_dict(target)


@app.post("/public/orders")
def public_create_order(data: OrderIn, db: Session = Depends(get_db)):
    """Public website order form. No login required."""
    order = Order(
        client_name=data.client_name.strip(),
        contact=data.contact.strip(),
        service=data.service.strip(),
        price=data.price,
        prepaid=0,
        status="new",
        worker_id=None,
        deadline=data.deadline,
        notes=data.notes,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order_dict(order)

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

@app.patch("/orders/{order_id}/status")
def update_order_status(order_id: int, data: OrderStatusIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if user.role == "worker" and order.worker_id != user.id:
        raise HTTPException(status_code=403, detail="This is not your order")
    order.status = data.status
    db.commit()
    db.refresh(order)
    return order_dict(order)
