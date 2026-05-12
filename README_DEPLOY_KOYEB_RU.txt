RPC Team CRM Cloud Free Edition — Koyeb
======================================

Что это:
Это серверная часть RPC Team CRM для бесплатного деплоя на Koyeb.
Клиентская программа остаётся на твоём ПК и ПК работников.

ВАЖНО:
Бесплатный Koyeb подходит для теста и маленькой команды.
Для боевой CRM лучше потом перейти на VPS/PostgreSQL, потому что бесплатные сервисы имеют ограничения.

Файлы для GitHub:
Загружай в GitHub именно содержимое этой папки cloud_server_koyeb:
- main.py
- database.py
- models.py
- requirements.txt
- Dockerfile
- .dockerignore

Шаги на GitHub:
1. Создай новый репозиторий, например rpc-team-crm-cloud.
2. Залей туда все файлы из cloud_server_koyeb.
3. Убедись, что Dockerfile лежит в корне репозитория.

Шаги на Koyeb:
1. Зайди на https://www.koyeb.com/
2. Sign up / Log in.
3. Create Web Service.
4. Выбери GitHub repository.
5. Выбери репозиторий rpc-team-crm-cloud.
6. Builder: Dockerfile.
7. Instance type: Free.
8. Port: 8000, если Koyeb спросит порт.
9. Environment variables:
   SECRET_KEY = любая длинная строка, например RPC_SECRET_2026_JrVinter_CHANGE_ME
10. Deploy.

После деплоя Koyeb даст ссылку типа:
https://имя-приложения.koyeb.app

Проверка:
Открой в браузере:
https://имя-приложения.koyeb.app/docs

Если открылась FastAPI Docs — сервер работает.

Как подключиться из клиента:
В RPC Team CRM на экране входа/регистрации в поле Server URL вставь:
https://имя-приложения.koyeb.app

Не пиши /docs в клиенте.
Нужно именно так:
https://имя-приложения.koyeb.app

Первый зарегистрированный аккаунт автоматически станет owner.

Важный момент про базу:
Сейчас по умолчанию используется SQLite файл внутри облачного сервера.
Это нормально для теста.
Для нормальной рабочей команды позже лучше подключить PostgreSQL или VPS с постоянным диском и бэкапами.
