@echo off
title KURYOS Frontend
cd /d C:\Users\MARLOS\Downloads\KURYOS\frontend
set REACT_APP_BACKEND_URL=http://localhost:8000
set PORT=3001
echo Iniciando KURYOS Frontend na porta 3001...
echo Backend: http://localhost:8000
echo.
C:\nvm4w\nodejs\npm.cmd start
