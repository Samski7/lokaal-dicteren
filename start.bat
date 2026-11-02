@echo off
rem Start de web-UI vanuit de projectmap, ongeacht waar je dit bestand opent.
cd /d "%~dp0"
".venv\Scripts\python.exe" start.py %*
pause
