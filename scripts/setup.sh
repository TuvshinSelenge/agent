#!/usr/bin/env bash
# Idempotent install for the ELK Lead Agent.
# Creates a virtualenv and installs the package (with dev extras) in editable mode.
set -euo pipefail

cd "$(dirname "$0")/.."

# The venv module needs ensurepip; on minimal Debian/Ubuntu images it ships in
# the python3-venv package. Install it only if it is missing.
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  echo "[setup] installing python3-venv ..."
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-venv
fi

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"

echo "[setup] done. Run: .venv/bin/elk-agent run"
