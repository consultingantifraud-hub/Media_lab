#!/bin/bash
# Упрощенная версия - использует docker compose logs
cd /opt/media-lab/deploy
docker-compose -f docker-compose.prod.yml logs -f --tail=50 bot worker-image worker-image-2 worker-image-3 api redis

