@echo off
chcp 65001 >nul
python -m pip install -r requirements.txt
set PORT=8000
set PUBLIC_URL=http://localhost:8000
python main.py
pause
