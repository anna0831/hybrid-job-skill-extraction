@echo off
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)
echo ============================================================
echo   正在啟動 104 職缺技能擷取系統 (RA 操作介面)...
echo   系統即將自動在瀏覽器開啟：http://localhost:8501
echo ============================================================
python -m streamlit run app.py
pause
