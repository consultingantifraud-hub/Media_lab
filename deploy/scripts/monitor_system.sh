#!/bin/bash
# Simple system monitoring script for NeuroStudio
# Usage: ./monitor_system.sh [interval_seconds]

INTERVAL=${1:-60}  # Default 60 seconds

echo "=== NeuroStudio System Monitor ==="
echo "Monitoring interval: ${INTERVAL} seconds"
echo "Press Ctrl+C to stop"
echo ""

while true; do
    clear
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') ==="
    echo ""
    
    # System resources
    echo "--- System Resources ---"
    free -h | grep -E "Mem|Swap"
    echo ""
    df -h / | tail -1
    echo ""
    uptime
    echo ""
    
    # Docker containers
    echo "--- Docker Containers ---"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" | head -20
    echo ""
    
    # PostgreSQL connections
    echo "--- PostgreSQL ---"
    docker exec deploy-postgres-1 psql -U media_lab_user -d media_lab -t -c "SELECT COUNT(*) as active_connections FROM pg_stat_activity WHERE datname = 'media_lab';" 2>/dev/null || echo "N/A"
    docker exec deploy-postgres-1 psql -U media_lab_user -d media_lab -t -c "SHOW max_connections;" 2>/dev/null || echo "N/A"
    echo ""
    
    # Redis
    echo "--- Redis ---"
    docker exec deploy-redis-1 redis-cli INFO stats | grep -E "connected_clients|used_memory_human" 2>/dev/null || echo "N/A"
    echo ""
    
    # Queue status
    echo "--- Queue Status ---"
    docker exec deploy-redis-1 redis-cli LLEN img_queue 2>/dev/null | xargs echo "Jobs in queue:"
    echo ""
    
    sleep $INTERVAL
done

