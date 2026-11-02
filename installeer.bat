@echo off
setlocal
rem Eenmalige installatie: Python-omgeving, pakketten, GPU-ondersteuning, spraakmodel en controle.
rem Opnieuw uitvoeren mag altijd (bv. na een update of als Windows iets blokkeert).
cd /d "%~dp0"

rem --- Python kiezen: een geteste versie, niet zomaar de nieuwste ---------------------------
rem (Python 3.15 is nog te nieuw voor sommige pakketten; 3.11 t.e.m. 3.14 werken.)
set "PY="
for %%V in (3.13 3.12 3.14 3.11) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
  )
)
rem Geen py-launcher, bv. Python uit de Microsoft Store: probeer "python" zelf.
if not defined PY (
  python -c "import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 14) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo Geen geschikte Python gevonden. Installeer Python 3.13 via
  echo https://www.python.org/downloads/  ^(vink "Add python.exe to PATH" aan^)
  echo en start dit bestand daarna opnieuw.
  pause
  exit /b 1
)
echo Python: %PY%

rem Vooraf controleren: ARM-Python, te diepe map (260-tekenlimiet), Python-versie.
%PY% -m app.installatiecheck
if errorlevel 1 (
  pause
  exit /b 1
)

rem Op pip.exe controleren: zo wordt ook een half aangemaakte omgeving hersteld.
if not exist ".venv\Scripts\pip.exe" (
  echo Python-omgeving aanmaken...
  %PY% -m venv .venv
  if errorlevel 1 (
    rmdir /s /q .venv 2>nul
    pause
    exit /b 1
  )
)

echo Pakketten installeren ^(dit kan enkele minuten duren^)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Installeren van de pakketten mislukte. Zie de fout hierboven.
  pause
  exit /b 1
)

where nvidia-smi >nul 2>nul
if not errorlevel 1 (
  echo NVIDIA-GPU gevonden: GPU-ondersteuning installeren ^(~1 GB^)...
  ".venv\Scripts\python.exe" -m pip install -r requirements-gpu.txt
)

rem Smart App Control (Windows 11) blokkeert soms een pas uitgebrachte pakketversie:
rem dan automatisch een vorige versie kiezen die Windows wel vertrouwt.
echo.
".venv\Scripts\python.exe" -m app.windows_blokkade

echo.
echo Spraakmodel downloaden en alles testen...
".venv\Scripts\python.exe" -m app.voorbereiden

echo.
echo Optioneel, kan ook later: dubbelklik nette-zinnen-aan.bat voor nette zinnen
echo via een lokaal taalmodel ^(Ollama, ~3 GB^).
pause
