SERVER UPDATE: PUBLIC ORDER STATUS
=================================

Добавляет endpoint для проверки статуса заявки:

GET /public/orders/{order_id}

Пример:
https://rpc-team-crm.onrender.com/public/orders/24

Как обновить:
1. Загрузи файлы из этой папки в GitHub репозиторий сервера.
2. Render -> Manual Deploy -> Deploy latest commit.
3. Проверь:
   https://rpc-team-crm.onrender.com/docs
4. В docs должны быть:
   POST /public/orders
   GET /public/orders/{order_id}
