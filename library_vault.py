"""
Library Vault — keeps the device library safe across reinstalls / laptop resets.

The working database lives in %APPDATA% (local, fast, but wiped by a factory
reset). The vault lives in OneDrive, which survives a reset and syncs to the
cloud:

    <OneDrive>\\DFP TakeoffPro Library\\
        library.json        products, assemblies, assembly items, labour units, settings
        cutsheets\\         a copy of every shop drawing / cut sheet / product image
        db_backups\\        daily full snapshots of takeoff.db (jobs included), last 30 kept

Behaviour:
  * Attaching a cut sheet/image copies the file into cutsheets\\ and the product
    points at the vault copy — so deleting Downloads can't break it.
  * backup() runs at startup, every few minutes while open, and on close.
  * On a fresh install (empty database) restore_on_startup() brings back the
    latest full snapshot, or the library.json if there is no snapshot.
  * Paths in library.json are stored relative to the vault, so restoring on a
    machine with a different Windows user name / OneDrive path still works.
"""
import os, sys, json, shutil, sqlite3, hashlib, datetime, glob

VAULT_NAME = "DFP TakeoffPro Library"
LIBRARY_TABLES = ["labour_units", "products", "assemblies", "assembly_items", "settings"]
KEEP_SNAPSHOTS = 30


# ── Locations ────────────────────────────────────────────────────────────────

def vault_dir() -> str:
    base = (os.environ.get("OneDriveCommercial") or os.environ.get("OneDrive")
            or os.path.join(os.path.expanduser("~"), "Documents"))
    path = os.path.join(base, VAULT_NAME)
    os.makedirs(os.path.join(path, "cutsheets"), exist_ok=True)
    os.makedirs(os.path.join(path, "db_backups"), exist_ok=True)
    return path


def _library_json():
    return os.path.join(vault_dir(), "library.json")


def _cutsheet_dir():
    return os.path.join(vault_dir(), "cutsheets")


def _norm(p):
    return os.path.normcase(os.path.abspath(p)) if p else ""


def _in_vault(p):
    return bool(p) and _norm(p).startswith(_norm(_cutsheet_dir()) + os.sep)


# ── Cut sheets / images ──────────────────────────────────────────────────────

def _file_hash(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def import_attachment(path: str) -> str:
    """Copy a cut sheet / image into the vault and return the vault path.
    Returns the original path unchanged if it is empty, missing, already in
    the vault, or the copy fails (never blocks the user)."""
    if not path or not os.path.isfile(path) or _in_vault(path):
        return path
    try:
        dest_dir = _cutsheet_dir()
        name = os.path.basename(path)
        stem, ext = os.path.splitext(name)
        dest = os.path.join(dest_dir, name)
        n = 1
        src_hash = None
        while os.path.exists(dest):
            src_hash = src_hash or _file_hash(path)
            if _file_hash(dest) == src_hash:
                return dest            # identical file already in the vault
            n += 1
            dest = os.path.join(dest_dir, f"{stem} ({n}){ext}")
        shutil.copy2(path, dest)
        return dest
    except Exception:
        return path


def _relink(path: str) -> str:
    """If a stored path no longer exists, look for the same file name in the
    vault's cutsheets folder (handles resets, renamed users, moved OneDrive)."""
    if not path or os.path.exists(path):
        return path
    candidate = os.path.join(_cutsheet_dir(), os.path.basename(path.replace("/", os.sep)))
    return candidate if os.path.exists(candidate) else path


def _to_vault_rel(path):
    if _in_vault(path):
        return "vault:" + os.path.relpath(path, vault_dir()).replace(os.sep, "/")
    return path or ""


def _from_vault_rel(path):
    if path and path.startswith("vault:"):
        return os.path.join(vault_dir(), path[6:].replace("/", os.sep))
    return _relink(path)


# ── Database helpers ─────────────────────────────────────────────────────────

def _connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _columns(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def _table_exists(conn, table):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (table,)).fetchone() is not None


def _count(conn, table):
    if not _table_exists(conn, table):
        return 0
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def secure_attachments(db_path):
    """Copy every product's cut sheet / image into the vault (if not already)
    and repoint the product at the vault copy. Also relinks missing paths."""
    with _connect(db_path) as conn:
        cols = _columns(conn, "products")
        fields = [c for c in ("shop_drawing_path", "image_path") if c in cols]
        for row in conn.execute(f"SELECT id, {', '.join(fields)} FROM products").fetchall():
            for f in fields:
                old = row[f] or ""
                if not old:
                    continue
                new = import_attachment(_relink(old))
                if new != old:
                    conn.execute(f"UPDATE products SET {f}=? WHERE id=?", (new, row["id"]))
        conn.commit()


# ── Backup ───────────────────────────────────────────────────────────────────

def export_library(db_path) -> dict:
    data = {"format": 1, "exported_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "tables": {}}
    with _connect(db_path) as conn:
        for t in LIBRARY_TABLES:
            if not _table_exists(conn, t):
                continue
            rows = [dict(r) for r in conn.execute(f"SELECT * FROM {t}")]
            if t == "products":
                for r in rows:
                    for f in ("shop_drawing_path", "image_path"):
                        if f in r:
                            r[f] = _to_vault_rel(r[f])
            data["tables"][t] = rows
    return data


def _write_json_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def _snapshot(db_path):
    """One full copy of the database per day (uses SQLite's online backup so
    it's safe while the app is running). Keeps the newest KEEP_SNAPSHOTS."""
    bdir = os.path.join(vault_dir(), "db_backups")
    dest = os.path.join(bdir, f"takeoff_{datetime.date.today():%Y-%m-%d}.db")
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(dest + ".tmp")
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()
    os.replace(dest + ".tmp", dest)
    snaps = sorted(glob.glob(os.path.join(bdir, "takeoff_*.db")))
    for old in snaps[:-KEEP_SNAPSHOTS]:
        try: os.remove(old)
        except OSError: pass


_last_hash = None

def backup(db_path, force=False) -> str:
    """Secure attachments, write library.json (only if changed) and today's
    full snapshot. Returns a short status string. Never raises."""
    global _last_hash
    try:
        with _connect(db_path) as conn:
            if _count(conn, "products") == 0 and _count(conn, "projects") == 0 and not force:
                return "Nothing to back up yet"   # never overwrite a good backup with an empty DB
        secure_attachments(db_path)
        data = export_library(db_path)
        body = json.dumps(data["tables"], sort_keys=True, default=str)
        h = hashlib.sha1(body.encode("utf-8")).hexdigest()
        if force or h != _last_hash or not os.path.exists(_library_json()):
            _write_json_atomic(_library_json(), data)
            _last_hash = h
        _snapshot(db_path)   # always — jobs change even when the library doesn't
        return f"Library backed up to {vault_dir()}"
    except Exception as e:
        return f"Library backup failed: {e}"


# ── Restore ──────────────────────────────────────────────────────────────────

def latest_snapshot():
    snaps = sorted(glob.glob(os.path.join(vault_dir(), "db_backups", "takeoff_*.db")))
    return snaps[-1] if snaps else None


def _db_is_empty(db_path):
    if not os.path.exists(db_path):
        return True
    try:
        with _connect(db_path) as conn:
            return _count(conn, "products") == 0 and _count(conn, "projects") == 0
    except Exception:
        return False


def restore_on_startup(db_path) -> str:
    """Call BEFORE db.init_db(). If the local database is new/empty, restore
    the newest full snapshot from the vault (devices + jobs), otherwise fall
    back to library.json. Returns a message ('' if nothing was done)."""
    try:
        if not _db_is_empty(db_path):
            return ""
        snap = latest_snapshot()
        if snap:
            shutil.copy2(snap, db_path)
            relink_all(db_path)
            return f"Restored your library and jobs from {os.path.basename(snap)}"
        if os.path.exists(_library_json()):
            return "__RESTORE_JSON_AFTER_INIT__"
    except Exception as e:
        return f"Automatic restore failed: {e}"
    return ""


def relink_all(db_path):
    with _connect(db_path) as conn:
        cols = _columns(conn, "products") if _table_exists(conn, "products") else []
        for f in ("shop_drawing_path", "image_path"):
            if f not in cols:
                continue
            for row in conn.execute(f"SELECT id, {f} FROM products").fetchall():
                new = _relink(row[f] or "")
                if new != (row[f] or ""):
                    conn.execute(f"UPDATE products SET {f}=? WHERE id=?", (new, row["id"]))
        conn.commit()


def restore_library_json(db_path, json_path=None) -> str:
    """Replace the library tables (devices, assemblies, labour units, settings)
    with the contents of library.json. Jobs/projects are left alone.
    Call after db.init_db() so all tables/columns exist."""
    json_path = json_path or _library_json()
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    tables = data.get("tables", {})
    with _connect(db_path) as conn:
        for t in reversed(LIBRARY_TABLES):
            if t in tables and _table_exists(conn, t):
                conn.execute(f"DELETE FROM {t}")
        for t in LIBRARY_TABLES:
            rows = tables.get(t)
            if not rows or not _table_exists(conn, t):
                continue
            cols = set(_columns(conn, t))
            for r in rows:
                if t == "products":
                    for fld in ("shop_drawing_path", "image_path"):
                        if fld in r:
                            r[fld] = _from_vault_rel(r[fld])
                keep = {k: v for k, v in r.items() if k in cols}
                ph = ",".join("?" * len(keep))
                conn.execute(f"INSERT OR REPLACE INTO {t} ({','.join(keep)}) VALUES ({ph})",
                             list(keep.values()))
        conn.commit()
    n = len(tables.get("products", []))
    return f"Restored {n} devices from {os.path.basename(json_path)}"


def merge_from_database(db_path, other_db) -> str:
    """Add devices, assemblies and labour units from another takeoff.db (e.g.
    an old copy) that aren't already in the library. Matches devices on
    name + part code, labour units on name + category, assemblies on name.
    Existing items are never changed or deleted."""
    src = _connect(other_db)
    try:
        with _connect(db_path) as dst:
            # Labour units
            lu_map = {}
            if _table_exists(src, "labour_units"):
                have = {(r["name"], r["category"]): r["id"]
                        for r in dst.execute("SELECT id, name, category FROM labour_units")}
                dcols = set(_columns(dst, "labour_units")) - {"id"}
                for r in src.execute("SELECT * FROM labour_units"):
                    key = (r["name"], r["category"])
                    if key in have:
                        lu_map[r["id"]] = have[key]; continue
                    vals = {k: r[k] for k in r.keys() if k in dcols}
                    cur = dst.execute(f"INSERT INTO labour_units ({','.join(vals)}) VALUES ({','.join('?'*len(vals))})",
                                      list(vals.values()))
                    lu_map[r["id"]] = have[key] = cur.lastrowid
            # Products
            prod_map, added = {}, 0
            have = {((r["name"] or "").strip().lower(), (r["code"] or "").strip().lower()): r["id"]
                    for r in dst.execute("SELECT id, name, code FROM products")}
            dcols = set(_columns(dst, "products")) - {"id"}
            for r in src.execute("SELECT * FROM products"):
                key = ((r["name"] or "").strip().lower(), (r["code"] or "").strip().lower())
                if key in have:
                    prod_map[r["id"]] = have[key]; continue
                vals = {k: r[k] for k in r.keys() if k in dcols}
                if vals.get("lu_id"):
                    vals["lu_id"] = lu_map.get(vals["lu_id"])
                for fld in ("shop_drawing_path", "image_path"):
                    if vals.get(fld):
                        vals[fld] = import_attachment(_relink(vals[fld]))
                cur = dst.execute(f"INSERT INTO products ({','.join(vals)}) VALUES ({','.join('?'*len(vals))})",
                                  list(vals.values()))
                prod_map[r["id"]] = have[key] = cur.lastrowid
                added += 1
            # Assemblies + items
            asm_added = 0
            if _table_exists(src, "assemblies"):
                have_a = {(r["name"] or "").strip().lower() for r in dst.execute("SELECT name FROM assemblies")}
                acols = set(_columns(dst, "assemblies")) - {"id"}
                for a in src.execute("SELECT * FROM assemblies").fetchall():
                    if (a["name"] or "").strip().lower() in have_a:
                        continue
                    vals = {k: a[k] for k in a.keys() if k in acols}
                    cur = dst.execute(f"INSERT INTO assemblies ({','.join(vals)}) VALUES ({','.join('?'*len(vals))})",
                                      list(vals.values()))
                    new_aid = cur.lastrowid
                    for it in src.execute("SELECT * FROM assembly_items WHERE assembly_id=?", (a["id"],)):
                        pid = prod_map.get(it["product_id"])
                        if pid:
                            dst.execute("INSERT INTO assembly_items (assembly_id, product_id, quantity) VALUES (?,?,?)",
                                        (new_aid, pid, it["quantity"]))
                    have_a.add((a["name"] or "").strip().lower())
                    asm_added += 1
            dst.commit()
    finally:
        src.close()
    return f"Added {added} devices and {asm_added} assemblies"


def missing_attachments(db_path):
    """(product name, path) for every cut sheet / image that can't be found."""
    out = []
    with _connect(db_path) as conn:
        cols = _columns(conn, "products")
        for f in ("shop_drawing_path", "image_path"):
            if f not in cols:
                continue
            for r in conn.execute(f"SELECT name, {f} AS p FROM products WHERE {f} != ''"):
                if not os.path.exists(r["p"]):
                    out.append((r["name"], r["p"]))
    return out
