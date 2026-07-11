# VPN Bot — Telegram VPN Service on VLESS + Reality

A complete, self-hosted VPN service managed through a Telegram bot. Users get one-tap access to a fast, censorship-resistant VPN — no apps to install beyond their favorite V2Ray client.

## Why This Project

| Problem | How VPN Bot solves it |
|---|---|
| VPN protocols get blocked by DPI | **VLESS + Reality** looks like regular HTTPS to any deep packet inspector |
| Single transport gets throttled | **Dual transport** — TCP and gRPC on every server; client auto-picks the one that works |
| Russian apps detect VPN and show popups | **Split-tunnel routing** — traffic to Russian sites goes direct, not through the tunnel |
| "White list" mode blocks everything | gRPC transport + Reality camouflage bypass even the strictest filters |
| Managing configs is painful | **Subscription URL** — one link, paste into V2Ray/Hiddify/Happ, always up to date |
| Adding servers is complicated | **One-click provisioning** — enter SSH credentials in admin panel, Xray installs automatically |

## Features

- **Telegram Bot** (aiogram 3) — single-message UI, trial activation, subscription purchase, config delivery
- **Subscription Links** — standard base64 V2Ray subscription format, auto-updates when you add servers
- **VLESS + Reality** — undetectable protocol with TCP and gRPC transports
- **Split-Tunnel** — Russian IPs and domains bypass the VPN (geoip/geosite rules on server)
- **Multi-Server Pool** — paid users get all servers, trial users get one
- **Admin Panel** — web dashboard for users, servers, keys, payments, settings
- **Auto-Provisioning** — add a server by IP + SSH credentials, Xray installs and configures itself
- **CryptoPay Payments** — accept crypto via [@CryptoBot](https://t.me/CryptoBot)
- **Referral System** — invite friends, earn bonus days
- **Server Health Monitor** — background checks with Telegram alerts to admins
- **Subscription Notifications** — reminds users before expiry via Telegram

## Architecture

```
Telegram User
    │
    ▼
┌──────────┐     HTTP      ┌──────────────────┐     SSH      ┌──────────────┐
│  TG Bot  │ ◄──────────► │  FastAPI Backend  │ ◄──────────► │  Xray Server │
│ aiogram 3│               │  + Admin Panel    │              │  VLESS+Reality│
└──────────┘               │  + SQLite/Postgres│              │  TCP + gRPC  │
                           └──────────────────┘              └──────────────┘
                                    │
                           ┌────────┴────────┐
                           │  /vpn/sub/{token}│  ← Subscription URL
                           │  (public, no key)│    for V2Ray clients
                           └─────────────────┘
```

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/yourname/vpn-bot.git
cd vpn-bot
cp .env.example .env
# Edit .env — set BOT_TOKEN, API_SECRET, SESSION_SECRET, PUBLIC_BASE_URL
```

### 2. Install dependencies

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Start the backend

```bash
cd backend
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Admin panel: `http://127.0.0.1:8080/admin`

### 4. Start the bot

```bash
# From the project root (vpn-bot/), not backend/
python3 -m bot.main
```

### 5. Add a VPN server

**Option A — Auto-provision (recommended):**

1. Get a VPS (Ubuntu 22.04+, any provider)
2. In admin panel → Servers → "Auto: SSH + Install Xray"
3. Enter IP, SSH port, login, password → Done

The backend SSHs into the VPS, installs Xray with VLESS+Reality (TCP + gRPC), sets up split-tunnel routing, and registers the server in the database. Takes ~30 seconds.

**Option B — Manual:**

1. Run `deploy/install_xray_vpnbot.sh` on your VPS
2. Copy the `VPNBOT_JSON` output
3. Add server manually in admin panel with the public key and short ID

### 6. Set up subscription URL (optional but recommended)

Point a domain to your backend with nginx:

```nginx
server {
    listen 443 ssl http2;
    server_name vpn.example.com;

    # SSL certs...

    location /vpn/sub/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Set `PUBLIC_BASE_URL=https://vpn.example.com` in `.env`. Users get a link like:
```
https://vpn.example.com/vpn/sub/a1b2c3d4-...
```
Paste it into V2Ray/Hiddify/Happ as a subscription — configs update automatically.

## Server Naming in Clients

Servers appear in V2Ray/Hiddify with clean names:
```
🇫🇮 Helsinki
🇫🇮 Helsinki gRPC
🇳🇱 Amsterdam
🇳🇱 Amsterdam gRPC
```

Set the `name` and `country` (ISO 3166-1 alpha-2) in the admin panel for each server.

## API Endpoints

All endpoints require `X-API-Key` header except subscription URLs.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/user/create` | Register user |
| GET | `/user/telegram/{id}` | Get user by Telegram ID |
| POST | `/vpn/create_trial` | Activate free trial |
| POST | `/vpn/create_paid` | Create paid subscription |
| POST | `/vpn/vless_export` | Get VLESS configs |
| GET | `/vpn/sub/{token}` | Subscription URL (public) |
| POST | `/vpn/sync_pool` | Sync keys across servers |
| GET | `/catalog` | List available plans |
| POST | `/payment/create_invoice` | Create CryptoPay invoice |
| POST | `/payment/webhook` | CryptoPay callback |

## Deploy Scripts

| Script | Purpose |
|--------|---------|
| `install_xray_vpnbot.sh` | Install Xray + VLESS Reality (TCP+gRPC) + split-tunnel |
| `remote_add_vless_client.sh` | Add UUID to all Xray inbounds |
| `remote_bulk_add_vless_clients.sh` | Bulk-add UUIDs after Xray reinstall |
| `remote_remove_vless_client.sh` | Remove UUID on subscription expiry |
| `remote_set_reality_dest.sh` | Change Reality masquerade target |
| `remote_apply_inbound_port.sh` | Change Xray listening port |
| `remote_remove_xray_vpnbot.sh` | Uninstall Xray from server |

## Split-Tunnel Details

The Xray server config includes routing rules that send Russian traffic direct:

- `geosite:category-ru` — Russian websites
- `geosite:category-gov-ru` — Government services
- `geoip:ru` — Russian IP ranges

This means Russian apps (banks, government services, delivery apps) work normally without VPN popups asking to disable it.

Geo-data is downloaded from [Loyalsoldier/v2ray-rules-dat](https://github.com/Loyalsoldier/v2ray-rules-dat) during server provisioning.

## Security Notes

- Change all default secrets in `.env` before deploying
- Never commit `.env` (it's in `.gitignore`)
- SSH passwords for servers are encrypted with Fernet (tied to `SESSION_SECRET`)
- Use HTTPS in production for the subscription endpoint
- Consider PostgreSQL instead of SQLite for production loads

## Project Structure

```
vpn-bot/
├── backend/
│   └── app/
│       ├── main.py              # FastAPI app + startup
│       ├── models.py            # SQLAlchemy models
│       ├── database.py          # DB engine + auto-migrations
│       ├── config.py            # Settings from .env
│       ├── admin_routes.py      # Admin panel (Jinja2)
│       ├── routers/             # API endpoints
│       │   ├── vpn.py           # VPN keys + subscription URL
│       │   ├── user.py          # User management
│       │   ├── payment.py       # CryptoPay integration
│       │   ├── catalog.py       # Plan catalog
│       │   └── ref.py           # Referral system
│       ├── services/            # Business logic
│       │   ├── vpn_core.py      # VLESS URI builder, pool management
│       │   ├── vless_bundle.py  # Subscription export (base64)
│       │   ├── xray_ssh.py      # SSH operations on Xray servers
│       │   ├── cryptobot.py     # CryptoPay API client
│       │   └── ...
│       └── templates/admin/     # Admin panel HTML
├── bot/
│   ├── main.py                  # Bot entry point
│   ├── client.py                # Backend HTTP client
│   ├── config.py                # Bot settings
│   ├── keyboards.py             # Inline keyboards
│   ├── handlers/menu.py         # All bot handlers
│   ├── middlewares/              # Channel subscription gate
│   └── utils/                   # UI helpers
├── deploy/                      # Server provisioning scripts
├── .env.example                 # Configuration template
└── requirements.txt             # Python dependencies
```

## Tech Stack

- **Python 3.11+**
- **FastAPI** — async backend + admin panel
- **aiogram 3** — Telegram bot framework
- **SQLAlchemy 2** (async) — ORM with auto-migrations
- **SQLite** (dev) / **PostgreSQL** (prod)
- **Xray-core** — VLESS + Reality protocol
- **asyncssh** — remote server management
- **CryptoPay** — cryptocurrency payments

## License

MIT
