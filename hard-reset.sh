#!/bin/bash
cd cloud/compose/Grafana-Mosquitto
docker compose down -v
docker compose up --build -d
