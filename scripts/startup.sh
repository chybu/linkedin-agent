#!/usr/bin/env bash
set -euo pipefail

CONFIG_MODEL="${OLLAMA_CONFIG_MODEL:-ResumeConfig.EMBED_MODEL}"
OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
OLLAMA_LOG="${OLLAMA_LOG:-/tmp/linkedin-agent-ollama.log}"

get_config_model() {
  python3 - "$CONFIG_MODEL" <<'PY'
import ast
import sys
from pathlib import Path

target = sys.argv[1]
try:
    class_name, field_name = target.split(".", 1)
except ValueError:
    raise SystemExit(f"Invalid config model path: {target}")

config_path = Path("src/config.py")
tree = ast.parse(config_path.read_text())

for node in tree.body:
    if isinstance(node, ast.ClassDef) and node.name == class_name:
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for assign_target in stmt.targets:
                    if isinstance(assign_target, ast.Name) and assign_target.id == field_name:
                        value = ast.literal_eval(stmt.value)
                        if not isinstance(value, str):
                            raise SystemExit(f"{target} must be a string")
                        print(value)
                        raise SystemExit(0)

raise SystemExit(f"Could not find {target} in {config_path}")
PY
}

MODEL="${OLLAMA_MODEL:-$(get_config_model)}"

model_is_installed() {
  local model="$1"

  if [[ "$model" == *:* ]]; then
    ollama list | awk 'NR > 1 {print $1}' | grep -Fxq "$model"
  else
    ollama list | awk 'NR > 1 {print $1}' | grep -Fxq "$model" \
      || ollama list | awk 'NR > 1 {print $1}' | grep -Fxq "${model}:latest"
  fi
}

wait_for_command() {
  local name="$1"
  local command="$2"
  local timeout_seconds="${3:-120}"
  local elapsed=0

  printf "Waiting for %s" "$name"
  until eval "$command" >/dev/null 2>&1; do
    if [ "$elapsed" -ge "$timeout_seconds" ]; then
      printf "\nTimed out waiting for %s after %s seconds.\n" "$name" "$timeout_seconds" >&2
      return 1
    fi

    printf "."
    sleep 2
    elapsed=$((elapsed + 2))
  done
  printf "\n"
}

echo "Starting Docker Desktop..."
if command -v open >/dev/null 2>&1; then
  open -a Docker >/dev/null 2>&1 || true
fi

wait_for_command "Docker" "docker info" 180

echo "Starting Docker Compose services..."
docker compose up -d --build

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama CLI was not found. Install Ollama, then run this script again." >&2
  exit 1
fi

export OLLAMA_HOST

if curl -fsS "${OLLAMA_HOST}/api/tags" >/dev/null 2>&1; then
  echo "Ollama is already running."
else
  echo "Starting Ollama..."
  if command -v open >/dev/null 2>&1; then
    open -a Ollama >/dev/null 2>&1 || true
  fi

  if ! pgrep -f "ollama serve" >/dev/null 2>&1; then
    nohup ollama serve >"$OLLAMA_LOG" 2>&1 &
  fi
fi

wait_for_command "Ollama" "curl -fsS '${OLLAMA_HOST}/api/tags'" 180

echo "Checking Ollama model: ${MODEL}"
if model_is_installed "${MODEL}"; then
  echo "Model already installed: ${MODEL}"
else
  echo "Installing Ollama model: ${MODEL}"
  ollama pull "${MODEL}"
fi

echo "Startup complete."
echo "Postgres: localhost:5432"
echo "Adminer:  http://localhost:8080"
echo "Ollama:   ${OLLAMA_HOST}"
