from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    username = Column(String(80), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), default="worker", index=True)  # owner, manager, worker
    approved = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assigned_orders = relationship("Order", back_populates="worker", foreign_keys="Order.worker_id")
    tasks = relationship("Task", back_populates="assignee", foreign_keys="Task.assignee_id")


class ClientAccount(Base):
    __tablename__ = "client_accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(180), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    provider = Column(String(40), default="email")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    orders = relationship("Order", back_populates="client_account")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    client_name = Column(String(120), nullable=False)
    contact = Column(String(180), default="")
    service = Column(String(180), nullable=False)
    price = Column(Float, default=0)
    prepaid = Column(Float, default=0)
    status = Column(String(50), default="new", index=True)
    priority = Column(String(50), default="normal")
    worker_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    client_account_id = Column(Integer, ForeignKey("client_accounts.id"), nullable=True, index=True)
    deadline = Column(String(80), default="")
    notes = Column(Text, default="")
    source = Column(String(80), default="CRM")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    worker = relationship("User", back_populates="assigned_orders", foreign_keys=[worker_id])
    client_account = relationship("ClientAccount", back_populates="orders")
    tasks = relationship("Task", back_populates="order")
    messages = relationship("OrderMessage", back_populates="order", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(180), nullable=False)
    description = Column(Text, default="")
    status = Column(String(50), default="not_started", index=True)
    priority = Column(String(50), default="normal")
    deadline = Column(String(80), default="")
    assignee_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True, index=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    assignee = relationship("User", back_populates="tasks", foreign_keys=[assignee_id])
    order = relationship("Order", back_populates="tasks")


class OrderMessage(Base):
    __tablename__ = "order_messages"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    author_type = Column(String(30), default="team")  # team, client, system
    author_name = Column(String(120), default="")
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    order = relationship("Order", back_populates="messages")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, nullable=True)
    actor_name = Column(String(120), default="")
    action = Column(String(120), nullable=False)
    entity = Column(String(80), default="")
    entity_id = Column(Integer, nullable=True)
    details = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
