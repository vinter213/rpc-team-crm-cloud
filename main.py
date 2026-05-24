import html
import os
from datetime import datetime, timedelta
from typing import Optional

import requests
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import ClientAccount, Order, Task, User

APP_NAME = "RPC Team CRM Cloud"
APP_VERSION = "3.0.0-web-owner-worker"
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_THIS_SECRET_KEY_RPC_2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = int(os.getenv("ACCESS_TOKEN_EXPIRE_DAYS", "30"))

# Auto-owner settings from Render Environment Variables.
# Example:
# RPC_OWNER_EMAILS=daniel134745@gmail.com,vinter@example.com
# RPC_OWNER_USERNAMES=ViNter,vinter
# RPC_AUTO_OWNER_PASSWORD=your_secret_password
OWNER_EMAILS = {
    x.strip().lower()
    for x in os.getenv("RPC_OWNER_EMAILS", os.getenv("OWNER_EMAILS", "")).split(",")
    if x.strip()
}
OWNER_USERNAMES = {
    x.strip().lower()
    for x in os.getenv("RPC_OWNER_USERNAMES", os.getenv("OWNER_USERNAMES", "")).split(",")
    if x.strip()
}
AUTO_OWNER_PASSWORD = os.getenv("RPC_AUTO_OWNER_PASSWORD", "").strip()
DEFAULT_OWNER_NAME = os.getenv("RPC_DEFAULT_OWNER_NAME", "RPC Owner").strip() or "RPC Owner"
RPC_FREE_SLOTS = int(os.getenv("RPC_FREE_SLOTS", "5"))

Base.metadata.create_all(bind=engine)
app = FastAPI(title=APP_NAME, version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash((password or "")[:72])


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify((password or "")[:72], password_hash)


def create_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def env_owner_match(username: str = "", email: str = "") -> bool:
    username_l = (username or "").strip().lower()
    email_l = (email or "").strip().lower()
    return bool((email_l and email_l in OWNER_EMAILS) or (username_l and username_l in OWNER_USERNAMES))


def apply_env_owner(user: User, db: Session) -> User:
    if env_owner_match(user.username, getattr(user, "email", "") or ""):
        changed = False
        if user.role != "owner":
            user.role = "owner"
            changed = True
        if not bool(getattr(user, "approved", False)):
            user.approved = True
            changed = True
        if not bool(getattr(user, "is_active", True)):
            user.is_active = True
            changed = True
        if changed:
            db.commit()
            db.refresh(user)
    return user


def ensure_schema() -> None:
    """Safe small migrations for old Render databases."""
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        if "users" in tables:
            columns = {c["name"] for c in inspector.get_columns("users")}
            with engine.begin() as conn:
                if "email" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(180)"))
                if "approved" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN approved BOOLEAN DEFAULT 0"))
                    conn.execute(text("UPDATE users SET approved = 1 WHERE role = 'owner'"))
                if "is_active" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1"))
        if "orders" in tables:
            columns = {c["name"] for c in inspector.get_columns("orders")}
            with engine.begin() as conn:
                if "source" not in columns:
                    conn.execute(text("ALTER TABLE orders ADD COLUMN source VARCHAR(80) DEFAULT 'site'"))
                if "client_account_id" not in columns:
                    conn.execute(text("ALTER TABLE orders ADD COLUMN client_account_id INTEGER"))
                if "updated_at" not in columns:
                    conn.execute(text("ALTER TABLE orders ADD COLUMN updated_at TIMESTAMP"))
        if "tasks" in tables:
            columns = {c["name"] for c in inspector.get_columns("tasks")}
            with engine.begin() as conn:
                if "updated_at" not in columns:
                    conn.execute(text("ALTER TABLE tasks ADD COLUMN updated_at TIMESTAMP"))
    except Exception as e:
        print("[RPC] schema migration skipped:", e)


def bootstrap_env_owners() -> None:
    """Create Owner accounts from Environment Variables if password is provided."""
    if not AUTO_OWNER_PASSWORD:
        return
    db_gen = get_db()
    db = next(db_gen)
    try:
        for email in sorted(OWNER_EMAILS):
            username = email.split("@", 1)[0].replace(".", "_").replace("-", "_")[:70]
            user = db.query(User).filter((User.email == email) | (User.username == username)).first()
            if not user:
                user = User(
                    name=DEFAULT_OWNER_NAME,
                    username=username,
                    email=email,
                    password_hash=hash_password(AUTO_OWNER_PASSWORD),
                    role="owner",
                    approved=True,
                    is_active=True,
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            else:
                user.email = user.email or email
                user.password_hash = user.password_hash or hash_password(AUTO_OWNER_PASSWORD)
                apply_env_owner(user, db)
        for username in sorted(OWNER_USERNAMES):
            user = db.query(User).filter(User.username == username).first()
            if not user:
                user = User(
                    name=DEFAULT_OWNER_NAME,
                    username=username,
                    email=None,
                    password_hash=hash_password(AUTO_OWNER_PASSWORD),
                    role="owner",
                    approved=True,
                    is_active=True,
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            else:
                apply_env_owner(user, db)
    finally:
        try:
            db.close()
        except Exception:
            pass


ensure_schema()
bootstrap_env_owners()


class RegisterIn(BaseModel):
    name: str = ""
    username: str = ""
    email: str = ""
    password: str
    role: str = "worker"


class LoginIn(BaseModel):
    username: str = ""
    email: str = ""
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


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


class OrderIn(BaseModel):
    client_name: str = ""
    name: str = ""
    contact: str = ""
    service: str = ""
    price: float | str = 0
    budget: float | str = 0
    prepaid: float | str = 0
    status: str = "new"
    worker_id: Optional[int] = None
    deadline: str = ""
    notes: str = ""
    description: str = ""
    source: str = "site"


class OrderStatusIn(BaseModel):
    status: str


class OrderAssignIn(BaseModel):
    worker_id: Optional[int] = None


class OrderNoteIn(BaseModel):
    notes: str


class UserApproveIn(BaseModel):
    approved: bool = True


class UserActiveIn(BaseModel):
    is_active: bool = True


class UserRoleIn(BaseModel):
    role: str = Field(pattern="^(owner|manager|worker)$")


class TaskIn(BaseModel):
    title: str
    description: str = ""
    assignee_id: Optional[int] = None
    deadline: str = ""
    priority: str = "normal"
    order_id: Optional[int] = None


class TaskStatusIn(BaseModel):
    status: str


def to_float(value) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace("₽", "").replace("тг", "").replace(" ", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "email": getattr(user, "email", "") or "",
        "role": user.role,
        "approved": bool(getattr(user, "approved", False)),
        "is_active": bool(getattr(user, "is_active", True)),
        "created_at": user.created_at.isoformat() if user.created_at else "",
    }


def order_dict(order: Order) -> dict:
    price = float(order.price or 0)
    prepaid = float(order.prepaid or 0)
    return {
        "id": order.id,
        "client_name": order.client_name,
        "contact": order.contact,
        "service": order.service,
        "price": price,
        "prepaid": prepaid,
        "rest": max(0, price - prepaid),
        "status": order.status,
        "worker_id": order.worker_id,
        "deadline": order.deadline,
        "notes": order.notes,
        "source": getattr(order, "source", "site") or "site",
        "client_account_id": getattr(order, "client_account_id", None),
        "created_at": order.created_at.isoformat() if order.created_at else "",
        "updated_at": order.updated_at.isoformat() if getattr(order, "updated_at", None) else "",
    }


def task_dict(task: Task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "deadline": task.deadline,
        "assignee_id": task.assignee_id,
        "order_id": task.order_id,
        "created_at": task.created_at.isoformat() if task.created_at else "",
        "updated_at": task.updated_at.isoformat() if getattr(task, "updated_at", None) else "",
    }


def client_dict(client: ClientAccount) -> dict:
    return {
        "id": client.id,
        "name": client.name,
        "email": client.email,
        "provider": client.provider,
        "created_at": client.created_at.isoformat() if client.created_at else "",
    }


def send_telegram_notification(text_msg: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text_msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        return True
    except Exception as e:
        print("[RPC] Telegram error:", e)
        return False


def order_telegram_text(order: Order) -> str:
    notes = html.escape(order.notes or "")
    if len(notes) > 900:
        notes = notes[:900] + "..."
    return (
        "🔥 <b>Новая заявка RPC</b>\n\n"
        f"🆔 Заявка: <b>RPC-{str(order.id).zfill(5)}</b>\n"
        f"👤 Клиент: {html.escape(order.client_name or '')}\n"
        f"📞 Контакт: <code>{html.escape(order.contact or '')}</code>\n"
        f"🛠 Услуга: {html.escape(order.service or '')}\n"
        f"💰 Бюджет: {order.price or 0}\n"
        f"⏰ Дедлайн: {html.escape(order.deadline or 'не указан')}\n"
        f"📌 Статус: {html.escape(order.status or 'new')}\n\n"
        f"📝 Описание:\n{notes}\n\n"
        "Открой RPC Web Panel, чтобы назначить рабочего."
    )


def get_user_by_login(db: Session, login: str = "", email: str = "") -> Optional[User]:
    login = (login or "").strip()
    email = (email or "").strip().lower()
    if email:
        user = db.query(User).filter(User.email == email).first()
        if user:
            return user
    if login:
        user = db.query(User).filter(User.username == login).first()
        if user:
            return user
        if "@" in login:
            return db.query(User).filter(User.email == login.lower()).first()
    return None


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    if not token:
        raise HTTPException(status_code=401, detail="Login required")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type", "user") != "user":
            raise HTTPException(status_code=401, detail="Invalid user token")
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    user = apply_env_owner(user, db)
    if not bool(getattr(user, "is_active", True)):
        raise HTTPException(status_code=403, detail="Account disabled")
    if user.role != "owner" and not bool(getattr(user, "approved", False)):
        raise HTTPException(status_code=403, detail="Account waiting owner approval")
    return user


async def get_current_user_unchecked(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    if not token:
        raise HTTPException(status_code=401, detail="Login required")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return apply_env_owner(user, db)


def require_owner(user: User) -> None:
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Only owner can do this")


def require_owner_or_manager(user: User) -> None:
    if user.role not in ["owner", "manager"]:
        raise HTTPException(status_code=403, detail="Only owner/manager can do this")


def create_order_from_payload(data: OrderIn, db: Session, authorization: Optional[str] = None) -> Order:
    client = None
    if authorization:
        client = get_optional_client(authorization, db)
    client_name = (data.client_name or data.name or "Клиент с сайта").strip()
    notes = (data.notes or data.description or "").strip()
    order = Order(
        client_name=client_name,
        contact=(data.contact or "").strip(),
        service=(data.service or "Не указано").strip(),
        price=to_float(data.price or data.budget),
        prepaid=to_float(data.prepaid),
        status=(data.status or "new").strip(),
        worker_id=data.worker_id,
        deadline=(data.deadline or "").strip(),
        notes=notes,
        source=(data.source or "site").strip(),
        updated_at=datetime.utcnow(),
    )
    if client:
        order.client_account_id = client.id
    db.add(order)
    db.commit()
    db.refresh(order)
    send_telegram_notification(order_telegram_text(order))
    return order


def create_client_token(client: ClientAccount) -> str:
    return create_token({"sub": str(client.id), "type": "client"})


async def get_current_client(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> ClientAccount:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "client":
            raise HTTPException(status_code=401, detail="Invalid client token")
        client_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid client token")
    client = db.query(ClientAccount).filter(ClientAccount.id == client_id).first()
    if not client:
        raise HTTPException(status_code=401, detail="Client not found")
    return client


def get_optional_client(token: Optional[str], db: Session) -> Optional[ClientAccount]:
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


@app.get("/")
def root():
    return {
        "app": APP_NAME,
        "status": "online",
        "version": APP_VERSION,
        "owner_env_emails_count": len(OWNER_EMAILS),
        "owner_env_usernames_count": len(OWNER_USERNAMES),
        "docs": "/docs",
    }


@app.post("/auth/register", response_model=TokenOut)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    if len(data.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 symbols")
    username = (data.username or data.email or "").strip()
    email = (data.email or (username if "@" in username else "")).strip().lower()
    if not username:
        raise HTTPException(status_code=400, detail="Username or email is required")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    if email and db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already exists")

    users_count = db.query(User).count()
    role = data.role.lower().strip()
    approved = False

    if env_owner_match(username, email):
        role = "owner"
        approved = True
    elif users_count == 0 and os.getenv("RPC_FIRST_USER_OWNER", "false").lower() in ["1", "true", "yes", "on"]:
        role = "owner"
        approved = True
    elif role not in ["worker", "manager"]:
        role = "worker"

    user = User(
        name=(data.name or username).strip(),
        username=username,
        email=email or None,
        password_hash=hash_password(data.password),
        role=role,
        approved=approved,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user = apply_env_owner(user, db)
    return {"access_token": create_token({"sub": str(user.id), "role": user.role, "type": "user"}), "user": user_dict(user)}


@app.post("/auth/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = get_user_by_login(db, data.username, data.email)
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong login or password")
    user = apply_env_owner(user, db)
    if not bool(getattr(user, "is_active", True)):
        raise HTTPException(status_code=403, detail="Account disabled")
    return {"access_token": create_token({"sub": str(user.id), "role": user.role, "type": "user"}), "user": user_dict(user)}


@app.post("/auth/token")
def login_for_swagger_docs(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = get_user_by_login(db, form_data.username, "")
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong login or password")
    user = apply_env_owner(user, db)
    return {"access_token": create_token({"sub": str(user.id), "role": user.role, "type": "user"}), "token_type": "bearer"}


@app.get("/me")
def me(user: User = Depends(get_current_user_unchecked), db: Session = Depends(get_db)):
    return user_dict(apply_env_owner(user, db))


@app.get("/users")
def list_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner_or_manager(user)
    q = db.query(User).order_by(User.id.desc())
    if user.role == "manager":
        q = q.filter(User.role != "owner")
    return [user_dict(apply_env_owner(u, db)) for u in q.all()]


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
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == user.id and data.role != "owner":
        raise HTTPException(status_code=400, detail="You cannot remove owner role from yourself")
    target.role = data.role
    if data.role == "owner":
        target.approved = True
    db.commit()
    db.refresh(target)
    return user_dict(target)


@app.post("/public/order")
def public_create_order_one(data: OrderIn, db: Session = Depends(get_db), authorization: Optional[str] = Header(None)):
    return {"ok": True, "order": order_dict(create_order_from_payload(data, db, authorization))}


@app.post("/public/orders")
def public_create_order_many(data: OrderIn, db: Session = Depends(get_db), authorization: Optional[str] = Header(None)):
    return {"ok": True, "order": order_dict(create_order_from_payload(data, db, authorization))}


@app.get("/public/order/test")
def public_order_test():
    return {"ok": True, "endpoint": "/public/order", "version": APP_VERSION}


@app.get("/public/orders/{order_id}")
def public_get_order_status(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    public = order_dict(order)
    public.pop("notes", None)
    public.pop("contact", None)
    return public


@app.get("/public/queue")
def public_queue(db: Session = Depends(get_db)):
    orders = db.query(Order).all()

    def count(*statuses: str) -> int:
        status_set = {s.lower() for s in statuses}
        return len([o for o in orders if (o.status or "new").lower() in status_set])

    active = count("new", "discussion", "waiting_prepay", "in_work", "review")
    return {
        "new": count("new"),
        "discussion": count("discussion"),
        "waiting_prepay": count("waiting_prepay"),
        "in_work": count("in_work"),
        "review": count("review"),
        "done": count("done"),
        "paid": count("paid"),
        "cancelled": count("cancelled"),
        "total": len(orders),
        "free_slots": max(0, RPC_FREE_SLOTS - active),
        "orders": [order_dict(o) for o in sorted(orders, key=lambda x: x.id, reverse=True)[:10]],
    }


@app.post("/orders")
def create_order(data: OrderIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner_or_manager(user)
    return order_dict(create_order_from_payload(data, db))


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
    order.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(order)
    return order_dict(order)


@app.patch("/orders/{order_id}/assign")
def assign_order(order_id: int, data: OrderAssignIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner_or_manager(user)
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if data.worker_id is not None:
        worker = db.query(User).filter(User.id == data.worker_id).first()
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found")
        if worker.role not in ["worker", "manager", "owner"]:
            raise HTTPException(status_code=400, detail="User cannot be assigned")
    order.worker_id = data.worker_id
    order.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(order)
    return order_dict(order)


@app.patch("/orders/{order_id}/notes")
def update_order_notes(order_id: int, data: OrderNoteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if user.role == "worker" and order.worker_id != user.id:
        raise HTTPException(status_code=403, detail="This is not your order")
    order.notes = data.notes
    order.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(order)
    return order_dict(order)


@app.post("/tasks")
def create_task(data: TaskIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner_or_manager(user)
    task = Task(**data.model_dump(), updated_at=datetime.utcnow())
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
    task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    return task_dict(task)


@app.post("/client/register", response_model=ClientTokenOut)
def client_register(data: ClientRegisterIn, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    if len(data.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 symbols")
    if db.query(ClientAccount).filter(ClientAccount.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    client = ClientAccount(name=data.name.strip() or email, email=email, password_hash=hash_password(data.password), provider="email")
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
    orders = db.query(Order).filter(Order.client_account_id == client.id).order_by(Order.id.desc()).all()
    return [order_dict(o) for o in orders]


@app.get("/admin/site/summary")
def admin_site_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner_or_manager(user)
    orders = db.query(Order).order_by(Order.id.desc()).limit(50).all()
    return {
        "clients": db.query(ClientAccount).count(),
        "users": db.query(User).count(),
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
            safe = "postgresql://***:***@" + safe.split("@", 1)[1]
        return {"mode": "postgresql", "persistent": True, "database": safe}
    return {"mode": "sqlite", "persistent": False, "warning": "DATABASE_URL is not configured"}


@app.post("/admin/telegram/test")
def admin_telegram_test(user: User = Depends(get_current_user)):
    require_owner(user)
    ok = send_telegram_notification("✅ RPC Telegram уведомления работают. Owner/Worker Web Panel подключена.")
    if not ok:
        raise HTTPException(status_code=400, detail="Telegram variables are not configured")
    return {"ok": True, "message": "Telegram test notification sent"}


@app.post("/admin/env/owners/sync")
def sync_env_owners(user: User = Depends(get_current_user)):
    require_owner(user)
    bootstrap_env_owners()
    return {"ok": True, "owner_emails": len(OWNER_EMAILS), "owner_usernames": len(OWNER_USERNAMES)}
