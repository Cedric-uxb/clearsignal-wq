#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
exec .venv/bin/python -m streamlit run app.py \
  --server.headless true \
  --server.address 127.0.0.1 \
  --server.port "${PORT:-8501}"
