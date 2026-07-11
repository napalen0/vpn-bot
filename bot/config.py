import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
# Load backend/.env first, then root .env (override=True so file values win over OS env)
load_dotenv(_ROOT / "backend" / ".env")
load_dotenv(_ROOT / ".env", override=True)

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
BACKEND_URL = (os.getenv("BACKEND_URL") or "http://127.0.0.1:8000").strip().rstrip("/")
API_SECRET = (os.getenv("API_SECRET") or "change-me-api-secret").strip()

# Required channel subscription (bot must be channel admin). Username without @
REQUIRED_CHANNEL_USERNAME = (os.getenv("REQUIRED_CHANNEL_USERNAME") or "rknspot").strip().lstrip("@")
REQUIRE_CHANNEL_SUBSCRIPTION = os.getenv("REQUIRE_CHANNEL_SUBSCRIPTION", "true").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
CHANNEL_PUBLIC_URL = (os.getenv("CHANNEL_PUBLIC_URL") or "https://t.me/rknspot").strip()
PUBLIC_BASE_URL = (os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")


def main_menu_image_path() -> Path | None:
    """Main menu image path. Defaults to menu_banner.png in project root; empty/none disables."""
    raw = (os.getenv("MAIN_MENU_IMAGE") or "menu_banner.png").strip()
    if not raw or raw.lower() in ("none", "0", "-"):
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = _ROOT / p
    return p if p.is_file() else None
