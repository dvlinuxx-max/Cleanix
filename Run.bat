@echo off
chcp 65001 >nul
cd /d "%~dp0"
where pyw >nul 2>nul && (start "" pyw Cleanix.py) || (start "" pythonw Cleanix.py)
