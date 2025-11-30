#!/bin/bash
# Быстрый перезапуск worker-image с гарантированной перезагрузкой настроек
cd "$(dirname "$0")"
docker compose up -d --build --force-recreate worker-image









