# E11-S4：存储后端抽象——内存 / SQLite / PostgreSQL / MySQL
#
# 选型理由：
# - SQLite：零额外服务、单文件、单实例/本地联调首选；容器内挂卷即可持久化。
# - PostgreSQL：多实例共享、生产常用、与 Synapse 等生态一致；需 TIANSHU_PG_URL。
# - MySQL：若已有 MySQL 可选用；需 TIANSHU_MYSQL_* 或 URL。
# 未配置或 memory 时用内存后端。

import os
from typing import Any, Dict, List, Optional

STORAGE_BACKEND = (os.getenv("TIANSHU_STORAGE") or "memory").lower()
SQLITE_PATH = os.getenv("TIANSHU_SQLITE_PATH", "")
# PostgreSQL: TIANSHU_PG_URL=postgresql://user:pass@host:5432/dbname
PG_URL = os.getenv("TIANSHU_PG_URL", "")
# MySQL: TIANSHU_MYSQL_HOST, TIANSHU_MYSQL_PORT, TIANSHU_MYSQL_USER, TIANSHU_MYSQL_PASSWORD, TIANSHU_MYSQL_DATABASE
MYSQL_HOST = os.getenv("TIANSHU_MYSQL_HOST", "")
MYSQL_PORT = int(os.getenv("TIANSHU_MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("TIANSHU_MYSQL_USER", "")
MYSQL_PASSWORD = os.getenv("TIANSHU_MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("TIANSHU_MYSQL_DATABASE", "tianshu")


class StorageBackend:
    """统一存储接口占位：key-value / 表式访问，由具体实现提供。"""

    def get(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def set(self, bucket: str, key: str, value: Dict[str, Any]) -> None:
        raise NotImplementedError

    def list_keys(self, bucket: str, prefix: str = "") -> List[str]:
        raise NotImplementedError

    def delete(self, bucket: str, key: str) -> bool:
        raise NotImplementedError


class MemoryBackend(StorageBackend):
    """内存后端：进程内 dict，重启丢失。"""

    def __init__(self) -> None:
        self._data: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def _bucket(self, bucket: str) -> Dict[str, Any]:
        if bucket not in self._data:
            self._data[bucket] = {}
        return self._data[bucket]

    def get(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        return self._bucket(bucket).get(key)

    def set(self, bucket: str, key: str, value: Dict[str, Any]) -> None:
        self._bucket(bucket)[key] = dict(value)

    def list_keys(self, bucket: str, prefix: str = "") -> List[str]:
        b = self._bucket(bucket)
        if not prefix:
            return list(b.keys())
        return [k for k in b if k.startswith(prefix)]

    def delete(self, bucket: str, key: str) -> bool:
        b = self._bucket(bucket)
        if key in b:
            del b[key]
            return True
        return False


class SQLiteBackend(StorageBackend):
    """SQLite 后端：单文件持久化，重启不丢。"""

    def __init__(self, path: str) -> None:
        self._path = path
        self._init_schema()

    def _init_schema(self) -> None:
        import sqlite3
        conn = sqlite3.connect(self._path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS kv (bucket TEXT, key TEXT, value TEXT, PRIMARY KEY (bucket, key))"
        )
        conn.commit()
        conn.close()

    def get(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        import json
        import sqlite3
        conn = sqlite3.connect(self._path)
        row = conn.execute(
            "SELECT value FROM kv WHERE bucket = ? AND key = ?", (bucket, key)
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return json.loads(row[0])

    def set(self, bucket: str, key: str, value: Dict[str, Any]) -> None:
        import json
        import sqlite3
        conn = sqlite3.connect(self._path)
        conn.execute(
            "INSERT OR REPLACE INTO kv (bucket, key, value) VALUES (?, ?, ?)",
            (bucket, key, json.dumps(value, ensure_ascii=False)),
        )
        conn.commit()
        conn.close()

    def list_keys(self, bucket: str, prefix: str = "") -> List[str]:
        import sqlite3
        conn = sqlite3.connect(self._path)
        if prefix:
            rows = conn.execute(
                "SELECT key FROM kv WHERE bucket = ? AND key LIKE ?",
                (bucket, prefix + "%"),
            ).fetchall()
        else:
            rows = conn.execute("SELECT key FROM kv WHERE bucket = ?", (bucket,)).fetchall()
        conn.close()
        return [r[0] for r in rows]

    def delete(self, bucket: str, key: str) -> bool:
        import sqlite3
        conn = sqlite3.connect(self._path)
        cur = conn.execute("DELETE FROM kv WHERE bucket = ? AND key = ?", (bucket, key))
        conn.commit()
        deleted = cur.rowcount > 0
        conn.close()
        return deleted


class PostgresBackend(StorageBackend):
    """PostgreSQL 后端：多实例共享、生产推荐。需 TIANSHU_PG_URL。"""

    def __init__(self, url: str) -> None:
        self._url = url
        self._init_schema()

    def _conn(self):
        import psycopg2
        return psycopg2.connect(self._url)

    def _init_schema(self) -> None:
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "CREATE TABLE IF NOT EXISTS kv (bucket TEXT, key TEXT, value JSONB, PRIMARY KEY (bucket, key))"
            )
            conn.commit()
            cur.close()
        finally:
            conn.close()

    def get(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        import json
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT value FROM kv WHERE bucket = %s AND key = %s", (bucket, key))
            row = cur.fetchone()
            cur.close()
            if row is None:
                return None
            v = row[0]
            return v if isinstance(v, dict) else json.loads(v)
        finally:
            conn.close()

    def set(self, bucket: str, key: str, value: Dict[str, Any]) -> None:
        import json
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO kv (bucket, key, value) VALUES (%s, %s, %s::jsonb) ON CONFLICT (bucket, key) DO UPDATE SET value = EXCLUDED.value",
                (bucket, key, json.dumps(value, ensure_ascii=False)),
            )
            conn.commit()
            cur.close()
        finally:
            conn.close()

    def list_keys(self, bucket: str, prefix: str = "") -> List[str]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            if prefix:
                cur.execute("SELECT key FROM kv WHERE bucket = %s AND key LIKE %s", (bucket, prefix + "%"))
            else:
                cur.execute("SELECT key FROM kv WHERE bucket = %s", (bucket,))
            keys = [r[0] for r in cur.fetchall()]
            cur.close()
            return keys
        finally:
            conn.close()

    def delete(self, bucket: str, key: str) -> bool:
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM kv WHERE bucket = %s AND key = %s", (bucket, key))
            deleted = cur.rowcount > 0
            conn.commit()
            cur.close()
            return deleted
        finally:
            conn.close()


class MySQLBackend(StorageBackend):
    """MySQL 后端：与 PG 同构，适合已有 MySQL 的环境。"""

    def __init__(self, host: str, port: int, user: str, password: str, database: str) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._database = database
        self._init_schema()

    def _conn(self):
        import pymysql
        return pymysql.connect(
            host=self._host, port=self._port, user=self._user, password=self._password, database=self._database
        )

    def _init_schema(self) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "CREATE TABLE IF NOT EXISTS kv (bucket VARCHAR(255), `key` VARCHAR(512), value JSON, PRIMARY KEY (bucket, `key`))"
                )
            conn.commit()
        finally:
            conn.close()

    def get(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        import json
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM kv WHERE bucket = %s AND `key` = %s", (bucket, key))
                row = cur.fetchone()
            if row is None:
                return None
            v = row[0]
            return v if isinstance(v, dict) else json.loads(v)
        finally:
            conn.close()

    def set(self, bucket: str, key: str, value: Dict[str, Any]) -> None:
        import json
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO kv (bucket, `key`, value) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE value = VALUES(value)",
                    (bucket, key, json.dumps(value, ensure_ascii=False)),
                )
            conn.commit()
        finally:
            conn.close()

    def list_keys(self, bucket: str, prefix: str = "") -> List[str]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                if prefix:
                    cur.execute("SELECT `key` FROM kv WHERE bucket = %s AND `key` LIKE %s", (bucket, prefix + "%"))
                else:
                    cur.execute("SELECT `key` FROM kv WHERE bucket = %s", (bucket,))
                return [r[0] for r in cur.fetchall()]
        finally:
            conn.close()

    def delete(self, bucket: str, key: str) -> bool:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM kv WHERE bucket = %s AND `key` = %s", (bucket, key))
                deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        finally:
            conn.close()


_backend_instance: Optional["StorageBackend"] = None


def get_backend() -> StorageBackend:
    """根据环境变量返回当前存储后端（单例）：memory | sqlite | postgres | mysql。"""
    global _backend_instance
    if _backend_instance is not None:
        return _backend_instance
    backend = (os.getenv("TIANSHU_STORAGE") or "memory").lower()
    if backend == "sqlite":
        path = os.getenv("TIANSHU_SQLITE_PATH", "")
        if path:
            _backend_instance = SQLiteBackend(path)
            return _backend_instance
    if backend == "postgres":
        url = os.getenv("TIANSHU_PG_URL", "")
        if url:
            _backend_instance = PostgresBackend(url)
            return _backend_instance
    if backend == "mysql":
        host, user = os.getenv("TIANSHU_MYSQL_HOST", ""), os.getenv("TIANSHU_MYSQL_USER", "")
        if host and user:
            port = int(os.getenv("TIANSHU_MYSQL_PORT", "3306"))
            _backend_instance = MySQLBackend(host, port, user, os.getenv("TIANSHU_MYSQL_PASSWORD", ""), os.getenv("TIANSHU_MYSQL_DATABASE", "tianshu"))
            return _backend_instance
    _backend_instance = MemoryBackend()
    return _backend_instance
