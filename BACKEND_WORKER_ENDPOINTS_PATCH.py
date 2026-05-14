# BACKEND_WORKER_ENDPOINTS_PATCH.py
# Добавь этот код в main.py FastAPI сервера rpc-team-crm,
# если на сайте регистрация работников пишет ошибку endpoint.

from fastapi import HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from pathlib import Path
import json, time, uuid

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
WORKERS_FILE = DATA_DIR / "workers.json"

def load_workers() -> List[Dict[str, Any]]:
    if not WORKERS_FILE.exists():
        WORKERS_FILE.write_text("[]", encoding="utf-8")
    try:
        return json.loads(WORKERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

def save_workers(workers):
    WORKERS_FILE.write_text(json.dumps(workers, ensure_ascii=False, indent=2), encoding="utf-8")

def find_worker(worker_id: str):
    workers = load_workers()
    sid = str(worker_id).lower()
    for w in workers:
        variants = [
            str(w.get("id", "")),
            str(w.get("worker_id", "")),
            str(w.get("name", "")),
            str(w.get("username", "")),
            str(w.get("phone", "")),
            str(w.get("telegram", "")),
        ]
        if sid in [v.lower() for v in variants if v]:
            return workers, w
    return workers, None

class WorkerRegisterPayload(BaseModel):
    name: str
    phone: Optional[str] = ""
    telegram: Optional[str] = ""
    discord: Optional[str] = ""
    specialty: Optional[str] = ""
    portfolio: Optional[str] = ""
    comment: Optional[str] = ""
    approved: Optional[bool] = False
    active: Optional[bool] = False
    status: Optional[str] = "pending"
    source: Optional[str] = "worker-register-site"

class WorkerRolePayload(BaseModel):
    role: str

@app.post("/worker/register")
@app.post("/workers/register")
@app.post("/api/worker/register")
@app.post("/worker-requests")
def worker_register(payload: WorkerRegisterPayload):
    workers = load_workers()
    worker_id = uuid.uuid4().hex[:10]
    item = payload.model_dump()
    item.update({
        "id": worker_id,
        "worker_id": worker_id,
        "approved": False,
        "active": False,
        "role": "worker",
        "status": "pending",
        "created_at": int(time.time())
    })
    workers.append(item)
    save_workers(workers)
    return {"ok": True, "worker_id": worker_id, "approved": False, "status": "pending"}

@app.get("/worker/status/{worker_id}")
@app.get("/workers/{worker_id}/status")
@app.get("/api/worker/status/{worker_id}")
def worker_status(worker_id: str):
    workers, w = find_worker(worker_id)
    if not w:
        raise HTTPException(status_code=404, detail="Worker not found")
    return w

@app.get("/admin/worker-requests")
@app.get("/admin/workers")
@app.get("/workers")
def admin_workers():
    return {"workers": load_workers()}

@app.post("/admin/workers/{worker_id}/approve")
@app.post("/workers/{worker_id}/approve")
@app.post("/admin/users/{worker_id}/approve")
def approve_worker(worker_id: str):
    workers, w = find_worker(worker_id)
    if not w:
        raise HTTPException(status_code=404, detail="Worker not found")
    w["approved"] = True
    w["active"] = True
    w["status"] = "approved"
    w["approved_at"] = int(time.time())
    save_workers(workers)
    return {"ok": True, "worker": w}

@app.post("/admin/workers/{worker_id}/reject")
@app.post("/workers/{worker_id}/reject")
@app.post("/admin/users/{worker_id}/reject")
def reject_worker(worker_id: str):
    workers, w = find_worker(worker_id)
    if not w:
        raise HTTPException(status_code=404, detail="Worker not found")
    w["approved"] = False
    w["active"] = False
    w["status"] = "rejected"
    save_workers(workers)
    return {"ok": True, "worker": w}

@app.post("/admin/workers/{worker_id}/disable")
@app.post("/workers/{worker_id}/disable")
@app.post("/admin/users/{worker_id}/disable")
def disable_worker(worker_id: str):
    workers, w = find_worker(worker_id)
    if not w:
        raise HTTPException(status_code=404, detail="Worker not found")
    w["active"] = False
    w["status"] = "disabled"
    save_workers(workers)
    return {"ok": True, "worker": w}

@app.post("/admin/workers/{worker_id}/role")
@app.post("/workers/{worker_id}/role")
def set_worker_role(worker_id: str, payload: WorkerRolePayload):
    workers, w = find_worker(worker_id)
    if not w:
        raise HTTPException(status_code=404, detail="Worker not found")
    w["role"] = payload.role
    save_workers(workers)
    return {"ok": True, "worker": w}
