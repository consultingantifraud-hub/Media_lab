@echo off
cd /d "%~dp0"
powershell.exe -ExecutionPolicy Bypass -File "%~dp0cleanup-simple.ps1" -CleanMedia
pause









