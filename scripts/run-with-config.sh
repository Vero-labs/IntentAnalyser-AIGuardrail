#!/usr/bin/env bash

set -euo pipefail

ENV_NAME="${1:-local}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_DIR="${ROOT_DIR}/configs/${ENV_NAME}"

if [[ ! -f "${ENV_DIR}/guardrail.config.yaml" ]]; then
  echo "[ERR] Missing config: ${ENV_DIR}/guardrail.config.yaml" >&2
  exit 1
fi

if [[ ! -f "${ENV_DIR}/.env.gateway" ]]; then
  echo "[ERR] Missing env file: ${ENV_DIR}/.env.gateway" >&2
  exit 1
fi

export GUARDRAIL_CONFIG_PATH="${ENV_DIR}/guardrail.config.yaml"
export GUARDRAIL_POLICY_PATH="${ROOT_DIR}/configs/policies/main.yaml"
export GUARDRAIL_ENV_FILE="${ENV_DIR}/.env.gateway"

exec python3 -m app.main
