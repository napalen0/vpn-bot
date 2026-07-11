#!/usr/bin/env bash
# Stop xray, disable unit, remove config.json (other files in the directory are untouched).
# Argument: [CONFIG] (default /usr/local/etc/xray/config.json)
set -euo pipefail
CONFIG="${1:-/usr/local/etc/xray/config.json}"

if command -v systemctl >/dev/null 2>&1; then
  systemctl stop xray 2>/dev/null || true
  systemctl disable xray 2>/dev/null || true
fi
if [[ -f "${CONFIG}" ]]; then
  rm -f "${CONFIG}"
fi
echo "OK:removed"
