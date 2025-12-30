#!/bin/bash
git stash
git pull
git stash pop
cd cloud/compose/Grafana-Mosquitto
docker compose down
docker compose up --build -d
echo "Updated"
