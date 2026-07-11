#!/usr/bin/env bash
# Add UUID to all vless inbounds (TCP + gRPC). Argument: UUID [CONFIG] [TAG]
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

# Add to ALL vless inbounds (both TCP tag and gRPC tag)
# For TCP inbound: add with flow xtls-rprx-vision
# For gRPC inbound: add without flow (gRPC incompatible with xtls-rprx-vision)
TMP="$(mktemp)"
jq --arg id "${UUID}" '
  .inbounds |= map(
    if .protocol == "vless" then
      .settings.clients |= (
        if map(.id) | index($id) then .
        else
          if .[-1].flow // "" != "" then
            . + [{"id": $id, "flow": "xtls-rprx-vision", "email": ("bot-" + $id)}]
          else
            . + [{"id": $id, "email": ("bot-" + $id)}]
          end
        end
      )
    else . end
  )
' "${CONFIG}" >"${TMP}"

# Correct: TCP inbound clients need flow, gRPC clients must NOT have flow
jq --arg id "${UUID}" '
  .inbounds |= map(
    if .protocol == "vless" and (.streamSettings.network // "tcp") == "grpc" then
      .settings.clients |= map(
        if .id == $id then del(.flow) else . end
      )
    elif .protocol == "vless" and (.streamSettings.network // "tcp") == "tcp" then
      .settings.clients |= map(
        if .id == $id and (.flow // "") == "" then . + {"flow": "xtls-rprx-vision"} else . end
      )
    else . end
  )
' "${TMP}" > "${TMP}.2"
mv "${TMP}.2" "${TMP}"
mv "${TMP}" "${CONFIG}"
_vpnbot_fix_xray_config_perms "${CONFIG}"

if command -v systemctl >/dev/null 2>&1; then
  systemctl restart xray || true
fi
echo "OK:${UUID}"
