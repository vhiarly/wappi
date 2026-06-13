#!/bin/bash
# Ejecuta esto localmente para insertar PA1

DATABASE_URL="postgresql://wasapeame:wappi2026!@wasapeame-db.postgres.database.azure.com:5432/wasapeame?sslmode=require" python3 seed_frescodelhorno.py

echo "✅ PA1 insertado"
