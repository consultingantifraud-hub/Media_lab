#!/bin/bash
set -e

cd /opt/media-lab

echo "=========================================="
echo "Building worker-image Docker container"
echo "=========================================="
echo ""

# Check if Dockerfile exists
if [ ! -f "docker/Dockerfile.worker" ]; then
    echo "✗ Error: docker/Dockerfile.worker not found!"
    exit 1
fi

# Check if app/workers/image_worker_server.py exists
if [ ! -f "app/workers/image_worker_server.py" ]; then
    echo "✗ Warning: app/workers/image_worker_server.py not found!"
    echo "  Build will continue, but file won't be in the image."
fi

echo "1. Starting build with timeout (30 minutes)..."
echo "   Using Dockerfile: docker/Dockerfile.worker"
echo ""

# Build with timeout to prevent infinite hanging
# Use timeout command if available, otherwise just run docker build
if command -v timeout &> /dev/null; then
    timeout 1800 docker build -f docker/Dockerfile.worker -t docker-worker-image:latest . 2>&1 | tee /tmp/docker-build-worker.log
    BUILD_EXIT_CODE=${PIPESTATUS[0]}
    
    # Check if timeout occurred
    if [ $BUILD_EXIT_CODE -eq 124 ]; then
        echo ""
        echo "✗ Build timed out after 30 minutes!"
        echo "  This usually indicates a network or repository issue."
        echo "  Check /tmp/docker-build-worker.log for details"
        exit 1
    fi
else
    docker build -f docker/Dockerfile.worker -t docker-worker-image:latest . 2>&1 | tee /tmp/docker-build-worker.log
    BUILD_EXIT_CODE=${PIPESTATUS[0]}
fi

if [ $BUILD_EXIT_CODE -eq 0 ]; then
    echo ""
    echo "✓ Build successful!"
    echo ""
    echo "2. Verifying image..."
    docker images | grep docker-worker-image || echo "  (Image not found in list)"
    echo ""
    echo "3. Testing file presence..."
    if docker run --rm docker-worker-image:latest test -f /app/app/workers/image_worker_server.py 2>/dev/null; then
        echo "✓ File /app/app/workers/image_worker_server.py exists in image"
        # Check file size
        FILE_SIZE=$(docker run --rm docker-worker-image:latest stat -c%s /app/app/workers/image_worker_server.py 2>/dev/null || echo "unknown")
        echo "  File size: $FILE_SIZE bytes"
    else
        echo "✗ File /app/app/workers/image_worker_server.py missing in image!"
        echo "  Checking what files are in /app/app/workers/..."
        docker run --rm docker-worker-image:latest ls -lah /app/app/workers/ 2>/dev/null || echo "  Directory not found"
    fi
    echo ""
    echo "=========================================="
    echo "✓ Build completed successfully!"
    echo "=========================================="
    exit 0
else
    echo ""
    echo "✗ Build failed with exit code $BUILD_EXIT_CODE"
    echo "Check /tmp/docker-build-worker.log for details"
    echo ""
    echo "Last 20 lines of build log:"
    tail -20 /tmp/docker-build-worker.log
    exit 1
fi


