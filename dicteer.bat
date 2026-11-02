@echo off
rem Dicteren: Ctrl+Shift+Spatie = start/stop, tekst verschijnt bij je cursor.
cd /d "%~dp0"
title Dicteren (spraak naar tekst)
".venv\Scripts\python.exe" -m app.dicteer %*
pause
