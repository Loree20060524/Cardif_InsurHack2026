"""Lazy Postgres document storage, shared transactions, and revision tracking."""

from __future__ import annotations

import hashlib
import os
import threading
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Iterator
from urllib.parse import urlsplit


URL_KEYS = (
    "REGINTEL_DATABASE_URL", "DATABASE_URL", "POSTGRES_URL", "STORAGE_URL",
    "STORAGE_DATABASE_URL", "STORAGE_POSTGRES_URL", "POSTGRES_URL_NON_POOLING",
)
DB_ENV_KEYS = (*URL_KEYS, "PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGPORT",
               "REGINTEL_STORAGE_NAMESPACE")
UNAVAILABLE = "資料庫暫時無法讀寫，請稍後重試或檢查 Neon 連線設定。"


class StorageError(RuntimeError):
    """A safe public error; never includes driver details or credentials."""


class StorageBusyError(StorageError):
    pass


def database_settings() -> tuple[str, str] | None:
    """Accept Marketplace variable names without automatically loading env files."""
    namespace = os.environ.get("REGINTEL_STORAGE_NAMESPACE", "regintel-v1").strip()
    if not 1 <= len(namespace) <= 128:
        raise StorageError("REGINTEL_STORAGE_NAMESPACE 必須介於 1 至 128 字。")
    for key in URL_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            try:
                valid = urlsplit(value).scheme in {"postgres", "postgresql"}
            except ValueError:
                valid = False
            if not valid:
                raise StorageError(f"{key} 必須是 PostgreSQL 連線設定。")
            return value, namespace
    if os.environ.get("PGHOST") and os.environ.get("PGDATABASE"):
        return "", namespace
    return None


def configured() -> bool:
    return database_settings() is not None


def _lock_key(namespace: str, key: str) -> int:
    return int.from_bytes(hashlib.sha256(f"regintel:{namespace}:{key}".encode()).digest()[:8],
                          "big", signed=True)


class PostgresStore:
    def __init__(self, dsn: str, namespace: str):
        self._dsn = dsn
        self.namespace = namespace
        self._local = threading.local()
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    @contextmanager
    def connection(self) -> Iterator[Any]:
        active = getattr(self._local, "connection", None)
        if active is not None:
            yield active
            return
        try:
            import psycopg
            from psycopg.conninfo import conninfo_to_dict
        except ImportError:
            raise StorageError("資料庫驅動尚未安裝，請安裝 requirements.txt。") from None
        try:
            options = conninfo_to_dict(self._dsn)
            options.setdefault("sslmode", "require")
            options.update(connect_timeout=10, prepare_threshold=None)
            # Transaction locks work with Neon's transaction-pooling endpoint.
            with psycopg.connect(**options) as conn:
                self._timeouts(conn)
                self._ensure_schema(conn)
                yield conn
        except psycopg.Error:
            self._schema_ready = False
            raise StorageError(UNAVAILABLE) from None
        except StorageError as exc:
            if not isinstance(exc, StorageBusyError):
                self._schema_ready = False
            raise

    def _execute(self, conn: Any, query: str, parameters=None):
        import psycopg
        try:
            return conn.execute(query, parameters)
        except psycopg.Error:
            if getattr(self._local, "connection", None) is not None:
                self._local.failed = True
            raise StorageError(UNAVAILABLE) from None

    def _timeouts(self, conn: Any) -> None:
        self._execute(conn, "SET LOCAL lock_timeout = '5s'")
        self._execute(conn, "SET LOCAL statement_timeout = '30s'")

    def _ensure_schema(self, conn: Any) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            self._execute(conn, "SELECT pg_advisory_xact_lock(%s)", (_lock_key("schema", "v1"),))
            self._execute(conn, """
                CREATE TABLE IF NOT EXISTS public.regintel_documents (
                    namespace text NOT NULL,
                    document_key text NOT NULL,
                    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
                    revision bigint NOT NULL DEFAULT 1,
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY (namespace, document_key)
                )
            """)
            # Commit DDL separately so a later request rollback cannot remove it.
            conn.commit()
            self._timeouts(conn)
            self._schema_ready = True

    @contextmanager
    def transaction(self, *keys: str, blocking: bool = True,
                    import_only: bool = False) -> Iterator[None]:
        """Serialize each read/merge/write cycle, reusing nested transactions."""
        active = getattr(self._local, "connection", None)
        if active is not None:
            if import_only:
                raise StorageError("資料搬移不能在其他交易內執行。")
            self._acquire(active, keys, blocking)
            yield
            return
        with self.connection() as conn:
            gate = "pg_advisory_xact_lock" if import_only else "pg_advisory_xact_lock_shared"
            self._execute(conn, f"SELECT {gate}(%s)", (_lock_key(self.namespace, "migration"),))
            self._local.connection = conn
            self._local.keys = set()
            self._local.failed = False
            try:
                self._acquire(conn, keys, blocking)
                yield
                if self._local.failed:
                    raise StorageError(UNAVAILABLE)
            finally:
                del self._local.connection, self._local.keys, self._local.failed

    def _acquire(self, conn: Any, keys: tuple[str, ...], blocking: bool) -> None:
        for key in sorted(set(keys) - self._local.keys):
            function = "pg_advisory_xact_lock" if blocking else "pg_try_advisory_xact_lock"
            result = self._execute(conn, f"SELECT {function}(%s)",
                                   (_lock_key(self.namespace, "document:" + key),)).fetchone()
            if not blocking and not result[0]:
                raise StorageBusyError("資料正在更新，請稍後再試。")
            self._local.keys.add(key)

    def load(self, key: str) -> dict[str, Any]:
        with self.connection() as conn:
            row = self._execute(conn,
                "SELECT payload FROM public.regintel_documents WHERE namespace = %s AND document_key = %s",
                (self.namespace, key),
            ).fetchone()
            return row[0] if row else {}

    def write(self, key: str, payload: dict[str, Any]) -> None:
        with self.transaction(key), self.connection() as conn:
            from psycopg.types.json import Jsonb
            self._execute(conn, """
                INSERT INTO public.regintel_documents (namespace, document_key, payload)
                VALUES (%s, %s, %s)
                ON CONFLICT (namespace, document_key) DO UPDATE
                SET payload = EXCLUDED.payload,
                    revision = regintel_documents.revision + 1,
                    updated_at = now()
                WHERE regintel_documents.payload IS DISTINCT FROM EXCLUDED.payload
            """, (self.namespace, key, Jsonb(payload)))

    def revisions(self, keys: list[str]) -> dict[str, int]:
        with self.connection() as conn:
            rows = self._execute(conn, """
                SELECT document_key, revision FROM public.regintel_documents
                WHERE namespace = %s AND document_key = ANY(%s)
            """, (self.namespace, keys)).fetchall()
            return dict(rows)

    def check(self) -> dict[str, Any]:
        with self.connection() as conn:
            count = self._execute(conn, "SELECT count(*) FROM public.regintel_documents WHERE namespace = %s",
                                  (self.namespace,)).fetchone()[0]
            return {"backend": "postgres", "connected": True, "document_count": count}


@lru_cache(maxsize=4)
def _store(dsn: str, namespace: str, pg_settings: tuple) -> PostgresStore:
    return PostgresStore(dsn, namespace)


def get_store() -> PostgresStore | None:
    settings = database_settings()
    if settings is None:
        return None
    return _store(*settings, tuple(os.environ.get(key, "") for key in
                                   ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGPORT")))
