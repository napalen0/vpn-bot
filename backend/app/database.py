import pathlib
from collections.abc import AsyncGenerator

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir(url: str) -> None:
    u = make_url(url)
    if not u.get_backend_name().startswith("sqlite") or not u.database:
        return
    path = pathlib.Path(u.database)
    if not path.is_absolute():
        path = pathlib.Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)


_settings = get_settings()
_ensure_sqlite_dir(_settings.database_url)
engine = create_async_engine(_settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


def _migrate_sqlite_servers_ssh(sync_conn) -> None:
    from sqlalchemy import text

    if sync_conn.engine.dialect.name != "sqlite":
        return
    rows = sync_conn.execute(text("PRAGMA table_info(servers)")).fetchall()
    cols = {row[1] for row in rows}
    if "ssh_user" not in cols:
        sync_conn.execute(text("ALTER TABLE servers ADD COLUMN ssh_user VARCHAR(255)"))
    if "ssh_port" not in cols:
        sync_conn.execute(text("ALTER TABLE servers ADD COLUMN ssh_port INTEGER DEFAULT 22"))
    if "ssh_password_encrypted" not in cols:
        sync_conn.execute(text("ALTER TABLE servers ADD COLUMN ssh_password_encrypted TEXT"))


def _sqlite_vpn_keys_has_uuid_unique_only(sync_conn) -> bool:
    """Legacy DBs: a UNIQUE constraint on uuid alone breaks pool (one UUID per multiple server_ids)."""
    from sqlalchemy import text

    rows = sync_conn.execute(text("PRAGMA index_list('vpn_keys')")).fetchall()
    for row in rows:
        if not row[2]:
            continue
        name = row[1]
        if not name:
            continue
        esc = str(name).replace("'", "''")
        cols = sync_conn.execute(text(f"PRAGMA index_info('{esc}')")).fetchall()
        col_names = [c[2] for c in cols if c[2]]
        if col_names == ["uuid"]:
            return True
    return False


def _migrate_sqlite_vpn_keys_drop_uuid_unique(sync_conn) -> None:
    """Recreate vpn_keys without global UNIQUE(uuid), preserving rows."""
    from sqlalchemy import text

    if sync_conn.engine.dialect.name != "sqlite":
        return
    t = sync_conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='vpn_keys'")
    ).scalar()
    if not t:
        return
    if not _sqlite_vpn_keys_has_uuid_unique_only(sync_conn):
        return

    sync_conn.execute(text("PRAGMA foreign_keys=OFF"))
    sync_conn.execute(text("ALTER TABLE vpn_keys RENAME TO vpn_keys_old"))
    sync_conn.execute(
        text(
            """
            CREATE TABLE vpn_keys (
              id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              server_id INTEGER NOT NULL,
              uuid VARCHAR(64) NOT NULL,
              vless_uri TEXT NOT NULL,
              expires_at DATETIME,
              traffic_limit_bytes INTEGER NOT NULL,
              traffic_used_bytes INTEGER NOT NULL,
              status VARCHAR(32) NOT NULL,
              created_at DATETIME,
              FOREIGN KEY(user_id) REFERENCES users (id),
              FOREIGN KEY(server_id) REFERENCES servers (id)
            )
            """
        )
    )
    sync_conn.execute(
        text(
            """
            INSERT INTO vpn_keys (
              id, user_id, server_id, uuid, vless_uri, expires_at,
              traffic_limit_bytes, traffic_used_bytes, status, created_at
            )
            SELECT
              id, user_id, server_id, uuid, vless_uri, expires_at,
              traffic_limit_bytes, traffic_used_bytes, status, created_at
            FROM vpn_keys_old
            """
        )
    )
    sync_conn.execute(text("DROP TABLE vpn_keys_old"))
    sync_conn.execute(text("CREATE INDEX IF NOT EXISTS ix_vpn_keys_user_id ON vpn_keys (user_id)"))
    sync_conn.execute(text("CREATE INDEX IF NOT EXISTS ix_vpn_keys_uuid ON vpn_keys (uuid)"))
    sync_conn.execute(text("PRAGMA foreign_keys=ON"))


def _migrate_sqlite_users_push_notify(sync_conn) -> None:
    from sqlalchemy import text

    if sync_conn.engine.dialect.name != "sqlite":
        return
    rows = sync_conn.execute(text("PRAGMA table_info(users)")).fetchall()
    cols = {row[1] for row in rows}
    if "notify_trial_ended_sent" not in cols:
        sync_conn.execute(text("ALTER TABLE users ADD COLUMN notify_trial_ended_sent BOOLEAN DEFAULT 0"))
    if "notify_sub_expired_sent" not in cols:
        sync_conn.execute(text("ALTER TABLE users ADD COLUMN notify_sub_expired_sent BOOLEAN DEFAULT 0"))
    if "notify_sub_3d_before_sent" not in cols:
        sync_conn.execute(text("ALTER TABLE users ADD COLUMN notify_sub_3d_before_sent BOOLEAN DEFAULT 0"))


def _migrate_sqlite_users_sub_token(sync_conn) -> None:
    from sqlalchemy import text

    if sync_conn.engine.dialect.name != "sqlite":
        return
    rows = sync_conn.execute(text("PRAGMA table_info(users)")).fetchall()
    cols = {row[1] for row in rows}
    if "sub_token" not in cols:
        sync_conn.execute(text("ALTER TABLE users ADD COLUMN sub_token VARCHAR(64)"))
        sync_conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_sub_token ON users (sub_token)"))


def _migrate_sqlite_servers_grpc(sync_conn) -> None:
    from sqlalchemy import text

    if sync_conn.engine.dialect.name != "sqlite":
        return
    rows = sync_conn.execute(text("PRAGMA table_info(servers)")).fetchall()
    cols = {row[1] for row in rows}
    if "grpc_port" not in cols:
        sync_conn.execute(text("ALTER TABLE servers ADD COLUMN grpc_port INTEGER"))


async def init_db() -> None:
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_sqlite_servers_ssh)
        await conn.run_sync(_migrate_sqlite_vpn_keys_drop_uuid_unique)
        await conn.run_sync(_migrate_sqlite_users_push_notify)
        await conn.run_sync(_migrate_sqlite_users_sub_token)
        await conn.run_sync(_migrate_sqlite_servers_grpc)
