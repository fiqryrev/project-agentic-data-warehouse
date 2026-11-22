#!/usr/bin/env bash
# Auto Ontology at the pinned commit, plus our overlay patches (PLAN: no fork; consumed at a
# pinned SHA). Clones upstream into infra/auto-ontology/upstream/ (gitignored), checks out
# UPSTREAM_SHA, and applies patches/*.patch in order. `make up-ontology` then builds the images
# from that folder. Safe to rerun: the clone is reset to the pinned commit before patching.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
sha="$(tr -d '[:space:]' < "$here/UPSTREAM_SHA")"
dir="$here/upstream"
url="https://github.com/NVIDIA/auto-ontology.git"

if [ ! -d "$dir/.git" ]; then
  git clone --quiet "$url" "$dir"
fi
git -C "$dir" fetch --quiet origin
git -C "$dir" checkout --quiet --force "$sha"
git -C "$dir" reset --quiet --hard "$sha"
for patch in "$here"/patches/*.patch; do
  git -C "$dir" apply --whitespace=nowarn "$patch"
  echo "[auto-ontology] applied $(basename "$patch")"
done
echo "[auto-ontology] upstream at ${sha:0:12} with $(ls "$here"/patches/*.patch | wc -l | tr -d ' ') patch(es)"
