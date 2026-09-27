@echo off
title Bhoomi Predict Portal
cd /d "%~dp0"
echo.
echo   BHOOMI PREDICT - NH-44 Madurai-Tirunelveli
echo.
echo   [1/3] Installing packages (first run 3-4 min)...
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (echo   Install failed. & pause & exit /b 1)
echo.
echo   [2/3] Self-test...
python bhoomi_portal.py
echo.
echo   [3/3] Starting portal.
echo         On this laptop : http://localhost:8501
echo         Login: collector.ttn@tn.gov.in / Collector@2026
echo.
python -m streamlit run bhoomi_portal.py --server.address 0.0.0.0
pause
