RPC CRM PERSISTENT DATABASE UPDATE
==================================

Проблема:
Если CRM сервер на Render хранит данные в SQLite-файле, то после перезапуска / redeploy аккаунты могут пропадать.
Поэтому приходится заново создавать аккаунт.

Решение:
Это обновление добавляет поддержку DATABASE_URL.
Если в Render добавить DATABASE_URL от PostgreSQL/Supabase, сервер будет хранить:
- аккаунты CRM;
- клиентские аккаунты;
- заказы;
- задачи;
- статусы;
- работников;

в постоянной базе данных.

Что добавлено:
- database.py теперь использует DATABASE_URL, если он есть.
- Если DATABASE_URL нет, остаётся SQLite fallback.
- Добавлен psycopg2-binary для PostgreSQL.
- Добавлен endpoint:
  GET /admin/database/status

Как поставить:
1. Загрузи все файлы из этой папки в GitHub репозиторий сервера CRM.
2. Render сделает deploy.
3. Создай PostgreSQL базу. Самый простой бесплатный вариант: Supabase.
4. В Render -> rpc-team-crm -> Environment добавь:
   DATABASE_URL = строка подключения PostgreSQL
5. Save Changes.
6. Manual Deploy / Redeploy.
7. Открой:
   https://rpc-team-crm.onrender.com/docs
8. Войди через /auth/login owner аккаунтом.
9. Authorize.
10. Запусти:
   GET /admin/database/status

Если ответ:
   "mode": "postgresql",
   "persistent": true

значит всё работает и аккаунты больше не должны пропадать.

Важно:
После подключения новой пустой базы нужно один раз заново создать owner аккаунт.
Но потом он уже будет сохраняться.
