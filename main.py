import html
import os
from datetime import datetime, timedelta
from typing import Optional

import requests
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import AuditLog, ClientAccount, Order, OrderMessage, Task, User

APP_NAME = "RPC Team CRM Sync Server"
APP_VERSION = "2.0.0"
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_THIS_SECRET_KEY_RPC_2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = int(os.getenv("ACCESS_TOKEN_EXPIRE_DAYS", "30"))

ORDER_STATUSES = [
    "new",
    "discussion",
    "waiting_prepay",
    "in_work",
    "review",
    "done",
    "paid",
    "cancelled",
]
TASK_STATUSES = ["not_started", "in_work", "review", "done", "cancelled"]
ROLES = ["owner", "manager", "worker"]

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)

Base.metadata.create_all(bind=engine)


def ensure_schema() -> None:
    """Safe tiny migrations for old SQLite/PostgreSQL installs."""
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        with engine.begin() as conn:
            if "users" in tables:
                cols = {c["name"] for c in inspector.get_columns("users")}
                if "approved" not in cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN approved BOOLEAN DEFAULT 0"))
                    conn.execute(text("UPDATE users SET approved = 1 WHERE role = 'owner'"))
                if "is_active" not in cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1"))
                if "updated_at" not in cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN updated_at DATETIME"))
            if "orders" in tables:
                cols = {c["name"] for c in inspector.get_columns("orders")}
                add_cols = {
                    "priority": "VARCHAR(50) DEFAULT 'normal'",
                    "source": "VARCHAR(80) DEFAULT 'CRM'",
                    "client_account_id": "INTEGER",
                    "updated_at": "DATETIME",
                }
                for name, sql_type in add_cols.items():
                    if name not in cols:
                        conn.execute(text(f"ALTER TABLE orders ADD COLUMN {name} {sql_type}"))
            if "tasks" in tables:
                cols = {c["name"] for c in inspector.get_columns("tasks")}
                if "created_by_id" not in cols:
                    conn.execute(text("ALTER TABLE tasks ADD COLUMN created_by_id INTEGER"))
                if "updated_at" not in cols:
                    conn.execute(text("ALTER TABLE tasks ADD COLUMN updated_at DATETIME"))
    except Exception as exc:
        print("[schema] migration skipped:", exc)


ensure_schema()

app = FastAPI(title=APP_NAME, version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


class ClientRegisterIn(BaseModel):
    name: str
    email: EmailStr
    password: str


class ClientLoginIn(BaseModel):
    email: EmailStr
    password: str


class ClientTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    client: dict


class UserApproveIn(BaseModel):
    approved: bool = True


class UserActiveIn(BaseModel):
    is_active: bool = True


class UserRoleIn(BaseModel):
    role: str


class OrderIn(BaseModel):
    client_name: str
    contact: str = ""
    service: str
    price: float = 0
    prepaid: float = 0
    status: str = "new"
    priority: str = "normal"
    worker_id: Optional[int] = None
    deadline: str = ""
    notes: str = ""
    source: str = "CRM"


class PublicOrderIn(BaseModel):
    client_name: Optional[str] = ""
    name: Optional[str] = ""
    contact: str = ""
    service: str = ""
    price: Optional[float] = 0
    budget: Optional[float] = None
    deadline: str = ""
    notes: Optional[str] = ""
    description: Optional[str] = ""
    source: str = "Сайт"


class OrderPatchIn(BaseModel):
    client_name: Optional[str] = None
    contact: Optional[str] = None
    service: Optional[str] = None
    price: Optional[float] = None
    prepaid: Optional[float] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    worker_id: Optional[int] = None
    deadline: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = None


class StatusIn(BaseModel):
    status: str


class AssignIn(BaseModel):
    worker_id: Optional[int] = None


class TaskIn(BaseModel):
    title: str
    description: str = ""
    assignee_id: Optional[int] = None
    order_id: Optional[int] = None
    deadline: str = ""
    priority: str = "normal"
    status: str = "not_started"


class TaskPatchIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_id: Optional[int] = None
    order_id: Optional[int] = None
    deadline: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None


class MessageIn(BaseModel):
    text: str


def now_iso(value) -> str:
    return value.isoformat() if value else ""


def hash_password(password: str) -> str:
    return pwd_context.hash(password[:72])


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password[:72], password_hash)


def create_token(data: dict) -> str:
    payload = data.copy()
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload.update({"exp": expire})
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def user_dict(u: User) -> dict:
    return {
        "id": u.id,
        "name": u.name,
        "username": u.username,
        "role": u.role,
        "approved": bool(u.approved),
        "is_active": bool(u.is_active),
        "created_at": now_iso(u.created_at),
        "updated_at": now_iso(u.updated_at),
    }


def client_dict(c: ClientAccount) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "email": c.email,
        "provider": c.provider,
        "is_active": bool(c.is_active),
        "created_at": now_iso(c.created_at),
        "updated_at": now_iso(c.updated_at),
    }


def order_dict(o: Order) -> dict:
    price = float(o.price or 0)
    prepaid = float(o.prepaid or 0)
    return {
        "id": o.id,
        "public_id": f"RPC-{str(o.id).zfill(5)}",
        "client_name": o.client_name,
        "contact": o.contact or "",
        "service": o.service,
        "price": price,
        "prepaid": prepaid,
        "rest": max(0, price - prepaid),
        "status": o.status,
        "priority": o.priority or "normal",
        "worker_id": o.worker_id,
        "worker_name": o.worker.name if o.worker else "",
        "client_account_id": o.client_account_id,
        "deadline": o.deadline or "",
        "notes": o.notes or "",
        "source": o.source or "CRM",
        "created_at": now_iso(o.created_at),
        "updated_at": now_iso(o.updated_at),
    }


def task_dict(t: Task) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "description": t.description or "",
        "status": t.status,
        "priority": t.priority or "normal",
        "deadline": t.deadline or "",
        "assignee_id": t.assignee_id,
        "assignee_name": t.assignee.name if t.assignee else "",
        "order_id": t.order_id,
        "created_by_id": t.created_by_id,
        "created_at": now_iso(t.created_at),
        "updated_at": now_iso(t.updated_at),
    }


def message_dict(m: OrderMessage) -> dict:
    return {
        "id": m.id,
        "order_id": m.order_id,
        "author_type": m.author_type,
        "author_name": m.author_name,
        "text": m.text,
        "created_at": now_iso(m.created_at),
    }


def audit(db: Session, user: Optional[User], action: str, entity: str = "", entity_id: Optional[int] = None, details: str = "") -> None:
    try:
        db.add(AuditLog(
            actor_id=user.id if user else None,
            actor_name=user.name if user else "system",
            action=action,
            entity=entity,
            entity_id=entity_id,
            details=details[:2000],
        ))
        db.commit()
    except Exception as exc:
        db.rollback()
        print("[audit] skipped:", exc)


def send_telegram_notification(text_msg: str) -> bool:
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
        r = requests.post(url, json=payload, timeout=10)
        return r.ok
    except Exception as exc:
        print("[telegram] error:", exc)
        return False


def order_telegram_text(o: Order) -> str:
    notes = (o.notes or "")[:900]
    if len(o.notes or "") > 900:
        notes += "..."
    return (
        "🔥 <b>Новый заказ RPC</b>\n\n"
        f"🧾 Заявка: <b>RPC-{str(o.id).zfill(5)}</b>\n"
        f"👤 Клиент: {html.escape(o.client_name or '')}\n"
        f"📞 Контакт: {html.escape(o.contact or '')}\n"
        f"🛠 Услуга: {html.escape(o.service or '')}\n"
        f"💰 Бюджет: {o.price or 0}\n"
        f"⏰ Дедлайн: {html.escape(o.deadline or 'не указан')}\n"
        f"📌 Источник: {html.escape(o.source or 'Сайт')}\n"
        f"📍 Статус: {html.escape(o.status or 'new')}\n\n"
        f"📝 Описание:\n{html.escape(notes)}\n\n"
        "Открой RPC Team CRM, чтобы назначить работника."
    )


def get_user_by_token(token: Optional[str], db: Session, unchecked: bool = False) -> User:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") == "client":
            raise HTTPException(status_code=401, detail="Client token is not allowed here")
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if unchecked:
        return user
    if not bool(user.is_active):
        raise HTTPException(status_code=403, detail="Account disabled")
    if user.role != "owner" and not bool(user.approved):
        raise HTTPException(status_code=403, detail="Account is waiting for owner approval")
    return user


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    return get_user_by_token(token, db)


async def get_current_user_unchecked(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    return get_user_by_token(token, db, unchecked=True)


async def get_current_client(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> ClientAccount:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "client":
            raise HTTPException(status_code=401, detail="Invalid client token")
        client_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid client token")
    client = db.query(ClientAccount).filter(ClientAccount.id == client_id).first()
    if not client or not bool(client.is_active):
        raise HTTPException(status_code=401, detail="Client not found or disabled")
    return client


def optional_client_from_header(authorization: Optional[str], db: Session) -> Optional[ClientAccount]:
    if not authorization:
        return None
    token = authorization.strip()
    if token.lower().startswith("bearer "):
        token = token.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "client":
            return None
        return db.query(ClientAccount).filter(ClientAccount.id == int(payload.get("sub"))).first()
    except Exception:
        return None


def require_owner(user: User) -> None:
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Only owner can do this")


def require_owner_or_manager(user: User) -> None:
    if user.role not in ["owner", "manager"]:
        raise HTTPException(status_code=403, detail="Only owner/manager can do this")


def require_order_access(order: Order, user: User) -> None:
    if user.role == "worker" and order.worker_id != user.id:
        raise HTTPException(status_code=403, detail="This is not your order")


def require_task_access(task: Task, user: User) -> None:
    if user.role == "worker" and task.assignee_id != user.id:
        raise HTTPException(status_code=403, detail="This is not your task")


@app.get("/")
def root():
    return {"app": APP_NAME, "version": APP_VERSION, "status": "online", "docs": "/docs"}


@app.get("/health")
def health(db: Session = Depends(get_db)):
    return {"ok": True, "time": datetime.utcnow().isoformat(), "users": db.query(User).count(), "orders": db.query(Order).count()}


@app.get("/meta")
def meta():
    return {"order_statuses": ORDER_STATUSES, "task_statuses": TASK_STATUSES, "roles": ROLES}


@app.post("/auth/register", response_model=TokenOut)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    username = data.username.strip().lower()
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 symbols")
    if len(data.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 symbols")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already exists")

    users_count = db.query(User).count()
    role = data.role.strip().lower()
    if users_count == 0:
        role = "owner"
        approved = True
    else:
        role = role if role in ["manager", "worker"] else "worker"
        approved = False

    user = User(
        name=data.name.strip() or username,
        username=username,
        password_hash=hash_password(data.password),
        role=role,
        approved=approved,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit(db, user, "register", "user", user.id, f"role={role}")
    token = create_token({"sub": str(user.id), "role": user.role})
    return {"access_token": token, "user": user_dict(user)}


@app.post("/auth/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username.strip().lower()).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong login or password")
    if not bool(user.is_active):
        raise HTTPException(status_code=403, detail="Account disabled")
    token = create_token({"sub": str(user.id), "role": user.role})
    return {"access_token": token, "user": user_dict(user)}


@app.post("/auth/token")
def login_for_docs(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username.strip().lower()).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong login or password")
    if not bool(user.is_active):
        raise HTTPException(status_code=403, detail="Account disabled")
    return {"access_token": create_token({"sub": str(user.id), "role": user.role}), "token_type": "bearer"}


@app.get("/me")
def me(user: User = Depends(get_current_user_unchecked)):
    return user_dict(user)


@app.post("/client/register", response_model=ClientTokenOut)
def client_register(data: ClientRegisterIn, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    if len(data.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 symbols")
    if db.query(ClientAccount).filter(ClientAccount.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    client = ClientAccount(name=data.name.strip() or email, email=email, password_hash=hash_password(data.password))
    db.add(client)
    db.commit()
    db.refresh(client)
    token = create_token({"sub": str(client.id), "type": "client"})
    return {"access_token": token, "client": client_dict(client)}


@app.post("/client/login", response_model=ClientTokenOut)
def client_login(data: ClientLoginIn, db: Session = Depends(get_db)):
    client = db.query(ClientAccount).filter(ClientAccount.email == data.email.strip().lower()).first()
    if not client or not verify_password(data.password, client.password_hash):
        raise HTTPException(status_code=401, detail="Wrong email or password")
    token = create_token({"sub": str(client.id), "type": "client"})
    return {"access_token": token, "client": client_dict(client)}


@app.get("/client/me")
def client_me(client: ClientAccount = Depends(get_current_client)):
    return client_dict(client)


@app.get("/client/orders")
def client_orders(client: ClientAccount = Depends(get_current_client), db: Session = Depends(get_db)):
    orders = db.query(Order).filter(Order.client_account_id == client.id).order_by(Order.id.desc()).all()
    return [order_dict(o) for o in orders]


@app.get("/client/orders/{order_id}/messages")
def client_order_messages(order_id: int, client: ClientAccount = Depends(get_current_client), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id, Order.client_account_id == client.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return [message_dict(m) for m in db.query(OrderMessage).filter(OrderMessage.order_id == order.id).order_by(OrderMessage.id.asc()).all()]


@app.post("/client/orders/{order_id}/messages")
def client_add_message(order_id: int, data: MessageIn, client: ClientAccount = Depends(get_current_client), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id, Order.client_account_id == client.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    msg = OrderMessage(order_id=order.id, author_type="client", author_name=client.name, text=data.text.strip())
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return message_dict(msg)


@app.post("/public/orders")
def public_create_order(data: PublicOrderIn, db: Session = Depends(get_db), authorization: Optional[str] = Header(None)):
    client = optional_client_from_header(authorization, db)
    client_name = (data.client_name or data.name or "Клиент с сайта").strip()
    notes = (data.notes or data.description or "").strip()
    price = data.price if data.price not in [None, 0] else (data.budget or 0)
    order = Order(
        client_name=client_name,
        contact=data.contact.strip(),
        service=(data.service or "Не указано").strip(),
        price=float(price or 0),
        prepaid=0,
        status="new",
        priority="normal",
        worker_id=None,
        client_account_id=client.id if client else None,
        deadline=data.deadline.strip(),
        notes=notes,
        source=data.source or "Сайт",
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    send_telegram_notification(order_telegram_text(order))
    audit(db, None, "public_order_created", "order", order.id, order.source or "Сайт")
    return {"ok": True, "message": "Order received", "order": order_dict(order)}


@app.post("/public/order")
def public_create_order_alias(data: PublicOrderIn, db: Session = Depends(get_db), authorization: Optional[str] = Header(None)):
    return public_create_order(data, db, authorization)


@app.get("/public/orders/{order_id}")
def public_order_status(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return {
        "id": order.id,
        "public_id": f"RPC-{str(order.id).zfill(5)}",
        "client_name": order.client_name,
        "service": order.service,
        "status": order.status,
        "deadline": order.deadline,
        "created_at": now_iso(order.created_at),
    }


@app.get("/public/queue")
def public_queue(db: Session = Depends(get_db)):
    orders = db.query(Order).all()
    counts = {s: 0 for s in ORDER_STATUSES}
    for o in orders:
        counts[o.status or "new"] = counts.get(o.status or "new", 0) + 1
    busy = counts.get("new", 0) + counts.get("discussion", 0) + counts.get("waiting_prepay", 0) + counts.get("in_work", 0) + counts.get("review", 0)
    counts["total"] = len(orders)
    counts["free_slots"] = max(0, int(os.getenv("RPC_FREE_SLOTS", "5")) - busy)
    return counts


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
    audit(db, user, "user_approval_changed", "user", target.id, str(data.approved))
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
    audit(db, user, "user_active_changed", "user", target.id, str(data.is_active))
    return user_dict(target)


@app.patch("/users/{user_id}/role")
def set_user_role(user_id: int, data: UserRoleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner(user)
    role = data.role.strip().lower()
    if role not in ROLES:
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
    audit(db, user, "user_role_changed", "user", target.id, role)
    return user_dict(target)


@app.get("/orders")
def list_orders(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    status_filter: Optional[str] = Query(None, alias="status"),
    worker_id: Optional[int] = None,
    search: str = "",
    limit: int = 300,
):
    q = db.query(Order).order_by(Order.id.desc())
    if user.role == "worker":
        q = q.filter(Order.worker_id == user.id)
    elif worker_id is not None:
        q = q.filter(Order.worker_id == worker_id)
    if status_filter:
        q = q.filter(Order.status == status_filter)
    if search.strip():
        s = f"%{search.strip()}%"
        q = q.filter((Order.client_name.ilike(s)) | (Order.contact.ilike(s)) | (Order.service.ilike(s)) | (Order.notes.ilike(s)))
    return [order_dict(o) for o in q.limit(max(1, min(limit, 1000))).all()]


@app.post("/orders")
def create_order(data: OrderIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner_or_manager(user)
    status_value = data.status if data.status in ORDER_STATUSES else "new"
    order = Order(**data.model_dump(exclude={"status"}), status=status_value)
    db.add(order)
    db.commit()
    db.refresh(order)
    audit(db, user, "order_created", "order", order.id, order.client_name)
    return order_dict(order)


@app.get("/orders/{order_id}")
def get_order(order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    require_order_access(order, user)
    return order_dict(order)


@app.patch("/orders/{order_id}")
def patch_order(order_id: int, data: OrderPatchIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    require_order_access(order, user)
    patch = data.model_dump(exclude_unset=True)
    if user.role == "worker":
        allowed = {"status", "notes"}
        patch = {k: v for k, v in patch.items() if k in allowed}
    if "status" in patch and patch["status"] not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail="Bad status")
    for key, value in patch.items():
        setattr(order, key, value)
    db.commit()
    db.refresh(order)
    audit(db, user, "order_updated", "order", order.id, str(patch))
    return order_dict(order)


@app.patch("/orders/{order_id}/status")
def update_order_status(order_id: int, data: StatusIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if data.status not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail="Bad status")
    return patch_order(order_id, OrderPatchIn(status=data.status), user, db)


@app.patch("/orders/{order_id}/assign")
def assign_order(order_id: int, data: AssignIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner_or_manager(user)
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if data.worker_id is not None:
        worker = db.query(User).filter(User.id == data.worker_id).first()
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found")
        if worker.role not in ["worker", "manager", "owner"] or not bool(worker.is_active):
            raise HTTPException(status_code=400, detail="Bad worker")
    order.worker_id = data.worker_id
    if order.status == "new" and data.worker_id:
        order.status = "in_work"
    db.commit()
    db.refresh(order)
    audit(db, user, "order_assigned", "order", order.id, str(data.worker_id))
    return order_dict(order)


@app.delete("/orders/{order_id}")
def delete_order(order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner(user)
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    db.delete(order)
    db.commit()
    audit(db, user, "order_deleted", "order", order_id, "")
    return {"ok": True}


@app.get("/orders/{order_id}/messages")
def order_messages(order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    require_order_access(order, user)
    return [message_dict(m) for m in db.query(OrderMessage).filter(OrderMessage.order_id == order.id).order_by(OrderMessage.id.asc()).all()]


@app.post("/orders/{order_id}/messages")
def add_order_message(order_id: int, data: MessageIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    require_order_access(order, user)
    msg = OrderMessage(order_id=order.id, author_type="team", author_name=user.name, text=data.text.strip())
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return message_dict(msg)


@app.get("/tasks")
def list_tasks(user: User = Depends(get_current_user), db: Session = Depends(get_db), status_filter: Optional[str] = Query(None, alias="status"), limit: int = 300):
    q = db.query(Task).order_by(Task.id.desc())
    if user.role == "worker":
        q = q.filter(Task.assignee_id == user.id)
    if status_filter:
        q = q.filter(Task.status == status_filter)
    return [task_dict(t) for t in q.limit(max(1, min(limit, 1000))).all()]


@app.post("/tasks")
def create_task(data: TaskIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner_or_manager(user)
    status_value = data.status if data.status in TASK_STATUSES else "not_started"
    task = Task(**data.model_dump(exclude={"status"}), status=status_value, created_by_id=user.id)
    db.add(task)
    db.commit()
    db.refresh(task)
    audit(db, user, "task_created", "task", task.id, task.title)
    return task_dict(task)


@app.patch("/tasks/{task_id}")
def patch_task(task_id: int, data: TaskPatchIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    require_task_access(task, user)
    patch = data.model_dump(exclude_unset=True)
    if user.role == "worker":
        patch = {k: v for k, v in patch.items() if k in ["status"]}
    if "status" in patch and patch["status"] not in TASK_STATUSES:
        raise HTTPException(status_code=400, detail="Bad status")
    for key, value in patch.items():
        setattr(task, key, value)
    db.commit()
    db.refresh(task)
    audit(db, user, "task_updated", "task", task.id, str(patch))
    return task_dict(task)


@app.patch("/tasks/{task_id}/status")
def update_task_status(task_id: int, data: StatusIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if data.status not in TASK_STATUSES:
        raise HTTPException(status_code=400, detail="Bad status")
    return patch_task(task_id, TaskPatchIn(status=data.status), user, db)


@app.get("/admin/site/summary")
def admin_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner_or_manager(user)
    all_orders = db.query(Order).all()
    status_counts = {s: 0 for s in ORDER_STATUSES}
    revenue_total = 0.0
    revenue_prepaid = 0.0
    for o in all_orders:
        status_counts[o.status or "new"] = status_counts.get(o.status or "new", 0) + 1
        revenue_total += float(o.price or 0)
        revenue_prepaid += float(o.prepaid or 0)
    return {
        "clients": db.query(ClientAccount).count(),
        "workers": db.query(User).filter(User.role == "worker").count(),
        "orders_total": len(all_orders),
        "status_counts": status_counts,
        "revenue_total": revenue_total,
        "revenue_prepaid": revenue_prepaid,
        "last_orders": [order_dict(o) for o in db.query(Order).order_by(Order.id.desc()).limit(20).all()],
    }


@app.get("/admin/database/status")
def database_status(user: User = Depends(get_current_user)):
    require_owner(user)
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        safe = url
        if "@" in safe:
            safe = "postgresql://***:***@" + safe.split("@", 1)[1]
        return {"mode": "postgresql", "persistent": True, "database": safe}
    return {"mode": "sqlite", "persistent": False, "warning": "DATABASE_URL is empty. On Render, SQLite can reset after redeploy."}


@app.post("/admin/telegram/test")
def telegram_test(user: User = Depends(get_current_user)):
    require_owner(user)
    ok = send_telegram_notification("✅ <b>RPC Telegram уведомления работают</b>\n\nНовые заявки будут приходить сюда.")
    if not ok:
        raise HTTPException(status_code=400, detail="Telegram variables are not configured")
    return {"ok": True, "message": "Telegram test sent"}
