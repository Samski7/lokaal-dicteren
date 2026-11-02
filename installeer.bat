@echo off
rem Eenmalige installatie: Python-omgeving + pakketten (+ GPU-pakketten als er een NVIDIA-kaart is).
cd /d "%~dp0"

where py >nul 2>nul || (
  echo Python niet gevonden. Installeer Python 3.11 of nieuwer via https://www.python.org
  pause & exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Python-omgeving aanmaken...
  py -3 -m venv .venv || (pause & exit /b 1)
)

echo Pakketten installeren (dit kan enkele minuten duren)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt || (pause & exit /b 1)

where nvidia-smi >nul 2>nul && (
  echo NVIDIA-GPU gevonden: GPU-pakketten installeren...
  ".venv\Scripts\python.exe" -m pip install -r requirements-gpu.txt
)

where ollama >nul 2>nul && (
  echo Ollama gevonden: taalmodel voor het opschonen ophalen...
  ollama pull gemma4:e2b-it-qat
) || (
  echo Ollama niet gevonden: opschonen gebeurt enkel met regels.
  echo Wil je ook nette zinnen? Installeer Ollama via https://ollama.com en start dit opnieuw.
)

echo.
echo Klaar! Start dicteer.bat om te dicteren, of start.bat voor de web-app.
pause
