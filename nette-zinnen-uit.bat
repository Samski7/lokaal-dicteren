@echo off
rem Nette zinnen (taalmodel) uitzetten; opvulwoorden worden wel nog weggefilterd.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m app.nette_zinnen uit
pause
