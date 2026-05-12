FIX PYTHON-MULTIPART
====================

Исправляет ошибку Render:

RuntimeError: Form data requires "python-multipart" to be installed.

Причина:
Swagger Authorize через OAuth2PasswordRequestForm использует form-data.
Для form-data FastAPI нужен пакет python-multipart.

Что исправлено:
В requirements.txt добавлено:

python-multipart==0.0.20

Что делать:
1. Загрузи файлы из server_update_persistent_database в GitHub сервера CRM.
2. Сделай Render redeploy.
3. Сервер должен стартовать нормально.
4. В /docs кнопка Authorize должна работать.
