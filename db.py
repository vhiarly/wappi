import os
from psycopg2 import pool

_pool = None

def init_pool():
    global _pool
    _pool = pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=10,
        dsn=os.getenv("DATABASE_URL"),
        sslmode="require",
    )

def get_conn():
    return _pool.getconn()

def put_conn(conn):
    _pool.putconn(conn)

def execute(sql, params=(), *, fetch=None):
    """
    Ejecuta SQL y retorna resultados según fetch:
      None  → sin resultado
      'one' → un dict o None
      'all' → lista de dicts
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            result = None
            if fetch == "one":
                row = cur.fetchone()
                if row is not None:
                    cols = [d[0] for d in cur.description]
                    result = dict(zip(cols, row))
            elif fetch == "all":
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
                result = [dict(zip(cols, r)) for r in rows]
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)
