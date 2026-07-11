#!/usr/bin/env bash
# Remove UUID from the vless-reality inbound (if present). Argument: UUID
set -euo pipefail

_vpnbot_fix_xray_config_perms() {
  local f="${1:?}"
  local d
  d="$(dirname "$f")"
  chmod 755 "$d" 2>/dev/null || true
  if getent passwd nobody >/dev/null 2>&1; then
    local ng
    ng="$(id -gn nobody 2>/dev/null || echo nogroup)"
    chown "nobody:${ng}" "$f" 2>/dev/null || chown nobody:nogroup "$f" 2>/dev/null || true
    chmod 640 "$f" 2>/dev/null || true
  else
    chmod 644 "$f" 2>/dev/null || true
    chown root:root "$f" 2>/dev/null || true
  fi
}

UUID="${1:?uuid required}"
CONFIG="${2:-/usr/local/etc/xray/config.json}"
TAG="${3:-vless-reality}"

if ! command -v jq >/dev/null 2>&1; then
  echo "jq required" >&2
  exit 1
fi
if [[ ! -f "${CONFIG}" ]]; then
  echo "config not found: ${CONFIG}" >&2
  exit 1
fi

TMP="$(mktemp)"
jq --arg id "${UUID}" --arg tag "${TAG}" '
  .inbounds |= map(
    if .tag == $tag then
      .settings |= (.clients = ((.clients // []) | map(select((.id // "") != $id))))
    else . end
  )
' "${CONFIG}" >"${TMP}"
mv "${TMP}" "${CONFIG}"
_vpnbot_fix_xray_config_perms "${CONFIG}"

if command -v systemctl >/dev/null 2>&1; then
  systemctl restart xray || true
fi
echo "OK:removed:${UUID}"
