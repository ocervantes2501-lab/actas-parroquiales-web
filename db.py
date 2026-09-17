import os
import datetime
import libsql_client

TURSO_URL = os.environ.get("TURSO_DATABASE_URL", "")
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "")


def get_client():
    """Crea un cliente síncrono contra Turso (HTTP)."""
    url = TURSO_URL.replace("libsql://", "https://") if TURSO_URL.startswith("libsql://") else TURSO_URL
    return libsql_client.create_client_sync(url=url, auth_token=TURSO_TOKEN)


def execute(sql, args=None):
    """Ejecuta una sentencia y regresa el resultado (rows, columns)."""
    client = get_client()
    try:
        rs = client.execute(sql, args or [])
        return rs
    finally:
        client.close()


def query(sql, args=None):
    """Regresa una lista de dicts para un SELECT."""
    rs = execute(sql, args)
    cols = rs.columns
    return [dict(zip(cols, row)) for row in rs.rows]


def query_one(sql, args=None):
    rows = query(sql, args)
    return rows[0] if rows else None


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS centros (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        direccion TEXT,
        activo INTEGER DEFAULT 1
    )""",
    """CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        usuario TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        rol TEXT NOT NULL,
        centro_id INTEGER,
        activo INTEGER DEFAULT 1
    )""",
    """CREATE TABLE IF NOT EXISTS libros (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        orden INTEGER DEFAULT 0,
        sacramento_relacionado TEXT DEFAULT 'ninguno'
    )""",
    """CREATE TABLE IF NOT EXISTS config (
        clave TEXT PRIMARY KEY,
        valor TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS ninos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre_completo TEXT NOT NULL,
        fecha_nacimiento TEXT,
        centro_id INTEGER,
        catequista_id INTEGER,
        libro_id INTEGER,
        fecha_inscripcion TEXT,
        extemporaneo INTEGER DEFAULT 0,
        activo INTEGER DEFAULT 1,
        nombre_padre TEXT,
        nombre_madre TEXT,
        telefono_contacto TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS actas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nino_id INTEGER NOT NULL,
        tipo TEXT NOT NULL,
        libro TEXT,
        acta TEXT,
        folio TEXT,
        fecha TEXT,
        parroquia TEXT,
        observaciones TEXT,
        capturado_por INTEGER,
        fecha_captura TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS movimientos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nino_id INTEGER NOT NULL,
        centro_origen_id INTEGER,
        centro_destino_id INTEGER,
        fecha TEXT,
        usuario_id INTEGER,
        motivo TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS notas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nino_id INTEGER NOT NULL,
        autor_id INTEGER,
        fecha TEXT,
        texto TEXT NOT NULL
    )""",
]

DEFAULT_CONFIG = {
    "edad_min_comunion": "8",
    "edad_min_confirmacion": "12",
    "fecha_inicio_ciclo": datetime.date.today().isoformat(),
    "dias_limite_extemporaneo": "15",
}


def init_db():
    """Crea las tablas si no existen y siembra datos base. Seguro de correr varias veces."""
    for stmt in SCHEMA:
        execute(stmt)

    # Config por defecto
    for clave, valor in DEFAULT_CONFIG.items():
        existe = query_one("SELECT clave FROM config WHERE clave = ?", [clave])
        if not existe:
            execute("INSERT INTO config (clave, valor) VALUES (?, ?)", [clave, valor])

    # Libros por defecto si no hay ninguno
    libros_existentes = query("SELECT id FROM libros")
    if not libros_existentes:
        libros_default = [
            ("Libro 1 - Iniciación", 1, "ninguno"),
            ("Libro 2 - Preparación Comunión", 2, "comunion"),
            ("Libro 3 - Post Comunión", 3, "ninguno"),
            ("Libro 4 - Preparación Confirmación", 4, "confirmacion"),
        ]
        for nombre, orden, sacramento in libros_default:
            execute(
                "INSERT INTO libros (nombre, orden, sacramento_relacionado) VALUES (?, ?, ?)",
                [nombre, orden, sacramento],
            )

    # Usuario coordinador general por defecto (solo si no existe ninguno)
    admin = query_one("SELECT id FROM usuarios WHERE rol = 'coordinador_general' LIMIT 1")
    if not admin:
        from werkzeug.security import generate_password_hash

        execute(
            "INSERT INTO usuarios (nombre, usuario, password_hash, rol, centro_id, activo) "
            "VALUES (?, ?, ?, 'coordinador_general', NULL, 1)",
            ["Coordinadora General", "admin", generate_password_hash("catequesis2026")],
        )
