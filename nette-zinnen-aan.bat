@echo off
rem Optioneel: nette zinnen via een lokaal taalmodel (Ollama). Dicteren werkt ook zonder.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Eerst installeer.bat uitvoeren.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m app.nette_zinnen aan
pause
