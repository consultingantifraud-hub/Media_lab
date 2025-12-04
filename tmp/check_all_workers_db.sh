#!/bin/bash
echo "=== Checking DATABASE_URL in all 16 workers ==="
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16; do
  if [ $i -eq 1 ]; then
    container="deploy-worker-image-1"
  else
    container="deploy-worker-image-${i}-1"
  fi
  
  if docker exec $container env 2>/dev/null | grep -q DATABASE_URL; then
    echo "Worker $i: OK"
  else
    echo "Worker $i: MISSING DATABASE_URL"
  fi
done

echo ""
echo "=== Testing DB connection from sample workers ==="
docker exec deploy-worker-image-1 python3 -c "from app.db.base import SessionLocal; db = SessionLocal(); print('Worker 1: DB OK'); db.close()" 2>&1
docker exec deploy-worker-image-8-1 python3 -c "from app.db.base import SessionLocal; db = SessionLocal(); print('Worker 8: DB OK'); db.close()" 2>&1
docker exec deploy-worker-image-16-1 python3 -c "from app.db.base import SessionLocal; db = SessionLocal(); print('Worker 16: DB OK'); db.close()" 2>&1




