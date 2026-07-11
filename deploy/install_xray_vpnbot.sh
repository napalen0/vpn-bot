#!/usr/bin/env bash
# Ubuntu 22.04+ — install Xray + VLESS Reality (TCP + gRPC) for VPN bot.
# TCP inbound on VLESS_PORT, gRPC inbound on VLESS_PORT+1.
# Routing: Russian IPs/domains → direct (split tunnel).
# Run as root: sudo bash install_xray_vpnbot.sh
# Optional env vars:
#   REALITY_SNI=www.google.com  REALITY_DEST=www.google.com:443  VLESS_PORT=8443

set -euo pipefail

REALITY_SNI="${REALITY_SNI:-www.microsoft.com}"
REALITY_DEST="${REALITY_DEST:-www.microsoft.com:443}"
VLESS_PORT="${VLESS_PORT:-8443}"
INBOUND_TAG="${INBOUND_TAG:-vless-reality}"
GRPC_TAG="${GRPC_TAG:-vless-reality-grpc}"

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

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl ca-certificates jq uuid-runtime iproute2

# If 443 was explicitly requested but is occupied (nginx etc.), fall back to 8443
_vpnbot_443_listening() {
  command -v ss >/dev/null 2>&1 && ss -H -tln 2>/dev/null | grep -qE '(:|\.)443\s'
}
if [[ "${VLESS_PORT}" == "443" ]] && _vpnbot_443_listening; then
  echo "[vpnbot] port 443 is busy — switching VLESS inbound to 8443" >&2
  VLESS_PORT=8443
fi

GRPC_PORT=$((VLESS_PORT + 1))

if ! command -v xray >/dev/null 2>&1; then
  echo "[vpnbot] Installing Xray..."
  bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
fi

XRAY_BIN="$(command -v xray)"
CONFIG_DIR="/usr/local/etc/xray"
CONFIG="${CONFIG_DIR}/config.json"
GEODATA_DIR="/usr/local/share/xray"
mkdir -p "${CONFIG_DIR}" "${GEODATA_DIR}"

# Download geo data for Russian split-tunnel routing
echo "[vpnbot] Downloading geoip.dat and geosite.dat..."
curl -sLo "${GEODATA_DIR}/geoip.dat" "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat" || true
curl -sLo "${GEODATA_DIR}/geosite.dat" "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat" || true

KEY_OUT="$(${XRAY_BIN} x25519)"
PRIV=""
PUB=""
PUB_FROM_PASSWORD=""
while IFS= read -r line; do
  line="${line//$'\r'/}"
  case "$line" in
    *PrivateKey:*|*Private\ key:*) PRIV="$(echo "${line#*:}" | xargs)" ;;
    *PublicKey:*|*Public\ key:*) PUB="$(echo "${line#*:}" | xargs)" ;;
    *Password*:*)
      V="$(echo "${line##*:}" | xargs)"
      [[ -n "${V}" ]] && PUB_FROM_PASSWORD="${V}"
      ;;
  esac
done <<< "${KEY_OUT}"
if [[ -z "${PUB}" && -n "${PUB_FROM_PASSWORD}" ]]; then
  PUB="${PUB_FROM_PASSWORD}"
fi
if [[ -z "${PUB}" || -z "${PRIV}" ]]; then
  echo "[vpnbot] ERROR: cannot parse x25519 output:" >&2
  echo "${KEY_OUT}" >&2
  exit 1
fi

SID="$(openssl rand -hex 4)"
BOOT_UUID="$(uuidgen | tr '[:upper:]' '[:lower:]')"

cat >"${CONFIG}" <<EOF
{
  "log": { "loglevel": "warning" },
  "inbounds": [
    {
      "tag": "${INBOUND_TAG}",
      "listen": "0.0.0.0",
      "port": ${VLESS_PORT},
      "protocol": "vless",
      "settings": {
        "clients": [
          {
            "id": "${BOOT_UUID}",
            "flow": "xtls-rprx-vision",
            "email": "bootstrap-vpnbot"
          }
        ],
        "decryption": "none"
      },
      "streamSettings": {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
          "show": false,
          "dest": "${REALITY_DEST}",
          "xver": 0,
          "serverNames": ["${REALITY_SNI}"],
          "privateKey": "${PRIV}",
          "shortIds": ["${SID}"]
        }
      },
      "sniffing": {
        "enabled": true,
        "destOverride": ["http", "tls", "quic"]
      }
    },
    {
      "tag": "${GRPC_TAG}",
      "listen": "0.0.0.0",
      "port": ${GRPC_PORT},
      "protocol": "vless",
      "settings": {
        "clients": [
          {
            "id": "${BOOT_UUID}",
            "email": "bootstrap-grpc"
          }
        ],
        "decryption": "none"
      },
      "streamSettings": {
        "network": "grpc",
        "grpcSettings": {
          "serviceName": "grpc"
        },
        "security": "reality",
        "realitySettings": {
          "show": false,
          "dest": "${REALITY_DEST}",
          "xver": 0,
          "serverNames": ["${REALITY_SNI}"],
          "privateKey": "${PRIV}",
          "shortIds": ["${SID}"]
        }
      },
      "sniffing": {
        "enabled": true,
        "destOverride": ["http", "tls", "quic"]
      }
    }
  ],
  "outbounds": [
    { "protocol": "freedom", "tag": "direct" },
    { "protocol": "blackhole", "tag": "block" }
  ],
  "routing": {
    "domainStrategy": "IPIfNonMatch",
    "rules": [
      {
        "type": "field",
        "domain": ["geosite:category-ru", "geosite:category-gov-ru"],
        "outboundTag": "direct"
      },
      {
        "type": "field",
        "ip": ["geoip:ru"],
        "outboundTag": "direct"
      },
      {
        "type": "field",
        "protocol": ["bittorrent"],
        "outboundTag": "block"
      }
    ]
  }
}
EOF

_vpnbot_fix_xray_config_perms "${CONFIG}"

# Firewall
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -qiE 'Status:\s+active'; then
  echo "[vpnbot] ufw: allow ${VLESS_PORT}/tcp + ${GRPC_PORT}/tcp"
  ufw allow "${VLESS_PORT}/tcp" comment 'vpnbot xray vless' >/dev/null 2>&1 || true
  ufw allow "${GRPC_PORT}/tcp" comment 'vpnbot xray grpc' >/dev/null 2>&1 || true
fi
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld 2>/dev/null; then
  echo "[vpnbot] firewalld: ${VLESS_PORT}/tcp + ${GRPC_PORT}/tcp"
  firewall-cmd --permanent --add-port="${VLESS_PORT}/tcp" >/dev/null 2>&1 || true
  firewall-cmd --permanent --add-port="${GRPC_PORT}/tcp" >/dev/null 2>&1 || true
  firewall-cmd --reload >/dev/null 2>&1 || true
fi

echo "VPNBOT_JSON:{\"public_key\":\"${PUB}\",\"short_id\":\"${SID}\",\"sni\":\"${REALITY_SNI}\",\"vless_port\":${VLESS_PORT},\"grpc_port\":${GRPC_PORT},\"dest\":\"${REALITY_DEST}\",\"inbound_tag\":\"${INBOUND_TAG}\"}"

if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload 2>/dev/null || true
  systemctl enable xray 2>/dev/null || true
  systemctl restart xray 2>/dev/null || true
  systemctl is-active --quiet xray || echo "[vpnbot] warning: xray not active, see journalctl -u xray -n 30" >&2
fi
