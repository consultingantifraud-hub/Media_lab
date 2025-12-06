#!/bin/bash
set -euo pipefail

ARCHIVE_DIR="/opt/media-lab/_archive_2025"
LOG_FILE="/opt/media-lab/_archive_2025/archive.log"

mkdir -p "$ARCHIVE_DIR"

echo "=== $(date) START ARCHIVE ===" | tee -a "$LOG_FILE"

move_if_exists() {
  local path="$1"
  if [[ -e "$path" ]]; then
    echo "MOVE: $path -> $ARCHIVE_DIR" | tee -a "$LOG_FILE"
    mv "$path" "$ARCHIVE_DIR"/
  else
    echo "SKIP (not found): $path" | tee -a "$LOG_FILE"
  fi
}

# 1) Старые deploy-папки и бэкапы
move_if_exists "/opt/media-lab/deploy/deploy"
move_if_exists "/opt/media-lab/deploy/=2.9.0"
move_if_exists "/opt/media-lab/deploy/=2.0.0"

for path in \
  /opt/media-lab/deploy/docker-compose.prod.yml.backup* \
  /opt/media-lab/deploy/*.backup* \
  /opt/media-lab/deploy/*old* \
  /opt/media-lab/deploy/*deprecated*
do
  move_if_exists "$path"
done

# 2) Бэкапы воркеров
for path in \
  /opt/media-lab/app/workers/image_worker.py.backup* \
  /opt/media-lab/app/workers/*.backup*
do
  move_if_exists "$path"
done

# 3) Windows-скрипты и docker-бэкапы
for path in \
  /opt/media-lab/docker/*.ps1 \
  /opt/media-lab/docker/*.bat \
  /opt/media-lab/docker/*backup* \
  /opt/media-lab/docker/*old* \
  /opt/media-lab/docker/*deprecated*
do
  move_if_exists "$path"
done

echo "=== $(date) ARCHIVE COMPLETE ===" | tee -a "$LOG_FILE"
echo "Archive dir content:" | tee -a "$LOG_FILE"
ls -la "$ARCHIVE_DIR" | tee -a "$LOG_FILE"


