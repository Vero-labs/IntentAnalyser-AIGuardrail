#!/usr/bin/env bash

set -euo pipefail

REPO_URL="${REPO_URL:-}"
BRANCH="${BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/intent-analyzer-gateway}"
OPENAI_API_KEY="${OPENAI_API_KEY:-}"
HUGGINGFACE_API_TOKEN="${HUGGINGFACE_API_TOKEN:-}"
START_GATEWAY=1

usage() {
  cat <<USAGE
Usage: quickstart.sh [options]

Options:
  --repo-url <url>       Git repository URL (required if REPO_URL is not set)
  --branch <name>        Git branch (default: main)
  --install-dir <path>   Install directory (default: ~/intent-analyzer-gateway)
  --openai-key <key>     OpenAI API key
  --hf-token <token>     Hugging Face API token
  --no-start             Configure only, do not start Docker
  --help                 Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-url)
      REPO_URL="$2"
      shift 2
      ;;
    --branch)
      BRANCH="$2"
      shift 2
      ;;
    --install-dir)
      INSTALL_DIR="$2"
      shift 2
      ;;
    --openai-key)
      OPENAI_API_KEY="$2"
      shift 2
      ;;
    --hf-token)
      HUGGINGFACE_API_TOKEN="$2"
      shift 2
      ;;
    --no-start)
      START_GATEWAY=0
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "[ERR] Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "${REPO_URL}" ]]; then
  echo "[ERR] Missing repo URL. Set REPO_URL env var or pass --repo-url." >&2
  exit 1
fi

for bin in git docker; do
  if ! command -v "${bin}" >/dev/null 2>&1; then
    echo "[ERR] Missing dependency: ${bin}" >&2
    exit 1
  fi
done

if ! docker compose version >/dev/null 2>&1; then
  echo "[ERR] Docker Compose plugin is required (docker compose)." >&2
  exit 1
fi

if [[ -d "${INSTALL_DIR}/.git" ]]; then
  git -C "${INSTALL_DIR}" fetch origin "${BRANCH}"
  git -C "${INSTALL_DIR}" checkout "${BRANCH}"
  git -C "${INSTALL_DIR}" pull --ff-only origin "${BRANCH}"
else
  git clone --branch "${BRANCH}" "${REPO_URL}" "${INSTALL_DIR}"
fi

if [[ -z "${OPENAI_API_KEY}" && -t 0 ]]; then
  read -r -s -p "OpenAI API key: " OPENAI_API_KEY
  echo
fi

if [[ -z "${HUGGINGFACE_API_TOKEN}" && -t 0 ]]; then
  read -r -s -p "Hugging Face token: " HUGGINGFACE_API_TOKEN
  echo
fi

ENV_FILE="${INSTALL_DIR}/configs/local/.env.gateway"
cat > "${ENV_FILE}" <<ENV
# Local gateway secrets/config
OPENAI_API_KEY=${OPENAI_API_KEY}
HUGGINGFACE_API_TOKEN=${HUGGINGFACE_API_TOKEN}
HF_TIMEOUT_SECONDS=20
HF_MAX_RETRIES=2
ENV

cd "${INSTALL_DIR}"

if [[ ${START_GATEWAY} -eq 1 ]]; then
  docker compose --env-file configs/local/.env.gateway -f docker-compose.gateway.yml up --build -d

  echo "[OK] Gateway started"
  echo "[INFO] Health:  http://localhost:8000/health"
  echo "[INFO] Proxy:   http://localhost:8000/proxy/openai/v1/chat/completions"
  echo "[INFO] Test:    curl http://localhost:8000/health"
else
  echo "[OK] Configured only"
  echo "[INFO] Start with:"
  echo "docker compose --env-file configs/local/.env.gateway -f docker-compose.gateway.yml up --build -d"
fi
