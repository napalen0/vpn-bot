#!/usr/bin/env bash
# Change listen port of the VLESS inbound + fix config perms + ufw/firewalld + restart xray.
# Arguments: PORT  [CONFIG]  [INBOUND_TAG]
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

PORT="${1:?port required}"
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
jq --argjson p "${PORT}" --arg tag "${TAG}" '
  .inbounds |= map(if .tag == $tag then .port = $p else . end)
' "${CONFIG}" >"${TMP}"
mv "${TMP}" "${CONFIG}"

_vpnbot_fix_xray_config_perms "${CONFIG}"

if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -qiE 'Status:\s+active'; then
  ufw allow "${PORT}/tcp" comment 'vpnbot xray vless' >/dev/null 2>&1 || true
fi
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld 2>/dev/null; then
  firewall-cmd --permanent --add-port="${PORT}/tcp" >/dev/null 2>&1 || true
  firewall-cmd --reload >/dev/null 2>&1 || true
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl restart xray || true
fi
echo "OK:inbound_port=${PORT}"
