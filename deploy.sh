#!/bin/bash

# Configuration
DOCKER_USERNAME="vgkole001"  # Replace with your Docker Hub username
IMAGE_NAME="$DOCKER_USERNAME/fastapi-app"
CONTAINER_NAME="fastapi-app"

echo "🚀 Deploying FastAPI locally..."

# Stop existing container
echo "⏹️  Stopping existing container..."
docker stop $CONTAINER_NAME 2>/dev/null || true
docker rm $CONTAINER_NAME 2>/dev/null || true

# Pull latest image
echo "📥 Pulling latest image from Docker Hub..."
docker pull $IMAGE_NAME:latest

# Start new container
echo "🐳 Starting new container..."
docker run -d \
  --name $CONTAINER_NAME \
  --restart unless-stopped \
  -p 8000:8000 \
  -e DATABASE_URL="postgresql://postgres:w4qu+0sj@host.docker.internal:5432/postgres" \
  -e ENVIRONMENT="development" \
  -e SECRET_KEY="dev-secret-key-change-in-production" \
  $IMAGE_NAME:latest

# Wait and check
echo "⏳ Waiting for container to start..."
sleep 10

# Health check
echo "🔍 Performing health check..."
if curl -f http://localhost:8000/health 2>/dev/null; then
  echo "✅ Deployment successful! FastAPI is running at http://localhost:8000"
else
  echo "❌ Health check failed. Checking logs..."
  docker logs $CONTAINER_NAME --tail 20
fi

echo "📊 Container status:"
docker ps | grep $CONTAINER_NAME