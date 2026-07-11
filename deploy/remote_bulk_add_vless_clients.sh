#!/usr/bin/env bash
# Add multiple UUIDs to all vless inbounds (TCP + gRPC), one restart at the end.
# Arguments: CONFIG  INBOUND_TAG  UUID [UUID ...]
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

CONFIG="${1:?config path}"
TAG="${2:?inbound tag}"
shift 2

if ! command -v jq >/dev/null 2>&1; then
  echo "jq required" >&2
  exit 1
fi
if [[ ! -f "${CONFIG}" ]]; then
  echo "config not found: ${CONFIG}" >&2
  exit 1
fi
if [[ $# -lt 1 ]]; then
  echo "at least one UUID required" >&2
  exit 1
fi

for id in "$@"; do
  [[ -z "${id// /}" ]] && continue
  TMP="$(mktemp)"
  # Add to ALL vless inbounds
  jq --arg id "${id}" '
    .inbounds |= map(
      if .protocol == "vless" then
        .settings.clients |= (
          if map(.id) | index($id) then .
          else
            if (.[-1].flow // "") != "" then
              . + [{"id": $id, "flow": "xtls-rprx-vision", "email": ("bot-" + $id)}]
            else
              . + [{"id": $id, "email": ("bot-" + $id)}]
            end
          end
        )
      else . end
    )
  ' "${CONFIG}" >"${TMP}"
  # Fix flow: remove from gRPC, ensure on TCP
  jq --arg id "${id}" '
    .inbounds |= map(
      if .protocol == "vless" and (.streamSettings.network // "tcp") == "grpc" then
        .settings.clients |= map(if .id == $id then del(.flow) else . end)
      elif .protocol == "vless" and (.streamSettings.network // "tcp") == "tcp" then
        .settings.clients |= map(if .id == $id and (.flow // "") == "" then . + {"flow": "xtls-rprx-vision"} else . end)
      else . end
    )
  ' "${TMP}" > "${TMP}.2"
  mv "${TMP}.2" "${TMP}"
  mv "${TMP}" "${CONFIG}"
done

_vpnbot_fix_xray_config_perms "${CONFIG}"

if command -v systemctl >/dev/null 2>&1; then
  systemctl restart xray || true
fi
echo "OK:bulk_added"
