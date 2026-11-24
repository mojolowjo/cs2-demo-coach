#!/usr/bin/env bash
# One-shot setup for a fresh Claude workspace (or any Linux box).
# Installs the Python tools and the newest awpy map data (radar images + wall geometry).
set -euo pipefail

echo "== Python packages"
pip install --break-system-packages -q awpy demoparser2 pandas pyarrow 2>/dev/null \
  || pip install -q awpy demoparser2 pandas pyarrow

echo "== awpy map data"
# awpy's own "latest release" lookup uses api.github.com, which is blocked in Claude's workspace.
# Git and the direct release-download links work, so find the newest tag with git and pass it explicitly.
TAG=$(git ls-remote --tags --refs https://github.com/pnxenopoulos/awpy-data \
      | sed 's#.*refs/tags/##' | grep -E '^[0-9]+$' | sort -n | tail -1)
if [ -z "${TAG}" ]; then
  echo "Could not read awpy-data tags; wall check and radar images will be off." >&2
  exit 0
fi
if [ -f "${HOME}/.awpy/${TAG}/.geometry.zip.done" ]; then
  echo "awpy-data ${TAG} already installed"
else
  awpy get "${TAG}"
fi
echo "== ready (awpy-data ${TAG})"
