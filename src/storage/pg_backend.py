# PostgreSQL backend: TIANSHU_STORAGE=postgres, TIANSHU_PG_DSN=...
import json
from typing import Any, Dict, List, Optional
from src.storage.backend import StorageBackend

class PostgresBackend(StorageBackend):
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._init_schema()

    def _init_schema(self) -> None:
        import psycopg2
        conn = psycopg2.connect(self._dsn)
        conn.autocommit = True
        conn.cursor().execute(
            "CREATE TABLE IF NOT EXISTS kv (bucket TEXT, key_col TEXT, value JSONB, PRIMARY KEY (bucket, key_col))"
        )
        conn.close()

    def get(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        import psycopg2
        conn = psycopg2.connect(self._dsn)
        cur = conn.cursor()
        cur.execute("SELECT value FROM kv WHERE bucket = %s AND key_col = %s", (bucket, key))
        row = cur.fetchone()
        conn.close()
        return json.loads(row[0]) if row and row[0] else None

    def set(self, bucket: str, key: str, value: Dict[str, Any]) -> None:
        import psycopg2
        conn = psycopg2.connect(self._dsn)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO kv (bucket, key_col, value) VALUES (%s, %s, %s) ON CONFLICT (bucket, key_col) DO UPDATE SET value = EXCLUDED.value",
            (bucket, key, json.dumps(value, ensure_ascii=False)),
        )
        conn.commit()
        conn.close()

    def list_keys(self, bucket: str, prefix: str = "") -> List[str]:
        import psycopg2
        conn = psycopg2.connect(self._dsn)
        cur = conn.cursor()
        if prefix:
            cur.execute("SELECT key_col FROM kv WHERE bucket = %s AND key_col LIKE %s", (bucket, prefix + "%"))
        else:
            cur.execute("SELECT key_col FROM kv WHERE bucket = %s", (bucket,))
        out = [r[0] for r in cur.fetchall()]
        conn.close()
        return out

    def delete(self, bucket: str, key: str) -> bool:
        import psycopg2
        conn = psycopg2.connect(self._dsn)
        cur = conn.cursor()
        cur.execute("DELETE FROM kv WHERE bucket = %s AND key_col = %s", (bucket, key))
        n = cur.rowcount
        conn.commit()
        conn.close()
        return n > 0
