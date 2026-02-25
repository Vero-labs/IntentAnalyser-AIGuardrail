#!/usr/bin/env bash

set -euo pipefail

REPO_URL="${REPO_URL:-}"
BRANCH="${BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-}"
OPENAI_API_KEY="${OPENAI_API_KEY:-}"
HUGGINGFACE_API_TOKEN="${HUGGINGFACE_API_TOKEN:-}"
GATEWAY_PORT="${GATEWAY_PORT:-8000}"
START_GATEWAY=1
AUTO_INSTALL_DEPS=1
NON_INTERACTIVE=0

PROVIDER_NAME="${PROVIDER_NAME:-openai}"
PROVIDER_MODEL="${PROVIDER_MODEL:-gpt-4o-mini}"
PROVIDER_BASE_URL="${PROVIDER_BASE_URL:-https://api.openai.com}"
PROVIDER_API_KEY_ENV="${PROVIDER_API_KEY_ENV:-OPENAI_API_KEY}"
PROVIDER_API_KEY_VALUE=""

CLASSIFIER_MODE="${CLASSIFIER_MODE:-local}"
CLASSIFIER_MODEL="${CLASSIFIER_MODEL:-distilbert-mnli}"
CLASSIFIER_LOCAL_MODEL_SOURCE="${CLASSIFIER_LOCAL_MODEL_SOURCE:-typeform/distilbert-base-uncased-mnli}"
CLASSIFIER_LOCAL_MODEL_DIR=""
CLASSIFIER_EXTERNAL_ENDPOINT="${CLASSIFIER_EXTERNAL_ENDPOINT:-}"
CLASSIFIER_EXTERNAL_AUTH_HEADER="${CLASSIFIER_EXTERNAL_AUTH_HEADER:-}"
DOWNLOAD_LOCAL_MODEL=1

GATEWAY_AUTH_MODE="${GATEWAY_AUTH_MODE:-api_key}"
GATEWAY_API_KEY="${GATEWAY_API_KEY:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd 2>/dev/null || pwd)"
REPO_FROM_SCRIPT="$(cd "${SCRIPT_DIR}/.." && pwd 2>/dev/null || pwd)"

usage() {
  cat <<USAGE
Usage: quickstart.sh [options]

Options:
  --repo-url <url>          Git repo URL (required when not running inside repo)
  --branch <name>           Git branch (default: main)
  --install-dir <path>      Install directory
  --openai-key <key>        OpenAI API key (or key for provider_api_key_env)
  --provider-key <key>      Explicit upstream provider API key value
  --hf-token <token>        Hugging Face token (only for classifier.mode=hosted)
  --port <port>             Host port (default: 8000)
  --no-start                Configure only
  --skip-install            Skip auto-install of dependencies
  --non-interactive         Disable wizard prompts (must pass required flags)
  --help                    Show this help
USAGE
}

log() {
  echo "[INFO] $*"
}

err() {
  echo "[ERR] $*" >&2
}

cmd_exists() {
  command -v "$1" >/dev/null 2>&1
}

is_interactive() {
  [[ ${NON_INTERACTIVE} -eq 0 ]] && [[ -r /dev/tty ]]
}

tty_read() {
  local prompt="$1"
  local default_value="${2:-}"
  local result

  if [[ -n "${default_value}" ]]; then
    printf "%s [%s]: " "${prompt}" "${default_value}" > /dev/tty
  else
    printf "%s: " "${prompt}" > /dev/tty
  fi

  IFS= read -r result < /dev/tty || true
  if [[ -z "${result}" ]]; then
    result="${default_value}"
  fi
  printf "%s" "${result}"
}

tty_read_secret() {
  local prompt="$1"
  local result
  printf "%s: " "${prompt}" > /dev/tty
  IFS= read -r -s result < /dev/tty || true
  printf "\n" > /dev/tty
  printf "%s" "${result}"
}

tty_confirm() {
  local prompt="$1"
  local default_yes="${2:-1}"
  local suffix="[Y/n]"
  if [[ ${default_yes} -eq 0 ]]; then
    suffix="[y/N]"
  fi
  local answer
  printf "%s %s: " "${prompt}" "${suffix}" > /dev/tty
  IFS= read -r answer < /dev/tty || true
  answer="$(printf '%s' "${answer}" | tr '[:upper:]' '[:lower:]')"

  if [[ -z "${answer}" ]]; then
    [[ ${default_yes} -eq 1 ]] && return 0 || return 1
  fi

  [[ "${answer}" == "y" || "${answer}" == "yes" ]]
}

sudo_run() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
    return
  fi
  if cmd_exists sudo; then
    sudo "$@"
    return
  fi
  err "Root privileges required but sudo is unavailable."
  exit 1
}

install_dependencies() {
  local missing=0
  for bin in git curl python3; do
    if ! cmd_exists "${bin}"; then
      missing=1
      break
    fi
  done

  if [[ ${START_GATEWAY} -eq 1 ]] && ! cmd_exists docker; then
    missing=1
  fi

  if [[ ${missing} -eq 0 ]] && [[ ${START_GATEWAY} -eq 0 ]]; then
    return
  fi

  if [[ ${missing} -eq 0 ]] && docker compose version >/dev/null 2>&1; then
    return
  fi

  if [[ ${AUTO_INSTALL_DEPS} -eq 0 ]]; then
    err "Missing dependencies and --skip-install was used."
    exit 1
  fi

  log "Installing dependencies (git, curl, python3, docker, compose)..."

  if cmd_exists apt-get; then
    sudo_run apt-get update
    sudo_run apt-get install -y git curl ca-certificates docker.io docker-compose-plugin python3 python3-pip
  elif cmd_exists dnf; then
    sudo_run dnf install -y git curl ca-certificates docker docker-compose-plugin python3 python3-pip
  elif cmd_exists yum; then
    sudo_run yum install -y git curl ca-certificates docker python3 python3-pip
  elif cmd_exists pacman; then
    sudo_run pacman -Sy --noconfirm git curl docker docker-compose python python-pip
  elif cmd_exists zypper; then
    sudo_run zypper --non-interactive install git curl docker docker-compose python3 python3-pip
  else
    err "Unsupported distro. Install git/curl/docker/docker-compose/python3 manually."
    exit 1
  fi

  if cmd_exists systemctl; then
    sudo_run systemctl enable --now docker || true
  fi
}

detect_docker_prefix() {
  if docker info >/dev/null 2>&1; then
    DOCKER_PREFIX=()
    return
  fi
  if cmd_exists sudo && sudo docker info >/dev/null 2>&1; then
    DOCKER_PREFIX=(sudo)
    log "Using sudo for docker commands"
    return
  fi
  err "Docker daemon not available"
  exit 1
}

docker_cmd() {
  "${DOCKER_PREFIX[@]}" docker "$@"
}

compose_cmd() {
  docker_cmd compose "$@"
}

default_provider_model() {
  case "$1" in
    openai) printf "gpt-4o-mini" ;;
    anthropic) printf "claude-3-5-sonnet-20241022" ;;
    azure) printf "gpt-4" ;;
    custom) printf "llama3" ;;
    *) printf "gpt-4o-mini" ;;
  esac
}

default_provider_base_url() {
  case "$1" in
    openai) printf "https://api.openai.com" ;;
    anthropic) printf "https://api.anthropic.com" ;;
    azure) printf "https://YOUR_RESOURCE.openai.azure.com" ;;
    custom) printf "http://localhost:11434/v1" ;;
    *) printf "https://api.openai.com" ;;
  esac
}

default_provider_api_env() {
  case "$1" in
    openai) printf "OPENAI_API_KEY" ;;
    anthropic) printf "ANTHROPIC_API_KEY" ;;
    azure) printf "AZURE_OPENAI_API_KEY" ;;
    custom) printf "PROVIDER_API_KEY" ;;
    *) printf "OPENAI_API_KEY" ;;
  esac
}

generate_api_key() {
  if cmd_exists openssl; then
    openssl rand -hex 24
    return
  fi
  od -An -N24 -tx1 /dev/urandom | tr -d ' \n'
}

sanitize_slug() {
  printf "%s" "$1" | tr '/: ' '___'
}

download_local_model() {
  local source_repo="$1"
  local target_dir="$2"

  log "Downloading local classifier model (${source_repo}) to ${target_dir}"
  mkdir -p "${target_dir}"

  python3 - "${source_repo}" "${target_dir}" <<'PY'
import os
import subprocess
import sys

repo_id = sys.argv[1]
local_dir = sys.argv[2]

try:
    from huggingface_hub import snapshot_download
except Exception:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub>=0.24.0"])
    from huggingface_hub import snapshot_download

snapshot_download(repo_id=repo_id, local_dir=local_dir)
print(f"Downloaded {repo_id} to {local_dir}")
PY
}

ensure_repo() {
  if [[ -z "${INSTALL_DIR}" ]]; then
    if [[ -f "${REPO_FROM_SCRIPT}/docker-compose.gateway.yml" ]]; then
      INSTALL_DIR="${REPO_FROM_SCRIPT}"
    else
      INSTALL_DIR="$HOME/guardrail-llm-gateway"
    fi
  fi

  if [[ -f "${INSTALL_DIR}/docker-compose.gateway.yml" ]]; then
    if [[ -n "${REPO_URL}" && -d "${INSTALL_DIR}/.git" ]]; then
      git -C "${INSTALL_DIR}" fetch origin "${BRANCH}"
      git -C "${INSTALL_DIR}" checkout "${BRANCH}"
      git -C "${INSTALL_DIR}" pull --ff-only origin "${BRANCH}"
    fi
    return
  fi

  if [[ -z "${REPO_URL}" ]]; then
    err "Repo not found at ${INSTALL_DIR}. Provide --repo-url."
    exit 1
  fi

  if [[ -d "${INSTALL_DIR}/.git" ]]; then
    git -C "${INSTALL_DIR}" fetch origin "${BRANCH}"
    git -C "${INSTALL_DIR}" checkout "${BRANCH}"
    git -C "${INSTALL_DIR}" pull --ff-only origin "${BRANCH}"
  else
    git clone --branch "${BRANCH}" "${REPO_URL}" "${INSTALL_DIR}"
  fi
}

run_wizard() {
  if ! is_interactive; then
    return
  fi

  log "Starting Guardrail setup wizard"

  if [[ -z "${REPO_URL}" && ! -f "${INSTALL_DIR:-}/docker-compose.gateway.yml" && ! -f "${REPO_FROM_SCRIPT}/docker-compose.gateway.yml" ]]; then
    REPO_URL="$(tty_read 'Git repository URL')"
  fi

  local default_install_dir="${INSTALL_DIR}"
  if [[ -z "${default_install_dir}" ]]; then
    if [[ -f "${REPO_FROM_SCRIPT}/docker-compose.gateway.yml" ]]; then
      default_install_dir="${REPO_FROM_SCRIPT}"
    else
      default_install_dir="$HOME/guardrail-llm-gateway"
    fi
  fi
  INSTALL_DIR="$(tty_read 'Install directory' "${default_install_dir}")"

  if [[ -z "${PROVIDER_NAME}" ]]; then
    PROVIDER_NAME="openai"
  fi

  provider_choice="$(tty_read 'Provider (openai/anthropic/azure/custom)' "${PROVIDER_NAME}")"
  PROVIDER_NAME="${provider_choice}"

  PROVIDER_MODEL="$(tty_read 'Upstream model' "$(default_provider_model "${PROVIDER_NAME}")")"
  PROVIDER_BASE_URL="$(tty_read 'Provider base URL' "$(default_provider_base_url "${PROVIDER_NAME}")")"
  PROVIDER_API_KEY_ENV="$(tty_read 'Provider API key env var' "$(default_provider_api_env "${PROVIDER_NAME}")")"

  if [[ -z "${OPENAI_API_KEY}" ]]; then
    PROVIDER_API_KEY_VALUE="$(tty_read_secret "${PROVIDER_API_KEY_ENV} value")"
  else
    PROVIDER_API_KEY_VALUE="${OPENAI_API_KEY}"
  fi

  CLASSIFIER_MODE="$(tty_read 'Classifier mode (local/hosted/external)' "${CLASSIFIER_MODE}")"
  case "${CLASSIFIER_MODE}" in
    local)
      CLASSIFIER_MODEL="$(tty_read 'Local classifier label' "${CLASSIFIER_MODEL}")"
      CLASSIFIER_LOCAL_MODEL_SOURCE="$(tty_read 'Local model source repo (for download)' "${CLASSIFIER_LOCAL_MODEL_SOURCE}")"
      ;;
    hosted)
      CLASSIFIER_MODEL="$(tty_read 'Hosted classifier model' "facebook/bart-large-mnli")"
      if [[ -z "${HUGGINGFACE_API_TOKEN}" ]]; then
        HUGGINGFACE_API_TOKEN="$(tty_read_secret 'Hugging Face API token')"
      fi
      ;;
    external)
      CLASSIFIER_EXTERNAL_ENDPOINT="$(tty_read 'External classifier endpoint' "${CLASSIFIER_EXTERNAL_ENDPOINT}")"
      CLASSIFIER_EXTERNAL_AUTH_HEADER="$(tty_read 'External classifier auth header (optional)' "${CLASSIFIER_EXTERNAL_AUTH_HEADER}")"
      ;;
    *)
      err "Invalid classifier mode: ${CLASSIFIER_MODE}"
      exit 1
      ;;
  esac

  GATEWAY_AUTH_MODE="$(tty_read 'Gateway auth mode (none/api_key/jwt/api_key_or_jwt/api_key_and_jwt)' "${GATEWAY_AUTH_MODE}")"
  if [[ "${GATEWAY_AUTH_MODE}" == *"api_key"* && -z "${GATEWAY_API_KEY}" ]]; then
    if tty_confirm "Generate gateway API key automatically?" 1; then
      GATEWAY_API_KEY="$(generate_api_key)"
    else
      GATEWAY_API_KEY="$(tty_read_secret 'Gateway API key')"
    fi
  fi

  GATEWAY_PORT="$(tty_read 'Gateway port' "${GATEWAY_PORT}")"

  if [[ "${CLASSIFIER_MODE}" == "local" ]]; then
    if ! tty_confirm "Download local classifier model now?" 1; then
      DOWNLOAD_LOCAL_MODEL=0
    fi
  fi

  if ! tty_confirm "Start gateway after configuration?" 1; then
    START_GATEWAY=0
  fi
}

write_runtime_config() {
  local config_file="$1"
  local local_model_dir_cfg=""
  local classifier_provider="huggingface"
  local classifier_api_token=""
  local classifier_endpoint=""
  local classifier_auth_header=""
  local classifier_offline="true"

  if [[ "${CLASSIFIER_MODE}" == "local" ]]; then
    local model_slug
    model_slug="$(sanitize_slug "${CLASSIFIER_MODEL}")"
    local host_model_dir="${INSTALL_DIR}/models/${model_slug}"
    CLASSIFIER_LOCAL_MODEL_DIR="/models/${model_slug}"
    local_model_dir_cfg="${CLASSIFIER_LOCAL_MODEL_DIR}"

    if [[ ${DOWNLOAD_LOCAL_MODEL} -eq 1 ]]; then
      if ! download_local_model "${CLASSIFIER_LOCAL_MODEL_SOURCE}" "${host_model_dir}"; then
        err "Local model download failed. Continuing with local mode configuration."
      fi
    else
      mkdir -p "${host_model_dir}"
    fi
  elif [[ "${CLASSIFIER_MODE}" == "hosted" ]]; then
    classifier_provider="huggingface"
    classifier_api_token='${HUGGINGFACE_API_TOKEN}'
    classifier_offline="false"
  else
    classifier_provider="custom"
    classifier_endpoint="${CLASSIFIER_EXTERNAL_ENDPOINT}"
    classifier_auth_header="${CLASSIFIER_EXTERNAL_AUTH_HEADER}"
    classifier_offline="false"
  fi

  mkdir -p "$(dirname "${config_file}")"

  cat > "${config_file}" <<EOF_CONFIG
provider:
  name: ${PROVIDER_NAME}
  model: ${PROVIDER_MODEL}
  base_url: ${PROVIDER_BASE_URL}
  api_key_env: ${PROVIDER_API_KEY_ENV}
classifier:
  mode: ${CLASSIFIER_MODE}
  model: ${CLASSIFIER_MODEL}
  local_model_dir: "${local_model_dir_cfg}"
  provider: ${classifier_provider}
  api_token: "${classifier_api_token}"
  endpoint: "${classifier_endpoint}"
  auth_header: "${classifier_auth_header}"
  timeout_seconds: 8.0
  offline_mode: ${classifier_offline}
server:
  host: 0.0.0.0
  port: 8000
policy_mode: custom
request_timeout_seconds: 60.0
logging:
  store_prompts: false
EOF_CONFIG
}

write_env_file() {
  local env_file="$1"
  mkdir -p "$(dirname "${env_file}")"

  cat > "${env_file}" <<EOF_ENV
# Local gateway secrets/config
${PROVIDER_API_KEY_ENV}=${PROVIDER_API_KEY_VALUE}
HUGGINGFACE_API_TOKEN=${HUGGINGFACE_API_TOKEN}
GATEWAY_AUTH_MODE=${GATEWAY_AUTH_MODE}
GATEWAY_API_KEYS=${GATEWAY_API_KEY}
GATEWAY_METRICS_REQUIRE_AUTH=false
GATEWAY_PORT=${GATEWAY_PORT}
HF_TIMEOUT_SECONDS=20
HF_MAX_RETRIES=2
EOF_ENV
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
    --provider-key)
      PROVIDER_API_KEY_VALUE="$2"
      shift 2
      ;;
    --hf-token)
      HUGGINGFACE_API_TOKEN="$2"
      shift 2
      ;;
    --port)
      GATEWAY_PORT="$2"
      shift 2
      ;;
    --no-start)
      START_GATEWAY=0
      shift
      ;;
    --skip-install)
      AUTO_INSTALL_DEPS=0
      shift
      ;;
    --non-interactive)
      NON_INTERACTIVE=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      err "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if ! [[ "${GATEWAY_PORT}" =~ ^[0-9]+$ ]] || [[ "${GATEWAY_PORT}" -lt 1 ]] || [[ "${GATEWAY_PORT}" -gt 65535 ]]; then
  err "Invalid --port value: ${GATEWAY_PORT}"
  exit 1
fi

install_dependencies
run_wizard
ensure_repo

if [[ -z "${PROVIDER_API_KEY_VALUE}" ]]; then
  PROVIDER_API_KEY_VALUE="${OPENAI_API_KEY}"
fi

if [[ "${GATEWAY_AUTH_MODE}" == *"api_key"* && -z "${GATEWAY_API_KEY}" ]]; then
  GATEWAY_API_KEY="$(generate_api_key)"
fi

CONFIG_FILE="${INSTALL_DIR}/configs/local/guardrail.config.yaml"
ENV_FILE="${INSTALL_DIR}/configs/local/.env.gateway"

write_runtime_config "${CONFIG_FILE}"
write_env_file "${ENV_FILE}"

cd "${INSTALL_DIR}"

if [[ ${START_GATEWAY} -eq 1 ]]; then
  detect_docker_prefix
  log "Starting gateway..."
  GATEWAY_PORT="${GATEWAY_PORT}" compose_cmd --env-file configs/local/.env.gateway -f docker-compose.gateway.yml up --build -d

  echo
  echo "[OK] Guardrail Gateway started"
  echo "[INFO] Health: http://localhost:${GATEWAY_PORT}/health"
  echo "[INFO] Proxy:  http://localhost:${GATEWAY_PORT}/proxy/openai/v1/chat/completions"
  echo "[INFO] Mode:   classifier=${CLASSIFIER_MODE} provider=${PROVIDER_NAME}"
  if [[ "${GATEWAY_AUTH_MODE}" == *"api_key"* ]]; then
    echo "[INFO] Gateway API key: ${GATEWAY_API_KEY}"
  fi
else
  echo "[OK] Configuration written"
  echo "[INFO] Config: ${CONFIG_FILE}"
  echo "[INFO] Env:    ${ENV_FILE}"
  echo "[INFO] Start with:"
  echo "GATEWAY_PORT=${GATEWAY_PORT} docker compose --env-file configs/local/.env.gateway -f docker-compose.gateway.yml up --build -d"
fi
