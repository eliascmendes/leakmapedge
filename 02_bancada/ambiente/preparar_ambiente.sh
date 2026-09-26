#!/usr/bin/env bash
# LEAKMAP - prepara o ambiente do TSNet no Linux ou no macOS e confere contra as simulacoes gravadas.
#
# Cria um ambiente virtual com Python 3.11 ou 3.12, instala as versoes
# congeladas (requirements-congelado.txt) e roda conferir_ambiente.py.
#
# Uso, a partir da raiz do repositorio:
#   bash 02_bancada/ambiente/preparar_ambiente.sh [destino] [--completo]
set -euo pipefail
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESTINO="${1:-$HOME/leakmap_env}"
COMPLETO="${2:-}"

PYTHON=""
for candidato in python3.11 python3.12; do
  if command -v "$candidato" >/dev/null 2>&1; then PYTHON="$candidato"; break; fi
done
if [ -z "$PYTHON" ] && command -v python3 >/dev/null 2>&1 \
   && python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) else 1)'; then
  PYTHON=python3
fi
if [ -z "$PYTHON" ] && command -v uv >/dev/null 2>&1; then
  PYTHON="$(uv python find 3.11 2>/dev/null || uv python find 3.12 2>/dev/null || true)"
fi
if [ -z "$PYTHON" ]; then
  echo "Nao achei Python 3.11 nem 3.12. Instale um deles (ou 'uv python install 3.11') e rode de novo." >&2
  exit 1
fi
echo "Python da bancada: $PYTHON"

[ -x "$DESTINO/bin/python" ] || "$PYTHON" -m venv "$DESTINO"
"$DESTINO/bin/python" -m pip install --upgrade pip --quiet
"$DESTINO/bin/python" -m pip install -r "$AQUI/requirements-congelado.txt"
"$DESTINO/bin/python" "$AQUI/conferir_ambiente.py" $COMPLETO
