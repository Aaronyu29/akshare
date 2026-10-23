@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
if exist "%~dp0..\.venv\Scripts\python.exe" (
  "%~dp0..\.venv\Scripts\python.exe" -m stock_alert.us_quotes %*
) else (
  python -m stock_alert.us_quotes %*
)
if "%~1"=="" pause
