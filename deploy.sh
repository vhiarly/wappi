#!/bin/bash
set -e

APP="Wappi"
RG="wasapeame-rg"
URL="https://wappi-gwbeheayascybpcv.canadacentral-01.azurewebsites.net/ping"
ZIP="/tmp/wasapeame_deploy.zip"
ESPERADO="¡El servidor está vivo!"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓ $1${NC}"; }
fail() { echo -e "${RED}✗ $1${NC}"; exit 1; }
info() { echo -e "${YELLOW}→ $1${NC}"; }

info "Verificando sesión Azure..."
az account show --query name -o tsv > /dev/null 2>&1 || fail "No estás logueado en Azure. Corre: az login"
ok "Azure autenticado"

COMMIT=$(git log --oneline -1)
info "Deployando: $COMMIT"

info "Creando zip..."
rm -f "$ZIP"
zip -r "$ZIP" . \
  -x "*.git*" ".DS_Store" ".env" "__pycache__/*" "*.pyc" "*.sh" "deploy.sh" \
  > /dev/null
ok "Zip creado ($(du -sh $ZIP | cut -f1))"

info "Subiendo a Azure App Service..."
az webapp deploy \
  --name "$APP" \
  --resource-group "$RG" \
  --src-path "$ZIP" \
  --type zip \
  --timeout 300 \
  --output none
ok "Deploy completado"

info "Esperando que el app reinicie..."
for i in {1..12}; do
  sleep 5
  RESP=$(curl -sk --max-time 5 "$URL" 2>/dev/null || true)
  if [ "$RESP" = "$ESPERADO" ]; then
    ok "App respondiendo en $URL"
    break
  fi
  echo "   intento $i/12..."
  if [ $i -eq 12 ]; then
    fail "App no responde después de 60s."
  fi
done

rm -f "$ZIP"
echo ""
echo -e "${GREEN}Deploy exitoso ✓${NC}"
echo -e "Commit: ${COMMIT}"
