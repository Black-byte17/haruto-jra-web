@echo off
chcp 65001 > nul
title HARUTO Web v4.1.0 - ローカル起動

echo.
echo ==========================================
echo   HARUTO Web v4.1.0  ローカル起動
echo ==========================================
echo.

cd /d "%~dp0"

REM ---- Python確認 ----
py --version > nul 2>&1
if errorlevel 1 (
    python --version > nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python が見つかりません
        pause
        exit /b 1
    )
    set PYTHON=python
) else (
    set PYTHON=py
)

REM ---- ライブラリインストール ----
echo [1/2] ライブラリ確認中...
%PYTHON% -c "import flask, requests, bs4" 2>nul
if errorlevel 1 (
    echo [1/2] ライブラリをインストール中...
    %PYTHON% -m pip install flask requests beautifulsoup4 gunicorn -q
)
echo [1/2] ライブラリ OK

echo.
echo [2/2] Webサーバー起動中...
echo.
echo ==========================================
echo   ブラウザで開く: http://localhost:5000
echo   停止: Ctrl+C
echo ==========================================
echo.

REM ---- ブラウザを自動で開く ----
timeout /t 2 /nobreak > nul
start http://localhost:5000

REM ---- Flask起動 ----
set PORT=5000
%PYTHON% app.py

pause
