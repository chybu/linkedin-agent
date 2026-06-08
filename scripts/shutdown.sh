#!/usr/bin/env bash
set -euo pipefail

OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
STOP_OLLAMA="${STOP_OLLAMA:-1}"
STOP_DOCKER="${STOP_DOCKER:-1}"
REMOVE_VOLUMES="${REMOVE_VOLUMES:-0}"

wait_for_process_to_stop() {
  local name="$1"
  local check_command="$2"
  local timeout_seconds="${3:-30}"
  local elapsed=0

  printf "Waiting for %s to stop" "$name"
  while eval "$check_command" >/dev/null 2>&1; do
    if [ "$elapsed" -ge "$timeout_seconds" ]; then
      printf "\nTimed out waiting for %s to stop.\n" "$name" >&2
      return 1
    fi

    printf "."
    sleep 2
    elapsed=$((elapsed + 2))
  done
  printf "\n"
}

echo "Stopping Docker Compose services..."
if docker info >/dev/null 2>&1; then
  if [ "$REMOVE_VOLUMES" = "1" ]; then
    docker compose down --volumes
  else
    docker compose down
  fi
else
  echo "Docker daemon is not running; skipping Docker Compose shutdown."
fi

if [ "$STOP_OLLAMA" != "1" ]; then
  echo "Leaving Ollama running because STOP_OLLAMA=${STOP_OLLAMA}."
elif curl -fsS "${OLLAMA_HOST}/api/tags" >/dev/null 2>&1; then
  echo "Stopping Ollama..."

  if command -v osascript >/dev/null 2>&1; then
    osascript -e 'tell application "Ollama" to quit' >/dev/null 2>&1 || true
  fi

  pkill -x "Ollama" >/dev/null 2>&1 || true
  pkill -f "ollama serve" >/dev/null 2>&1 || true
  wait_for_process_to_stop "Ollama" "pgrep -x 'Ollama' || pgrep -f 'ollama serve'" 20 || true
else
  echo "Ollama is not running at ${OLLAMA_HOST}."
fi

if [ "$STOP_DOCKER" = "1" ]; then
  echo "Stopping Docker Desktop..."
  if command -v osascript >/dev/null 2>&1; then
    osascript -e 'tell application "Docker Desktop" to quit' >/dev/null 2>&1 || true
    osascript -e 'tell application "Docker" to quit' >/dev/null 2>&1 || true
    osascript -e 'tell application id "com.electron.dockerdesktop" to quit' >/dev/null 2>&1 || true
    osascript -e 'tell application id "com.docker.docker" to quit' >/dev/null 2>&1 || true
  fi

  pkill -x "Docker" >/dev/null 2>&1 || true
  pkill -x "Docker Desktop" >/dev/null 2>&1 || true
  pkill -f "Docker Desktop.app" >/dev/null 2>&1 || true
  pkill -f "com.docker.backend" >/dev/null 2>&1 || true
  pkill -f "com.docker.virtualization" >/dev/null 2>&1 || true
  pkill -f "com.docker.osxfs" >/dev/null 2>&1 || true
  pkill -f "com.docker.socket" >/dev/null 2>&1 || true

  if pgrep -x "Docker" >/dev/null 2>&1 \
    || pgrep -x "Docker Desktop" >/dev/null 2>&1 \
    || pgrep -f "Docker Desktop.app" >/dev/null 2>&1 \
    || pgrep -f "com.docker.backend" >/dev/null 2>&1; then
    wait_for_process_to_stop "Docker Desktop" "pgrep -x 'Docker' || pgrep -x 'Docker Desktop' || pgrep -f 'Docker Desktop.app' || pgrep -f 'com.docker.backend'" 30 || true
  else
    echo "Docker Desktop is not running."
  fi
else
  echo "Leaving Docker Desktop running because STOP_DOCKER=${STOP_DOCKER}."
fi

echo "Shutdown complete."
