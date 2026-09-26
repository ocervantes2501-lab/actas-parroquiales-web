# -*- coding: utf-8 -*-
"""
app.py
======================================================
Aplicación web de Actas Parroquiales, para usarse desde
el navegador del celular (o cualquier computadora). Se
conecta a la MISMA base de datos en la nube (Turso) que
usa el programa de escritorio.

Incluye: inicio de sesión, base de datos de actas
(consultar/agregar), intenciones de misa, agenda de
reservaciones (con pagos) y directorio de servicio.

No incluye (por ahora, se puede agregar después): generar
el PDF con el membrete, firma digital, envío por correo o
WhatsApp. Esas funciones siguen viviendo en el programa de
escritorio.
======================================================
"""

import os
from datetime import date, datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash

import db_web as db
import horario_misas as hm

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambia-esta-clave-en-produccion")


@app.context_processor
def _inyectar_datos_parroquia():
    """Pone la configuración de la parroquia (nombre, ciudad, diócesis)
    disponible en TODAS las plantillas, sin tener que pasarla a mano
    en cada 'render_template'. Así, si alguien cambia estos datos
    desde el programa de escritorio, la página web los refleja solos
    en la siguiente carga de página."""
    return {"parroquia": db.obtener_config_parroquia()}


# =====================================================
# Inicio de sesión
# =====================================================
def login_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login", siguiente=request.path))
        return vista(*args, **kwargs)
    return envoltura


@app.route("/verificar/<categoria>/<int:folio>")
def verificar(categoria, folio):
    """
    Página pública (sin necesidad de iniciar sesión) para validar la
    autenticidad de un acta o constancia escaneando su código QR.
    Solo muestra los datos esenciales, no información sensible
    adicional (padrinos, domicilio, etc.).
    """
    categoria = categoria.lower()
    if categoria == "acta":
        registro = db.obtener_acta_por_folio(folio)
        if registro is None:
            return render_template("verificar.html", encontrado=False, categoria="Acta")
        datos = {
            "titulo": f"Acta de {registro.get('sacramento', '').title()}",
            "nombre": registro.get("nombre_completo", ""),
            "fecha": f"{registro.get('dia_sacramento','')} de {registro.get('mes_sacramento','')} de {registro.get('anio_sacramento','')}",
            "sacerdote": registro.get("sacerdote_sacramento", ""),
            "extra": f"Libro {registro.get('num_libro','')} · Foja {registro.get('num_foja','')} · Acta {registro.get('num_acta','')}",
            "folio": folio,
            "estatus_pago": "PAGADO" if (registro.get("estatus_pago") or "").upper() == "PAGADO" else "PENDIENTE",
        }
        return render_template("verificar.html", encontrado=True, categoria="Acta", datos=datos)

    elif categoria == "constancia":
        registro = db.obtener_constancia_por_folio(folio)
        if registro is None:
            return render_template("verificar.html", encontrado=False, categoria="Constancia")
        tipo = registro.get("tipo", "")
        if tipo == "CATEQUESIS":
            extra = f"Libro {registro.get('libro', '')}"
        elif tipo == "PREPARACION":
            lista = (registro.get("sacramentos") or "").split(",")
            extra = "Sacramento(s): " + ", ".join(db.ETIQUETAS_SACRAMENTO.get(s, s) for s in lista if s)
        else:
            extra = ""
        datos = {
            "titulo": f"Constancia de {db.ETIQUETAS_TIPO_CONSTANCIA.get(tipo, tipo)}",
            "nombre": registro.get("nombre", ""),
            "fecha": registro.get("fecha_emision", ""),
            "sacerdote": registro.get("sacerdote_firma", ""),
            "extra": extra,
            "folio": folio,
        }
        return render_template("verificar.html", encontrado=True, categoria="Constancia", datos=datos)

    return render_template("verificar.html", encontrado=False, categoria="Documento")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")
        print(f"[DEBUG LOGIN] usuario recibido={usuario!r} | longitud_password={len(password)}", flush=True)
        try:
            resultado = db.verificar_login(usuario, password)
        except RuntimeError as e:
            flash(str(e), "error")
            return render_template("login.html")
        if resultado is None:
            flash("Usuario o contraseña incorrectos, o la cuenta está desactivada.", "error")
            return render_template("login.html")
        session["usuario"] = resultado["usuario"]
        session["es_admin"] = resultado["es_admin"]
        siguiente = request.args.get("siguiente") or url_for("inicio")
        return redirect(siguiente)
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# =====================================================
# Tablero principal
# =====================================================
@app.route("/")
@login_requerido
def inicio():
    proximas = db.listar_reservaciones_pendientes(dias=7)
    return render_template("inicio.html", proximas=proximas, etiquetas=db.ETIQUETAS_TIPO_RESERVACION)


# =====================================================
# Base de Datos (actas)
# =====================================================
@app.route("/base-de-datos")
@login_requerido
def base_de_datos():
    texto = request.args.get("q", "")
    registros = db.buscar_todos(texto)
    return render_template("base_de_datos.html", registros=registros, texto=texto)


@app.route("/base-de-datos/nuevo", methods=["GET", "POST"])
@login_requerido
def nuevo_registro():
    if request.method == "POST":
        datos = {c: request.form.get(c, "").strip() for c in db.COLUMNAS if c != "id_registro"}
        nombre = datos.get("nombre_completo")
        libro = datos.get("num_libro")
        foja = datos.get("num_foja")
        acta = datos.get("num_acta")
        sacramento = datos.get("sacramento", "").upper()

        if not nombre:
            flash("Falta el nombre completo.", "error")
            return render_template("nuevo_registro.html", datos=datos)

        duplicado_por_sacramento = sacramento in ("COMUNION", "CONFIRMACION")
        if db.existe_duplicado(
            nombre, libro, foja, acta,
            sacramento=sacramento if duplicado_por_sacramento else None,
        ):
            flash("Ya existe un registro con ese nombre, libro, foja y acta.", "error")
            return render_template("nuevo_registro.html", datos=datos)

        nuevo_id = db.obtener_nuevo_id()
        datos["id_registro"] = nuevo_id
        datos["sacramento"] = sacramento
        db.insertar_registro(datos)
        flash(f"Registro guardado correctamente. Folio: {nuevo_id}", "exito")
        return redirect(url_for("base_de_datos"))

    return render_template("nuevo_registro.html", datos={})


# =====================================================
# Intenciones de Misa
# =====================================================
@app.route("/intenciones", methods=["GET", "POST"])
@login_requerido
def intenciones():
    fecha_texto = request.args.get("fecha") or date.today().isoformat()
    try:
        fecha = date.fromisoformat(fecha_texto)
    except ValueError:
        fecha = date.today()
        fecha_texto = fecha.isoformat()

    horarios = hm.horarios_sugeridos(fecha)
    horas_con_datos = db.listar_horas_con_intenciones(fecha_texto)
    for h in horas_con_datos:
        if h not in horarios:
            horarios.append(h)
    horarios = hm.ordenar_horarios(horarios) or ["7:00 PM"]

    hora = request.args.get("hora") or horarios[0]

    if request.method == "POST":
        hora = request.form.get("hora", "").strip() or hora
        categoria = request.form.get("categoria", "VIVO")
        nombre = request.form.get("nombre", "").strip()
        if not nombre:
            flash("Escribe el nombre de la persona.", "error")
        else:
            db.agregar_intencion(fecha_texto, hora, categoria, nombre)
            flash("Intención agregada.", "exito")
        return redirect(url_for("intenciones", fecha=fecha_texto, hora=hora))

    lista = db.listar_intenciones(fecha_texto, hora)
    return render_template(
        "intenciones.html",
        fecha_texto=fecha_texto, fecha_larga=hm.fecha_larga(fecha),
        horarios=horarios, hora=hora, lista=lista,
        categorias=db.CATEGORIAS_INTENCION, etiquetas=db.ETIQUETAS_CATEGORIA,
    )


@app.route("/intenciones/eliminar/<int:id_intencion>", methods=["POST"])
@login_requerido
def eliminar_intencion(id_intencion):
    fecha_texto = request.form.get("fecha")
    hora = request.form.get("hora")
    db.eliminar_intencion(id_intencion)
    flash("Intención eliminada.", "exito")
    return redirect(url_for("intenciones", fecha=fecha_texto, hora=hora))


# =====================================================
# Agenda de Reservaciones
# =====================================================
@app.route("/agenda", methods=["GET", "POST"])
@login_requerido
def agenda():
    if request.method == "POST":
        tipo = request.form.get("tipo", "OTRA")
        try:
            precio = float(request.form.get("precio_total") or db.obtener_precio_misa_default())
        except ValueError:
            precio = db.obtener_precio_misa_default()

        datos = dict(
            tipo=tipo,
            fecha=request.form.get("fecha", ""),
            hora=request.form.get("hora", "").strip(),
            nombre=request.form.get("nombre", "").strip(),
            telefono=request.form.get("telefono", "").strip(),
            edad=request.form.get("edad", "").strip(),
            estado_civil=request.form.get("estado_civil", "").strip(),
            hijos=request.form.get("hijos", "").strip(),
            causa_muerte=request.form.get("causa_muerte", "").strip(),
            domicilio=request.form.get("domicilio", "").strip(),
            descripcion=request.form.get("descripcion", "").strip(),
            precio_total=precio,
            monto_pagado=0,
            estatus="PENDIENTE",
        )
        if not datos["nombre"] or not datos["telefono"]:
            flash("El nombre y el teléfono son obligatorios.", "error")
        else:
            db.agregar_reservacion(datos)
            flash("Reservación guardada.", "exito")
        return redirect(url_for("agenda"))

    texto = request.args.get("q", "")
    reservaciones = db.listar_reservaciones(texto)
    return render_template(
        "agenda.html", reservaciones=reservaciones, texto=texto,
        tipos=db.TIPOS_RESERVACION, etiquetas=db.ETIQUETAS_TIPO_RESERVACION,
        precio_default=db.obtener_precio_misa_default(),
    )


@app.route("/agenda/pago/<int:id_reservacion>", methods=["POST"])
@login_requerido
def registrar_pago(id_reservacion):
    try:
        monto = float(request.form.get("monto", "0"))
    except ValueError:
        monto = 0
    if monto > 0:
        db.registrar_pago(id_reservacion, monto)
        flash("Pago registrado.", "exito")
    return redirect(url_for("agenda"))


@app.route("/agenda/eliminar/<int:id_reservacion>", methods=["POST"])
@login_requerido
def eliminar_reservacion(id_reservacion):
    db.eliminar_reservacion(id_reservacion)
    flash("Reservación eliminada.", "exito")
    return redirect(url_for("agenda"))


# =====================================================
# Directorio de Servicio
# =====================================================
@app.route("/directorio", methods=["GET", "POST"])
@login_requerido
def directorio():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        rama = request.form.get("rama_servicio", "").strip()
        telefono = request.form.get("telefono", "").strip()
        correo = request.form.get("correo", "").strip()
        if not nombre or not rama:
            flash("El nombre y la rama de servicio son obligatorios.", "error")
        else:
            db.agregar_colaborador(nombre, rama, telefono, correo)
            flash("Persona agregada al directorio.", "exito")
        return redirect(url_for("directorio"))

    texto = request.args.get("q", "")
    colaboradores = db.listar_colaboradores(texto)
    return render_template("directorio.html", colaboradores=colaboradores, texto=texto)


@app.route("/directorio/eliminar/<int:id_colaborador>", methods=["POST"])
@login_requerido
def eliminar_colaborador(id_colaborador):
    db.eliminar_colaborador(id_colaborador)
    flash("Persona eliminada del directorio.", "exito")
    return redirect(url_for("directorio"))


# =====================================================
# Celebraciones pendientes (acceso para los padres)
# =====================================================
# Página aparte, SOLO DE CONSULTA, para que los sacerdotes vean las
# próximas celebraciones desde un enlace, sin usuario: solo con una
# contraseña compartida. La contraseña se puede cambiar en Render
# (variable PASSWORD_CELEBRACIONES) sin tocar el código.
PASSWORD_CELEBRACIONES = os.environ.get("PASSWORD_CELEBRACIONES", "2026")

RANGOS_CELEBRACIONES = {"7": 7, "30": 30, "todas": None}


@app.route("/celebraciones", methods=["GET", "POST"])
def celebraciones():
    import hmac
    from datetime import timedelta

    if request.method == "POST":
        intento = request.form.get("password", "")
        if hmac.compare_digest(intento.encode(), PASSWORD_CELEBRACIONES.encode()):
            session["acceso_celebraciones"] = True
            session.permanent = True  # no pedirla otra vez en ese teléfono por un tiempo
            return redirect(url_for("celebraciones"))
        flash("Contraseña incorrecta.", "error")
        return render_template("celebraciones_acceso.html")

    if not session.get("acceso_celebraciones"):
        return render_template("celebraciones_acceso.html")

    rango = request.args.get("rango", "30")
    if rango not in RANGOS_CELEBRACIONES:
        rango = "30"
    dias = RANGOS_CELEBRACIONES[rango]

    # El servidor de Render usa hora UTC; se usa la hora de México para
    # que las celebraciones de la tarde/noche no desaparezcan antes de tiempo.
    try:
        from zoneinfo import ZoneInfo
        hoy = datetime.now(ZoneInfo("America/Mexico_City")).date()
    except Exception:
        hoy = date.today()
    limite = hoy + timedelta(days=dias) if dias is not None else None

    grupos = {}
    for r in db.listar_reservaciones():
        try:
            f = date.fromisoformat(r.get("fecha") or "")
        except ValueError:
            continue
        if f < hoy or (limite and f > limite):
            continue
        grupos.setdefault(f, []).append(r)

    dias_ordenados = []
    for f in sorted(grupos):
        eventos = sorted(grupos[f], key=lambda r: hm._minutos_desde_medianoche(r.get("hora") or ""))
        dias_ordenados.append({
            "fecha_larga": hm.fecha_larga(f),
            "es_hoy": f == hoy,
            "eventos": eventos,
        })

    return render_template(
        "celebraciones.html",
        dias=dias_ordenados, rango=rango,
        etiquetas=db.ETIQUETAS_TIPO_RESERVACION,
    )


@app.route("/celebraciones/salir")
def celebraciones_salir():
    session.pop("acceso_celebraciones", None)
    return redirect(url_for("celebraciones"))


if __name__ == "__main__":
    app.run(debug=True)
