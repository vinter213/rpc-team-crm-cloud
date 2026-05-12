FIX AUTH TOKEN SUB ID
=====================

Исправляет ошибку 500 после Authorize в /docs.

Причина:
POST /auth/token создавал токен с:
sub = username

Но get_current_user ожидал:
sub = user.id

Из-за этого endpoint /admin/database/status падал с Internal Server Error.

Что исправлено:
POST /auth/token теперь создаёт токен:
sub = str(user.id)
role = user.role

Также get_current_user стал безопаснее:
если старый токен неправильный, он вернёт 401, а не 500.

Что делать:
1. Загрузи файлы из server_update_persistent_database в GitHub сервера CRM.
2. Сделай Render redeploy.
3. Открой /docs.
4. Нажми Authorize.
5. Введи owner username/password.
6. Запусти GET /admin/database/status.

Важно:
После обновления нужно нажать Logout/Authorize заново в /docs, чтобы получить новый правильный токен.
