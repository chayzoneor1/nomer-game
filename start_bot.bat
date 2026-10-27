@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================
echo  Генератор телефонных номеров - Telegram
 echo ==========================================
where py >nul 2>nul
if errorlevel 1 (
  echo Не найден Python. Установи Python 3.11+ и включи Add Python to PATH.
  pause
  exit /b 1
)
if not exist ".env" (
  copy ".env.example" ".env" >nul
)
py -m pip install -r requirements.txt
if errorlevel 1 (
  echo Не удалось установить зависимости.
  pause
  exit /b 1
)
py bot.py
pause
