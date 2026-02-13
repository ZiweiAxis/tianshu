# MySQL backend: TIANSHU_STORAGE=mysql, TIANSHU_MYSQL_* env vars
import json
import os
from typing import Any, Dict, List, Optional
from src.storage.backend import StorageBackend

class MySQLBackend(StorageBackend):
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._host = os.getenv("TIANSHU_MYSQL_HOST", "localhost")
        self._port = int(os.getenv("TIANSHU_MYSQL_PORT", "3306"))
        self._user = os.getenv("TIANSHU_MYSQL_USER", "")
        self._password = os.getenv("TIANSHU_MYSQL_PASSWORD", "")
        self._database = os.getenv("TIANSHU_MYSQL_DATABASE", "tianshu")
        self._init_schema()

    def _conn(self):
        import pymysql
        return pymysql.connect(host=self._host, port=self._port, user=self._user, password=self._password, database=self._database)

    def _init_schema(self) -> None:
        conn = self._conn()
        conn.cursor().execute(
            "CREATE TABLE IF NOT EXISTS kv (bucket VARCHAR(255), key_col VARCHAR(512), value JSON, PRIMARY KEY (bucket, key_col))"
        )
        conn.commit()
        conn.close()

    def get(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("SELECT value FROM kv WHERE bucket = %s AND key_col = %s", (bucket, key))
        row = cur.fetchone()
        conn.close()
        return json.loads(row[0]) if row and row[0] else None

    def set(self, bucket: str, key: str, value: Dict[str, Any]) -> None:
        conn = self._conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO kv (bucket, key_col, value) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE value = VALUES(value)",
            (bucket, key, json.dumps(value, ensure_ascii=False)),
        )
        conn.commit()
        conn.close()

    def list_keys(self, bucket: str, prefix: str = "") -> List[str]:
        conn = self._conn()
        cur = conn.cursor()
        if prefix:
            cur.execute("SELECT key_col FROM kv WHERE bucket = %s AND key_col LIKE %s", (bucket, prefix + "%"))
        else:
            cur.execute("SELECT key_col FROM kv WHERE bucket = %s", (bucket,))
        out = [r[0] for r in cur.fetchall()]
        conn.close()
        return out

    def delete(self, bucket: str, key: str) -> bool:
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM kv WHERE bucket = %s AND key_col = %s", (bucket, key))
        n = cur.rowcount
        conn.commit()
        conn.close()
        return n > 0
