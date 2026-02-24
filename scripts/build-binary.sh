#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "[ERR] Python binary not found: ${PYTHON_BIN}" >&2
  exit 1
fi

if ! "${PYTHON_BIN}" -m PyInstaller --version >/dev/null 2>&1; then
  echo "[ERR] PyInstaller is not installed." >&2
  echo "Install build dependencies with:" >&2
  echo "  ${PYTHON_BIN} -m pip install -r ${ROOT_DIR}/requirements-build.txt" >&2
  exit 1
fi

cd "${ROOT_DIR}"
"${PYTHON_BIN}" -m PyInstaller --clean --noconfirm packaging/llm_gateway.spec

echo "[OK] Binary created at: ${ROOT_DIR}/dist/llm-gateway"
