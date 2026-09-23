#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
SWAY_BIOME_VERSION="$(cat .biome-version)"
SWAY_BIOME="$SWAY_ROOT/.cache/tools/biome-$SWAY_BIOME_VERSION"
if [[ -x "$SWAY_BIOME" ]]; then
  "$SWAY_BIOME" --version
  exit 0
fi
case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) SWAY_BIOME_PLATFORM=darwin-arm64 ;;
  Darwin-x86_64) SWAY_BIOME_PLATFORM=darwin-x64 ;;
  Linux-aarch64|Linux-arm64) SWAY_BIOME_PLATFORM=linux-arm64 ;;
  Linux-x86_64) SWAY_BIOME_PLATFORM=linux-x64 ;;
  *) echo "No pinned Biome binary for this platform." >&2; exit 1 ;;
esac
mkdir -p "$SWAY_ROOT/.cache/tools"
SWAY_DOWNLOAD="$(mktemp "$SWAY_ROOT/.cache/tools/biome.XXXXXX")"
trap 'rm -f "$SWAY_DOWNLOAD"' EXIT
curl --fail --location --retry 2 --connect-timeout 15 --max-time 180   "https://github.com/biomejs/biome/releases/download/@biomejs/biome@$SWAY_BIOME_VERSION/biome-$SWAY_BIOME_PLATFORM"   --output "$SWAY_DOWNLOAD"
SWAY_EXPECTED="$(awk -v name="biome-$SWAY_BIOME_PLATFORM" '$2 == name {print $1}' scripts/biome.sha256)"
SWAY_ACTUAL="$(shasum -a 256 "$SWAY_DOWNLOAD" | awk '{print $1}')"
if [[ -z "$SWAY_EXPECTED" || "$SWAY_ACTUAL" != "$SWAY_EXPECTED" ]]; then
  echo "Biome checksum mismatch; refusing to install." >&2
  exit 1
fi
chmod +x "$SWAY_DOWNLOAD"
mv "$SWAY_DOWNLOAD" "$SWAY_BIOME"
"$SWAY_BIOME" --version
