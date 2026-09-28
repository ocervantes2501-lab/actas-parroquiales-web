# -*- coding: utf-8 -*-
"""
documentos_pdf.py
======================================================
PDFs que se pueden DESCARGAR desde la versión web:

  - Actas ya guardadas (Bautismo, Matrimonio, Primera
    Comunión, Confirmación), con el membrete, el folio y el
    código QR de verificación.
  - Hoja de intenciones de una misa (para lectores o para el
    padre), o de TODAS las misas de un día en un solo PDF.
  - Hoja de reservación de la Agenda (Exequias, XV Años,
    Boda, Aniversario, Otra misa).

Es el mismo diseño y la misma redacción que usa el programa
de escritorio (certificados.py, intenciones_pdf.py y
reservaciones_pdf.py), incluyendo los textos que se hayan
personalizado desde "Editar textos de documentos". La
diferencia es que aquí el PDF se arma en memoria y se manda
directo al navegador, en vez de guardarse en una carpeta.
======================================================
"""

import io
import os
from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image as RLImage, NextPageTemplate, PageBreak,
    PageTemplate, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

import db_web as db
import horario_misas as hm
import plantillas_texto

CARPETA = os.path.dirname(os.path.abspath(__file__))
MEMBRETE_PATH = os.path.join(CARPETA, "static", "membrete.jpeg")

MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

FUENTE_NORMAL = "Helvetica"
FUENTE_NEGRITA = "Helvetica-Bold"

VERDE_OSCURO = colors.HexColor("#2F4A38")
DORADO = colors.HexColor("#B08D3E")
NEGRO_SUAVE = colors.HexColor("#1A1A1A")
ROJO_FOLIO = colors.HexColor("#B22222")

MARGEN_SUPERIOR = 8.0 * cm
MARGEN_INFERIOR = 2.0 * cm
MARGEN_IZQUIERDO = 1.6 * cm
MARGEN_DERECHO = 1.6 * cm

ESTILO_TITULO = ParagraphStyle(
    "Titulo", fontName=FUENTE_NEGRITA, fontSize=16,
    alignment=TA_CENTER, spaceAfter=10, textColor=VERDE_OSCURO,
)
ESTILO_CUERPO = ParagraphStyle(
    "Cuerpo", fontName=FUENTE_NORMAL, fontSize=12,
    alignment=TA_JUSTIFY, leading=15, spaceAfter=8, textColor=NEGRO_SUAVE,
)
ESTILO_NOMBRE = ParagraphStyle(
    "Nombre", fontName=FUENTE_NEGRITA, fontSize=16,
    alignment=TA_CENTER, spaceAfter=8, textColor=VERDE_OSCURO,
)
ESTILO_ETIQUETA = ParagraphStyle(
    "Etiqueta", fontName=FUENTE_NORMAL, fontSize=12,
    alignment=TA_LEFT, leading=14, spaceAfter=6, textColor=NEGRO_SUAVE,
)
ESTILO_FIRMA = ParagraphStyle(
    "Firma", fontName=FUENTE_NORMAL, fontSize=12,
    alignment=TA_CENTER, spaceAfter=2, textColor=VERDE_OSCURO,
)
ESTILO_FIRMA_NEGRITA = ParagraphStyle(
    "FirmaNegrita", fontName=FUENTE_NEGRITA, fontSize=12,
    alignment=TA_CENTER, spaceAfter=2, textColor=VERDE_OSCURO,
)

SACRAMENTOS_ACTA = {
    "BAUTISMO": ("ACTA DE BAUTISMO", "Acta de Bautismo"),
    "BODA": ("ACTA DE MATRIMONIO", "Acta de Matrimonio"),
    "MATRIMONIO": ("ACTA DE MATRIMONIO", "Acta de Matrimonio"),
    "COMUNION": ("ACTA DE PRIMERA COMUNIÓN", "Acta de Primera Comunión"),
    "CONFIRMACION": ("ACTA DE CONFIRMACIÓN", "Acta de Confirmación"),
}


def _t(valor):
    """Texto seguro para ReportLab (un '&' o '<' en un nombre ya no
    rompe el documento)."""
    return escape(str(valor if valor is not None else ""))


def _texto_parroquia():
    config = db.obtener_config_parroquia()
    return f"{config['nombre_parroquia']} en {config['ciudad_estado']}"


def _pdf_a_bytes(construir):
    buffer = io.BytesIO()
    construir(buffer)
    return buffer.getvalue()


# =====================================================
# ACTAS
# =====================================================
def nombre_archivo_acta(registro):
    _, prefijo = SACRAMENTOS_ACTA.get((registro.get("sacramento") or "").upper(), ("", "Acta"))
    nombre = (registro.get("nombre_completo") or "").replace("/", "-").strip()
    return f"{prefijo} - {nombre} (folio {registro.get('id_registro')}).pdf"


def generar_acta(registro, url_base=None, sacerdote_firma=None, cargo=None, fecha_entrega=None):
    """Devuelve el PDF (bytes) del acta guardada en la base de datos.
    La fecha de entrega es la de hoy, y firma quien quedó registrado
    como 'sacerdote que entrega' (se puede cambiar con los parámetros)."""
    sacramento = (registro.get("sacramento") or "").upper()
    if sacramento not in SACRAMENTOS_ACTA:
        raise ValueError(f"Tipo de acta desconocido: {registro.get('sacramento')!r}")

    hoy = fecha_entrega or date.today()
    d = {k: _t(v) for k, v in registro.items()}
    fecha_sacramento = f"{d.get('dia_sacramento','')} de {d.get('mes_sacramento','')} de {d.get('anio_sacramento','')}"
    fecha_nacimiento = f"{d.get('dia_nacimiento','')} de {d.get('mes_nacimiento','')} de {d.get('anio_nacimiento','')}"
    fecha_entrega_txt = f"{hoy.day} días del mes de {MESES_ES[hoy.month - 1]} de {hoy.year}"
    parroquia = _t(_texto_parroquia())
    comunes = dict(
        num_libro=d.get("num_libro", ""), num_foja=d.get("num_foja", ""), num_acta=d.get("num_acta", ""),
        parroquia=parroquia, fecha_sacramento=fecha_sacramento,
        sacerdote_sacramento=d.get("sacerdote_sacramento", ""),
    )
    nombre = Paragraph(_t((registro.get("nombre_completo") or "").upper()), ESTILO_NOMBRE)
    entrega = Paragraph(
        plantillas_texto.obtener_texto("acta_entrega", parroquia=parroquia, fecha_entrega=fecha_entrega_txt),
        ESTILO_CUERPO,
    )

    if sacramento == "BAUTISMO":
        elementos = [
            Paragraph(plantillas_texto.obtener_texto("bautismo_principal", **comunes), ESTILO_CUERPO),
            nombre, Spacer(1, 0.9 * cm),
            Paragraph(plantillas_texto.obtener_texto(
                "bautismo_nacimiento", fecha_nacimiento=fecha_nacimiento,
                lugar_nacimiento=d.get("lugar_nacimiento", ""), hijo=d.get("hijo", ""), padres=d.get("padres", ""),
            ), ESTILO_CUERPO),
            Paragraph(f"<b>Abuelos paternos:</b> {d.get('abuelos_paternos','')}", ESTILO_ETIQUETA),
            Paragraph(f"<b>Abuelos maternos:</b> {d.get('abuelos_maternos','')}", ESTILO_ETIQUETA),
            Paragraph(f"<b>Padrinos:</b> {d.get('padrinos','')}", ESTILO_ETIQUETA),
            Paragraph(f"<b>Notas Marginales:</b> {d.get('notas_marginales','')}", ESTILO_ETIQUETA),
            entrega,
        ]
    elif sacramento in ("BODA", "MATRIMONIO"):
        elementos = [
            Paragraph(plantillas_texto.obtener_texto("boda_principal", **comunes), ESTILO_CUERPO),
            nombre, Spacer(1, 0.9 * cm),
            Paragraph(f"<b>Siendo testigos:</b> {d.get('testigos','')}.", ESTILO_ETIQUETA),
            Paragraph(f"<b>Siendo padrinos:</b> {d.get('padrinos','')}.", ESTILO_ETIQUETA),
            entrega,
        ]
    else:
        clave = "comunion_principal" if sacramento == "COMUNION" else "confirmacion_principal"
        texto_bautizado = "Que fue bautizada" if (registro.get("hijo") or "").strip().lower() == "hija" else "Que fue bautizado"
        elementos = [
            Paragraph(plantillas_texto.obtener_texto(clave, **comunes), ESTILO_CUERPO),
            nombre, Spacer(1, 0.9 * cm),
            Paragraph(plantillas_texto.obtener_texto(
                "comunion_confirmacion_nacimiento", texto_bautizado=texto_bautizado,
                fecha_nacimiento=fecha_nacimiento, lugar_nacimiento=d.get("lugar_nacimiento", ""),
                hijo=d.get("hijo", ""), padres=d.get("padres", ""),
            ), ESTILO_CUERPO),
            Paragraph(f"<b>Su {d.get('indicar','')}:</b> {d.get('padrinos','')}.", ESTILO_ETIQUETA),
            entrega,
        ]

    folio = registro.get("id_registro")
    firma = sacerdote_firma if sacerdote_firma is not None else (registro.get("sacerdote_entrega") or "")
    cargo = cargo if cargo is not None else (registro.get("cargo") or "")
    titulo, _ = SACRAMENTOS_ACTA[sacramento]

    def construir(buffer):
        doc = SimpleDocTemplate(
            buffer, pagesize=letter, title=nombre_archivo_acta(registro)[:-4],
            leftMargin=MARGEN_IZQUIERDO, rightMargin=MARGEN_DERECHO,
            topMargin=MARGEN_SUPERIOR, bottomMargin=MARGEN_INFERIOR,
        )
        story = [Paragraph(titulo, ESTILO_TITULO)]
        story.extend(elementos)
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph("Para constancia firmo:", ESTILO_ETIQUETA))
        qr = _imagen_qr(url_base, "acta", folio)
        if qr is not None:
            story.append(Spacer(1, 0.2 * cm))
            story.append(qr)
        story.append(Spacer(1, 0.9 * cm))
        story.append(Paragraph("_______________________", ESTILO_FIRMA))
        story.append(Paragraph(_t(firma), ESTILO_FIRMA_NEGRITA))
        story.append(Paragraph(_t(cargo), ESTILO_FIRMA_NEGRITA))
        fondo = _fondo_con_folio(folio)
        doc.build(story, onFirstPage=fondo, onLaterPages=fondo)

    return _pdf_a_bytes(construir)


def _fondo_con_folio(folio):
    def _dibujar(canvas_obj, doc):
        ancho, alto = letter
        if os.path.exists(MEMBRETE_PATH):
            canvas_obj.drawImage(MEMBRETE_PATH, 0, 0, width=ancho, height=alto,
                                 preserveAspectRatio=False, mask="auto")
        if folio in (None, ""):
            return
        ancho_caja, alto_caja, margen = 2.6 * cm, 1.0 * cm, 0.9 * cm
        x0 = ancho - margen - ancho_caja
        y0 = margen
        canvas_obj.setStrokeColor(DORADO)
        canvas_obj.setLineWidth(1)
        canvas_obj.roundRect(x0, y0, ancho_caja, alto_caja, 4, stroke=1, fill=0)
        canvas_obj.setFont(FUENTE_NEGRITA, 9)
        canvas_obj.setFillColor(ROJO_FOLIO)
        canvas_obj.drawCentredString(x0 + ancho_caja / 2, y0 + alto_caja / 2 - 3, f"Folio: {folio}")
    return _dibujar


def _imagen_qr(url_base, categoria, folio):
    if not url_base or folio in (None, ""):
        return None
    try:
        import qrcode
        imagen = qrcode.make(f"{url_base.rstrip('/')}/verificar/{categoria}/{folio}", box_size=4, border=1)
        buffer = io.BytesIO()
        imagen.save(buffer, format="PNG")
        buffer.seek(0)
        return RLImage(buffer, width=2.3 * cm, height=2.3 * cm, hAlign="LEFT")
    except Exception:
        return None


# =====================================================
# HOJAS DE INTENCIONES
# =====================================================
ETIQUETAS_INTENCION = {
    "VIVO": "VIVOS:", "DIFUNTO": "DIFUNTOS:", "ANIVERSARIO": "ANIVERSARIO:",
    "CUMPLEANOS": "CUMPLEAÑOS:", "ACCION_GRACIAS": "ACCIÓN DE GRACIAS:",
    "FAMILIAS": "FAMILIAS:", "SALUD": "SALUD:",
}
ORDEN_CATEGORIAS = ["VIVO", "ANIVERSARIO", "CUMPLEANOS", "ACCION_GRACIAS", "FAMILIAS", "SALUD", "DIFUNTO"]
FILAS_EXTRA_EN_BLANCO = 3
MARGEN_HOJA = 1.27 * cm
ESPACIO_ENTRE_COLUMNAS = 0.6 * cm
ALTURA_ENCABEZADO = 2.1 * cm

HOJAS_INTENCIONES = {
    # clave: (categorías, etiqueta, mostrar VIVOS aunque vacío, texto si no hay nada)
    "lectores": (ORDEN_CATEGORIAS, "Lectores", True, None),
    "padre": (["ANIVERSARIO", "CUMPLEANOS"], "Para el Padre", False,
              "No hay aniversarios ni cumpleaños registrados para esta misa."),
}


def nombre_archivo_intenciones(fecha, hora, hoja="lectores"):
    sufijo = "" if hoja == "lectores" else f" ({HOJAS_INTENCIONES[hoja][1]})"
    hora_txt = (hora or "todas las misas").replace(":", "")
    return f"Intenciones{sufijo} {fecha.isoformat()} {hora_txt}.pdf"


def _tabla_intenciones(intenciones, categorias, mostrar_vivos, texto_si_vacio, ancho_columna):
    por_categoria = {}
    for it in intenciones:
        por_categoria.setdefault(it["categoria"], []).append(it["nombre"])
    filas = []
    for cat in categorias:
        nombres = por_categoria.get(cat, [])
        if (cat == "VIVO" and mostrar_vivos) or nombres:
            filas.append((ETIQUETAS_INTENCION[cat], True))
            filas.extend((n, False) for n in nombres)
    if not filas and texto_si_vacio:
        filas.append((texto_si_vacio, False))
    filas.extend(("", False) for _ in range(FILAS_EXTRA_EN_BLANCO))

    normal = ParagraphStyle("FilaIntencion", fontName="Helvetica", fontSize=12, leading=14)
    negrita = ParagraphStyle("FilaIntencionNegrita", fontName="Helvetica-Bold", fontSize=12, leading=14)
    tabla = Table([[Paragraph(_t(texto), negrita if es_titulo else normal)] for texto, es_titulo in filas],
                  colWidths=[ancho_columna])
    tabla.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.75, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tabla


def generar_hoja_intenciones(fecha, misas, hoja="lectores"):
    """
    'misas' es una lista de (hora, lista_de_intenciones). Con una sola
    misa sale igual que la hoja del escritorio; con varias, cada misa
    empieza en su propia hoja, todo dentro del mismo PDF.
    Mismo acomodo que en Word: se llena la columna izquierda, luego la
    derecha de la MISMA hoja, y hasta entonces se pasa a la siguiente.
    """
    categorias, etiqueta, mostrar_vivos, texto_si_vacio = HOJAS_INTENCIONES[hoja]
    ancho_pagina, alto_pagina = letter
    ancho_columna = (ancho_pagina - 2 * MARGEN_HOJA - ESPACIO_ENTRE_COLUMNAS) / 2
    alto_columna = alto_pagina - 2 * MARGEN_HOJA - ALTURA_ENCABEZADO
    titulo = hm.fecha_larga(fecha)
    estilo_titulo = ParagraphStyle("TituloIntencion", fontName="Helvetica-Bold", fontSize=14,
                                   alignment=TA_CENTER, leading=17)
    estilo_continua = ParagraphStyle("ContinuaIntencion", fontName="Helvetica-Oblique", fontSize=9,
                                     alignment=TA_CENTER, textColor=colors.HexColor("#555555"))

    def construir(buffer):
        doc = BaseDocTemplate(buffer, pagesize=letter, title=nombre_archivo_intenciones(fecha, None, hoja)[:-4],
                              leftMargin=MARGEN_HOJA, rightMargin=MARGEN_HOJA,
                              topMargin=MARGEN_HOJA, bottomMargin=MARGEN_HOJA)
        plantillas, story = [], []
        for i, (hora, intenciones) in enumerate(misas):
            subtitulo = f"HORA: {hora}" + (f" · {etiqueta}" if etiqueta != "Lectores" else "")
            primera_pagina = {}

            def encabezado(canvas_obj, _doc, subtitulo=subtitulo, primera_pagina=primera_pagina):
                pagina = canvas_obj.getPageNumber()
                primera_pagina.setdefault("n", pagina)
                canvas_obj.saveState()
                y = alto_pagina - MARGEN_HOJA - 0.5 * cm
                p1 = Paragraph(_t(titulo), estilo_titulo)
                p1.wrapOn(canvas_obj, ancho_pagina - 2 * MARGEN_HOJA, ALTURA_ENCABEZADO)
                p1.drawOn(canvas_obj, MARGEN_HOJA, y - p1.height)
                y -= p1.height + 2
                if pagina == primera_pagina["n"]:
                    p2 = Paragraph(_t(subtitulo), estilo_titulo)
                else:
                    n = pagina - primera_pagina["n"] + 1
                    p2 = Paragraph(_t(f"{subtitulo} · continuación (página {n})"), estilo_continua)
                p2.wrapOn(canvas_obj, ancho_pagina - 2 * MARGEN_HOJA, ALTURA_ENCABEZADO)
                p2.drawOn(canvas_obj, MARGEN_HOJA, y - p2.height)
                canvas_obj.restoreState()

            marcos = [
                Frame(MARGEN_HOJA, MARGEN_HOJA, ancho_columna, alto_columna, id=f"izq{i}",
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
                Frame(MARGEN_HOJA + ancho_columna + ESPACIO_ENTRE_COLUMNAS, MARGEN_HOJA, ancho_columna,
                      alto_columna, id=f"der{i}", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
            ]
            plantillas.append(PageTemplate(id=f"misa{i}", frames=marcos, onPage=encabezado))
            if i > 0:
                story.append(NextPageTemplate(f"misa{i}"))
                story.append(PageBreak())
            story.append(_tabla_intenciones(intenciones, categorias, mostrar_vivos, texto_si_vacio, ancho_columna))
        doc.addPageTemplates(plantillas)
        doc.build(story)

    return _pdf_a_bytes(construir)


# =====================================================
# HOJA DE RESERVACIÓN (Agenda)
# =====================================================
def nombre_archivo_reservacion(r):
    tipo = db.ETIQUETAS_TIPO_RESERVACION.get(r.get("tipo"), r.get("tipo") or "")
    return f"Reservacion {tipo} - {(r.get('nombre') or '').replace('/', '-')}.pdf"


def generar_hoja_reservacion(r):
    tipo_legible = db.ETIQUETAS_TIPO_RESERVACION.get(r.get("tipo"), r.get("tipo") or "")
    try:
        fecha_legible = hm.fecha_larga(date.fromisoformat(r.get("fecha") or ""))
    except Exception:
        fecha_legible = r.get("fecha") or ""
    hora = r.get("hora") or ""
    fecha_txt = fecha_legible + (f"  —  Hora: {hora}" if hora else "")

    if r.get("tipo") == "EXEQUIAS":
        titulo = "HOJA DE EXEQUIAS"
        filas = [
            ("Fecha:", fecha_txt), ("Nombre:", r.get("nombre")), ("Edad:", r.get("edad")),
            ("Estado civil:", r.get("estado_civil")), ("Hijos:", r.get("hijos")),
            ("Causa de muerte:", r.get("causa_muerte")), ("Domicilio:", r.get("domicilio")),
            ("Teléfono:", r.get("telefono")),
        ]
    else:
        titulo = f"HOJA DE RESERVACIÓN — {tipo_legible.upper()}"
        filas = [
            ("Fecha:", fecha_txt), ("Tipo de celebración:", tipo_legible),
            ("Nombre:", r.get("nombre")), ("Teléfono:", r.get("telefono")),
        ]

    estilo_titulo = ParagraphStyle("TituloReservacion", fontName="Helvetica-Bold", fontSize=15,
                                   alignment=TA_CENTER, spaceAfter=14)
    estilo = ParagraphStyle("EtiquetaReservacion", fontName="Helvetica", fontSize=12,
                            alignment=TA_LEFT, leading=16)
    tabla = Table([[Paragraph(f"<b>{_t(a)}</b>", estilo), Paragraph(_t(b), estilo)] for a, b in filas],
                  colWidths=[5.5 * cm, 12.5 * cm])
    tabla.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.75, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    def construir(buffer):
        doc = SimpleDocTemplate(buffer, pagesize=letter, title=nombre_archivo_reservacion(r)[:-4],
                                leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm)
        doc.build([Paragraph(_t(titulo), estilo_titulo), Spacer(1, 0.3 * cm), tabla])

    return _pdf_a_bytes(construir)
