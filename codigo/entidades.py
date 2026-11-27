# Santiago Piero Camayo Jimenez
# 2024200488G
# Tema N.o 91 - El factoring como instrumento de financiamiento de corto plazo en el Peru (Unidad II)
# Fecha de extraccion: la que registre log_ejecucion.txt en cada corrida

"""Diccionario de entidades: convierte el nombre que usa cada cuadro en un
identificador unico y estable de banco.

Hace falta porque la SBS nombra al mismo banco de cuatro maneras distintas
segun el cuadro, le pega marcas de nota al pie, y ademas varias entidades
cambiaron de razon social dentro del periodo 2018-2025. Sin esto, la union de
las fuentes devolveria cero filas, y un banco renombrado aparecería partido en
dos series a mitad del panel.

Las equivalencias no se dan por supuestas: el inventario de los 96 meses
demostro que los meses de cada par encajan sin huecos ni solapamientos.
    Continental hasta 2019-05  +  BBVA desde 2019-06   = 96 meses
    Financiero  hasta 2018-07  +  Pichincha desde 2018-08 = 96 meses
    de Comercio hasta 2023-09  +  BANCOM desde 2023-10  = 96 meses
    Azteca      hasta 2021-10  +  Alfin desde 2021-11   = 96 meses
    CAT y Cencosud aparecen ambos 2018-01 a 2019-02, los mismos 14 meses
"""

from __future__ import annotations

import re
import unicodedata

# Filas o columnas que no son un banco y nunca entran al panel.
NO_SON_ENTIDADES = {
    "total banca multiple",   # el agregado del sistema en los cuadros XLS
    "concepto",               # el encabezado de la columna de etiquetas del B-2362
    "promedio",               # el promedio del sistema en el portal de tasas
}

# Palabras que se quitan del principio y del final del nombre ya normalizado.
# "banco de credito del peru" y "Credito" tienen que llegar al mismo sitio.
PREFIJOS = ("banco", "b", "de")
SUFIJOS = ("sa", "peru", "del", "banco")

# Equivalencias que la limpieza automatica no resuelve: abreviaturas propias
# del portal de tasas y los cambios de razon social.
EQUIVALENCIAS = {
    "azteca": "alfin",                       # Azteca paso a ser Alfin en 2021-11
    "continental": "bbva",                   # Continental paso a ser BBVA en 2019-06
    "financiero": "pichincha",               # Financiero paso a Pichincha en 2018-08
    "bancom": "comercio",                    # de Comercio paso a BANCOM en 2023-10
    "cat": "cencosud",                       # CAT es como el portal llama a Cencosud
    "bif": "interamericano de finanzas",     # abreviatura del portal
    "santander cons bank": "santander consumer bank",
}

# Nombre legible de cada entidad, para las tablas del articulo.
NOMBRES = {
    "alfin": "Alfin Banco (antes Azteca)",
    "bbva": "BBVA Peru (antes Continental)",
    "bci": "BCI Peru",
    "bank of china": "Bank of China",
    "cencosud": "Banco Cencosud",
    "citibank": "Citibank",
    "comercio": "BANCOM (antes Banco de Comercio)",
    "compartamos": "Compartamos Banco",
    "credito": "Banco de Credito del Peru",
    "falabella": "Banco Falabella",
    "gnb": "Banco GNB",
    "icbc": "Banco ICBC",
    "interamericano de finanzas": "BanBif",
    "interbank": "Interbank",
    "mibanco": "Mibanco",
    # Aparece en el portal de tasas de 2026, no en el periodo 2018-2025. Se
    # declara porque se observo en un archivo real; si nunca sale en el
    # periodo congelado, simplemente no genera ninguna fila del panel.
    "efectiva": "Banco Efectiva",
    "pichincha": "Banco Pichincha (antes Financiero)",
    "ripley": "Banco Ripley",
    "santander": "Banco Santander Peru",
    "santander consumer bank": "Santander Consumer Bank",
    "scotiabank": "Scotiabank Peru",
}


class EntidadDesconocida(Exception):
    """Aparecio un nombre que el diccionario no contempla.

    Se levanta en vez de descartar la fila: perder un banco en silencio es
    peor que detenerse, porque no deja rastro en los resultados.
    """


def _sin_tildes(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in s if not unicodedata.combining(c))


def limpiar(nombre: str) -> str:
    """Deja el nombre en su forma comparable.

    Quita tildes, parentesis, asteriscos y marcas de nota al pie, y luego
    recorta las palabras de relleno del principio y del final hasta que no
    quede ninguna. Asi "Banco de Credito del Peru", "B. de Credito del Peru
    (con sucursales en el exterior)" y "Credito" terminan en "credito".
    """
    s = _sin_tildes(str(nombre)).lower()
    s = re.sub(r"\(.*?\)", " ", s)      # parentesis cerrados
    s = re.sub(r"\(.*$", " ", s)        # parentesis que el cuadro dejo abierto
    s = s.replace("*", " ")
    s = re.sub(r"\d+\s*/", " ", s)      # marcas tipo 1/ 2/ 3/
    # La forma societaria se quita antes de tocar los puntos: si no, "S.A."
    # se parte en dos letras sueltas y deja de ser reconocible como sufijo.
    s = re.sub(r"\bs\s*\.?\s*a\s*\.?\s*a?\s*\.?\s*$", " ", s)
    s = s.replace(".", " ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    cambio = True
    while cambio and s:
        cambio = False
        partes = s.split(" ")
        if len(partes) > 1 and partes[0] in PREFIJOS:
            s, cambio = " ".join(partes[1:]), True
            continue
        partes = s.split(" ")
        if len(partes) > 1 and partes[-1] in SUFIJOS:
            s, cambio = " ".join(partes[:-1]), True
    return s


def identificar(nombre: str) -> str | None:
    """Devuelve el identificador del banco, o None si la fila no es un banco.

    Levanta EntidadDesconocida ante un nombre que no esta en el diccionario.
    """
    limpio = limpiar(nombre)
    if not limpio or limpio in NO_SON_ENTIDADES:
        return None
    entidad = EQUIVALENCIAS.get(limpio, limpio)
    if entidad not in NOMBRES:
        raise EntidadDesconocida(
            f"nombre no reconocido: {nombre!r} (normalizado a {limpio!r}). "
            f"Agregarlo a EQUIVALENCIAS o a NOMBRES en entidades.py"
        )
    return entidad


def nombre_legible(entidad: str) -> str:
    """Nombre para mostrar en las tablas del articulo."""
    return NOMBRES.get(entidad, entidad)
