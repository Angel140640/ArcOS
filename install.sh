#!/usr/bin/env sh
# Instala o ArcOS (Termux ou qualquer Linux). Uso: sh install.sh
set -e
cd "$(dirname "$0")"

PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  if command -v pkg >/dev/null 2>&1; then
    pkg install -y python
    PY="$(command -v python3 || command -v python)"
  else
    echo "Python 3.8+ não encontrado. Instale-o e rode de novo." >&2
    exit 1
  fi
fi

if "$PY" -m pip install --upgrade . ; then
  echo "Instalado via pip."
else
  echo "pip falhou; criando um atalho direto para esta pasta."
  BIN="${PREFIX:-$HOME/.local}/bin"
  mkdir -p "$BIN"
  printf '#!/usr/bin/env sh\nPYTHONPATH="%s" exec "%s" -m arcos "$@"\n' "$(pwd)" "$PY" > "$BIN/arc-os"
  chmod +x "$BIN/arc-os"
  echo "Atalho criado em $BIN/arc-os (não apague esta pasta)."
fi

echo
echo "Pronto! Teste com:  arc-os help"
