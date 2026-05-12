RPC CRM SWAGGER AUTHORIZE FIX
=============================

Исправляет проблему в /docs:

Auth error
Error: response status is 422

Причина:
Кнопка Authorize в Swagger отправляет username/password как OAuth2 form-data.
А старый POST /auth/login принимает JSON.

Что добавлено:
POST /auth/token

Что изменено:
OAuth2PasswordBearer tokenUrl теперь указывает на /auth/token.

Как пользоваться после deploy:
1. Открой https://rpc-team-crm.onrender.com/docs
2. Нажми Authorize.
3. Введи:
   username = owner логин CRM
   password = owner пароль CRM
4. client_id и client_secret оставь пустыми.
5. Нажми Authorize.
6. После этого GET /admin/database/status и POST /admin/telegram/test будут работать.

POST /auth/login с JSON тоже остаётся рабочим.
