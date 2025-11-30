@echo off
REM Быстрый перезапуск worker-image с гарантированной перезагрузкой настроек
cd /d "%~dp0"
docker compose up -d --build --force-recreate worker-image









