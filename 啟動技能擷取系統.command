#!/bin/bash
cd "$(dirname "$0")"
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi
echo "============================================================"
echo "  正在啟動 104 職缺技能擷取系統 (RA 操作介面)..."
echo "  系統即將自動在瀏覽器開啟：http://localhost:8501"
echo "============================================================"
python3 -m streamlit run app.py
