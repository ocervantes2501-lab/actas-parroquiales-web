import os
import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash

import db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambia-esta-clave-en-produccion")

# Se inicializa la base de datos una vez, al arrancar el proceso.
_DB_READY = False


@app.before_request
def ensure_db():
    global _DB_READY
    if not _DB_READY:
        db.init_db()
        _DB_READY = True


# ---------------------------------------------------------------------------
# Helpers de sesión / permisos
# ---------------------------------------------------------------------------

def current_user():
    if "user_id" not in session:
        return None
    return {
        "id": session["user_id"],
        "nombre": session.get("nombre"),
        "rol": session.get("rol"),
        "centro_id": session.get("centro_id"),
    }


def login_required(roles=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for("login"))
            if roles and user["rol"] not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator


def calcular_edad(fecha_nacimiento_str):
    if not fecha_nacimiento_str:
        return None
    try:
        fn = datetime.date.fromisoformat(fecha_nacimiento_str)
    except ValueError:
        return None
    hoy = datetime.date.today()
    return hoy.year - fn.year - ((hoy.month, hoy.day) < (fn.month, fn.day))


def get_config():
    filas = db.query("SELECT clave, valor FROM config")
    return {f["clave"]: f["valor"] for f in filas}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")
        row = db.query_one("SELECT * FROM usuarios WHERE usuario = ? AND activo = 1", [usuario])
        if row and check_password_hash(row["password_hash"], password):
            session["user_id"] = row["id"]
            session["nombre"] = row["nombre"]
            session["rol"] = row["rol"]
            session["centro_id"] = row["centro_id"]
            return redirect(url_for("dashboard"))
        flash("Usuario o contraseña incorrectos.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required()
def dashboard():
    user = current_user()
    if user["rol"] == "coordinador_general":
        total_ninos = db.query_one("SELECT COUNT(*) AS n FROM ninos WHERE activo = 1")["n"]
        total_centros = db.query_one("SELECT COUNT(*) AS n FROM centros WHERE activo = 1")["n"]
        extemporaneos = db.query_one("SELECT COUNT(*) AS n FROM ninos WHERE extemporaneo = 1 AND activo = 1")["n"]
    elif user["rol"] == "coordinador_centro":
        total_ninos = db.query_one(
            "SELECT COUNT(*) AS n FROM ninos WHERE activo = 1 AND centro_id = ?", [user["centro_id"]]
        )["n"]
        total_centros = 1
        extemporaneos = db.query_one(
            "SELECT COUNT(*) AS n FROM ninos WHERE extemporaneo = 1 AND activo = 1 AND centro_id = ?",
            [user["centro_id"]],
        )["n"]
    else:  # catequista
        total_ninos = db.query_one(
            "SELECT COUNT(*) AS n FROM ninos WHERE activo = 1 AND catequista_id = ?", [user["id"]]
        )["n"]
        total_centros = None
        extemporaneos = None
    return render_template(
        "dashboard.html", user=user, total_ninos=total_ninos,
        total_centros=total_centros, extemporaneos=extemporaneos,
    )


# ---------------------------------------------------------------------------
# Centros (solo coordinadora general)
# ---------------------------------------------------------------------------

@app.route("/centros", methods=["GET", "POST"])
@login_required(roles=["coordinador_general"])
def centros():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        direccion = request.form.get("direccion", "").strip()
        if nombre:
            db.execute("INSERT INTO centros (nombre, direccion, activo) VALUES (?, ?, 1)", [nombre, direccion])
            flash("Centro agregado.", "ok")
        return redirect(url_for("centros"))
    lista = db.query("SELECT * FROM centros WHERE activo = 1 ORDER BY nombre")
    return render_template("centros.html", centros=lista, user=current_user())


@app.route("/centros/<int:centro_id>/desactivar", methods=["POST"])
@login_required(roles=["coordinador_general"])
def desactivar_centro(centro_id):
    db.execute("UPDATE centros SET activo = 0 WHERE id = ?", [centro_id])
    flash("Centro desactivado.", "ok")
    return redirect(url_for("centros"))


# ---------------------------------------------------------------------------
# Usuarios (catequistas / coordinadoras de centro)
# ---------------------------------------------------------------------------

@app.route("/usuarios", methods=["GET", "POST"])
@login_required(roles=["coordinador_general", "coordinador_centro"])
def usuarios():
    user = current_user()
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        usuario_login = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")
        rol = request.form.get("rol")
        centro_id = request.form.get("centro_id") or None

        # Una coordinadora de centro solo puede crear catequistas de SU centro.
        if user["rol"] == "coordinador_centro":
            rol = "catequista"
            centro_id = user["centro_id"]

        if nombre and usuario_login and password and rol:
            existe = db.query_one("SELECT id FROM usuarios WHERE usuario = ?", [usuario_login])
            if existe:
                flash("Ese nombre de usuario ya existe.", "error")
            else:
                db.execute(
                    "INSERT INTO usuarios (nombre, usuario, password_hash, rol, centro_id, activo) "
                    "VALUES (?, ?, ?, ?, ?, 1)",
                    [nombre, usuario_login, generate_password_hash(password), rol, centro_id],
                )
                flash("Usuario creado.", "ok")
        return redirect(url_for("usuarios"))

    if user["rol"] == "coordinador_general":
        lista = db.query(
            "SELECT u.*, c.nombre AS centro_nombre FROM usuarios u "
            "LEFT JOIN centros c ON c.id = u.centro_id WHERE u.activo = 1 ORDER BY u.rol, u.nombre"
        )
    else:
        lista = db.query(
            "SELECT u.*, c.nombre AS centro_nombre FROM usuarios u "
            "LEFT JOIN centros c ON c.id = u.centro_id "
            "WHERE u.activo = 1 AND u.centro_id = ? ORDER BY u.nombre",
            [user["centro_id"]],
        )
    centros_lista = db.query("SELECT * FROM centros WHERE activo = 1 ORDER BY nombre")
    return render_template("usuarios.html", usuarios=lista, centros=centros_lista, user=user)


def _puede_gestionar_usuario(user, otro):
    if user["rol"] == "coordinador_general":
        return True
    if user["rol"] == "coordinador_centro":
        return otro["rol"] == "catequista" and otro["centro_id"] == user["centro_id"]
    return False


@app.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@login_required(roles=["coordinador_general", "coordinador_centro"])
def usuario_editar(usuario_id):
    user = current_user()
    otro = db.query_one("SELECT * FROM usuarios WHERE id = ?", [usuario_id])
    if not otro or not _puede_gestionar_usuario(user, otro):
        abort(403)

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        rol = request.form.get("rol") if user["rol"] == "coordinador_general" else otro["rol"]
        centro_id = request.form.get("centro_id") if user["rol"] == "coordinador_general" else otro["centro_id"]
        if nombre:
            db.execute(
                "UPDATE usuarios SET nombre = ?, rol = ?, centro_id = ? WHERE id = ?",
                [nombre, rol, centro_id or None, usuario_id],
            )
            flash("Usuario actualizado.", "ok")
        return redirect(url_for("usuarios"))

    centros_lista = db.query("SELECT * FROM centros WHERE activo = 1 ORDER BY nombre")
    return render_template("usuario_editar.html", otro=otro, centros=centros_lista, user=user)


@app.route("/usuarios/<int:usuario_id>/resetear", methods=["POST"])
@login_required(roles=["coordinador_general", "coordinador_centro"])
def usuario_resetear(usuario_id):
    user = current_user()
    otro = db.query_one("SELECT * FROM usuarios WHERE id = ?", [usuario_id])
    if not otro or not _puede_gestionar_usuario(user, otro):
        abort(403)
    nueva = request.form.get("nueva", "")
    if len(nueva) < 6:
        flash("La nueva contraseña debe tener al menos 6 caracteres.", "error")
    else:
        db.execute("UPDATE usuarios SET password_hash = ? WHERE id = ?", [generate_password_hash(nueva), usuario_id])
        flash(f"Contraseña de {otro['nombre']} restablecida correctamente.", "ok")
    return redirect(url_for("usuarios"))


@app.route("/usuarios/<int:usuario_id>/baja", methods=["POST"])
@login_required(roles=["coordinador_general", "coordinador_centro"])
def usuario_baja(usuario_id):
    user = current_user()
    otro = db.query_one("SELECT * FROM usuarios WHERE id = ?", [usuario_id])
    if not otro or not _puede_gestionar_usuario(user, otro):
        abort(403)
    if otro["id"] == user["id"]:
        flash("No puedes eliminar tu propia cuenta mientras tienes la sesión abierta.", "error")
        return redirect(url_for("usuarios"))
    db.execute("UPDATE usuarios SET activo = 0 WHERE id = ?", [usuario_id])
    flash(f"Usuario {otro['nombre']} eliminado (dado de baja).", "ok")
    return redirect(url_for("usuarios"))


# ---------------------------------------------------------------------------
# Configuración general (edades mínimas, ciclo, límite de extemporaneidad)
# ---------------------------------------------------------------------------

@app.route("/config", methods=["GET", "POST"])
@login_required(roles=["coordinador_general"])
def configuracion():
    if request.method == "POST":
        for clave in ["edad_min_comunion", "edad_min_confirmacion", "fecha_inicio_ciclo", "dias_limite_extemporaneo"]:
            valor = request.form.get(clave, "").strip()
            if valor:
                db.execute("UPDATE config SET valor = ? WHERE clave = ?", [valor, clave])
        flash("Configuración actualizada.", "ok")
        return redirect(url_for("configuracion"))
    cfg = get_config()
    libros = db.query("SELECT * FROM libros ORDER BY orden")
    return render_template("config.html", cfg=cfg, libros=libros, user=current_user())


@app.route("/config/libros", methods=["POST"])
@login_required(roles=["coordinador_general"])
def agregar_libro():
    nombre = request.form.get("nombre", "").strip()
    orden = request.form.get("orden", "0")
    sacramento = request.form.get("sacramento_relacionado", "ninguno")
    if nombre:
        db.execute(
            "INSERT INTO libros (nombre, orden, sacramento_relacionado) VALUES (?, ?, ?)",
            [nombre, orden, sacramento],
        )
        flash("Libro agregado.", "ok")
    return redirect(url_for("configuracion"))


# ---------------------------------------------------------------------------
# Niños
# ---------------------------------------------------------------------------

def _ninos_visibles(user):
    if user["rol"] == "coordinador_general":
        return db.query(
            "SELECT n.*, c.nombre AS centro_nombre, l.nombre AS libro_nombre, u.nombre AS catequista_nombre "
            "FROM ninos n LEFT JOIN centros c ON c.id = n.centro_id "
            "LEFT JOIN libros l ON l.id = n.libro_id "
            "LEFT JOIN usuarios u ON u.id = n.catequista_id "
            "WHERE n.activo = 1 ORDER BY c.nombre, n.nombre_completo"
        )
    if user["rol"] == "coordinador_centro":
        return db.query(
            "SELECT n.*, c.nombre AS centro_nombre, l.nombre AS libro_nombre, u.nombre AS catequista_nombre "
            "FROM ninos n LEFT JOIN centros c ON c.id = n.centro_id "
            "LEFT JOIN libros l ON l.id = n.libro_id "
            "LEFT JOIN usuarios u ON u.id = n.catequista_id "
            "WHERE n.activo = 1 AND n.centro_id = ? ORDER BY n.nombre_completo",
            [user["centro_id"]],
        )
    # catequista: solo sus propios niños asignados
    return db.query(
        "SELECT n.*, c.nombre AS centro_nombre, l.nombre AS libro_nombre, u.nombre AS catequista_nombre "
        "FROM ninos n LEFT JOIN centros c ON c.id = n.centro_id "
        "LEFT JOIN libros l ON l.id = n.libro_id "
        "LEFT JOIN usuarios u ON u.id = n.catequista_id "
        "WHERE n.activo = 1 AND n.catequista_id = ? ORDER BY n.nombre_completo",
        [user["id"]],
    )


@app.route("/ninos")
@login_required()
def ninos():
    user = current_user()
    lista = _ninos_visibles(user)
    return render_template("ninos_list.html", ninos=lista, user=user)


@app.route("/ninos/nuevo", methods=["GET", "POST"])
@login_required(roles=["coordinador_general", "coordinador_centro"])
def nino_nuevo():
    user = current_user()
    if request.method == "POST":
        nombre_completo = request.form.get("nombre_completo", "").strip().upper()
        fecha_nacimiento = request.form.get("fecha_nacimiento", "")
        libro_id = request.form.get("libro_id")
        catequista_id = request.form.get("catequista_id") or None
        fecha_inscripcion = request.form.get("fecha_inscripcion") or datetime.date.today().isoformat()
        nombre_padre = request.form.get("nombre_padre", "").strip()
        nombre_madre = request.form.get("nombre_madre", "").strip()
        telefono_contacto = request.form.get("telefono_contacto", "").strip()

        centro_id = user["centro_id"] if user["rol"] == "coordinador_centro" else request.form.get("centro_id")

        # --- Validación de edad mínima según el libro/sacramento ---
        cfg = get_config()
        libro = db.query_one("SELECT * FROM libros WHERE id = ?", [libro_id]) if libro_id else None
        edad = calcular_edad(fecha_nacimiento)
        if libro and edad is not None:
            sacramento = libro["sacramento_relacionado"]
            minimo = None
            if sacramento == "comunion":
                minimo = int(cfg.get("edad_min_comunion", 8))
            elif sacramento == "confirmacion":
                minimo = int(cfg.get("edad_min_confirmacion", 12))
            if minimo is not None and edad < minimo:
                flash(
                    f"Atención: el niño tiene {edad} años y el mínimo configurado para este libro es {minimo}. "
                    "Se guardó de todas formas, revísalo con la coordinadora general.",
                    "warn",
                )

        # --- Validación de inscripción extemporánea ---
        extemporaneo = 0
        try:
            inicio_ciclo = datetime.date.fromisoformat(cfg.get("fecha_inicio_ciclo"))
            limite_dias = int(cfg.get("dias_limite_extemporaneo", 15))
            fecha_insc = datetime.date.fromisoformat(fecha_inscripcion)
            if (fecha_insc - inicio_ciclo).days > limite_dias:
                extemporaneo = 1
        except (ValueError, TypeError):
            pass

        db.execute(
            "INSERT INTO ninos (nombre_completo, fecha_nacimiento, centro_id, catequista_id, libro_id, "
            "fecha_inscripcion, extemporaneo, activo, nombre_padre, nombre_madre, telefono_contacto) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
            [nombre_completo, fecha_nacimiento, centro_id, catequista_id, libro_id,
             fecha_inscripcion, extemporaneo, nombre_padre, nombre_madre, telefono_contacto],
        )
        if extemporaneo:
            flash("El niño quedó marcado como INSCRIPCIÓN EXTEMPORÁNEA (fuera del plazo del ciclo).", "warn")
        flash("Niño registrado.", "ok")
        return redirect(url_for("ninos"))

    libros = db.query("SELECT * FROM libros ORDER BY orden")
    if user["rol"] == "coordinador_general":
        centros_lista = db.query("SELECT * FROM centros WHERE activo = 1 ORDER BY nombre")
        catequistas = db.query("SELECT * FROM usuarios WHERE rol = 'catequista' AND activo = 1 ORDER BY nombre")
    else:
        centros_lista = db.query("SELECT * FROM centros WHERE id = ?", [user["centro_id"]])
        catequistas = db.query(
            "SELECT * FROM usuarios WHERE rol = 'catequista' AND activo = 1 AND centro_id = ? ORDER BY nombre",
            [user["centro_id"]],
        )
    return render_template(
        "nino_form.html", libros=libros, centros=centros_lista, catequistas=catequistas, user=user
    )


def _puede_ver_nino(user, nino):
    if user["rol"] == "coordinador_general":
        return True
    if user["rol"] == "coordinador_centro":
        return nino["centro_id"] == user["centro_id"]
    return nino["catequista_id"] == user["id"]


# ---------------------------------------------------------------------------
# Actas (bautismo / comunión / confirmación) — NO accesibles a catequistas
# ---------------------------------------------------------------------------

@app.route("/ninos/<int:nino_id>/actas", methods=["GET", "POST"])
@login_required(roles=["coordinador_general", "coordinador_centro"])
def actas_nino(nino_id):
    user = current_user()
    nino = db.query_one("SELECT * FROM ninos WHERE id = ?", [nino_id])
    if not nino or not _puede_ver_nino(user, nino):
        abort(403)

    if request.method == "POST":
        tipo = request.form.get("tipo")
        libro = request.form.get("libro", "").strip()
        acta = request.form.get("acta", "").strip()
        folio = request.form.get("folio", "").strip()
        fecha = request.form.get("fecha", "")
        parroquia = request.form.get("parroquia", "").strip()
        observaciones = request.form.get("observaciones", "").strip()
        db.execute(
            "INSERT INTO actas (nino_id, tipo, libro, acta, folio, fecha, parroquia, observaciones, "
            "capturado_por, fecha_captura) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [nino_id, tipo, libro, acta, folio, fecha, parroquia, observaciones,
             user["id"], datetime.date.today().isoformat()],
        )
        flash("Acta cargada.", "ok")
        return redirect(url_for("actas_nino", nino_id=nino_id))

    actas = db.query("SELECT * FROM actas WHERE nino_id = ? ORDER BY tipo", [nino_id])
    return render_template("actas.html", nino=nino, actas=actas, user=user)


# ---------------------------------------------------------------------------
# Movimientos entre centros (con auditoría)
# ---------------------------------------------------------------------------

@app.route("/ninos/<int:nino_id>/mover", methods=["GET", "POST"])
@login_required(roles=["coordinador_general", "coordinador_centro"])
def mover_nino(nino_id):
    user = current_user()
    nino = db.query_one("SELECT * FROM ninos WHERE id = ?", [nino_id])
    if not nino or not _puede_ver_nino(user, nino):
        abort(403)

    if request.method == "POST":
        centro_destino_id = request.form.get("centro_destino_id")
        motivo = request.form.get("motivo", "").strip()
        centro_origen_id = nino["centro_id"]
        db.execute(
            "INSERT INTO movimientos (nino_id, centro_origen_id, centro_destino_id, fecha, usuario_id, motivo) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [nino_id, centro_origen_id, centro_destino_id, datetime.date.today().isoformat(), user["id"], motivo],
        )
        db.execute("UPDATE ninos SET centro_id = ? WHERE id = ?", [centro_destino_id, nino_id])
        flash("Movimiento registrado y niño transferido de centro.", "ok")
        return redirect(url_for("ninos"))

    centros_lista = db.query("SELECT * FROM centros WHERE activo = 1 AND id != ? ORDER BY nombre", [nino["centro_id"]])
    return render_template("mover.html", nino=nino, centros=centros_lista, user=user)


@app.route("/movimientos")
@login_required(roles=["coordinador_general", "coordinador_centro"])
def movimientos():
    user = current_user()
    if user["rol"] == "coordinador_general":
        lista = db.query(
            "SELECT m.*, n.nombre_completo, co.nombre AS origen_nombre, cd.nombre AS destino_nombre, "
            "u.nombre AS usuario_nombre FROM movimientos m "
            "LEFT JOIN ninos n ON n.id = m.nino_id "
            "LEFT JOIN centros co ON co.id = m.centro_origen_id "
            "LEFT JOIN centros cd ON cd.id = m.centro_destino_id "
            "LEFT JOIN usuarios u ON u.id = m.usuario_id "
            "ORDER BY m.fecha DESC"
        )
    else:
        lista = db.query(
            "SELECT m.*, n.nombre_completo, co.nombre AS origen_nombre, cd.nombre AS destino_nombre, "
            "u.nombre AS usuario_nombre FROM movimientos m "
            "LEFT JOIN ninos n ON n.id = m.nino_id "
            "LEFT JOIN centros co ON co.id = m.centro_origen_id "
            "LEFT JOIN centros cd ON cd.id = m.centro_destino_id "
            "LEFT JOIN usuarios u ON u.id = m.usuario_id "
            "WHERE m.centro_origen_id = ? OR m.centro_destino_id = ? ORDER BY m.fecha DESC",
            [user["centro_id"], user["centro_id"]],
        )
    return render_template("movimientos.html", movimientos=lista, user=user)


# ---------------------------------------------------------------------------
# Expediente del niño: datos + movimientos + actas (si aplica) + notas
# ---------------------------------------------------------------------------

@app.route("/ninos/<int:nino_id>/expediente", methods=["GET", "POST"])
@login_required()
def expediente_nino(nino_id):
    user = current_user()
    nino = db.query_one(
        "SELECT n.*, c.nombre AS centro_nombre, l.nombre AS libro_nombre, u.nombre AS catequista_nombre "
        "FROM ninos n LEFT JOIN centros c ON c.id = n.centro_id "
        "LEFT JOIN libros l ON l.id = n.libro_id "
        "LEFT JOIN usuarios u ON u.id = n.catequista_id WHERE n.id = ?",
        [nino_id],
    )
    if not nino or not _puede_ver_nino(user, nino):
        abort(403)

    if request.method == "POST":
        texto = request.form.get("texto", "").strip()
        if texto:
            db.execute(
                "INSERT INTO notas (nino_id, autor_id, fecha, texto) VALUES (?, ?, ?, ?)",
                [nino_id, user["id"], datetime.date.today().isoformat(), texto],
            )
            flash("Nota agregada al expediente.", "ok")
        return redirect(url_for("expediente_nino", nino_id=nino_id))

    ve_actas = user["rol"] in ["coordinador_general", "coordinador_centro"]
    actas = db.query("SELECT * FROM actas WHERE nino_id = ? ORDER BY tipo", [nino_id]) if ve_actas else []
    movs = db.query(
        "SELECT m.*, co.nombre AS origen_nombre, cd.nombre AS destino_nombre, u.nombre AS usuario_nombre "
        "FROM movimientos m LEFT JOIN centros co ON co.id = m.centro_origen_id "
        "LEFT JOIN centros cd ON cd.id = m.centro_destino_id "
        "LEFT JOIN usuarios u ON u.id = m.usuario_id "
        "WHERE m.nino_id = ? ORDER BY m.fecha DESC",
        [nino_id],
    )
    notas = db.query(
        "SELECT n.*, u.nombre AS autor_nombre FROM notas n LEFT JOIN usuarios u ON u.id = n.autor_id "
        "WHERE n.nino_id = ? ORDER BY n.fecha DESC, n.id DESC",
        [nino_id],
    )
    return render_template(
        "expediente.html", nino=nino, actas=actas, ve_actas=ve_actas, movimientos=movs, notas=notas, user=user
    )


# ---------------------------------------------------------------------------
# Editar / dar de baja niño
# ---------------------------------------------------------------------------

@app.route("/ninos/<int:nino_id>/editar", methods=["GET", "POST"])
@login_required(roles=["coordinador_general", "coordinador_centro"])
def nino_editar(nino_id):
    user = current_user()
    nino = db.query_one("SELECT * FROM ninos WHERE id = ?", [nino_id])
    if not nino or not _puede_ver_nino(user, nino):
        abort(403)

    if request.method == "POST":
        nombre_completo = request.form.get("nombre_completo", "").strip().upper()
        fecha_nacimiento = request.form.get("fecha_nacimiento", "")
        libro_id = request.form.get("libro_id")
        catequista_id = request.form.get("catequista_id") or None
        nombre_padre = request.form.get("nombre_padre", "").strip()
        nombre_madre = request.form.get("nombre_madre", "").strip()
        telefono_contacto = request.form.get("telefono_contacto", "").strip()

        db.execute(
            "UPDATE ninos SET nombre_completo=?, fecha_nacimiento=?, libro_id=?, catequista_id=?, "
            "nombre_padre=?, nombre_madre=?, telefono_contacto=? WHERE id=?",
            [nombre_completo, fecha_nacimiento, libro_id, catequista_id,
             nombre_padre, nombre_madre, telefono_contacto, nino_id],
        )
        flash("Datos del niño actualizados.", "ok")
        return redirect(url_for("ninos"))

    libros = db.query("SELECT * FROM libros ORDER BY orden")
    if user["rol"] == "coordinador_general":
        catequistas = db.query(
            "SELECT * FROM usuarios WHERE rol = 'catequista' AND activo = 1 AND centro_id = ? ORDER BY nombre",
            [nino["centro_id"]],
        )
    else:
        catequistas = db.query(
            "SELECT * FROM usuarios WHERE rol = 'catequista' AND activo = 1 AND centro_id = ? ORDER BY nombre",
            [user["centro_id"]],
        )
    return render_template("nino_form.html", libros=libros, centros=None, catequistas=catequistas, user=user, nino=nino)


@app.route("/ninos/<int:nino_id>/baja", methods=["POST"])
@login_required(roles=["coordinador_general", "coordinador_centro"])
def nino_baja(nino_id):
    user = current_user()
    nino = db.query_one("SELECT * FROM ninos WHERE id = ?", [nino_id])
    if not nino or not _puede_ver_nino(user, nino):
        abort(403)
    db.execute("UPDATE ninos SET activo = 0 WHERE id = ?", [nino_id])
    flash("Niño dado de baja del sistema.", "ok")
    return redirect(url_for("ninos"))


# ---------------------------------------------------------------------------
# Cambiar contraseña (cualquier usuario logueado, sobre su propia cuenta)
# ---------------------------------------------------------------------------

@app.route("/perfil/password", methods=["GET", "POST"])
@login_required()
def cambiar_password():
    user = current_user()
    if request.method == "POST":
        actual = request.form.get("actual", "")
        nueva = request.form.get("nueva", "")
        confirmar = request.form.get("confirmar", "")
        row = db.query_one("SELECT * FROM usuarios WHERE id = ?", [user["id"]])
        if not check_password_hash(row["password_hash"], actual):
            flash("La contraseña actual no es correcta.", "error")
        elif len(nueva) < 6:
            flash("La nueva contraseña debe tener al menos 6 caracteres.", "error")
        elif nueva != confirmar:
            flash("La confirmación no coincide con la nueva contraseña.", "error")
        else:
            db.execute(
                "UPDATE usuarios SET password_hash = ? WHERE id = ?",
                [generate_password_hash(nueva), user["id"]],
            )
            flash("Contraseña actualizada correctamente.", "ok")
            return redirect(url_for("dashboard"))
    return render_template("cambiar_password.html", user=user)


# ---------------------------------------------------------------------------
# PWA: manifest y service worker se sirven como estáticos (ver /static)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
