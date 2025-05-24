@echo off
chcp 65001 >nul
cd /d "%~dp0\files"

REM 1. Создание виртуального окружения при необходимости
if not exist "venv\Scripts\python.exe" (
    echo [i] Создаю виртуальное окружение...
    python -m venv venv || goto :error
)

REM 2. Активация окружения
call venv\Scripts\activate

REM 3. Установка зависимостей
echo [i] Устанавливаю зависимости...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 goto :error

REM 4. Установка браузеров Playwright (если не установлен firefox)
echo [i] Проверяю браузер Playwright...
python -c "import os; from pathlib import Path; p = Path('playwright-browsers/firefox-1449/firefox/firefox.exe'); exit(0) if p.exists() else exit(1)"
if %ERRORLEVEL% NEQ 0 (
    echo [i] Устанавливаю Firefox для Playwright...
    python -m playwright install firefox || goto :error
)

REM 5. Запуск парсера и веб-интерфейса
echo [i] Запускаю парсер и веб-интерфейс...

start "VOLNA Scraper" cmd /k "venv\Scripts\python.exe -m app.scraper.volna"
start "Web UI"        cmd /k "venv\Scripts\python.exe -m uvicorn app.web.main:app --port 8000 --reload"

REM 6. Открытие веб-интерфейса
timeout /t 3 >nul
start "" http://localhost:8000

echo [✓] Всё запущено. Парсинг и веб-интерфейс работают.
exit /b 0

:error
echo [✗] Произошла ошибка. Проверь вывод выше.
pause
exit /b 1