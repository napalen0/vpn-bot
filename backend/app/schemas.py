from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserCreateIn(BaseModel):
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    referrer_telegram_id: int | None = None
    language: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: str | None
    status: str
    subscription_end: datetime | None
    referrer_id: int | None
    trial_used: bool
    sub_token: str | None = None
    language: str = "ru"


class VpnTrialIn(BaseModel):
    user_id: int


class VpnPaidIn(BaseModel):
    user_id: int
    days: int = Field(ge=1, le=3650)


class VpnExtendIn(BaseModel):
    user_id: int
    days: int = Field(ge=1, le=3650)


class VpnDeleteIn(BaseModel):
    user_id: int


class RefApplyIn(BaseModel):
    new_user_telegram_id: int
    referrer_telegram_id: int


class RefRewardIn(BaseModel):
    referred_user_id: int
    plan_days: int


class PaymentCreateInvoiceIn(BaseModel):
    user_id: int
    plan_days: int = Field(ge=1)
    amount: str
    currency: str = "USDT"


class VpnKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    vless_uri: str
    expires_at: datetime | None
    traffic_limit_bytes: int
    status: str
    server_id: int | None = None
    server_country: str | None = None
    server_name: str | None = None
