@echo off
cd /d "%~dp0"
py -3 -m pip install -r requirements.txt
py -3 -m streamlit run quick_app.py --server.address 127.0.0.1 --server.port 8502
