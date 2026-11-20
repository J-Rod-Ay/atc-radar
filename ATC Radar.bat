@echo off
rem Double-click to start ATC Radar (runs in WSL) and open the GUI
start "" /min wsl --cd "%~dp0." -e bash -lc "./run.sh"
timeout /t 4 >nul
start "" http://localhost:8790
