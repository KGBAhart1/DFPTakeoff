import sqlite3, os, sys

def _data_dir() -> str:
    """
    When running as a PyInstaller bundle, store user data in AppData
    (not next to the .exe which may be in Program Files).
    When running as a script, store next to the script as before.
    """
    if getattr(sys, "frozen", False):
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        path = os.path.join(base, "DFP TakeoffPro")
    else:
        path = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(path, exist_ok=True)
    return path

DB_PATH = os.path.join(_data_dir(), "takeoff.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                code TEXT DEFAULT '',
                unit_cost REAL DEFAULT 0.0,
                category TEXT DEFAULT 'General',
                sort_order INTEGER DEFAULT 0,
                shop_drawing_path TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assemblies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT DEFAULT 'General',
                description TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assembly_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assembly_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 1,
                FOREIGN KEY (assembly_id) REFERENCES assemblies(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                pdf_path TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS takeoff_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                section_id INTEGER DEFAULT NULL,
                count INTEGER DEFAULT 0,
                notes TEXT DEFAULT '',
                FOREIGN KEY (project_id) REFERENCES projects(id),
                FOREIGN KEY (product_id) REFERENCES products(id),
                FOREIGN KEY (section_id) REFERENCES sections(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS marks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                pdf_path TEXT NOT NULL,
                page_index INTEGER DEFAULT 0,
                page_x REAL NOT NULL,
                page_y REAL NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                color TEXT DEFAULT '#e74c3c',
                label TEXT DEFAULT '',
                section_id INTEGER DEFAULT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS page_scales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                pdf_path TEXT NOT NULL,
                page_index INTEGER DEFAULT 0,
                pixels_per_meter REAL NOT NULL,
                UNIQUE(project_id, pdf_path, page_index) ON CONFLICT REPLACE,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS labour_units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT DEFAULT 'General',
                lu_reg  REAL DEFAULT 0.0,
                lu_diff REAL DEFAULT 0.0,
                lu_hard REAL DEFAULT 0.0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        # Default settings
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('units', 'metric')")
        conn.commit()

    # Migrate existing databases — add columns that may not exist yet
    _safe_alter("ALTER TABLE products ADD COLUMN shop_drawing_path TEXT DEFAULT ''")
    _safe_alter("ALTER TABLE products ADD COLUMN image_path TEXT DEFAULT ''")
    _safe_alter("ALTER TABLE products ADD COLUMN use_count INTEGER DEFAULT 0")
    _safe_alter("ALTER TABLE products ADD COLUMN coverage_type TEXT DEFAULT ''")
    _safe_alter("ALTER TABLE products ADD COLUMN coverage_radius_m REAL DEFAULT 0.0")
    _safe_alter("ALTER TABLE products ADD COLUMN lu_reg REAL DEFAULT 0.0")
    _safe_alter("ALTER TABLE products ADD COLUMN lu_diff REAL DEFAULT 0.0")
    _safe_alter("ALTER TABLE products ADD COLUMN lu_hard REAL DEFAULT 0.0")
    _safe_alter("ALTER TABLE products ADD COLUMN lu_id INTEGER DEFAULT NULL")
    _safe_alter("ALTER TABLE products ADD COLUMN subcategory TEXT DEFAULT ''")
    _safe_alter("ALTER TABLE products ADD COLUMN candela REAL DEFAULT 0")   # default candela suggested for new placements
    _safe_alter("ALTER TABLE marks ADD COLUMN candela REAL DEFAULT 0")     # actual per-placed-device candela — editable independently on each plot
    _seed_labour_units()
    _safe_alter("ALTER TABLE takeoff_items ADD COLUMN section_id INTEGER DEFAULT NULL")
    _safe_alter("ALTER TABLE takeoff_items ADD COLUMN notes TEXT DEFAULT ''")
    _safe_alter("ALTER TABLE install_estimates ADD COLUMN labour_included INTEGER DEFAULT 1")
    _safe_alter("ALTER TABLE install_line_items ADD COLUMN source_type TEXT DEFAULT 'manual'")
    _safe_alter("ALTER TABLE install_line_items ADD COLUMN source_id INTEGER DEFAULT NULL")
    _safe_alter("ALTER TABLE install_line_items ADD COLUMN lu_id INTEGER DEFAULT NULL")
    # Linear assembly fields
    _safe_alter("ALTER TABLE assemblies ADD COLUMN is_linear INTEGER DEFAULT 0")
    _safe_alter("ALTER TABLE assemblies ADD COLUMN wire_count INTEGER DEFAULT 1")
    _safe_alter("ALTER TABLE assemblies ADD COLUMN bundle_factor REAL DEFAULT 0.35")
    _safe_alter("ALTER TABLE assemblies ADD COLUMN prep_lu_per_wire REAL DEFAULT 0.0")
    _safe_alter("ALTER TABLE assemblies ADD COLUMN lu_reg REAL DEFAULT 0.0")
    _safe_alter("ALTER TABLE assemblies ADD COLUMN lu_diff REAL DEFAULT 0.0")
    _safe_alter("ALTER TABLE assemblies ADD COLUMN lu_hard REAL DEFAULT 0.0")
    _safe_alter("ALTER TABLE assemblies ADD COLUMN wire_lu_reg REAL DEFAULT 0.0")
    _safe_alter("ALTER TABLE assemblies ADD COLUMN wire_lu_diff REAL DEFAULT 0.0")
    _safe_alter("ALTER TABLE assemblies ADD COLUMN wire_lu_hard REAL DEFAULT 0.0")
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS install_estimate_excluded (
                estimate_id INTEGER NOT NULL,
                lu_id       INTEGER,
                product_id  INTEGER,
                PRIMARY KEY (estimate_id, lu_id, product_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS linear_runs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER NOT NULL,
                assembly_id INTEGER NOT NULL,
                pdf_path    TEXT    NOT NULL,
                page_index  INTEGER NOT NULL DEFAULT 0,
                points      TEXT    NOT NULL,
                footage     REAL    NOT NULL DEFAULT 0.0,
                section_id  INTEGER DEFAULT NULL,
                FOREIGN KEY (project_id)  REFERENCES projects(id),
                FOREIGN KEY (assembly_id) REFERENCES assemblies(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS page_labels (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER NOT NULL,
                pdf_path    TEXT    NOT NULL,
                page_index  INTEGER NOT NULL,
                label       TEXT    DEFAULT '',
                UNIQUE(project_id, pdf_path, page_index) ON CONFLICT REPLACE,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS field_notes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER NOT NULL,
                pdf_path    TEXT    NOT NULL,
                page_index  INTEGER NOT NULL DEFAULT 0,
                page_x      REAL    NOT NULL,
                page_y      REAL    NOT NULL,
                text        TEXT    NOT NULL DEFAULT '',
                color       TEXT    DEFAULT '#000000',
                bold        INTEGER DEFAULT 0,
                font_size   REAL    DEFAULT 10.0,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS field_lines (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER NOT NULL,
                pdf_path    TEXT    NOT NULL,
                page_index  INTEGER NOT NULL DEFAULT 0,
                points      TEXT    NOT NULL,
                color       TEXT    DEFAULT '#000000',
                width       REAL    DEFAULT 2.0,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pdf_snips (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER NOT NULL,
                name        TEXT    NOT NULL,
                image       BLOB    NOT NULL,
                visible     INTEGER DEFAULT 0,
                win_x       INTEGER DEFAULT 80,
                win_y       INTEGER DEFAULT 80,
                win_w       INTEGER DEFAULT 320,
                win_h       INTEGER DEFAULT 240,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fire_plans (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id          INTEGER NOT NULL UNIQUE,
                ahj                 TEXT    DEFAULT 'calgary',
                vbi_data            TEXT    DEFAULT '{}',
                has_zoned_alarm     INTEGER DEFAULT 0,
                base_building_path  TEXT    DEFAULT '',
                alarm_zone_path     TEXT    DEFAULT '',
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fire_plan_certificates (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER NOT NULL,
                label       TEXT    DEFAULT '',
                path        TEXT    NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)
        conn.commit()


def _safe_alter(sql):
    try:
        with get_conn() as conn:
            conn.execute(sql)
            conn.commit()
    except Exception:
        pass


# ── Products ──────────────────────────────────────────────────────────────────

def get_products():
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM products ORDER BY category, sort_order, name"
        ).fetchall()


def get_distinct_categories():
    """Every category value actually in use, so custom groups the user has
    typed (e.g. 'Hi-Ca Horn Strobes') show up as reusable options instead of
    needing to be retyped identically each time."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT category FROM products WHERE category != '' ORDER BY category"
        ).fetchall()
        return [r["category"] for r in rows]


def get_distinct_subcategories(category=None):
    """Every subcategory value actually in use — the optional second level
    of grouping inside a category (e.g. Category 'Horn Strobes', subcategory
    'Wall Mount' / 'Ceiling Mount'). Pass a category to scope suggestions to
    subcategories already used within it; omit for the full list."""
    with get_conn() as conn:
        if category:
            rows = conn.execute(
                "SELECT DISTINCT subcategory FROM products "
                "WHERE subcategory != '' AND category=? ORDER BY subcategory",
                (category,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT subcategory FROM products WHERE subcategory != '' ORDER BY subcategory"
            ).fetchall()
        return [r["subcategory"] for r in rows]


def add_product(name, code="", unit_cost=0.0, category="General",
                shop_drawing_path="", image_path="",
                coverage_type="", coverage_radius_m=0.0,
                lu_reg=0.0, lu_diff=0.0, lu_hard=0.0, lu_id=None,
                subcategory="", candela=0.0):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO products "
            "(name, code, unit_cost, category, shop_drawing_path, image_path, "
            " coverage_type, coverage_radius_m, lu_reg, lu_diff, lu_hard, lu_id, subcategory, candela)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, code, unit_cost, category, shop_drawing_path, image_path,
             coverage_type, coverage_radius_m, lu_reg, lu_diff, lu_hard, lu_id, subcategory, candela),
        )
        conn.commit()


def update_product(pid, name, code, unit_cost, category,
                   shop_drawing_path="", image_path="",
                   coverage_type="", coverage_radius_m=0.0,
                   lu_reg=0.0, lu_diff=0.0, lu_hard=0.0, lu_id=None,
                   subcategory="", candela=0.0):
    with get_conn() as conn:
        conn.execute(
            "UPDATE products SET name=?,code=?,unit_cost=?,category=?,"
            "shop_drawing_path=?,image_path=?,"
            "coverage_type=?,coverage_radius_m=?,"
            "lu_reg=?,lu_diff=?,lu_hard=?,lu_id=?,subcategory=?,candela=? WHERE id=?",
            (name, code, unit_cost, category, shop_drawing_path, image_path,
             coverage_type, coverage_radius_m, lu_reg, lu_diff, lu_hard, lu_id, subcategory, candela, pid),
        )
        conn.commit()


def set_product_shop_drawing(product_id, path):
    with get_conn() as conn:
        conn.execute("UPDATE products SET shop_drawing_path=? WHERE id=?", (path, product_id))
        conn.commit()


def increment_use_count(product_id):
    with get_conn() as conn:
        conn.execute("UPDATE products SET use_count = use_count + 1 WHERE id=?", (product_id,))
        conn.commit()


def delete_product(pid):
    with get_conn() as conn:
        conn.execute("DELETE FROM assembly_items WHERE product_id=?", (pid,))
        conn.execute("DELETE FROM products WHERE id=?", (pid,))
        conn.commit()


# ── Assemblies ────────────────────────────────────────────────────────────────

def get_assemblies():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM assemblies ORDER BY category, name").fetchall()


def get_assembly_items(assembly_id):
    with get_conn() as conn:
        return conn.execute("""
            SELECT ai.id, ai.quantity,
                   p.id as product_id, p.name, p.code, p.unit_cost, p.category
            FROM assembly_items ai
            JOIN products p ON ai.product_id = p.id
            WHERE ai.assembly_id = ?
            ORDER BY p.name
        """, (assembly_id,)).fetchall()


def add_assembly(name, category="General", description="",
                 is_linear=0, wire_count=1, bundle_factor=0.35, prep_lu_per_wire=0.0,
                 lu_reg=0.0, lu_diff=0.0, lu_hard=0.0,
                 wire_lu_reg=0.0, wire_lu_diff=0.0, wire_lu_hard=0.0):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO assemblies (name,category,description,"
            "is_linear,wire_count,bundle_factor,prep_lu_per_wire,"
            "lu_reg,lu_diff,lu_hard,wire_lu_reg,wire_lu_diff,wire_lu_hard)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, category, description,
             is_linear, wire_count, bundle_factor, prep_lu_per_wire,
             lu_reg, lu_diff, lu_hard, wire_lu_reg, wire_lu_diff, wire_lu_hard),
        )
        conn.commit()
        return cur.lastrowid


def update_assembly(aid, name, category, description,
                    is_linear=0, wire_count=1, bundle_factor=0.35, prep_lu_per_wire=0.0,
                    lu_reg=0.0, lu_diff=0.0, lu_hard=0.0,
                    wire_lu_reg=0.0, wire_lu_diff=0.0, wire_lu_hard=0.0):
    with get_conn() as conn:
        conn.execute(
            "UPDATE assemblies SET name=?,category=?,description=?,"
            "is_linear=?,wire_count=?,bundle_factor=?,prep_lu_per_wire=?,"
            "lu_reg=?,lu_diff=?,lu_hard=?,wire_lu_reg=?,wire_lu_diff=?,wire_lu_hard=?"
            " WHERE id=?",
            (name, category, description,
             is_linear, wire_count, bundle_factor, prep_lu_per_wire,
             lu_reg, lu_diff, lu_hard, wire_lu_reg, wire_lu_diff, wire_lu_hard, aid),
        )
        conn.commit()


def delete_assembly(aid):
    with get_conn() as conn:
        conn.execute("DELETE FROM assembly_items WHERE assembly_id=?", (aid,))
        conn.execute("DELETE FROM assemblies WHERE id=?", (aid,))
        conn.commit()


def set_assembly_items(assembly_id, items):
    with get_conn() as conn:
        conn.execute("DELETE FROM assembly_items WHERE assembly_id=?", (assembly_id,))
        for pid, qty in items:
            conn.execute(
                "INSERT INTO assembly_items (assembly_id, product_id, quantity) VALUES (?,?,?)",
                (assembly_id, pid, qty),
            )
        conn.commit()


# ── Projects ──────────────────────────────────────────────────────────────────

def get_projects():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()


def create_project(name, pdf_path=""):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO projects (name, pdf_path) VALUES (?,?)", (name, pdf_path)
        )
        conn.commit()
        return cur.lastrowid


def update_project_pdf(project_id, pdf_path):
    with get_conn() as conn:
        conn.execute("UPDATE projects SET pdf_path=? WHERE id=?", (pdf_path, project_id))
        conn.commit()


def delete_project(project_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM marks WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM takeoff_items WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM sections WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM page_labels WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM field_notes WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM field_lines WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM pdf_snips WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM fire_plans WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM fire_plan_certificates WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
        conn.commit()


# ── Sections ──────────────────────────────────────────────────────────────────

def get_sections(project_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM sections WHERE project_id=? ORDER BY sort_order, name",
            (project_id,)
        ).fetchall()


def add_section(project_id, name):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO sections (project_id, name) VALUES (?,?)", (project_id, name)
        )
        conn.commit()
        return cur.lastrowid


def rename_section(section_id, name):
    with get_conn() as conn:
        conn.execute("UPDATE sections SET name=? WHERE id=?", (name, section_id))
        conn.commit()


def delete_section(section_id):
    with get_conn() as conn:
        conn.execute("UPDATE marks SET section_id=NULL WHERE section_id=?", (section_id,))
        conn.execute("UPDATE takeoff_items SET section_id=NULL WHERE section_id=?", (section_id,))
        conn.execute("DELETE FROM sections WHERE id=?", (section_id,))
        conn.commit()


# ── Takeoff items ──────────────────────────────────────────────────────────────

def get_takeoff_items(project_id, section_id=None):
    with get_conn() as conn:
        if section_id is None:
            return conn.execute("""
                SELECT ti.id, ti.count, ti.notes, ti.section_id,
                       p.id as product_id, p.name, p.code, p.unit_cost, p.category,
                       p.shop_drawing_path
                FROM takeoff_items ti
                JOIN products p ON ti.product_id = p.id
                WHERE ti.project_id=? AND ti.section_id IS NULL
                ORDER BY p.category, p.name
            """, (project_id,)).fetchall()
        else:
            return conn.execute("""
                SELECT ti.id, ti.count, ti.notes, ti.section_id,
                       p.id as product_id, p.name, p.code, p.unit_cost, p.category,
                       p.shop_drawing_path
                FROM takeoff_items ti
                JOIN products p ON ti.product_id = p.id
                WHERE ti.project_id=? AND ti.section_id=?
                ORDER BY p.category, p.name
            """, (project_id, section_id)).fetchall()


def get_all_takeoff_items(project_id, section_ids=None):
    """All items across all sections (for export). Pass section_ids (an
    iterable of section id) to scope to just those sections instead."""
    with get_conn() as conn:
        if section_ids:
            placeholders = ",".join("?" * len(section_ids))
            return conn.execute(f"""
                SELECT p.id as product_id, p.name, p.code, p.unit_cost, p.category,
                       p.shop_drawing_path,
                       SUM(ti.count) as count
                FROM takeoff_items ti
                JOIN products p ON ti.product_id = p.id
                WHERE ti.project_id=? AND ti.section_id IN ({placeholders})
                GROUP BY p.id
                ORDER BY p.category, p.name
            """, (project_id, *section_ids)).fetchall()
        return conn.execute("""
            SELECT p.id as product_id, p.name, p.code, p.unit_cost, p.category,
                   p.shop_drawing_path,
                   SUM(ti.count) as count
            FROM takeoff_items ti
            JOIN products p ON ti.product_id = p.id
            WHERE ti.project_id=?
            GROUP BY p.id
            ORDER BY p.category, p.name
        """, (project_id,)).fetchall()


def get_item_count(project_id, product_id, section_id=None):
    with get_conn() as conn:
        if section_id is None:
            row = conn.execute(
                "SELECT count FROM takeoff_items WHERE project_id=? AND product_id=? AND section_id IS NULL",
                (project_id, product_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT count FROM takeoff_items WHERE project_id=? AND product_id=? AND section_id=?",
                (project_id, product_id, section_id),
            ).fetchone()
        return row["count"] if row else 0


def set_item_count(project_id, product_id, count, section_id=None):
    with get_conn() as conn:
        if section_id is None:
            existing = conn.execute(
                "SELECT id FROM takeoff_items WHERE project_id=? AND product_id=? AND section_id IS NULL",
                (project_id, product_id),
            ).fetchone()
        else:
            existing = conn.execute(
                "SELECT id FROM takeoff_items WHERE project_id=? AND product_id=? AND section_id=?",
                (project_id, product_id, section_id),
            ).fetchone()

        if existing:
            if count <= 0:
                conn.execute("DELETE FROM takeoff_items WHERE id=?", (existing["id"],))
            else:
                conn.execute("UPDATE takeoff_items SET count=? WHERE id=?", (count, existing["id"]))
        elif count > 0:
            conn.execute(
                "INSERT INTO takeoff_items (project_id, product_id, count, section_id) VALUES (?,?,?,?)",
                (project_id, product_id, count, section_id),
            )
        conn.commit()


def adjust_item_count(project_id, product_id, delta, section_id=None):
    cur = get_item_count(project_id, product_id, section_id)
    set_item_count(project_id, product_id, max(0, cur + delta), section_id)


# ── Marks ─────────────────────────────────────────────────────────────────────

def add_mark(project_id, pdf_path, page_index, page_x, page_y,
             entity_type, entity_id, color, label, section_id=None, candela=0.0):
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO marks
                (project_id, pdf_path, page_index, page_x, page_y,
                 entity_type, entity_id, color, label, section_id, candela)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (project_id, pdf_path, page_index, page_x, page_y,
              entity_type, entity_id, color, label, section_id, candela))
        conn.commit()
        return cur.lastrowid


def delete_mark(mark_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM marks WHERE id=?", (mark_id,))
        conn.commit()


def update_mark_candela(mark_id, candela):
    """Each placed device's candela is independent of every other plot of
    the same product — set/change it per mark, not per catalogue item."""
    with get_conn() as conn:
        conn.execute("UPDATE marks SET candela=? WHERE id=?", (candela, mark_id))
        conn.commit()


def get_marks(project_id, pdf_path=None):
    with get_conn() as conn:
        if pdf_path:
            return conn.execute(
                "SELECT * FROM marks WHERE project_id=? AND pdf_path=? ORDER BY page_index",
                (project_id, pdf_path),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM marks WHERE project_id=? ORDER BY page_index",
            (project_id,),
        ).fetchall()


def get_candela_breakdown(project_id, section_ids=None):
    """Device count per candela rating across every placed mark in the
    project (any page), for NAC circuit loading math on export. Pass
    section_ids to scope to just those sections instead of the whole
    project — unassigned (no-section) marks are excluded once a section
    filter is applied, matching how the rest of the export is scoped."""
    with get_conn() as conn:
        if section_ids:
            placeholders = ",".join("?" * len(section_ids))
            rows = conn.execute(
                f"SELECT candela, COUNT(*) as cnt FROM marks "
                f"WHERE project_id=? AND candela > 0 AND section_id IN ({placeholders}) "
                f"GROUP BY candela ORDER BY candela",
                (project_id, *section_ids),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT candela, COUNT(*) as cnt FROM marks "
                "WHERE project_id=? AND candela > 0 GROUP BY candela ORDER BY candela",
                (project_id,),
            ).fetchall()
        return {r["candela"]: r["cnt"] for r in rows}


def get_page_scale(project_id, pdf_path, page_index):
    """Return points_per_meter for this page, or None if not set."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT pixels_per_meter FROM page_scales "
            "WHERE project_id=? AND pdf_path=? AND page_index=?",
            (project_id, pdf_path, page_index),
        ).fetchone()
        return row["pixels_per_meter"] if row else None


def set_page_scale(project_id, pdf_path, page_index, points_per_meter):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO page_scales "
            "(project_id, pdf_path, page_index, pixels_per_meter) VALUES (?,?,?,?)",
            (project_id, pdf_path, page_index, points_per_meter),
        )
        conn.commit()


def get_page_label(project_id, pdf_path, page_index):
    """Return the custom label for this page, or None if not set."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT label FROM page_labels WHERE project_id=? AND pdf_path=? AND page_index=?",
            (project_id, pdf_path, page_index),
        ).fetchone()
        return row["label"] if row and row["label"] else None


def set_page_label(project_id, pdf_path, page_index, label):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO page_labels "
            "(project_id, pdf_path, page_index, label) VALUES (?,?,?,?)",
            (project_id, pdf_path, page_index, label),
        )
        conn.commit()


def get_page_labels(project_id, pdf_path):
    """Return {page_index: label} for every labeled page of this PDF."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT page_index, label FROM page_labels WHERE project_id=? AND pdf_path=?",
            (project_id, pdf_path),
        ).fetchall()
        return {r["page_index"]: r["label"] for r in rows if r["label"]}


def rewrite_page_data(project_id, pdf_path, kept_old_indices):
    """
    Called after a PDF's pages have been trimmed/reordered (see
    MainWindow._manage_pages). kept_old_indices lists the OLD page_index
    values that survive, in their NEW left-to-right order — e.g. [0, 2, 5]
    means old pages 0, 2, 5 survive and become new pages 0, 1, 2.

    Deletes every row (marks, scale, runs, labels, field notes/lines) tied
    to a page that was removed, and remaps page_index for surviving rows
    so they still line up with their device/annotation on the trimmed PDF.
    Two passes per table (delete, then update) avoid UNIQUE collisions on
    page_scales/page_labels when a freed index is about to be reused by a
    shifted-down row.
    """
    old_to_new = {old: new for new, old in enumerate(kept_old_indices)}
    tables = ["marks", "page_scales", "linear_runs", "page_labels",
              "field_notes", "field_lines"]
    with get_conn() as conn:
        placeholders = ",".join("?" * len(kept_old_indices))
        for t in tables:
            conn.execute(
                f"DELETE FROM {t} WHERE project_id=? AND pdf_path=? "
                f"AND page_index NOT IN ({placeholders})",
                (project_id, pdf_path, *kept_old_indices),
            )
        for t in tables:
            rows = conn.execute(
                f"SELECT id, page_index FROM {t} WHERE project_id=? AND pdf_path=?",
                (project_id, pdf_path),
            ).fetchall()
            for r in rows:
                new_idx = old_to_new[r["page_index"]]
                if new_idx != r["page_index"]:
                    conn.execute(f"UPDATE {t} SET page_index=? WHERE id=?", (new_idx, r["id"]))
        conn.commit()


def add_linear_run(project_id, assembly_id, pdf_path, page_index, points_json, footage, section_id=None):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO linear_runs"
            "(project_id,assembly_id,pdf_path,page_index,points,footage,section_id)"
            " VALUES(?,?,?,?,?,?,?)",
            (project_id, assembly_id, pdf_path, page_index, points_json, footage, section_id),
        )
        conn.commit()
        return cur.lastrowid


def get_linear_runs(project_id, pdf_path=None):
    with get_conn() as conn:
        if pdf_path:
            return conn.execute(
                "SELECT * FROM linear_runs WHERE project_id=? AND pdf_path=? ORDER BY id",
                (project_id, pdf_path),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM linear_runs WHERE project_id=? ORDER BY id",
            (project_id,),
        ).fetchall()


def delete_linear_run(run_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM linear_runs WHERE id=?", (run_id,))
        conn.commit()


# ── Field Notes (installer markup layer) ────────────────────────────────────────

def add_field_note(project_id, pdf_path, page_index, page_x, page_y,
                    text, color, bold, font_size):
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO field_notes
                (project_id, pdf_path, page_index, page_x, page_y,
                 text, color, bold, font_size)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (project_id, pdf_path, page_index, page_x, page_y,
              text, color, int(bold), font_size))
        conn.commit()
        return cur.lastrowid


def get_field_notes(project_id, pdf_path=None):
    with get_conn() as conn:
        if pdf_path:
            return conn.execute(
                "SELECT * FROM field_notes WHERE project_id=? AND pdf_path=? ORDER BY page_index",
                (project_id, pdf_path),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM field_notes WHERE project_id=? ORDER BY page_index",
            (project_id,),
        ).fetchall()


def update_field_note(note_id, text, color, bold, font_size):
    with get_conn() as conn:
        conn.execute(
            "UPDATE field_notes SET text=?, color=?, bold=?, font_size=? WHERE id=?",
            (text, color, int(bold), font_size, note_id),
        )
        conn.commit()


def delete_field_note(note_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM field_notes WHERE id=?", (note_id,))
        conn.commit()


def add_field_line(project_id, pdf_path, page_index, points_json, color, width):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO field_lines (project_id, pdf_path, page_index, points, color, width)"
            " VALUES (?,?,?,?,?,?)",
            (project_id, pdf_path, page_index, points_json, color, width),
        )
        conn.commit()
        return cur.lastrowid


def get_field_lines(project_id, pdf_path=None):
    with get_conn() as conn:
        if pdf_path:
            return conn.execute(
                "SELECT * FROM field_lines WHERE project_id=? AND pdf_path=? ORDER BY id",
                (project_id, pdf_path),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM field_lines WHERE project_id=? ORDER BY id",
            (project_id,),
        ).fetchall()


def delete_field_line(line_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM field_lines WHERE id=?", (line_id,))
        conn.commit()


# ── PDF Snips — pinned reference crops (e.g. a symbol legend on another page) ───

def add_snip(project_id, name, image_bytes, win_x=80, win_y=80, win_w=320, win_h=240, visible=1):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO pdf_snips (project_id, name, image, visible, win_x, win_y, win_w, win_h)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (project_id, name, sqlite3.Binary(image_bytes), visible, win_x, win_y, win_w, win_h),
        )
        conn.commit()
        return cur.lastrowid


def get_snips(project_id):
    """List of snips (no image blob — use get_snip_image for that) for menu/list building."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, name, visible, win_x, win_y, win_w, win_h FROM pdf_snips "
            "WHERE project_id=? ORDER BY name",
            (project_id,),
        ).fetchall()


def get_snip_image(snip_id):
    with get_conn() as conn:
        row = conn.execute("SELECT image FROM pdf_snips WHERE id=?", (snip_id,)).fetchone()
        return bytes(row["image"]) if row else None


def rename_snip(snip_id, name):
    with get_conn() as conn:
        conn.execute("UPDATE pdf_snips SET name=? WHERE id=?", (name, snip_id))
        conn.commit()


def set_snip_visible(snip_id, visible):
    with get_conn() as conn:
        conn.execute("UPDATE pdf_snips SET visible=? WHERE id=?", (int(visible), snip_id))
        conn.commit()


def update_snip_geometry(snip_id, x, y, w, h):
    with get_conn() as conn:
        conn.execute(
            "UPDATE pdf_snips SET win_x=?, win_y=?, win_w=?, win_h=? WHERE id=?",
            (x, y, w, h, snip_id),
        )
        conn.commit()


def delete_snip(snip_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM pdf_snips WHERE id=?", (snip_id,))
        conn.commit()


# ── Fire Plan Builder (AHJ submission packages) ─────────────────────────────────

def get_fire_plan(project_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM fire_plans WHERE project_id=?", (project_id,)
        ).fetchone()


def upsert_fire_plan(project_id, ahj, vbi_data, has_zoned_alarm,
                     base_building_path, alarm_zone_path):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO fire_plans "
            "(id, project_id, ahj, vbi_data, has_zoned_alarm, base_building_path, alarm_zone_path) "
            "VALUES ((SELECT id FROM fire_plans WHERE project_id=?), ?,?,?,?,?,?)",
            (project_id, project_id, ahj, vbi_data, int(has_zoned_alarm),
             base_building_path, alarm_zone_path),
        )
        conn.commit()


def add_fire_plan_certificate(project_id, label, path):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO fire_plan_certificates (project_id, label, path) VALUES (?,?,?)",
            (project_id, label, path),
        )
        conn.commit()
        return cur.lastrowid


def get_fire_plan_certificates(project_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM fire_plan_certificates WHERE project_id=? ORDER BY id",
            (project_id,),
        ).fetchall()


def delete_fire_plan_certificate(cert_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM fire_plan_certificates WHERE id=?", (cert_id,))
        conn.commit()


def get_assembly_footage(project_id, assembly_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(footage),0) as total FROM linear_runs"
            " WHERE project_id=? AND assembly_id=?",
            (project_id, assembly_id),
        ).fetchone()
        return row["total"] if row else 0.0


def get_linear_run_totals(project_id):
    """Return {assembly_id: total_footage} for all linear runs in a project."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT assembly_id, SUM(footage) as total FROM linear_runs"
            " WHERE project_id=? GROUP BY assembly_id",
            (project_id,),
        ).fetchall()
    return {r["assembly_id"]: r["total"] for r in rows}


def move_section_count(project_id, product_id, qty, from_section_id, to_section_id):
    """Move qty units from one section to another."""
    if qty <= 0:
        return
    adjust_item_count(project_id, product_id, -qty, from_section_id)
    adjust_item_count(project_id, product_id,  qty, to_section_id)


def get_section_breakdown(project_id):
    """Returns rows of (section_id, section_name, product_name, code, count) for reporting."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT s.id as section_id, s.name as section_name, p.name as product_name, p.code,
                   p.category, ti.count
            FROM takeoff_items ti
            JOIN products p ON ti.product_id = p.id
            JOIN sections s ON ti.section_id = s.id
            WHERE ti.project_id=? AND ti.count > 0
            ORDER BY s.sort_order, s.name, p.category, p.name
        """, (project_id,)).fetchall()


# ── Labour Units ──────────────────────────────────────────────────────────────

_LU_DEFAULTS = [
    # Fire Alarm – Devices
    ("Detector Head",              "FA – Devices",   0.20, 0.25, 0.31),
    ("Detector Base",              "FA – Devices",   0.65, 0.81, 1.02),
    ("Duct Detector",              "FA – Devices",   2.00, 2.50, 3.00),
    ("Beam Detector TX/RX",        "FA – Devices",   4.00, 5.00, 6.25),
    ("Manual Station",             "FA – Devices",   0.50, 0.63, 0.78),
    ("Horn / Strobe",              "FA – Devices",   0.75, 0.94, 1.17),
    ("Bell",                       "FA – Devices",   0.75, 0.94, 1.17),
    ("Speaker",                    "FA – Devices",   1.00, 1.25, 1.56),
    ("Phone Handset",              "FA – Devices",   1.20, 1.50, 1.88),
    ("Phone Jack",                 "FA – Devices",   0.50, 0.63, 0.78),
    ("Door Holder / Relay",        "FA – Devices",   0.75, 0.94, 1.17),
    ("Flow / Tamper Switch",       "FA – Devices",   1.20, 1.50, 1.88),
    # Fire Alarm – Panels & Modules
    ("FACP Conventional 4-Zone",   "FA – Panels",   3.00, 3.75, 4.50),
    ("FACP Conventional 8-Zone",   "FA – Panels",   7.00, 8.75,10.50),
    ("FACP Addressable Small",     "FA – Panels",  12.00,15.00,18.75),
    ("FACP Addressable Large",     "FA – Panels",  20.00,25.00,31.25),
    ("Annunciator",                "FA – Panels",   2.00, 2.50, 3.13),
    ("Relay Module",               "FA – Panels",   0.90, 1.13, 1.41),
    ("Power Supply 6A",            "FA – Panels",   2.00, 2.50, 3.13),
    # Wiring & Conduit
    ("Wire 18/2 per 1000 LF",      "Wiring",        2.20, 2.80, 3.30),
    ("Wire 18/4 per 1000 LF",      "Wiring",        2.50, 3.10, 3.80),
    ("EMT 1/2\" per 100 LF",       "Conduit",       3.00, 3.80, 4.50),
    ("EMT 3/4\" per 100 LF",       "Conduit",       3.50, 4.40, 5.30),
    ("Rigid Steel 1/2\" per 100 LF","Conduit",      5.50, 6.80, 8.20),
    # Sprinkler
    ("Sprinkler Head",             "Sprinkler",      0.50, 0.65, 0.80),
    ("Concealed Pendant",          "Sprinkler",      0.70, 0.90, 1.10),
    ("Dry Pendant",                "Sprinkler",      0.75, 0.95, 1.20),
    ("Grooved Coupling 2\"",       "Sprinkler",      0.20, 0.25, 0.31),
    ("Grooved Coupling 3\"",       "Sprinkler",      0.30, 0.38, 0.47),
    ("Hanger Small",               "Sprinkler",      0.15, 0.19, 0.23),
    ("Hanger Large",               "Sprinkler",      0.30, 0.38, 0.47),
    ("Zone Control Valve Assembly","Sprinkler",      4.00, 5.00, 6.25),
    ("Alarm Check Valve 4\"",      "Sprinkler",      8.00,10.00,12.50),
    # Extinguisher / Suppression
    ("Portable Extinguisher",      "Ext / Suppression", 0.40, 0.50, 0.63),
    ("Kitchen Suppression System", "Ext / Suppression", 8.00,10.00,12.50),
    ("Suppression Nozzle",         "Ext / Suppression", 0.50, 0.63, 0.78),
]


def _seed_labour_units():
    """Insert default LU entries once if the table is empty."""
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM labour_units").fetchone()[0]
        if count > 0:
            return
        for name, cat, lr, ld, lh in _LU_DEFAULTS:
            conn.execute(
                "INSERT INTO labour_units(name,category,lu_reg,lu_diff,lu_hard) VALUES(?,?,?,?,?)",
                (name, cat, lr, ld, lh)
            )
        conn.commit()


def get_labour_units():
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM labour_units ORDER BY category, name"
        ).fetchall()


def add_labour_unit(name, category, lu_reg, lu_diff, lu_hard):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO labour_units(name,category,lu_reg,lu_diff,lu_hard) VALUES(?,?,?,?,?)",
            (name, category, lu_reg, lu_diff, lu_hard)
        )
        conn.commit()
        return cur.lastrowid


def update_labour_unit(lu_id, name, category, lu_reg, lu_diff, lu_hard):
    with get_conn() as conn:
        conn.execute(
            "UPDATE labour_units SET name=?,category=?,lu_reg=?,lu_diff=?,lu_hard=? WHERE id=?",
            (name, category, lu_reg, lu_diff, lu_hard, lu_id)
        )
        conn.commit()


def delete_labour_unit(lu_id):
    with get_conn() as conn:
        conn.execute("UPDATE products SET lu_id=NULL WHERE lu_id=?", (lu_id,))
        conn.execute("DELETE FROM labour_units WHERE id=?", (lu_id,))
        conn.commit()


def resolve_lu(product_row):
    """Return (lu_reg, lu_diff, lu_hard, lu_name) for a product, following lu_id if set."""
    lu_id = product_row.get("lu_id") if hasattr(product_row, "get") else product_row["lu_id"]
    if lu_id:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT name,lu_reg,lu_diff,lu_hard FROM labour_units WHERE id=?", (lu_id,)
            ).fetchone()
            if row:
                return row["lu_reg"], row["lu_diff"], row["lu_hard"], row["name"]
    lr = product_row["lu_reg"]  if product_row["lu_reg"]  else 0.0
    ld = product_row["lu_diff"] if product_row["lu_diff"] else 0.0
    lh = product_row["lu_hard"] if product_row["lu_hard"] else 0.0
    return lr, ld, lh, "(custom)" if (lr or ld or lh) else "—"
