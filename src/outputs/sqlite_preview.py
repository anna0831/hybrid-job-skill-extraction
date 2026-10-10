"""Read-only, bounded preview queries compatible with the existing test_db.py DB."""
from contextlib import closing
from pathlib import Path
import sqlite3

from src.outputs.sqlite_store import quote

PAGE_SIZE = 100
PREVIEW_COLUMNS = ["category", "subcategory", "record_id", "ID", "資料月份", "104職位名稱",
                   "Skill_Name_ZH", "SKILL_ID", "Skill_group10", "MATCHED_FROM"]


def connect_readonly(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Database not found: {path}")
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def fetch_page(path, *, cursor=None, filters=None):
    """Fetch at most 100 metadata rows + one lookahead, never the original description."""
    filters = filters or {}
    conditions, params = [], []
    with closing(connect_readonly(path)) as conn:
        available = {r[1] for r in conn.execute("PRAGMA table_info(v_skill_long)")}
        required = {"record_id", "ID", "資料月份", "104職位名稱", "category", "subcategory", "Skill_Name_ZH", "SKILL_ID"}
        if required - available:
            raise ValueError(f"Incompatible v_skill_long schema: missing {sorted(required - available)}")
        for key in ("ID", "資料月份", "category", "SKILL_ID", "MATCHED_FROM", "Skill_group10"):
            if filters.get(key):
                if key not in available:
                    raise ValueError(f"Filter column unavailable: {key}")
                conditions.append(f"{quote(key)}=?")
                params.append(filters[key])
        if filters.get("skill_text"):
            conditions.append("instr(COALESCE(Skill_Name_ZH,''),?)>0")
            params.append(filters["skill_text"])
        if filters.get("title_text"):
            conditions.append('instr(COALESCE("104職位名稱",\'\'),?)>0')
            params.append(filters["title_text"])
        if filters.get("empty_name"):
            conditions.append("record_id IS NOT NULL AND Skill_Name_ZH=''")
        if filters.get("no_detail"):
            conditions.append("record_id IS NULL")
        if cursor is not None:
            conditions.append('(ID, 資料月份, COALESCE(record_id,0)) > (?,?,?)')
            params.extend(cursor)
        selected = [c for c in PREVIEW_COLUMNS if c in available]
        sql = f"SELECT {','.join(map(quote, selected))} FROM v_skill_long"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY ID, 資料月份, COALESCE(record_id,0) LIMIT ?"
        fetched = [dict(r) for r in conn.execute(sql, params + [PAGE_SIZE + 1])]
    rows = fetched[:PAGE_SIZE]
    has_more = len(fetched) > PAGE_SIZE
    next_cursor = ((rows[-1]["ID"], rows[-1]["資料月份"], rows[-1]["record_id"] or 0)
                   if has_more else None)
    return rows, next_cursor


def fetch_job(path, job_id, month):
    """Only called after an explicit selection; both snapshot key fields are required."""
    with closing(connect_readonly(path)) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE ID=? AND 資料月份=?", (job_id, month)).fetchone()
        return dict(row) if row else None


def database_version(path):
    path = Path(path).expanduser().resolve()
    stats = path.stat()
    wal = Path(str(path) + "-wal")
    wal_stats = wal.stat() if wal.exists() else None
    return str(path), stats.st_mtime_ns, stats.st_size, (wal_stats.st_mtime_ns, wal_stats.st_size) if wal_stats else None
