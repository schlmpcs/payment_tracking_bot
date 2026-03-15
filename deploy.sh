#!/bin/bash
# Run this on the server to deploy the latest version
set -euo pipefail

echo "Pulling latest code..."
git pull

echo "Rebuilding and restarting containers..."
docker compose down
docker compose up -d --build

echo "Removing dangling images..."
docker image prune -f

echo "Deploy complete. Logs:"
docker compose logs -f
