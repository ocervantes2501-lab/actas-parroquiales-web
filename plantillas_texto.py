# -*- coding: utf-8 -*-
"""
plantillas_texto.py
======================================================
Sistema de "plantillas de texto" editables: permite cambiar la
REDACCIÓN de las actas, boletas y constancias (los párrafos
principales, no las etiquetas de cada campo) sin tocar código,
desde la ventana "Editar textos de documentos" (ver
ventana_config_textos.py).

Cada plantilla es un texto con espacios {entre_llaves} (como
{parroquia}, {num_libro}, {fecha_sacramento}, etc.) que se
rellenan con los datos de cada documento al momento de generarlo.
CATALOGO indica, para cada una, qué espacios están disponibles.

Si el texto personalizado tiene un error (por ejemplo, un espacio
mal escrito o borrado sin querer), se usa el texto ORIGINAL en su
lugar automáticamente -- así nunca se rompe la generación de un
documento por un error de redacción.
======================================================
"""

import time

import db_web as db

# VERSIÓN WEB: copia de plantillas_texto.py del programa de escritorio
# (mismo CATALOGO). Los textos personalizados se editan desde el
# escritorio y se guardan en la nube; aquí se leen de ahí mismo y se
# guardan en memoria solo 60 segundos, para que un cambio hecho en el
# escritorio se note en la web casi de inmediato.
_cache_plantillas = None
_cache_momento = 0.0
SEGUNDOS_CACHE = 60


def invalidar_cache():
    global _cache_plantillas
    _cache_plantillas = None

# clave -> (grupo, etiqueta para el editor, texto original, lista de
# espacios {disponibles} para esa plantilla en particular)
CATALOGO = {
    "bautismo_principal": (
        "Acta de Bautismo",
        "Párrafo principal (antes del nombre)",
        "El suscrito párroco de esta comunidad eclesial que camina en esta Iglesia "
        "parroquial certifica que, en el libro de bautismos n°{num_libro} "
        "de este Archivo Parroquial a fojas n°{num_foja}, "
        "partida n°{num_acta} se encuentra un acta que dice lo siguiente: "
        "en la parroquia de {parroquia}, el día {fecha_sacramento}, "
        "el Pbro. {sacerdote_sacramento}. bautizó solemnemente a:",
        ["num_libro", "num_foja", "num_acta", "parroquia", "fecha_sacramento", "sacerdote_sacramento"],
    ),
    "bautismo_nacimiento": (
        "Acta de Bautismo",
        "Párrafo de nacimiento (después del nombre)",
        "Nació el día {fecha_nacimiento}, en {lugar_nacimiento}. "
        "Es {hijo} de {padres}.",
        ["fecha_nacimiento", "lugar_nacimiento", "hijo", "padres"],
    ),
    "boda_principal": (
        "Acta de Matrimonio",
        "Párrafo principal (antes del nombre)",
        "El suscrito párroco de esta comunidad eclesial que camina en esta Iglesia "
        "parroquial certifica que en el libro de matrimonio n°{num_libro} "
        "de este archivo parroquial a foja n°{num_foja}, "
        "partida n°{num_acta}, se encuentra un acta que dice lo siguiente: "
        "en la Parroquia de {parroquia}; el día {fecha_sacramento}. "
        "El Sr Pbro. {sacerdote_sacramento}; casó y veló a:",
        ["num_libro", "num_foja", "num_acta", "parroquia", "fecha_sacramento", "sacerdote_sacramento"],
    ),
    "comunion_principal": (
        "Acta de Primera Comunión",
        "Párrafo principal (antes del nombre)",
        "El suscrito párroco de esta comunidad eclesial que camina en esta Iglesia "
        "parroquial certifica que, en el libro n°{num_libro} "
        "de este archivo parroquial a foja n°{num_foja}, "
        "partida n°{num_acta} se encuentra un acta que dice lo siguiente: "
        "en la Parroquia de {parroquia}, el día {fecha_sacramento}, "
        "por el Pbro. {sacerdote_sacramento}. recibió el Sacramento de la Primera Comunión:",
        ["num_libro", "num_foja", "num_acta", "parroquia", "fecha_sacramento", "sacerdote_sacramento"],
    ),
    "confirmacion_principal": (
        "Acta de Confirmación",
        "Párrafo principal (antes del nombre)",
        "El suscrito párroco de esta comunidad eclesial que camina en esta Iglesia "
        "parroquial certifica que, en el libro de confirmaciones n°{num_libro} "
        "de este archivo parroquial a foja n°{num_foja}, "
        "partida n°{num_acta} se encuentra un acta que dice lo siguiente: "
        "en la Parroquia de {parroquia}, el día {fecha_sacramento}, "
        "El Pbro. {sacerdote_sacramento}. Confirmó solemnemente a:",
        ["num_libro", "num_foja", "num_acta", "parroquia", "fecha_sacramento", "sacerdote_sacramento"],
    ),
    "comunion_confirmacion_nacimiento": (
        "Acta de Primera Comunión / Confirmación",
        "Párrafo de nacimiento (después del nombre)",
        "{texto_bautizado} el {fecha_nacimiento}, en {lugar_nacimiento}. "
        "Es {hijo} de {padres}.",
        ["texto_bautizado", "fecha_nacimiento", "lugar_nacimiento", "hijo", "padres"],
    ),
    "acta_entrega": (
        "Actas (Bautismo, Matrimonio, Comunión, Confirmación)",
        "Párrafo de cierre (antes de la firma)",
        "La anterior es copia fiel tomada de su original a petición de la parte "
        "interesada y para los fines legales que convengan. Dada en la notaria "
        "parroquial de {parroquia}; a los {fecha_entrega}.",
        ["parroquia", "fecha_entrega"],
    ),
    "boleta_bautizo_principal": (
        "Boleta de Bautizo",
        "Párrafo principal (antes del nombre)",
        "El día {fecha_celebracion}, {sacerdote_celebro}, "
        "bautizó en esta parroquia a un {palabra_hijo} a quien se le puso por nombre:",
        ["fecha_celebracion", "sacerdote_celebro", "palabra_hijo"],
    ),
    "boleta_bautizo_expedida": (
        "Boleta de Bautizo",
        "Línea final (lugar y fecha de expedición)",
        "Expedida: {lugar}. A {fecha_expedicion}.",
        ["lugar", "fecha_expedicion"],
    ),
    "boleta_matrimonio_principal": (
        "Boleta de Matrimonio",
        "Párrafo principal (antes del nombre)",
        "En la Parroquia de {parroquia}, el día {fecha_celebracion}, "
        "se unieron por medio del Sacramento del Matrimonio Católico:",
        ["parroquia", "fecha_celebracion"],
    ),
    "boleta_matrimonio_expedida": (
        "Boleta de Matrimonio",
        "Línea final (lugar y fecha)",
        "{lugar}; a {fecha_celebracion}.",
        ["lugar", "fecha_celebracion"],
    ),
    "constancia_catequesis_cuerpo": (
        "Constancia de Catequesis",
        "Párrafo principal",
        "Por medio de la presente hago constar que <b>{nombre}</b>, "
        "cursó y concluyó satisfactoriamente su formación del libro "
        "{libro} de catequesis infantil en esta Parroquia de {parroquia}.",
        ["nombre", "libro", "parroquia"],
    ),
    "constancia_platicas_cuerpo": (
        "Constancia de Pláticas Pre-Bautismales",
        "Párrafo principal",
        "Por medio de la presente hago constar que <b>{nombre}</b> "
        "asistieron a las pláticas Pre Bautismales impartidas en esta "
        "parroquia como preparación de bautismo.",
        ["nombre"],
    ),
    "constancia_preparacion_parrafo1": (
        "Constancia de Preparación de Sacramentos",
        "Primer párrafo",
        "Por medio de la presente se hace constar que <b>{nombre}</b> "
        "ha recibido la catequesis correspondiente de preparación para {frase_sacramentos}, "
        "mostrando la disposición y preparación necesarias para recibir {dicho_sacramentos}.",
        ["nombre", "frase_sacramentos", "dicho_sacramentos"],
    ),
    "constancia_preparacion_parrafo2": (
        "Constancia de Preparación de Sacramentos",
        "Segundo párrafo",
        "Por lo anterior, se hace constar que se encuentra debidamente "
        "preparado para recibir {frase_sacramentos}, pudiendo {celebrar_sacramentos} en la parroquia "
        "de su elección, conforme a las disposiciones y requisitos que la "
        "misma establezca.",
        ["frase_sacramentos", "celebrar_sacramentos"],
    ),
    "constancia_expide": (
        "Constancias (Catequesis, Pláticas, Preparación)",
        "Párrafo de cierre (antes de la firma)",
        "La presente se expide a solicitud de la parte interesada y para los "
        "fines legales que a él convengan. Dada en la notaría parroquial de "
        "{parroquia}; a los {dia} días del mes de {mes} de {anio}.",
        ["parroquia", "dia", "mes", "anio"],
    ),
    "constancia_bautismo_externo_cuerpo": (
        "Constancia de Bautismo (persona no registrada aquí)",
        "Párrafo principal",
        "Por medio de la presente hago constar que <b>{nombre}</b>, recibió "
        "el sacramento del Bautismo en esta parroquia, el {fecha_sacramento}. "
        "De manos del {sacerdote_que_bautizo} en esta parroquia.",
        ["nombre", "fecha_sacramento", "sacerdote_que_bautizo"],
    ),
    "constancia_comunion_externa_cuerpo": (
        "Constancia de Primera Comunión (persona no registrada aquí)",
        "Párrafo principal",
        "Por medio de la presente hago constar que <b>{nombre}</b>, recibió "
        "el sacramento de la Primera Comunión en esta parroquia, en {mes_sacramento} "
        "del año {anio_sacramento}. Siendo párroco el {sacerdote_parroco}.",
        ["nombre", "mes_sacramento", "anio_sacramento", "sacerdote_parroco"],
    ),
    "constancia_confirmacion_externa_cuerpo": (
        "Constancia de Confirmación (persona no registrada aquí)",
        "Párrafo principal",
        "Por medio de la presente hago constar que <b>{nombre}</b>, recibió "
        "el sacramento de la Confirmación en esta parroquia, el {fecha_sacramento}. "
        "De manos del {sacerdote_que_confirmo}.",
        ["nombre", "fecha_sacramento", "sacerdote_que_confirmo"],
    ),
}


def obtener_texto(clave, **contexto):
    """Devuelve el texto YA RELLENADO con los datos de 'contexto'.
    Usa el texto personalizado si existe (ver ventana_config_textos.py);
    si no hay ninguno, o si tiene un error de formato (por ejemplo,
    un espacio {mal_escrito} que ya no existe), usa el texto
    original -- así nunca se rompe la generación de un documento por
    un error de redacción."""
    global _cache_plantillas, _cache_momento
    if _cache_plantillas is None or time.time() - _cache_momento > SEGUNDOS_CACHE:
        try:
            _cache_plantillas = db.listar_plantillas_texto_personalizadas()
        except Exception:
            _cache_plantillas = {}
        _cache_momento = time.time()
    _, _, texto_original, _ = CATALOGO[clave]
    texto_a_usar = _cache_plantillas.get(clave) or texto_original
    try:
        return texto_a_usar.format(**contexto)
    except Exception:
        return texto_original.format(**contexto)
