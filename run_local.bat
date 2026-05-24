@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv py -3.12 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
set RPC_OWNER_EMAILS=daniel134745@gmail.com
set RPC_AUTO_OWNER_PASSWORD=123456
uvicorn main:app --reload --host 127.0.0.1 --port 8000
pause
