@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Создан файл .env. Открой его в Блокноте и вставь токен бота.
  notepad ".env"
  pause
  exit /b
)
py -m pip install -r requirements.txt
if errorlevel 1 (
  echo Не удалось установить зависимости. Проверь подключение к интернету и Python.
  pause
  exit /b 1
)
py bot.py
pause
