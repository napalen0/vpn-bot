import pathlib
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent
# Load backend/.env first, then root vpn-bot/.env (override so file values win over OS env)
load_dotenv(_BACKEND_ROOT / ".env", encoding="utf-8")
load_dotenv(_BACKEND_ROOT.parent / ".env", encoding="utf-8", override=True)


class Settings(BaseSettings):
    # After load_dotenv everything comes from os.environ; no env_file to avoid priority confusion
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./data/vpn_bot.db"
    api_secret: str = "change-me-api-secret"
    admin_username: str = "admin"
    admin_password: str = "change-me-admin"
    session_secret: str = "change-me-session-secret"

    bot_token: str = ""
    admin_telegram_ids: str = ""

    cryptobot_token: str = ""
    skip_webhook_signature: bool = False

    public_base_url: str = "http://127.0.0.1:8000"
    server_monitor_interval_sec: int = 0
    # User notifications for trial/subscription (0 = off). Recommended: 3600 or less.
    subscription_notify_interval_sec: int = 0
    xray_sync_ssh_private_key_path: str = ""
    xray_sync_ssh_password: str = ""

    @field_validator("api_secret", "admin_password", "session_secret", mode="before")
    @classmethod
    def _strip_secrets(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("admin_username", mode="before")
    @classmethod
    def _strip_username(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    @property
    def admin_ids_list(self) -> list[int]:
        if not self.admin_telegram_ids.strip():
            return []
        out: list[int] = []
        for part in self.admin_telegram_ids.split(","):
            part = part.strip()
            if part.isdigit():
                out.append(int(part))
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()
