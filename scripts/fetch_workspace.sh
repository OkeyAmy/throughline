#!/usr/bin/env bash
# Rebuild the demo workspace from scratch: clone the five public repos, run
# graphify over each, and drop graph.json where workspace.yml expects it.
# Nothing here is private — a judge can run it and get the same graph.
set -euo pipefail

REPOS=(
  "fastapi/fastapi"
  "encode/starlette"
  "encode/uvicorn"
  "encode/httpx"
  "encode/httpcore"
)

command -v graphify >/dev/null || { echo "install graphify first: uv tool install graphifyy"; exit 1; }

mkdir -p .repos data
for slug in "${REPOS[@]}"; do
  name="${slug##*/}"
  [ -d ".repos/$name" ] || git clone --depth 1 "https://github.com/$slug.git" ".repos/$name"
  graphify update ".repos/$name" --no-cluster
  mkdir -p "data/$name"
  cp ".repos/$name/graphify-out/graph.json" "data/$name/graph.json"
  echo "$name ready"
done

echo "now: python -m loader ingest --workspace workspace.yml"
