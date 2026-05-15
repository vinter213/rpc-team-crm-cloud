# RPC PUBLIC ORDER ENDPOINT PATCH
# Загрузи этот файл в репозиторий rpc-team-crm и запусти один раз:
# python BACKEND_PUBLIC_ORDER_PATCH.py
#
# Он добавит в конец main.py публичный endpoint:
# POST /public/order
# POST /public/orders
#
# После этого сделай Deploy на Render.

from pathlib import Path

MAIN_FILE = Path("main.py")
PATCH_MARK = "# === RPC_PUBLIC_ORDER_ENDPOINT_PATCH_V1 ==="

PATCH_CODE = r'''
# === RPC_PUBLIC_ORDER_ENDPOINT_PATCH_V1 ===
# Public order endpoint for rpc-order-website
# This endpoint does not require client login. It receives orders from the public website.

from typing import Optional, Any, Dict
from pydantic import BaseModel

class RPCPublicOrderIn(BaseModel):
    client_name: Optional[str] = ""
    name: Optional[str] = ""
    contact: Optional[str] = ""
    service: Optional[str] = ""
    price: Optional[str] = ""
    budget: Optional[str] = ""
    deadline: Optional[str] = ""
    source: Optional[str] = "Сайт"
    description: Optional[str] = ""
    notes: Optional[str] = ""
    status: Optional[str] = "new"
    created_from: Optional[str] = "rpc-order-website"

def _rpc_public_order_to_dict(data: RPCPublicOrderIn) -> Dict[str, Any]:
    client_name = (data.client_name or data.name or "Клиент с сайта").strip()
    price = (data.price or data.budget or "").strip()
    description = (data.description or data.notes or "").strip()
    return {
        "title": f"Заявка с сайта: {data.service or 'Новая заявка'}",
        "client_name": client_name,
        "client": client_name,
        "contact": data.contact or "",
        "service": data.service or "Не указано",
        "price": price,
        "amount": price,
        "budget": price,
        "deadline": data.deadline or "",
        "source": data.source or "Сайт",
        "description": description,
        "notes": description,
        "status": data.status or "new",
        "created_from": data.created_from or "rpc-order-website",
    }

def _rpc_try_create_order_in_memory(order: Dict[str, Any]) -> Dict[str, Any]:
    import time
    oid = int(time.time())
    order["id"] = oid

    global ORDERS
    try:
        ORDERS
    except NameError:
        ORDERS = []

    if isinstance(ORDERS, list):
        ORDERS.append(order)
    elif isinstance(ORDERS, dict):
        ORDERS[str(oid)] = order

    return order

def _rpc_try_send_telegram_public_order(order: Dict[str, Any]) -> None:
    try:
        import os
        import requests

        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

        if not token or not chat_id:
            return

        text = (
            "🆕 <b>Новая заявка с сайта RPC</b>\n\n"
            f"👤 Клиент: <b>{order.get('client_name','')}</b>\n"
            f"📞 Контакт: <code>{order.get('contact','')}</code>\n"
            f"🛠 Услуга: <b>{order.get('service','')}</b>\n"
            f"💰 Бюджет: <b>{order.get('price') or order.get('budget') or order.get('amount') or '-'}</b>\n"
            f"⏳ Срок: <b>{order.get('deadline') or '-'}</b>\n"
            f"📌 Источник: <b>{order.get('source') or 'Сайт'}</b>\n\n"
            f"📝 {order.get('description') or order.get('notes') or '-'}"
        )

        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print("[RPC PUBLIC ORDER] Telegram notify failed:", e)

async def _rpc_public_create_order_handler(data: RPCPublicOrderIn):
    order = _rpc_public_order_to_dict(data)
    saved = None

    try:
        db_gen = get_db()
        db = next(db_gen)

        try:
            OrderModel = None
            for name in ["Order", "OrderModel", "CRMOrder"]:
                if name in globals():
                    OrderModel = globals()[name]
                    break

            if OrderModel is not None:
                allowed = {}
                for k, v in order.items():
                    if hasattr(OrderModel, k):
                        allowed[k] = v

                if not allowed:
                    allowed = {
                        "title": order["title"],
                        "client_name": order["client_name"],
                        "contact": order["contact"],
                        "service": order["service"],
                        "description": order["description"],
                        "status": "new",
                    }

                obj = OrderModel(**allowed)
                db.add(obj)
                db.commit()
                db.refresh(obj)
                saved = obj
        finally:
            try:
                db.close()
            except Exception:
                pass
    except Exception as e:
        print("[RPC PUBLIC ORDER] SQL save skipped:", e)

    if saved is None:
        saved = _rpc_try_create_order_in_memory(order)

    _rpc_try_send_telegram_public_order(order)

    return {"ok": True, "message": "Order received", "order": order}

@app.post("/public/order")
async def rpc_public_order_single(data: RPCPublicOrderIn):
    return await _rpc_public_create_order_handler(data)

@app.post("/public/orders")
async def rpc_public_order_plural(data: RPCPublicOrderIn):
    return await _rpc_public_create_order_handler(data)

@app.get("/public/order/test")
async def rpc_public_order_test():
    return {"ok": True, "endpoint": "/public/order", "message": "RPC public order endpoint works"}
# === /RPC_PUBLIC_ORDER_ENDPOINT_PATCH_V1 ===
'''

def main():
    if not MAIN_FILE.exists():
        raise SystemExit("ОШИБКА: main.py не найден. Положи этот файл рядом с main.py в репозитории rpc-team-crm.")

    text = MAIN_FILE.read_text(encoding="utf-8", errors="ignore")

    if PATCH_MARK in text:
        print("Патч уже установлен. Ничего не меняю.")
        return

    MAIN_FILE.write_text(text.rstrip() + "\n\n" + PATCH_CODE + "\n", encoding="utf-8")
    print("ГОТОВО: endpoint /public/order добавлен в main.py")
    print("Теперь сделай commit и deploy на Render.")

if __name__ == "__main__":
    main()
