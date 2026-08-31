# -*- coding: utf-8 -*-
"""
db_web.py
======================================================
Capa de acceso a datos para la versión WEB (para verla
desde el iPhone u otro navegador). A diferencia del
programa de escritorio, esta versión SIEMPRE usa la base
de datos en la nube (Turso) -- no tiene modo local, porque
un servidor web no tiene una "computadora del usuario"
donde guardar un archivo local.

Las credenciales de Turso se leen de variables de entorno
(TURSO_URL y TURSO_AUTH_TOKEN), que se configuran en el
panel de Render (no se escriben en el código, por seguridad).

El esquema de las tablas es EXACTAMENTE el mismo que usa el
programa de escritorio (db.py), porque ambos leen y escriben
la misma base de datos de Turso.
======================================================
"""

import os
import libsql

TURSO_URL = os.environ.get("TURSO_URL")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")

COLUMNAS = [
    "nombre_completo", "num_libro", "num_foja", "num_acta",
    "dia_sacramento", "mes_sacramento", "anio_sacramento",
    "sacerdote_sacramento", "dia_nacimiento", "mes_nacimiento",
    "anio_nacimiento", "lugar_nacimiento", "hijo", "padres",
    "abuelos_paternos", "abuelos_maternos", "padrinos",
    "notas_marginales", "dia_bautizo", "mes_bautizo", "anio_bautizo",
    "lugar_bautizo", "testigos", "sacerdote_entrega", "cargo",
    "id_registro", "sacramento", "indicar",
]

COLUMNAS_TABLA = (
    ["pk"] + [c for c in COLUMNAS if c != "id_registro"] + ["id_registro"]
)


def conectar():
    if not TURSO_URL or not TURSO_AUTH_TOKEN:
        raise RuntimeError(
            "Faltan las variables de entorno TURSO_URL y TURSO_AUTH_TOKEN. "
            "Configúralas en el panel de Render."
        )
    return libsql.connect(database=TURSO_URL, auth_token=TURSO_AUTH_TOKEN)


def _fila_a_dict(fila):
    if fila is None:
        return None
    return dict(zip(COLUMNAS_TABLA, fila))


# =====================================================
# ACTAS (registros)
# =====================================================
def buscar_todos(texto_busqueda: str = ""):
    conn = conectar()
    cur = conn.cursor()
    cur.execute(
        f"SELECT {','.join(COLUMNAS_TABLA)} FROM registros "
        f"ORDER BY CAST(id_registro AS INTEGER)"
    )
    filas = [_fila_a_dict(f) for f in cur.fetchall()]
    conn.close()

    texto = _limpiar_texto(texto_busqueda)
    if texto == "":
        return filas
    if texto.isdigit():
        return [f for f in filas if str(f.get("id_registro", "")).strip() == texto]
    palabras = [p for p in texto.split(" ") if p.strip() != ""]

    def coincide(fila):
        nombre = _limpiar_texto(str(fila.get("nombre_completo", "")))
        return all(p.upper() in nombre.upper() for p in palabras)

    return [f for f in filas if coincide(f)]


def obtener_nuevo_id():
    conn = conectar()
    cur = conn.cursor()
    cur.execute("SELECT MAX(id_registro) FROM registros")
    fila = cur.fetchone()
    conn.close()
    maximo = fila[0] if fila else None
    return 1 if maximo is None else int(maximo) + 1


def existe_duplicado(nombre, libro, foja, acta, sacramento=None):
    conn = conectar()
    cur = conn.cursor()
    if sacramento:
        cur.execute("""
            SELECT COUNT(*) FROM registros
            WHERE nombre_completo = ? AND num_libro = ?
              AND num_foja = ? AND num_acta = ?
              AND UPPER(sacramento) = UPPER(?)
        """, (nombre, libro, foja, acta, sacramento))
    else:
        cur.execute("""
            SELECT COUNT(*) FROM registros
            WHERE nombre_completo = ? AND num_libro = ?
              AND num_foja = ? AND num_acta = ?
        """, (nombre, libro, foja, acta))
    n = cur.fetchone()[0]
    conn.close()
    return n > 0


def insertar_registro(datos: dict):
    conn = conectar()
    cur = conn.cursor()
    campos = [c for c in COLUMNAS]
    placeholders = ",".join("?" for _ in campos)
    valores = [datos.get(c, "") for c in campos]
    cur.execute(
        f"INSERT INTO registros ({','.join(campos)}) VALUES ({placeholders})",
        valores,
    )
    conn.commit()
    conn.close()
    return datos.get("id_registro")


def obtener_registro_por_pk(pk: int):
    conn = conectar()
    cur = conn.cursor()
    cur.execute(
        f"SELECT {','.join(COLUMNAS_TABLA)} FROM registros WHERE pk = ?", (pk,),
    )
    fila = cur.fetchone()
    conn.close()
    return _fila_a_dict(fila)


def _limpiar_texto(texto: str) -> str:
    texto = (texto or "").strip()
    while "  " in texto:
        texto = texto.replace("  ", " ")
    return texto


# =====================================================
# INTENCIONES DE MISA
# =====================================================
CATEGORIAS_INTENCION = [
    "VIVO", "DIFUNTO", "ANIVERSARIO", "CUMPLEANOS",
    "ACCION_GRACIAS", "FAMILIAS", "SALUD",
]

ETIQUETAS_CATEGORIA = {
    "VIVO": "Vivo",
    "DIFUNTO": "Difunto",
    "ANIVERSARIO": "Aniversario",
    "CUMPLEANOS": "Cumpleaños",
    "ACCION_GRACIAS": "Acción de Gracias",
    "FAMILIAS": "Familias",
    "SALUD": "Salud",
}


def agregar_intencion(fecha, hora, categoria, nombre):
    conn = conectar()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO intenciones (fecha, hora, categoria, nombre) VALUES (?, ?, ?, ?)",
        (fecha, hora, categoria, nombre),
    )
    conn.commit()
    conn.close()


def listar_intenciones(fecha, hora):
    conn = conectar()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, categoria, nombre FROM intenciones "
        "WHERE fecha = ? AND hora = ? ORDER BY id",
        (fecha, hora),
    )
    filas = cur.fetchall()
    conn.close()
    return [{"id": f[0], "categoria": f[1], "nombre": f[2]} for f in filas]


def eliminar_intencion(id_intencion: int):
    conn = conectar()
    cur = conn.cursor()
    cur.execute("DELETE FROM intenciones WHERE id = ?", (id_intencion,))
    conn.commit()
    conn.close()


def listar_horas_con_intenciones(fecha):
    conn = conectar()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT hora FROM intenciones WHERE fecha = ?", (fecha,))
    filas = cur.fetchall()
    conn.close()
    return [f[0] for f in filas]


def listar_fechas_con_intenciones(limite=30):
    """Fechas más recientes que ya tienen alguna intención (para
    mostrar un resumen en la app web sin necesitar un calendario)."""
    conn = conectar()
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT fecha FROM intenciones ORDER BY fecha DESC LIMIT ?",
        (limite,),
    )
    filas = cur.fetchall()
    conn.close()
    return [f[0] for f in filas]


# =====================================================
# AGENDA DE RESERVACIONES
# =====================================================
TIPOS_RESERVACION = ["EXEQUIAS", "XV_ANOS", "BODA", "ANIVERSARIO", "OTRA"]

ETIQUETAS_TIPO_RESERVACION = {
    "EXEQUIAS": "Exequias",
    "XV_ANOS": "XV Años",
    "BODA": "Boda",
    "ANIVERSARIO": "Aniversario",
    "OTRA": "Otra misa",
}

PRECIO_MISA_DEFAULT = 500.0

COLUMNAS_RESERVACION = [
    "id", "tipo", "fecha", "hora", "nombre", "telefono",
    "edad", "estado_civil", "hijos", "causa_muerte", "domicilio",
    "descripcion", "precio_total", "monto_pagado", "estatus",
]


def agregar_reservacion(datos: dict):
    campos = [c for c in COLUMNAS_RESERVACION if c != "id"]
    conn = conectar()
    cur = conn.cursor()
    placeholders = ",".join("?" for _ in campos)
    valores = [datos.get(c) for c in campos]
    cur.execute(
        f"INSERT INTO reservaciones ({','.join(campos)}) VALUES ({placeholders})",
        valores,
    )
    conn.commit()
    conn.close()


def listar_reservaciones(filtro_texto: str = ""):
    conn = conectar()
    cur = conn.cursor()
    cur.execute(
        f"SELECT {','.join(COLUMNAS_RESERVACION)} FROM reservaciones ORDER BY fecha, hora"
    )
    filas = cur.fetchall()
    conn.close()
    registros = [dict(zip(COLUMNAS_RESERVACION, f)) for f in filas]

    texto = _limpiar_texto(filtro_texto).upper()
    if not texto:
        return registros
    return [
        r for r in registros
        if texto in str(r.get("nombre") or "").upper()
        or texto in str(r.get("telefono") or "")
    ]


def obtener_reservacion(id_reservacion: int):
    conn = conectar()
    cur = conn.cursor()
    cur.execute(
        f"SELECT {','.join(COLUMNAS_RESERVACION)} FROM reservaciones WHERE id = ?",
        (id_reservacion,),
    )
    fila = cur.fetchone()
    conn.close()
    return dict(zip(COLUMNAS_RESERVACION, fila)) if fila else None


def registrar_pago(id_reservacion: int, monto_abonado: float):
    reservacion = obtener_reservacion(id_reservacion)
    if reservacion is None:
        return None
    nuevo_monto = float(reservacion.get("monto_pagado") or 0) + float(monto_abonado)
    precio = float(reservacion.get("precio_total") or 0)
    nuevo_estatus = "PAGADO" if nuevo_monto >= precio else "PENDIENTE"
    conn = conectar()
    cur = conn.cursor()
    cur.execute(
        "UPDATE reservaciones SET monto_pagado = ?, estatus = ? WHERE id = ?",
        (nuevo_monto, nuevo_estatus, id_reservacion),
    )
    conn.commit()
    conn.close()
    return nuevo_monto, nuevo_estatus


def eliminar_reservacion(id_reservacion: int):
    conn = conectar()
    cur = conn.cursor()
    cur.execute("DELETE FROM reservaciones WHERE id = ?", (id_reservacion,))
    conn.commit()
    conn.close()


def listar_reservaciones_pendientes(dias: int = None):
    """Reservaciones cuyo pago sigue PENDIENTE. Si se indica 'dias',
    solo las que además caen dentro de los próximos 'dias' días."""
    from datetime import date, timedelta

    pendientes = [r for r in listar_reservaciones() if (r.get("estatus") or "") == "PENDIENTE"]

    if dias is None:
        pendientes.sort(key=lambda r: (r.get("fecha") or "", r.get("hora") or ""))
        return pendientes

    hoy = date.today()
    limite = hoy + timedelta(days=dias)
    resultado = []
    for r in pendientes:
        try:
            f = date.fromisoformat(r.get("fecha") or "")
        except Exception:
            continue
        if hoy <= f <= limite:
            resultado.append(r)
    resultado.sort(key=lambda r: (r.get("fecha") or "", r.get("hora") or ""))
    return resultado


# =====================================================
# DIRECTORIO DE SERVICIO
# =====================================================
def agregar_colaborador(nombre, rama_servicio, telefono, correo):
    conn = conectar()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO colaboradores (nombre, rama_servicio, telefono, correo) VALUES (?, ?, ?, ?)",
        (nombre, rama_servicio, telefono, correo),
    )
    conn.commit()
    conn.close()


def actualizar_colaborador(id_colaborador, nombre, rama_servicio, telefono, correo):
    conn = conectar()
    cur = conn.cursor()
    cur.execute(
        "UPDATE colaboradores SET nombre=?, rama_servicio=?, telefono=?, correo=? WHERE id=?",
        (nombre, rama_servicio, telefono, correo, id_colaborador),
    )
    conn.commit()
    conn.close()


def listar_colaboradores(filtro_texto: str = ""):
    conn = conectar()
    cur = conn.cursor()
    cur.execute("SELECT id, nombre, rama_servicio, telefono, correo FROM colaboradores ORDER BY nombre")
    filas = cur.fetchall()
    conn.close()
    columnas = ["id", "nombre", "rama_servicio", "telefono", "correo"]
    registros = [dict(zip(columnas, f)) for f in filas]
    texto = _limpiar_texto(filtro_texto).upper()
    if not texto:
        return registros
    return [
        r for r in registros
        if texto in str(r.get("nombre") or "").upper()
        or texto in str(r.get("rama_servicio") or "").upper()
    ]


def obtener_colaborador(id_colaborador: int):
    conn = conectar()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, nombre, rama_servicio, telefono, correo FROM colaboradores WHERE id = ?",
        (id_colaborador,),
    )
    fila = cur.fetchone()
    conn.close()
    if fila is None:
        return None
    columnas = ["id", "nombre", "rama_servicio", "telefono", "correo"]
    return dict(zip(columnas, fila))


def eliminar_colaborador(id_colaborador: int):
    conn = conectar()
    cur = conn.cursor()
    cur.execute("DELETE FROM colaboradores WHERE id = ?", (id_colaborador,))
    conn.commit()
    conn.close()


# =====================================================
# USUARIOS (login) -- misma tabla que el programa de escritorio
# =====================================================
def verificar_login(usuario: str, password: str):
    import hashlib
    import hmac

    conn = conectar()
    cur = conn.cursor()
    cur.execute(
        "SELECT usuario, password_hash, salt, es_admin, activo FROM usuarios "
        "WHERE LOWER(usuario) = LOWER(?)",
        (usuario.strip(),),
    )
    fila = cur.fetchone()
    conn.close()
    if fila is None:
        return None
    usuario_real, password_hash, salt, es_admin, activo = fila
    if not activo:
        return None
    intento = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), 200_000
    ).hex()
    if not hmac.compare_digest(intento, password_hash):
        return None
    return {"usuario": usuario_real, "es_admin": bool(es_admin)}


# =====================================================
# Verificación de autenticidad (para el código QR)
# =====================================================
COLUMNAS_CONSTANCIA = [
    "folio", "tipo", "nombre", "libro", "sacramentos",
    "sacerdote_firma", "cargo", "fecha_emision",
]

ETIQUETAS_TIPO_CONSTANCIA = {
    "CATEQUESIS": "Catequesis",
    "PLATICAS": "Pláticas Pre-Bautismales",
    "PREPARACION": "Preparación de Sacramentos",
}

ETIQUETAS_SACRAMENTO = {
    "BAUTISMO": "Bautismo",
    "COMUNION": "Primera Comunión",
    "CONFIRMACION": "Confirmación",
}


def obtener_acta_por_folio(folio: int):
    """Busca en 'registros' por id_registro (ese es el folio del acta)."""
    conn = conectar()
    cur = conn.cursor()
    cur.execute(
        f"SELECT {','.join(COLUMNAS_TABLA)} FROM registros WHERE id_registro = ? LIMIT 1",
        (folio,),
    )
    fila = cur.fetchone()
    conn.close()
    return _fila_a_dict(fila)


def obtener_constancia_por_folio(folio: int):
    conn = conectar()
    cur = conn.cursor()
    cur.execute(
        f"SELECT {','.join(COLUMNAS_CONSTANCIA)} FROM constancias WHERE folio = ?",
        (folio,),
    )
    fila = cur.fetchone()
    conn.close()
    if fila is None:
        return None
    return dict(zip(COLUMNAS_CONSTANCIA, fila))

