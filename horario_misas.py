# -*- coding: utf-8 -*-
"""
horario_misas.py
======================================================
Reglas de horario de misas de la parroquia:

  - Martes a sábado: 7:00 PM
  - Lunes: sin horario fijo (libre para agregar una misa
    distinta manualmente, si se necesita)
  - Domingos: 7:00 AM, 9:30 AM, 12:00 PM y 7:00 PM
  - Día 1 de cada mes: se agrega una misa de 12:00 PM
    (además de la que ya corresponda ese día de la semana)

También arma el título con el nombre del día y del mes en
español para las hojas de intenciones impresas.
======================================================
"""

from datetime import date

DIAS_SEMANA_ES = [
    "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo",
]

MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def nombre_dia(fecha: date) -> str:
    return DIAS_SEMANA_ES[fecha.weekday()]


def fecha_larga(fecha: date) -> str:
    """Ej: 'LUNES 8 DE DICIEMBRE DE 2025' (igual que en la hoja de muestra)."""
    return f"{nombre_dia(fecha).upper()} {fecha.day} DE {MESES_ES[fecha.month - 1].upper()} DE {fecha.year}"


def horarios_sugeridos(fecha: date):
    """Devuelve la lista de horarios que le corresponden a esa fecha
    según el horario fijo de la parroquia. El usuario siempre puede
    escribir un horario distinto a mano (misa diversa)."""
    dia_semana = fecha.weekday()  # lunes=0 ... domingo=6

    if dia_semana == 6:
        horarios = ["7:00 AM", "9:30 AM", "12:00 PM", "7:00 PM"]
    elif dia_semana == 0:
        horarios = []  # lunes: libre
    else:
        horarios = ["7:00 PM"]

    if fecha.day == 1 and "12:00 PM" not in horarios:
        horarios.append("12:00 PM")

    return horarios


def _minutos_desde_medianoche(hora_texto: str):
    """Convierte '7:00 PM' -> minutos desde medianoche, para poder
    ordenar horarios cronológicamente. Si no logra interpretarlo,
    devuelve un número grande para que quede al final sin tronar."""
    try:
        hora_texto = hora_texto.strip().upper()
        es_pm = "PM" in hora_texto
        es_am = "AM" in hora_texto
        limpio = hora_texto.replace("AM", "").replace("PM", "").strip()
        partes = limpio.split(":")
        h = int(partes[0])
        m = int(partes[1]) if len(partes) > 1 else 0
        if es_pm and h != 12:
            h += 12
        if es_am and h == 12:
            h = 0
        return h * 60 + m
    except Exception:
        return 99999


def ordenar_horarios(lista_horas):
    return sorted(lista_horas, key=_minutos_desde_medianoche)
