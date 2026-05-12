from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    username = Column(String(80), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), default="worker")  # owner, manager, worker
    created_at = Column(DateTime, default=datetime.utcnow)

    tasks = relationship("Task", back_populates="assignee")

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    client_name = Column(String(120), nullable=False)
    contact = Column(String(160), default="")
    service = Column(String(160), nullable=False)
    price = Column(Float, default=0)
    prepaid = Column(Float, default=0)
    status = Column(String(50), default="new")
    worker_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    deadline = Column(String(50), default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(180), nullable=False)
    description = Column(Text, default="")
    status = Column(String(50), default="not_started")
    priority = Column(String(50), default="normal")
    deadline = Column(String(50), default="")
    assignee_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    assignee = relationship("User", back_populates="tasks")
