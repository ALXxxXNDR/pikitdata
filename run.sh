#!/usr/bin/env bash
# Launch the PIKIT Balance Dashboard.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "[setup] creating venv"
  python3 -m venv .venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate

if ! python -c "import streamlit" 2>/dev/null; then
  echo "[setup] installing requirements"
  python -m pip install --upgrade pip --quiet
  python -m pip install -r requirements.txt --quiet
fi

PORT="${PORT:-8501}"
exec streamlit run app.py \
  --server.port "${PORT}" \
  --server.address "${ADDRESS:-127.0.0.1}" \
  --browser.gatherUsageStats false
