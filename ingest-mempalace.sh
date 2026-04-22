#!/usr/bin/env bash
# Ingestador de Emisiones - Lee configuración de .env
set -e

# Cargar variables desde .env
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Usar variable del env o fallback al comando global
BIN=${MEMPALACE_BIN:-"mempalace"}
JSON="data/emisiones.json"

if [ ! -f "$JSON" ]; then
    echo "❌ Error: No existe $JSON"
    exit 1
fi

echo "🚀 Ingestando en MemPalace..."
$BIN mine "$JSON" --wing bva-emisiones --room investment-offers
echo "✅ ¡Listo!"
