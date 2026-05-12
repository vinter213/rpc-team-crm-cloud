FIX GET_DB IMPORT ERROR
=======================

Исправляет ошибку Render:

ImportError: cannot import name 'get_db' from 'database'

Причина:
main.py импортирует get_db из database.py, а в прошлом обновлении get_db не был добавлен.

Что исправлено:
В database.py добавлена функция:

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

Что делать:
1. Загрузи файлы из этой папки в GitHub репозиторий сервера CRM.
2. Сделай Render redeploy.
3. Сервер должен запуститься нормально.
