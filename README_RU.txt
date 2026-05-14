RPC SITE UPDATED WORKER SYSTEM
==============================

Это обновлённый сайт RPC в одном наборе файлов.

Файлы:
- index.html
- worker-register.html
- worker-status.html
- owner-workers.html
- style.css
- app.js
- BACKEND_WORKER_ENDPOINTS_PATCH.py
- README_RU.txt

Что добавлено:
1. Основной сайт в стиле RPC.
2. Форма заказа с нормальными полями цены и дедлайна.
3. Регистрация рабочих на сайте.
4. Проверка статуса заявки рабочего.
5. Owner-страница для подтверждения рабочих.
6. Кнопки:
   - Одобрить
   - Отклонить
   - Отключить
   - Worker
   - Manager

Как загрузить на сайт:
1. Распакуй ZIP.
2. Закинь ВСЕ файлы в корень сайта рядом с index.html.
3. Загрузи в GitHub.
4. Render сам обновит сайт.

Ссылки:
- /index.html
- /worker-register.html
- /worker-status.html
- /owner-workers.html

Важно:
Если регистрация рабочих или owner-кнопки пишут ошибку endpoint,
добавь код из BACKEND_WORKER_ENDPOINTS_PATCH.py в main.py сервера rpc-team-crm.

API в app.js:
https://rpc-team-crm.onrender.com
