# -*- coding: utf-8 -*-
"""
firma_web.py
======================================================
Firma y sello para las actas descargadas desde la versión web.

- La imagen se sube desde la pantalla "Firma y sello" y se guarda en
  la base de datos (Turso), no en el disco, porque el servidor de
  Render no conserva archivos entre reinicios.
- Se normaliza a PNG con fondo transparente (lo casi blanco se vuelve
  transparente) y se recorta al trazo visible.
- La firma se dibuja sobre una línea de firma, justo encima del
  nombre del sacerdote. El sello se dibuja en la columna derecha del
  bloque de firma, para poder enviar el acta ya sellada en PDF.
======================================================
"""

import base64
import io

from PIL import Image
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Flowable

UMBRAL_BLANCO = 240
MAX_LADO_PX = 1200

ANCHO_FIRMA_DEFAULT_CM = 4.5
ANCHO_SELLO_DEFAULT_CM = 3.0
ANCHO_CM_MINIMO = 1.5
ANCHO_CM_MAXIMO = 8.0
DESPLAZAMIENTO_CM_MAXIMO = 5.0
ALTO_MAX_FIRMA_CM = 2.0
ALTO_MAX_SELLO_CM = 3.5


def preparar_png(datos_imagen: bytes) -> bytes:
    """Convierte la imagen subida (PNG o JPG) en PNG transparente y recortado."""
    imagen = Image.open(io.BytesIO(datos_imagen)).convert("RGBA")
    imagen.thumbnail((MAX_LADO_PX, MAX_LADO_PX))
    pixeles = imagen.load()
    ancho, alto = imagen.size
    for y in range(alto):
        for x in range(ancho):
            r, g, b, a = pixeles[x, y]
            if r >= UMBRAL_BLANCO and g >= UMBRAL_BLANCO and b >= UMBRAL_BLANCO:
                pixeles[x, y] = (r, g, b, 0)
    bbox = imagen.getchannel("A").getbbox()
    if bbox:
        imagen = imagen.crop(bbox)
    salida = io.BytesIO()
    imagen.save(salida, "PNG")
    return salida.getvalue()


def png_desde_base64(texto_b64):
    if not texto_b64:
        return None
    return base64.b64decode(texto_b64)


class ImagenEnCelda(Flowable):
    """
    Imagen centrada dentro de una celda de ancho fijo (ancho_celda).
    Si linea=True, dibuja una línea de firma justo debajo de la imagen,
    del mismo ancho que la imagen.
    """

    def __init__(self, png_bytes, ancho_cm, alto_max_cm, ancho_celda, linea=False):
        Flowable.__init__(self)
        imagen = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        w, h = imagen.size
        escala = min((ancho_cm * cm) / w, (alto_max_cm * cm) / h)
        self._dw, self._dh = w * escala, h * escala
        self._lector = ImageReader(imagen)
        self._linea = linea
        self._margen = 0  # los trazos de la firma tocan la línea
        self._espacio_bajo_linea = 0.14 * cm if linea else 0
        self.width = ancho_celda
        self.height = self._espacio_bajo_linea + self._margen + self._dh
        self.hAlign = "CENTER"

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        x = (self.width - self._dw) / 2
        y_linea = self._espacio_bajo_linea
        self.canv.drawImage(self._lector, x, y_linea + self._margen, width=self._dw, height=self._dh,
                            mask="auto", preserveAspectRatio=True)
        if self._linea:
            self.canv.setStrokeColorRGB(0, 0, 0)
            self.canv.setLineWidth(0.8)
            self.canv.line(x, y_linea, x + self._dw, y_linea)


DY_MINIMO_CM = -3.0
DX_MINIMO_CM = -4.0
DX_MAXIMO_CM = 4.0
DY_MAXIMO_CM = 5.0


def limitar_posicion(dx_cm, dy_cm):
    """Devuelve (dx, dy) dentro de los límites permitidos."""
    try:
        dx = float(dx_cm or 0)
    except (TypeError, ValueError):
        dx = 0.0
    try:
        dy = float(dy_cm or 0)
    except (TypeError, ValueError):
        dy = 0.0
    return (max(DX_MINIMO_CM, min(dx, DX_MAXIMO_CM)), max(DY_MINIMO_CM, min(dy, DY_MAXIMO_CM)))


class BloqueFirmaWeb(Flowable):
    """
    Firma sobre una línea y, debajo, el nombre y el cargo. Solo la IMAGEN
    de la firma se mueve (dx, dy en cm; dy positivo = hacia abajo). La
    línea y el nombre quedan fijos. Con dx=dy=0, los trazos tocan la línea.
    """

    def __init__(self, png_bytes, ancho_cm, alto_max_cm, ancho_celda, parrafos, dx_cm=0.0, dy_cm=0.0):
        Flowable.__init__(self)
        self.hAlign = "CENTER"
        imagen = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        w, h = imagen.size
        escala = min((ancho_cm * cm) / w, (alto_max_cm * cm) / h)
        self._dw, self._dh = w * escala, h * escala
        self._lector = ImageReader(imagen)
        self._ancho_celda = ancho_celda
        self._parrafos = parrafos
        dx, dy = limitar_posicion(dx_cm, dy_cm)
        self._dx, self._dy = dx * cm, dy * cm
        alto_nombres = 0
        for parrafo in parrafos:
            _, alto = parrafo.wrap(ancho_celda, 10000)
            alto_nombres += alto
        self._y_linea = alto_nombres + 0.14 * cm
        self.width = ancho_celda
        self.height = self._y_linea + self._dh

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        canv = self.canv
        cursor = 0
        for parrafo in reversed(self._parrafos):
            _, alto = parrafo.wrap(self._ancho_celda, 10000)
            parrafo.drawOn(canv, 0, cursor)
            cursor += alto
        y_linea = self._y_linea
        x_linea = self._ancho_celda / 2 - self._dw / 2
        canv.setStrokeColorRGB(0, 0, 0)
        canv.setLineWidth(0.8)
        canv.line(x_linea, y_linea, x_linea + self._dw, y_linea)
        # dy positivo = hacia abajo (en el PDF el eje Y sube, por eso se resta)
        x_firma = self._ancho_celda / 2 + self._dx - self._dw / 2
        canv.drawImage(self._lector, x_firma, y_linea - self._dy, width=self._dw, height=self._dh,
                       mask="auto", preserveAspectRatio=True)
