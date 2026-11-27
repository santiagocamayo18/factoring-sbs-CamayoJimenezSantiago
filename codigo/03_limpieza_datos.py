# Santiago Piero Camayo Jimenez
# 2024200488G
# Tema N.o 91 - El factoring como instrumento de financiamiento de corto plazo en el Peru (Unidad II)
# Fecha de extraccion: la que registre log_ejecucion.txt en cada corrida

"""Etapa 4 - Limpieza, normalizacion y union de las tres fuentes.

Este script tiene dos modos.

MODO_INVENTARIO (primero): recorre los 289 archivos crudos y levanta un censo
    de lo que realmente contienen: que entidades aparecen y en que meses, que
    etiquetas de fila trae cada cuadro, y que archivos no encajan en la
    estructura esperada. No produce datos; produce el informe con el que se
    construye el diccionario de entidades sobre hechos y no sobre suposiciones.

Modo limpieza (despues, con MODO_INVENTARIO = False): lee las cuatro fuentes,
    normaliza los nombres de las entidades y de los tipos de credito con
    entidades.py, une todo por fecha + entidad + tipo, valida y escribe el
    panel. Ninguna de esas equivalencias se supone: todas salen del inventario.

Entradas : datos_crudos/bcrp/*.csv                 tasa de referencia (via 1)
           datos_crudos/sbs_xls/B-2359-*.XLS       saldos por modalidad
           datos_crudos/sbs_xls/B-2362-*.XLS       morosidad por modalidad
           datos_crudos/sbs_xls/B-230803-*.XLS     numero de deudores
           datos_crudos/sbs_tasas/tasas_*.html     tasas por empresa bancaria
Salidas  : salidas/inventario_fuentes.txt          (modo inventario)
           datos_procesados/panel_factoring.csv          (modo limpieza)
           datos_procesados/panel_factoring_agregado.csv (modo limpieza)
           salidas/informe_limpieza.txt                  (modo limpieza)

Los datos crudos no se modifican nunca. Se abren solo para leer, y de cada uno
se recalcula el SHA-256 al leerlo, para encadenar la evidencia con el log de
la extraccion.
"""

from __future__ import annotations

import hashlib
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

# Modulo hermano, en la misma carpeta codigo/. Python agrega por si mismo la
# carpeta del script a la ruta de busqueda, asi que no hace falta tocar nada.
import entidades

# --------------------------------------------------------------------------
# Parametros congelados
# --------------------------------------------------------------------------
MATRICULA = "2024200488G"
ANIO_INICIO = 2018
ANIO_CORTE = 2025

MODO_INVENTARIO = False

# Tipos de credito que entran al panel. Los tres no minoristas concentran el
# 92,3 % del saldo de factoring mas descuentos (verificado en enero de 2025).
TIPOS_INCLUIDOS = ("corporativos", "grandes empresas", "medianas empresas")

# Los mismos tres, con el identificador corto que usa el panel.
TIPOS_INCLUIDOS_ID = ("corporativo", "grandes", "medianas")

# Extension con la que la SBS publica sus cuadros. Es una constante y no un
# literal repetido para poder probar los lectores contra copias convertidas
# sin tocar ninguna otra linea del script.
EXT_XLS = ".XLS"

MESES = (
    ("Enero", "en"), ("Febrero", "fe"), ("Marzo", "ma"), ("Abril", "ab"),
    ("Mayo", "my"), ("Junio", "jn"), ("Julio", "jl"), ("Agosto", "ag"),
    ("Setiembre", "se"), ("Octubre", "oc"), ("Noviembre", "no"), ("Diciembre", "di"),
)

# Cuadros XLS de la SBS: (codigo, de que trata, donde estan las entidades).
#
# Los dos primeros ponen los bancos en COLUMNAS y los conceptos en filas.
# El B-230803 viene transpuesto: un banco por FILA y un tipo de credito por
# columna. Por eso el lector necesita saber la orientacion de cada cuadro;
# aplicar la de uno al otro devolveria los nombres de los bancos como si
# fueran etiquetas de concepto.
CUADROS_XLS = (
    ("B-2359", "Creditos directos por tipo, modalidad y moneda", "columnas"),
    ("B-2362", "Morosidad por tipo de credito y modalidad", "columnas"),
    ("B-230803", "Numero de deudores segun tipo de credito", "filas"),
)

# Modalidades que suma la variable 1. Van juntas porque las entidades no las
# clasifican igual: el BCP registra cero en factoring y montos altos en
# descuentos, para operaciones economicamente equivalentes.
MODALIDADES_VOLUMEN = ("factoring", "descuentos")

# --- Rutas, siempre relativas ---------------------------------------------
RAIZ = Path(__file__).resolve().parent.parent
DIR_BCRP = RAIZ / "datos_crudos" / "bcrp"
DIR_XLS = RAIZ / "datos_crudos" / "sbs_xls"
DIR_TASAS = RAIZ / "datos_crudos" / "sbs_tasas"
DIR_PROCESADOS = RAIZ / "datos_procesados"
DIR_SALIDAS = RAIZ / "salidas"
ARCHIVO_LOG = RAIZ / "log_ejecucion.txt"
ARCHIVO_INVENTARIO = DIR_SALIDAS / "inventario_fuentes.txt"

# Identificadores de la tabla de tasas, leidos del HTML real de la SBS.
# El portal usa un RadPivotGrid de Telerik, que separa en dos tablas las
# etiquetas de fila y los datos; hay que cruzarlas por posicion.
TABLA_DATOS_MN = "ctl00_cphContent_rpgActualMn_ctl00_DataZone_DT"
TABLA_EXTERNA_MN = "ctl00_cphContent_rpgActualMn_OT"


class LecturaFallida(Exception):
    """Un archivo no tiene la forma esperada. Se reporta y no se interpreta."""


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def normalizar(texto: object) -> str:
    """Minusculas, sin tildes y sin espacios repetidos, para comparar."""
    s = "" if texto is None else str(texto)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().lower()


def sha256_archivo(ruta: Path) -> str:
    """SHA-256 del archivo al momento de leerlo, para encadenar la evidencia."""
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def registrar(mensaje: str) -> None:
    """Imprime en consola y agrega la linea a log_ejecucion.txt."""
    marca = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linea = f"[{marca}] 03_limpieza_datos | {mensaje}"
    print(linea, flush=True)
    ARCHIVO_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ARCHIVO_LOG.open("a", encoding="utf-8") as f:
        f.write(linea + "\n")


def meses_del_periodo() -> list[tuple[int, int]]:
    """Los 96 pares (anio, mes) del periodo congelado."""
    return [(a, m) for a in range(ANIO_INICIO, ANIO_CORTE + 1) for m in range(1, 13)]


# --------------------------------------------------------------------------
# Lectura de los cuadros XLS
# --------------------------------------------------------------------------
def leer_xls(ruta: Path) -> pd.DataFrame:
    """Lee el XLS crudo sin interpretar encabezados ni tipos.

    header=None porque estos cuadros traen titulos y filas combinadas arriba:
    dejar que pandas adivine el encabezado desplazaria todo.
    """
    try:
        return pd.read_excel(ruta, sheet_name=0, header=None)
    except Exception as e:  # xlrd ausente, archivo corrupto, hoja vacia
        raise LecturaFallida(f"{ruta.name}: no se pudo abrir ({type(e).__name__}: {e})")


def fila_de_encabezado(df: pd.DataFrame, limite: int = 10) -> int:
    """Devuelve el indice de la fila que lleva los nombres de las entidades.

    Se localiza por contenido y no por numero fijo, para que el parser no se
    rompa si la SBS agrega o quita una linea de titulo en algun mes.

    El criterio son los valores DISTINTOS, no la cantidad de celdas. En el
    B-2359 cada banco ocupa tres columnas rotuladas MN, ME y Total: esa fila
    tiene 57 celdas pero solo 3 valores distintos, mientras que la de los
    nombres tiene 19 celdas y 19 valores distintos. Contando celdas ganaria la
    fila equivocada.
    """
    mejor, mejor_n = -1, 0
    for i in range(min(limite, len(df))):
        valores = {
            normalizar(v) for v in df.iloc[i]
            if isinstance(v, str) and len(v.strip()) > 2 and not v.strip().isdigit()
        }
        if len(valores) > mejor_n:
            mejor, mejor_n = i, len(valores)
    if mejor < 0 or mejor_n < 3:
        raise LecturaFallida("no se encontro la fila con nombres de entidades")
    return mejor


def textos_del_encabezado(df: pd.DataFrame) -> list[tuple[int, str]]:
    """Devuelve [(columna, texto), ...] de la fila de encabezado."""
    i = fila_de_encabezado(df)
    return [
        (c, str(v).strip())
        for c, v in enumerate(df.iloc[i])
        if isinstance(v, str) and v.strip()
    ]


def textos_de_la_primera_columna(df: pd.DataFrame, con_datos: bool = False) -> list[tuple[int, str]]:
    """Devuelve [(fila, texto), ...] de la primera columna, bajo el encabezado.

    Con con_datos=True solo se quedan las filas que llevan algun numero a la
    derecha. Sirve para los cuadros transpuestos, donde la primera columna son
    los bancos y abajo vienen notas al pie que no deben colarse como si lo
    fueran.
    """
    inicio = fila_de_encabezado(df) + 1
    salida = []
    for i in range(inicio, len(df)):
        v = df.iat[i, 0]
        if not (isinstance(v, str) and v.strip()):
            continue
        if con_datos:
            # a_numero y no isinstance(x, float): segun el mes, la SBS guarda
            # las cifras como numero o como texto, y una nota al pie que empieza
            # con "1/" tiene digitos pero no es un numero.
            hay_numero = any(a_numero(x) is not None for x in df.iloc[i, 1:])
            if not hay_numero:
                continue
        salida.append((i, v.strip()))
    return salida


def censar_xls(df: pd.DataFrame, orientacion: str) -> tuple[list[str], list[str]]:
    """Devuelve (entidades, etiquetas) segun donde viva cada cosa en el cuadro."""
    if orientacion == "columnas":
        entidades = [t for _, t in textos_del_encabezado(df)]
        etiquetas = [t for _, t in textos_de_la_primera_columna(df)]
    elif orientacion == "filas":
        entidades = [t for _, t in textos_de_la_primera_columna(df, con_datos=True)]
        etiquetas = [t for _, t in textos_del_encabezado(df)]
    else:
        raise LecturaFallida(f"orientacion desconocida: {orientacion!r}")
    return entidades, etiquetas


# --------------------------------------------------------------------------
# Lectura de los reportes de tasas
# --------------------------------------------------------------------------
def leer_tasas(ruta: Path) -> tuple[list[str], list[str], list[list[str]], str | None]:
    """Extrae del HTML (entidades, etiquetas, datos, fecha declarada).

    El RadPivotGrid reparte la tabla en dos: la externa lleva las etiquetas de
    fila, cada una sola en su propia fila de una celda; la interna lleva la
    cabecera de entidades y los valores. Se cruzan por posicion, asi que la
    cantidad de etiquetas debe coincidir con la de filas de datos.
    """
    html = ruta.read_text(encoding="utf-8", errors="replace")
    sopa = BeautifulSoup(html, "lxml")

    tabla_datos = sopa.find(id=TABLA_DATOS_MN)
    tabla_externa = sopa.find(id=TABLA_EXTERNA_MN)
    if tabla_datos is None or tabla_externa is None:
        raise LecturaFallida(f"{ruta.name}: no se encontro la tabla de moneda nacional")

    filas = tabla_datos.find_all("tr")
    if len(filas) < 2:
        raise LecturaFallida(f"{ruta.name}: la tabla de datos esta vacia")

    entidades = [c.get_text(strip=True) for c in filas[0].find_all(["td", "th"])]
    datos = [
        [c.get_text(strip=True) for c in fila.find_all(["td", "th"])]
        for fila in filas[1:]
    ]

    etiquetas = []
    for fila in tabla_externa.find_all("tr"):
        celdas = fila.find_all(["td", "th"])
        if len(celdas) == 1:
            texto = celdas[0].get_text(" ", strip=True)
            if texto:
                etiquetas.append(texto)

    if len(etiquetas) != len(datos):
        raise LecturaFallida(
            f"{ruta.name}: {len(etiquetas)} etiquetas contra {len(datos)} filas de "
            f"datos; no se pueden cruzar por posicion"
        )

    m = re.search(r"al\s+(\d{2}/\d{2}/\d{4})", html)
    return entidades, etiquetas, datos, (m.group(1) if m else None)


# --------------------------------------------------------------------------
# MODO INVENTARIO
# --------------------------------------------------------------------------
class Censo:
    """Acumula que nombres y etiquetas aparecen, y en que meses."""

    def __init__(self, titulo: str) -> None:
        self.titulo = titulo
        self.entidades: dict[str, list[str]] = defaultdict(list)
        self.etiquetas: dict[str, int] = defaultdict(int)
        self.archivos = 0
        self.anomalias: list[str] = []

    def anotar(self, mes: str, entidades: list[str], etiquetas: list[str]) -> None:
        self.archivos += 1
        for e in entidades:
            self.entidades[e].append(mes)
        for t in etiquetas:
            self.etiquetas[t] += 1

    def informe(self) -> list[str]:
        lineas = [
            "",
            "=" * 78,
            f"{self.titulo}  ({self.archivos} archivos leidos)",
            "=" * 78,
            "",
            f"ENTIDADES DISTINTAS: {len(self.entidades)}",
            f"  {'nombre tal como aparece':48s} {'meses':>6s}  {'desde':>8s} {'hasta':>8s}",
        ]
        for nombre in sorted(self.entidades):
            meses = sorted(self.entidades[nombre])
            lineas.append(
                f"  {nombre[:48]:48s} {len(meses):6d}  {meses[0]:>8s} {meses[-1]:>8s}"
            )

        lineas += ["", f"ETIQUETAS DE FILA DISTINTAS: {len(self.etiquetas)}"]
        for etq in sorted(self.etiquetas):
            lineas.append(f"  {self.etiquetas[etq]:5d} x  {etq[:66]}")

        if self.anomalias:
            lineas += ["", f"ANOMALIAS: {len(self.anomalias)}"]
            lineas += [f"  {a}" for a in self.anomalias]
        else:
            lineas += ["", "ANOMALIAS: ninguna"]
        return lineas


def inventariar() -> int:
    """Recorre los crudos y escribe el informe del que saldra el diccionario."""
    DIR_SALIDAS.mkdir(parents=True, exist_ok=True)

    censos = {cod: Censo(f"{cod} - {desc}") for cod, desc, _ in CUADROS_XLS}
    censos["TASAS"] = Censo("Portal SAEE - Tasa activa por tipo de credito y empresa")
    faltantes: list[str] = []

    for anio, mes in meses_del_periodo():
        etiqueta_mes = f"{anio}-{mes:02d}"
        _, cod = MESES[mes - 1]

        for cuadro, _, orientacion in CUADROS_XLS:
            ruta = DIR_XLS / f"{cuadro}-{cod}{anio}{EXT_XLS}"
            if not ruta.exists():
                faltantes.append(ruta.name)
                continue
            try:
                df = leer_xls(ruta)
                entidades, etiquetas = censar_xls(df, orientacion)
                censos[cuadro].anotar(etiqueta_mes, entidades, etiquetas)
            except LecturaFallida as e:
                censos[cuadro].anomalias.append(str(e))

        ruta = DIR_TASAS / f"tasas_{etiqueta_mes}.html"
        if not ruta.exists():
            faltantes.append(ruta.name)
            continue
        try:
            entidades, etiquetas, datos, declarada = leer_tasas(ruta)
            censos["TASAS"].anotar(etiqueta_mes, entidades, etiquetas)
            if declarada and declarada[3:] != f"{mes:02d}/{anio}":
                censos["TASAS"].anomalias.append(
                    f"{ruta.name}: declara {declarada}, que no es de {etiqueta_mes}"
                )
        except LecturaFallida as e:
            censos["TASAS"].anomalias.append(str(e))

    lineas = [
        "INVENTARIO DE LAS FUENTES CRUDAS",
        f"Generado el {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Periodo {ANIO_INICIO}-01 a {ANIO_CORTE}-12 ({len(meses_del_periodo())} meses)",
    ]
    for censo in censos.values():
        lineas += censo.informe()

    lineas += ["", "=" * 78, f"ARCHIVOS QUE FALTAN: {len(faltantes)}"]
    lineas += [f"  {n}" for n in faltantes[:40]]

    ARCHIVO_INVENTARIO.write_text("\n".join(lineas) + "\n", encoding="utf-8")

    for censo in censos.values():
        registrar(
            f"{censo.titulo[:34]:34s} | {censo.archivos:3d} archivos | "
            f"{len(censo.entidades):3d} entidades | {len(censo.etiquetas):3d} etiquetas | "
            f"{len(censo.anomalias)} anomalias"
        )
    registrar(f"archivos que faltan: {len(faltantes)}")
    registrar(f"informe escrito en {ARCHIVO_INVENTARIO}")
    return 0


# --------------------------------------------------------------------------
# MODO LIMPIEZA - normalizacion de los tipos de credito
# --------------------------------------------------------------------------
# Las cuatro fuentes nombran al mismo tipo de credito de cuatro maneras:
#   B-2359    "Créditos corporativo"        (singular, sin s)
#   B-2362    "Créditos corporativos"       (plural)
#   B-230803  "Deudores Corporativos"       (y "Deudores  Medianas Empresas",
#                                            con dos espacios)
#   Portal    "Corporativos"                (a secas)
# Sin normalizar esto, la union por tipo devolveria cero filas.
RAICES_TIPO = (
    ("corporativ", "corporativo"),
    ("grandes", "grandes"),
    ("medianas", "medianas"),
    ("pequen", "otro"),
    ("micro", "otro"),
    ("consumo", "otro"),
    ("hipotecario", "otro"),
)

# Palabras de relleno que preceden al nucleo del nombre del tipo.
RELLENO_TIPO = r"^(deudores|creditos|credito|de|del|a)\s+"

NOMBRES_TIPO = {
    "corporativo": "Corporativos",
    "grandes": "Grandes empresas",
    "medianas": "Medianas empresas",
}


def encabezado_de_tipo(etiqueta: object) -> str | None:
    """Si la etiqueta encabeza un bloque de tipo de credito, devuelve cual.

    Devuelve el identificador de los tres tipos que entran al panel, "otro"
    para los cuatro que no entran, y None si la etiqueta no encabeza ningun
    bloque (es una modalidad, una nota al pie o un titulo).

    Reconocer tambien los tipos EXCLUIDOS es imprescindible, no un lujo: los
    cuadros repiten la fila "Factoring" una vez por cada tipo. Si el lector no
    se diera cuenta de que empezo el bloque de pequenas empresas, le atribuiria
    ese factoring a medianas empresas, que es el ultimo tipo incluido que vio.
    El error no daria ningun aviso y contaminaria toda la variable.
    """
    s = normalizar(etiqueta)
    if not s or s.startswith("otros"):
        return None
    if s.startswith("total"):
        return "otro"
    previo = None
    while s != previo:
        previo = s
        s = re.sub(RELLENO_TIPO, "", s)
    for raiz, tipo in RAICES_TIPO:
        if s.startswith(raiz):
            return tipo
    return None


def modalidad_de(etiqueta: object) -> str | None:
    """Devuelve "factoring" o "descuentos" si la etiqueta es esa modalidad."""
    s = normalizar(etiqueta)
    if s in ("factoring", "descuentos", "descuento"):
        return "factoring" if s == "factoring" else "descuentos"
    return None


def a_numero(v: object) -> float | None:
    """Convierte la celda en float, o None si es un dato ausente.

    El guion es el dato ausente en los cuadros de porcentajes y en el portal de
    tasas; en los cuadros de saldos y de deudores el vacio no existe y el cero
    es un cero de verdad. Esa diferencia la decide quien llama, no esta funcion.
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return None if pd.isna(v) else float(v)
    s = str(v).strip().replace(" ", "").replace("\xa0", "")
    if s in ("", "-", "--", "n.d.", "nd", "s/i", "*"):
        return None
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def fila_con_texto(df: pd.DataFrame, inicio: str) -> int | None:
    """Indice de la primera fila cuya primera celda empieza con ese texto."""
    for i in range(len(df)):
        if normalizar(df.iat[i, 0]).startswith(inicio):
            return i
    return None


# --------------------------------------------------------------------------
# MODO LIMPIEZA - lectores, uno por fuente
# --------------------------------------------------------------------------
def columnas_por_entidad(df: pd.DataFrame, fila: int) -> dict[str, int]:
    """{entidad: columna} leyendo los nombres de una fila de encabezado.

    Sirve para el B-2362, donde cada banco ocupa una sola columna.
    """
    salida: dict[str, int] = {}
    for c in range(df.shape[1]):
        v = df.iat[fila, c]
        if not (isinstance(v, str) and v.strip()):
            continue
        entidad = entidades.identificar(v)
        if entidad is not None:
            salida[entidad] = c
    return salida


def columnas_totales_2359(df: pd.DataFrame, fila: int) -> dict[str, tuple[int, int, int]]:
    """{entidad: (columna MN, columna ME, columna Total)} del B-2359.

    Este cuadro da a cada banco tres columnas (MN, ME y Total) y escribe su
    nombre solo encima de la primera, en una celda combinada; las otras dos
    llegan vacias. Por eso el nombre se arrastra hacia la derecha hasta que
    aparece el siguiente.

    Se devuelven las tres y no solo la de Total porque con las tres se puede
    comprobar la aritmetica del cuadro: Total tiene que ser igual a MN mas ME
    por el tipo de cambio del mes. Si el lector se hubiera desalineado una
    columna, esa igualdad fallaria, asi que la comprobacion es la prueba de que
    esta leyendo las celdas que cree.
    """
    grupos: dict[str, dict[str, int]] = {}
    actual: str | None = None
    for c in range(df.shape[1]):
        v = df.iat[fila, c]
        if isinstance(v, str) and v.strip():
            actual = entidades.identificar(v)
        if actual is None:
            continue
        moneda = normalizar(df.iat[fila + 1, c])
        for prefijo, clave in (("mn", "mn"), ("me", "me"), ("total", "total")):
            if moneda.startswith(prefijo):
                grupos.setdefault(actual, {})[clave] = c

    salida: dict[str, tuple[int, int, int]] = {}
    for entidad, cols in grupos.items():
        if {"mn", "me", "total"} <= cols.keys():
            salida[entidad] = (cols["mn"], cols["me"], cols["total"])
    return salida


def leer_saldos(ruta: Path) -> tuple[list[dict], float | None]:
    """B-2359: saldo de factoring y de descuentos, por entidad y tipo.

    Devuelve las filas largas y el tipo de cambio declarado del mes.

    Las dos modalidades se leen por separado y se suman despues, en la union.
    Van juntas porque las entidades no las clasifican igual: hay bancos que
    registran cero en factoring y montos altos en descuentos para operaciones
    economicamente equivalentes, de modo que cualquiera de las dos por si sola
    describiria mal el mercado.

    Entra  : la ruta del XLS crudo.
    Sale   : [{entidad, tipo, modalidad, saldo_miles}, ...], el tipo de cambio
             y la lista de descuadres aritmeticos encontrados.
    Falla  : LecturaFallida si no encuentra el encabezado; EntidadDesconocida
             si aparece un banco que el diccionario no contempla.
    """
    df = leer_xls(ruta)
    fila = fila_de_encabezado(df)
    columnas = columnas_totales_2359(df, fila)
    if not columnas:
        raise LecturaFallida(f"{ruta.name}: no se ubicaron columnas Total por entidad")

    i_tc = fila_con_texto(df, "tipo de cambio")
    tc = a_numero(df.iat[i_tc, 1]) if i_tc is not None else None

    filas: list[dict] = []
    descuadres: list[str] = []
    tipo_actual: str | None = None
    for i in range(fila + 2, len(df)):
        etiqueta = df.iat[i, 0]
        if not (isinstance(etiqueta, str) and etiqueta.strip()):
            continue
        cabecera = encabezado_de_tipo(etiqueta)
        if cabecera is not None:
            tipo_actual = cabecera if cabecera in TIPOS_INCLUIDOS_ID else None
            continue
        modalidad = modalidad_de(etiqueta)
        if modalidad is None or tipo_actual is None:
            continue
        for entidad, (c_mn, c_me, c_total) in columnas.items():
            mn = a_numero(df.iat[i, c_mn]) or 0.0
            me = a_numero(df.iat[i, c_me]) or 0.0
            total = a_numero(df.iat[i, c_total]) or 0.0

            # Total = MN + ME x tipo de cambio. Se tolera 1 por mil por el
            # redondeo del propio cuadro, no mas.
            if tc is not None:
                esperado = mn + me * tc
                if abs(total - esperado) > max(1.0, 0.001 * abs(esperado)):
                    descuadres.append(
                        f"{ruta.name}: {entidad}/{tipo_actual}/{modalidad}: "
                        f"total {total:.3f} contra MN+ME*TC {esperado:.3f}"
                    )

            filas.append({
                "entidad": entidad,
                "tipo": tipo_actual,
                "modalidad": modalidad,
                # En este cuadro el vacio no existe: la ausencia de cifra es un
                # cero contable, no un dato que falte.
                "saldo_miles": total,
            })

    return filas, tc, descuadres


def leer_morosidad(ruta: Path) -> list[dict]:
    """B-2362: morosidad del factoring y del tipo de credito, por entidad.

    Se extraen dos cosas de cada bloque:
      - la morosidad de la fila "Factoring", especifica pero muy dispersa:
        la mayoria de bancos la deja en guion porque no tiene cartera atrasada
        en esa modalidad o no la reporta;
      - la morosidad de la fila que encabeza el bloque, que es la del tipo de
        credito completo y esta casi siempre informada.
    Cual de las dos es la variable del articulo es una decision metodologica
    que no toma este script: las escribe en dos columnas y las documenta.

    El guion aqui SI es dato faltante, no cero: un banco sin cartera atrasada
    informa 0,00 y el que no reporta deja guion. Confundirlos hundiria la
    morosidad promedio.
    """
    df = leer_xls(ruta)
    fila = fila_de_encabezado(df)
    columnas = columnas_por_entidad(df, fila)
    if not columnas:
        raise LecturaFallida(f"{ruta.name}: no se ubicaron columnas por entidad")

    filas: list[dict] = []
    tipo_actual: str | None = None
    for i in range(fila + 1, len(df)):
        etiqueta = df.iat[i, 0]
        if not (isinstance(etiqueta, str) and etiqueta.strip()):
            continue
        cabecera = encabezado_de_tipo(etiqueta)
        if cabecera is not None:
            tipo_actual = cabecera if cabecera in TIPOS_INCLUIDOS_ID else None
            if tipo_actual is not None:
                for entidad, c in columnas.items():
                    filas.append({
                        "entidad": entidad,
                        "tipo": tipo_actual,
                        "campo": "morosidad_tipo_pct",
                        "valor": a_numero(df.iat[i, c]),
                    })
            continue
        if tipo_actual is None or modalidad_de(etiqueta) != "factoring":
            continue
        for entidad, c in columnas.items():
            filas.append({
                "entidad": entidad,
                "tipo": tipo_actual,
                "campo": "morosidad_factoring_pct",
                "valor": a_numero(df.iat[i, c]),
            })
    return filas


def leer_deudores(ruta: Path) -> list[dict]:
    """B-230803: numero de deudores por entidad y tipo de credito.

    Este cuadro viene transpuesto respecto de los otros dos: un banco por fila
    y un tipo de credito por columna. De ahi que el lector sea distinto y no
    una reutilizacion del anterior.

    La variable mide tamano del mercado, no monto: dice entre cuantas empresas
    se reparte el credito de cada tipo, que es el denominador natural para
    leer el monto negociado.

    ADVERTENCIA para el analisis: la suma de los deudores de todos los bancos
    NO da el total que declara el cuadro, y no es un error de lectura. En
    febrero de 2025 la suma por banco da 3 590 deudores corporativos y el
    cuadro declara 1 867, porque su nota 1/ consolida: una empresa que debe a
    tres bancos cuenta tres veces en las filas y una sola en el total. Por eso
    esta variable se puede usar por entidad y comparar entre entidades, pero
    nunca sumar entre entidades para hablar del mercado.
    """
    df = leer_xls(ruta)
    fila = fila_de_encabezado(df)

    columnas: dict[str, int] = {}
    for c in range(1, df.shape[1]):
        cabecera = encabezado_de_tipo(df.iat[fila, c])
        if cabecera in TIPOS_INCLUIDOS_ID:
            columnas[cabecera] = c
    if not columnas:
        raise LecturaFallida(f"{ruta.name}: no se ubicaron columnas de tipo de credito")

    filas: list[dict] = []
    for i, texto in textos_de_la_primera_columna(df, con_datos=True):
        entidad = entidades.identificar(texto)
        if entidad is None:
            continue
        for tipo, c in columnas.items():
            valor = a_numero(df.iat[i, c])
            filas.append({
                "entidad": entidad,
                "tipo": tipo,
                "deudores": None if valor is None else int(round(valor)),
            })
    return filas


def leer_tasas_panel(ruta: Path) -> tuple[list[dict], str | None]:
    """Portal SAEE: tasa de descuento y tasa del tipo, por entidad.

    El portal no publica una tasa de "factoring": publica la de "Descuentos",
    que es el precio al que la banca compra documentos por cobrar y por tanto
    el equivalente directo de la tasa de descuento del factoring. Esa es la
    variable; la del encabezado del bloque es la tasa promedio de todo el tipo
    de credito y sirve de referencia para construir el diferencial.

    Se lee la tabla de moneda nacional. La tasa es un precio en soles, y
    mezclarla con la de dolares sumaria dos precios de mercados distintos.
    """
    nombres, etiquetas, datos, declarada = leer_tasas(ruta)

    columnas: dict[str, int] = {}
    for c, nombre in enumerate(nombres):
        entidad = entidades.identificar(nombre)
        if entidad is not None:
            columnas[entidad] = c

    filas: list[dict] = []
    tipo_actual: str | None = None
    for etiqueta, valores in zip(etiquetas, datos):
        cabecera = encabezado_de_tipo(etiqueta)
        if cabecera is not None:
            tipo_actual = cabecera if cabecera in TIPOS_INCLUIDOS_ID else None
            campo = "tasa_tipo_pct"
        elif tipo_actual is not None and modalidad_de(etiqueta) == "descuentos":
            campo = "tasa_descuento_pct"
        else:
            continue
        if tipo_actual is None:
            continue
        for entidad, c in columnas.items():
            if c >= len(valores):
                continue
            filas.append({
                "entidad": entidad,
                "tipo": tipo_actual,
                "campo": campo,
                "valor": a_numero(valores[c]),
            })
    return filas, declarada


MES_BCRP = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


def leer_bcrp() -> dict[str, float]:
    """Via 1: la tasa preferencial corporativa a 90 dias, mes a mes.

    Es la unica variable que no varia entre entidades: es el costo de
    referencia del dinero de corto plazo para el sistema. Entra al panel
    repetida en todas las filas del mismo mes, y por eso en un modelo con
    efectos fijos de entidad actua como variable de tiempo, no de entidad.

    Convierte "Ene.2018" al mes calendario; si el CSV trajera un periodo con
    otro formato, se detiene en vez de adivinar.
    """
    rutas = sorted(DIR_BCRP.glob("PN07809NM_*.csv"))
    rutas = [r for r in rutas if "_previo_" not in r.name]
    if len(rutas) != 1:
        raise LecturaFallida(
            f"se esperaba un unico CSV del BCRP en {DIR_BCRP}, hay {len(rutas)}"
        )
    df = pd.read_csv(rutas[0])
    if list(df.columns) != ["periodo", "valor"]:
        raise LecturaFallida(f"{rutas[0].name}: columnas inesperadas {list(df.columns)}")

    serie: dict[str, float] = {}
    for periodo, valor in zip(df["periodo"], df["valor"]):
        m = re.match(r"([A-Za-z]{3})\.?(\d{4})$", str(periodo).strip())
        if not m:
            raise LecturaFallida(f"{rutas[0].name}: periodo ilegible {periodo!r}")
        mes = MES_BCRP.get(normalizar(m.group(1)))
        if mes is None:
            raise LecturaFallida(f"{rutas[0].name}: mes ilegible {periodo!r}")
        serie[f"{int(m.group(2))}-{mes:02d}"] = float(valor)

    registrar(f"BCRP: {len(serie)} meses desde {rutas[0].name}")
    registrar(f"  sha256 {sha256_archivo(rutas[0])}")
    return serie


# --------------------------------------------------------------------------
# MODO LIMPIEZA - union
# --------------------------------------------------------------------------
def construir_panel() -> pd.DataFrame:
    """Une las cuatro fuentes por fecha + entidad + tipo de credito.

    La llave declarada en la especificacion es fecha + entidad. Se le agrega el
    tipo de credito porque la propia SBS publica todo desagregado asi y porque
    con la llave doble el panel se queda en unas 900 filas, por debajo del
    minimo exigido. El profesor autorizo la desagregacion en la clase del
    19 de noviembre, a condicion de que no altere los resultados; el script
    escribe tambien el panel agregado a fecha + entidad para comprobarlo.

    La union es un outer join deliberado: si una entidad aparece en un cuadro y
    no en otro, la fila se conserva con el dato faltante a la vista. Un inner
    join borraria en silencio a los bancos que una fuente no cubre.
    """
    bcrp = leer_bcrp()
    registros: dict[tuple[str, str, str], dict] = {}
    tipos_cambio: dict[str, float] = {}
    fechas_declaradas: list[str] = []
    incidencias: list[str] = []

    def celda(mes: str, entidad: str, tipo: str) -> dict:
        llave = (mes, entidad, tipo)
        if llave not in registros:
            registros[llave] = {"fecha": mes, "entidad": entidad, "tipo": tipo}
        return registros[llave]

    for anio, mes in meses_del_periodo():
        etiqueta_mes = f"{anio}-{mes:02d}"
        _, cod = MESES[mes - 1]

        # --- B-2359: saldos de factoring y descuentos ---
        ruta = DIR_XLS / f"B-2359-{cod}{anio}{EXT_XLS}"
        if ruta.exists():
            filas, tc, descuadres = leer_saldos(ruta)
            if tc is not None:
                tipos_cambio[etiqueta_mes] = tc
            incidencias.extend(descuadres)
            for f in filas:
                d = celda(etiqueta_mes, f["entidad"], f["tipo"])
                clave = f"saldo_{f['modalidad']}_miles"
                d[clave] = d.get(clave, 0.0) + f["saldo_miles"]
        else:
            incidencias.append(f"falta {ruta.name}")

        # --- B-2362: morosidad ---
        ruta = DIR_XLS / f"B-2362-{cod}{anio}{EXT_XLS}"
        if ruta.exists():
            for f in leer_morosidad(ruta):
                celda(etiqueta_mes, f["entidad"], f["tipo"])[f["campo"]] = f["valor"]
        else:
            incidencias.append(f"falta {ruta.name}")

        # --- B-230803: numero de deudores ---
        ruta = DIR_XLS / f"B-230803-{cod}{anio}{EXT_XLS}"
        if ruta.exists():
            for f in leer_deudores(ruta):
                celda(etiqueta_mes, f["entidad"], f["tipo"])["deudores"] = f["deudores"]
        else:
            incidencias.append(f"falta {ruta.name}")

        # --- Portal SAEE: tasas ---
        ruta = DIR_TASAS / f"tasas_{etiqueta_mes}.html"
        if ruta.exists():
            filas, declarada = leer_tasas_panel(ruta)
            if declarada:
                fechas_declaradas.append(f"{etiqueta_mes} -> {declarada}")
                if declarada[3:] != f"{mes:02d}/{anio}":
                    incidencias.append(
                        f"{ruta.name}: declara {declarada}, que no es de {etiqueta_mes}"
                    )
            for f in filas:
                celda(etiqueta_mes, f["entidad"], f["tipo"])[f["campo"]] = f["valor"]
        else:
            incidencias.append(f"falta {ruta.name}")

    if not registros:
        raise LecturaFallida("la union no produjo ninguna fila")

    df = pd.DataFrame(list(registros.values()))
    df["tipo_cambio"] = df["fecha"].map(tipos_cambio)
    df["tasa_referencia_pct"] = df["fecha"].map(bcrp)

    # Variable 1: el monto negociado es la suma de las dos modalidades.
    for c in ("saldo_factoring_miles", "saldo_descuentos_miles"):
        if c not in df.columns:
            df[c] = 0.0
        df[c] = df[c].fillna(0.0)
    df["monto_negociado_miles"] = (
        df["saldo_factoring_miles"] + df["saldo_descuentos_miles"]
    )
    df["opera_factoring"] = (df["monto_negociado_miles"] > 0).astype(int)

    df["entidad_nombre"] = df["entidad"].map(entidades.nombre_legible)
    df["tipo_nombre"] = df["tipo"].map(NOMBRES_TIPO)

    columnas = [
        "fecha", "entidad", "entidad_nombre", "tipo", "tipo_nombre",
        "monto_negociado_miles", "saldo_factoring_miles", "saldo_descuentos_miles",
        "tasa_descuento_pct", "deudores", "morosidad_factoring_pct",
        "tasa_referencia_pct",
        "tasa_tipo_pct", "morosidad_tipo_pct", "tipo_cambio", "opera_factoring",
    ]
    for c in columnas:
        if c not in df.columns:
            df[c] = pd.NA
    df = df[columnas].sort_values(["fecha", "entidad", "tipo"]).reset_index(drop=True)

    for linea in incidencias[:20]:
        registrar(f"  incidencia: {linea}")
    if len(incidencias) > 20:
        registrar(f"  ... y {len(incidencias) - 20} incidencias mas")
    registrar(f"union: {len(df)} filas, {df['entidad'].nunique()} entidades")
    return df


def validar(df: pd.DataFrame) -> list[str]:
    """Comprueba el panel y devuelve los problemas encontrados.

    Son comprobaciones que podrian fallar: si ninguna falla nunca, no estan
    comprobando nada.
    """
    problemas: list[str] = []

    meses = sorted(df["fecha"].unique())
    esperados = [f"{a}-{m:02d}" for a, m in meses_del_periodo()]
    if meses != esperados:
        problemas.append(
            f"cobertura: {len(meses)} meses en el panel contra {len(esperados)} "
            f"esperados (faltan {sorted(set(esperados) - set(meses))[:6]})"
        )

    if len(df) < 1200:
        problemas.append(f"tamano: {len(df)} filas, por debajo del minimo de 1200")

    duplicadas = df.duplicated(["fecha", "entidad", "tipo"]).sum()
    if duplicadas:
        problemas.append(f"llave: {duplicadas} filas repiten fecha+entidad+tipo")

    tc = df.dropna(subset=["tipo_cambio"])["tipo_cambio"]
    if not tc.empty and not (2.5 <= tc.min() and tc.max() <= 4.5):
        problemas.append(f"tipo de cambio fuera de rango: {tc.min()} a {tc.max()}")

    for columna, bajo, alto in (
        ("tasa_descuento_pct", 0, 60),
        ("tasa_tipo_pct", 0, 60),
        ("morosidad_factoring_pct", 0, 100),
        ("morosidad_tipo_pct", 0, 100),
    ):
        s = pd.to_numeric(df[columna], errors="coerce").dropna()
        if not s.empty and (s.min() < bajo or s.max() > alto):
            problemas.append(
                f"{columna} fuera de rango plausible: {s.min():.2f} a {s.max():.2f}"
            )

    negativos = (pd.to_numeric(df["monto_negociado_miles"], errors="coerce") < 0).sum()
    if negativos:
        problemas.append(f"monto negociado negativo en {negativos} filas")

    ref = df.dropna(subset=["tasa_referencia_pct"])
    if ref.empty:
        problemas.append("ninguna fila quedo con la tasa de referencia del BCRP")
    elif ref["fecha"].nunique() != len(esperados):
        problemas.append(
            f"la tasa del BCRP solo cubre {ref['fecha'].nunique()} de "
            f"{len(esperados)} meses"
        )

    return problemas


def resumen(df: pd.DataFrame) -> list[str]:
    """Las lineas de cobertura que van al informe y al log."""
    lineas = [
        f"filas del panel desagregado        : {len(df)}",
        f"meses                              : {df['fecha'].nunique()}",
        f"entidades                          : {df['entidad'].nunique()}",
        f"tipos de credito                   : {df['tipo'].nunique()}",
        f"filas con monto negociado > 0      : {int(df['opera_factoring'].sum())}",
        "",
        "completitud de cada variable (filas con dato / total):",
    ]
    for c in (
        "monto_negociado_miles", "tasa_descuento_pct", "deudores",
        "morosidad_factoring_pct", "tasa_referencia_pct",
        "tasa_tipo_pct", "morosidad_tipo_pct",
    ):
        n = pd.to_numeric(df[c], errors="coerce").notna().sum()
        lineas.append(f"  {c:28s} {n:6d} / {len(df):6d}  ({100 * n / len(df):5.1f} %)")
    return lineas


def agregar(df: pd.DataFrame) -> pd.DataFrame:
    """Colapsa el panel a la llave original fecha + entidad.

    Los montos y los deudores se suman; las tasas y la morosidad se promedian
    ponderando por el monto negociado, porque un promedio simple le daria el
    mismo peso a un banco con mil soles de factoring que a uno con mil millones.

    Este panel no es el del analisis: existe para comprobar que la
    desagregacion por tipo de credito no cambia la historia que cuentan los
    datos, que es la condicion que puso el profesor al autorizarla.
    """
    def ponderado(sub: pd.DataFrame, columna: str) -> float | None:
        v = pd.to_numeric(sub[columna], errors="coerce")
        w = pd.to_numeric(sub["monto_negociado_miles"], errors="coerce")
        valido = v.notna() & w.notna() & (w > 0)
        if not valido.any():
            return None
        return float((v[valido] * w[valido]).sum() / w[valido].sum())

    filas = []
    for (fecha, entidad), sub in df.groupby(["fecha", "entidad"], sort=True):
        filas.append({
            "fecha": fecha,
            "entidad": entidad,
            "entidad_nombre": sub["entidad_nombre"].iloc[0],
            "monto_negociado_miles": pd.to_numeric(
                sub["monto_negociado_miles"], errors="coerce").sum(),
            "deudores": pd.to_numeric(sub["deudores"], errors="coerce").sum(
                min_count=1),
            "tasa_descuento_pct": ponderado(sub, "tasa_descuento_pct"),
            "morosidad_factoring_pct": ponderado(sub, "morosidad_factoring_pct"),
            "morosidad_tipo_pct": ponderado(sub, "morosidad_tipo_pct"),
            "tasa_referencia_pct": sub["tasa_referencia_pct"].iloc[0],
        })
    return pd.DataFrame(filas)


def limpiar() -> int:
    """Lee los crudos, construye el panel, lo valida y lo escribe."""
    DIR_PROCESADOS.mkdir(parents=True, exist_ok=True)
    DIR_SALIDAS.mkdir(parents=True, exist_ok=True)

    df = construir_panel()
    problemas = validar(df)

    for linea in resumen(df):
        registrar(linea)

    if problemas:
        registrar(f"VALIDACION: {len(problemas)} problemas")
        for p in problemas:
            registrar(f"  - {p}")
    else:
        registrar("VALIDACION: sin problemas")

    salida = DIR_PROCESADOS / "panel_factoring.csv"
    df.to_csv(salida, index=False, encoding="utf-8", lineterminator="\n")
    registrar(f"escrito {salida.name}: {len(df)} filas")
    registrar(f"  sha256 {sha256_archivo(salida)}")

    agregado = agregar(df)
    salida_ag = DIR_PROCESADOS / "panel_factoring_agregado.csv"
    agregado.to_csv(salida_ag, index=False, encoding="utf-8", lineterminator="\n")
    registrar(f"escrito {salida_ag.name}: {len(agregado)} filas")
    registrar(f"  sha256 {sha256_archivo(salida_ag)}")

    informe = DIR_SALIDAS / "informe_limpieza.txt"
    lineas = [
        "INFORME DE LIMPIEZA Y UNION",
        f"Generado el {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Periodo {ANIO_INICIO}-01 a {ANIO_CORTE}-12",
        "",
    ] + resumen(df) + [
        "",
        f"PROBLEMAS DE VALIDACION: {len(problemas)}",
    ] + [f"  - {p}" for p in problemas] + [
        "",
        "ENTIDADES Y MESES CON DATO",
    ]
    for entidad, sub in df.groupby("entidad"):
        con_monto = sub[sub["opera_factoring"] == 1]
        lineas.append(
            f"  {entidades.nombre_legible(entidad)[:42]:42s} "
            f"{sub['fecha'].nunique():3d} meses  "
            f"{con_monto['fecha'].nunique():3d} con monto > 0"
        )
    informe.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    registrar(f"informe escrito en {informe}")

    return 1 if problemas else 0


# --------------------------------------------------------------------------
# Orquestacion
# --------------------------------------------------------------------------
def main() -> int:
    registrar("inicio")
    try:
        if MODO_INVENTARIO:
            return inventariar()
        return limpiar()
    except (LecturaFallida, entidades.EntidadDesconocida) as e:
        registrar(f"ABORTADO: {e}")
        return 1
    finally:
        registrar("fin")


if __name__ == "__main__":
    sys.exit(main())
