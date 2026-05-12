import requests
from datetime import datetime, timedelta
import os
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, status, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text

from database import Base, engine, get_db
from models import User, Order, Task, ClientAccount

APP_NAME = "RPC Team CRM Server"
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_THIS_SECRET_KEY_IN_PRODUCTION_RPC_2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30


def send_telegram_notification(text_msg: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text_msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        requests.post(url, json=payload, timeout=8)
        return True
    except Exception as e:
        print("Telegram notification error:", e)
        return False


def order_telegram_text(order):
    price = getattr(order, "price", 0) or 0
    deadline = getattr(order, "deadline", "") or "не указан"
    notes = getattr(order, "notes", "") or ""
    if len(notes) > 900:
        notes = notes[:900] + "..."

    return (
        "🔥 <b>Новый заказ RPC</b>\n\n"
        f"🆔 <b>Заявка:</b> RPC-{str(order.id).zfill(5)}\n"
        f"👤 <b>Клиент:</b> {order.client_name}\n"
        f"📞 <b>Контакт:</b> {order.contact}\n"
        f"🛠 <b>Услуга:</b> {order.service}\n"
        f"💰 <b>Бюджет:</b> {price}\n"
        f"⏰ <b>Дедлайн:</b> {deadline}\n"
        f"📌 <b>Статус:</b> {order.status}\n\n"
        f"📝 <b>Описание:</b>\n{notes}\n\n"
        "Открой RPC Team CRM, чтобы назначить работника."
    )


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
        if "orders" in inspector.get_table_names():
            order_columns = {c["name"] for c in inspector.get_columns("orders")}
            with engine.begin() as conn:
                if "client_account_id" not in order_columns:
                    conn.execute(text("ALTER TABLE orders ADD COLUMN client_account_id INTEGER"))
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
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

class RegisterIn(BaseModel):
    name: str
    username: str
    password: str
    role: str = "worker"

class LoginIn(BaseModel):
    username: str
    password: str

class ClientRegisterIn(BaseModel):
    name: str
    email: str
    password: str

class ClientLoginIn(BaseModel):
    email: str
    password: str

class ClientTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    client: dict

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

def client_dict(client: ClientAccount):
    return {
        "id": client.id,
        "name": client.name,
        "email": client.email,
        "provider": client.provider,
        "created_at": client.created_at.isoformat() if client.created_at else "",
    }

def create_client_token(client: ClientAccount) -> str:
    return create_token({"sub": str(client.id), "type": "client"})

async def get_current_client(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> ClientAccount:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "client":
            raise HTTPException(status_code=401, detail="Invalid client token")
        client_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid client token")
    client = db.query(ClientAccount).filter(ClientAccount.id == int(client_id)).first()
    if not client:
        raise HTTPException(status_code=401, detail="Client not found")
    return client

def get_optional_client(token: Optional[str], db: Session):
    if not token:
        return None
    try:
        if token.lower().startswith("bearer "):
            token = token.split(" ", 1)[1]
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "client":
            return None
        return db.query(ClientAccount).filter(ClientAccount.id == int(payload.get("sub"))).first()
    except Exception:
        return None

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        try:
            user_id_int = int(user_id)
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token. Please login again.")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == user_id_int).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not bool(getattr(user, "is_active", True)):
        raise HTTPException(status_code=403, detail="Account disabled")
    if user.role != "owner" and not bool(getattr(user, "approved", False)):
        raise HTTPException(status_code=403, detail="Account is waiting for owner approval")
    return user

def client_dict(client: ClientAccount):
    return {
        "id": client.id,
        "name": client.name,
        "email": client.email,
        "provider": client.provider,
        "created_at": client.created_at.isoformat() if client.created_at else "",
    }

def create_client_token(client: ClientAccount) -> str:
    return create_token({"sub": str(client.id), "type": "client"})

async def get_current_client(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> ClientAccount:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "client":
            raise HTTPException(status_code=401, detail="Invalid client token")
        client_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid client token")
    client = db.query(ClientAccount).filter(ClientAccount.id == int(client_id)).first()
    if not client:
        raise HTTPException(status_code=401, detail="Client not found")
    return client

def get_optional_client(token: Optional[str], db: Session):
    if not token:
        return None
    try:
        if token.lower().startswith("bearer "):
            token = token.split(" ", 1)[1]
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "client":
            return None
        return db.query(ClientAccount).filter(ClientAccount.id == int(payload.get("sub"))).first()
    except Exception:
        return None

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


@app.post("/auth/token")
def login_for_swagger_docs(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Swagger /docs Authorize fix.
    This endpoint accepts OAuth2 form data from the green Authorize button.
    Normal JSON login still works at POST /auth/login.
    """
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong login or password")
    if hasattr(user, "is_active") and user.is_active is False:
        raise HTTPException(status_code=403, detail="User is disabled")
    return {
        "access_token": create_token({"sub": str(user.id), "role": user.role}),
        "token_type": "bearer"
    }


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
def public_create_order(data: OrderIn, db: Session = Depends(get_db), authorization: Optional[str] = Header(None)):
    """Public website order form. No login required. If client token is provided, binds order to client account."""
    client = get_optional_client(authorization, db)
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
    if client:
        try:
            order.client_account_id = client.id
        except Exception:
            pass
    db.add(order)
    db.commit()
    db.refresh(order)

    try:
        send_telegram_notification(order_telegram_text(order))
    except Exception as e:
        print("Telegram notification failed:", e)

    return order_dict(order)


@app.get("/public/orders/{order_id}")
def public_get_order_status(order_id: int, db: Session = Depends(get_db)):
    """Public status check for website clients."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return {
        "id": order.id,
        "client_name": order.client_name,
        "service": order.service,
        "status": order.status,
        "deadline": order.deadline,
        "created_at": order.created_at.isoformat() if order.created_at else "",
    }


@app.post("/client/register", response_model=ClientTokenOut)
def client_register(data: ClientRegisterIn, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    if len(data.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 symbols")
    if db.query(ClientAccount).filter(ClientAccount.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    client = ClientAccount(
        name=data.name.strip() or email,
        email=email,
        password_hash=hash_password(data.password),
        provider="email",
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return {"access_token": create_client_token(client), "client": client_dict(client)}

@app.post("/client/login", response_model=ClientTokenOut)
def client_login(data: ClientLoginIn, db: Session = Depends(get_db)):
    client = db.query(ClientAccount).filter(ClientAccount.email == data.email.strip().lower()).first()
    if not client or not verify_password(data.password, client.password_hash):
        raise HTTPException(status_code=401, detail="Wrong email or password")
    return {"access_token": create_client_token(client), "client": client_dict(client)}

@app.get("/client/me")
def client_me(client: ClientAccount = Depends(get_current_client)):
    return client_dict(client)

@app.get("/client/orders")
def client_orders(client: ClientAccount = Depends(get_current_client), db: Session = Depends(get_db)):
    try:
        orders = db.query(Order).filter(Order.client_account_id == client.id).order_by(Order.id.desc()).all()
    except Exception:
        orders = []
    return [order_dict(o) for o in orders]

@app.get("/public/queue")
def public_queue(db: Session = Depends(get_db)):
    orders = db.query(Order).all()
    def count(statuses):
        return len([o for o in orders if (o.status or "new") in statuses])
    return {
        "new": count(["new"]),
        "discussion": count(["discussion", "Обсуждение"]),
        "waiting_prepay": count(["waiting_prepay", "Ожидает предоплату"]),
        "in_work": count(["in_work", "В работе"]),
        "review": count(["review", "На проверке"]),
        "done": count(["done", "Готово"]),
        "paid": count(["paid", "Оплачено"]),
        "total": len(orders),
        "free_slots": max(0, 5 - count(["new", "discussion", "waiting_prepay", "in_work", "review"]))
    }

@app.get("/admin/site/summary")
def admin_site_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner(user)
    orders = db.query(Order).order_by(Order.id.desc()).limit(50).all()
    return {
        "clients": db.query(ClientAccount).count(),
        "orders_total": db.query(Order).count(),
        "orders_new": db.query(Order).filter(Order.status == "new").count(),
        "orders_in_work": db.query(Order).filter(Order.status == "in_work").count(),
        "last_orders": [order_dict(o) for o in orders],
    }



@app.get("/admin/database/status")
def admin_database_status(user: User = Depends(get_current_user)):
    require_owner(user)
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        safe = url
        if "@" in safe:
            safe = safe.split("@", 1)[1]
            safe = "postgresql://***:***@" + safe
        return {"mode": "postgresql", "persistent": True, "database": safe}
    return {
        "mode": "sqlite",
        "persistent": False,
        "warning": "DATABASE_URL is not configured. Accounts can disappear after Render restart/redeploy."
    }

@app.post("/admin/telegram/test")
def admin_telegram_test(user: User = Depends(get_current_user)):
    require_owner(user)
    ok = send_telegram_notification("✅ <b>RPC Telegram уведомления работают</b>\n\nТеперь новые заявки будут приходить на телефон.")
    if not ok:
        raise HTTPException(status_code=400, detail="Telegram variables are not configured")
    return {"ok": True, "message": "Telegram test notification sent"}

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
