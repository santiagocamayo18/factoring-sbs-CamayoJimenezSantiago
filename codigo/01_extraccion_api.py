# Santiago Piero Camayo Jimenez
# 2024200488G
# Tema N.o 91 - El factoring como instrumento de financiamiento de corto plazo en el Peru (Unidad II)
# Fecha de extraccion: la que registre log_ejecucion.txt en cada corrida

"""Via 1 - Extraccion por API REST de BCRPData.

Descarga la serie mensual de la tasa activa preferencial corporativa a 90 dias
en moneda nacional, que sirve de costo de referencia de corto plazo frente a la
tasa de descuento del factoring.

Entradas : ninguna. Todos los parametros estan congelados como constantes.
Salidas  : datos_crudos/bcrp/<serie>_<periodo>_<matricula>.json  (crudo tal cual)
           datos_crudos/bcrp/<serie>_<periodo>_<matricula>.csv   (sin convertir)
           log_ejecucion.txt  (fecha, endpoint, codigo HTTP, filas, hashes)

El script no guarda nada si falla una validacion critica.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import requests

# --------------------------------------------------------------------------
# Parametros congelados. Nunca usar datetime.today() ni "la ultima observacion".
# --------------------------------------------------------------------------
MATRICULA = "2024200488G"

SERIE = "PN07809NM"
FECHA_INICIO = "2018-1"
FECHA_CORTE = "2025-12"
N_PERIODOS_ESPERADOS = 96

# Control de identidad de la serie. PN07829NM tiene el mismo nombre corto pero
# pertenece al cuadro en moneda extranjera: estas palabras lo separan.
#
# La corrida del 2026-11-24 mostro que el nombre completo que devuelve la API es
#   "Tasas de interes activas y pasivas promedio de las empresas bancarias en MN
#    (terminos efectivos anuales) - Activas - Preferencial Corporativa a 90 dias"
# El cuadro gemelo dice "en ME", no "extranjera", asi que la moneda se verifica
# exigiendo "en mn" y no confiando en la lista de palabras prohibidas.
PALABRAS_OBLIGATORIAS = ("preferencial", "corporativa", "90", "en mn")
PALABRAS_PROHIBIDAS = ("en me", "extranjera", "dolares")

URL_BASE = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"
CABECERAS = {
    "User-Agent": (
        "Mozilla/5.0 (proyecto academico UNCP, Finanzas I 055D; "
        "e_2024200488G@uncp.edu.pe)"
    ),
    "Accept": "application/json",
}

TIEMPO_ESPERA = 30          # segundos antes de abandonar una solicitud
REINTENTOS = 3              # intentos ante fallos de conexion
PAUSA_BASE = 2              # segundos; se duplica en cada reintento

# Rutas siempre relativas al propio archivo, nunca absolutas.
RAIZ = Path(__file__).resolve().parent.parent
DIR_CRUDOS = RAIZ / "datos_crudos" / "bcrp"
ARCHIVO_LOG = RAIZ / "log_ejecucion.txt"


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def normalizar(texto: str) -> str:
    """Pasa a minusculas y quita tildes, para comparar nombres sin sorpresas."""
    sin_tildes = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return sin_tildes.lower()


def sha256(ruta: Path) -> str:
    """Devuelve el SHA-256 del archivo, leido en bloques."""
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def registrar(mensaje: str) -> None:
    """Imprime en consola y agrega la linea a log_ejecucion.txt."""
    marca = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linea = f"[{marca}] 01_extraccion_api | {mensaje}"
    print(linea)
    ARCHIVO_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ARCHIVO_LOG.open("a", encoding="utf-8") as f:
        f.write(linea + "\n")


def respaldar(ruta: Path) -> None:
    """Renombra el archivo anterior en vez de sobrescribirlo."""
    if ruta.exists():
        marca = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = ruta.with_name(f"{ruta.stem}_previo_{marca}{ruta.suffix}")
        ruta.rename(destino)
        registrar(f"respaldo: {ruta.name} -> {destino.name}")


class ValidacionFallida(Exception):
    """Se levanta cuando algo no cuadra y por eso no se debe guardar nada."""


# --------------------------------------------------------------------------
# 1. Descarga
# --------------------------------------------------------------------------
def construir_url() -> str:
    """Arma el endpoint con los parametros congelados."""
    return f"{URL_BASE}/{SERIE}/json/{FECHA_INICIO}/{FECHA_CORTE}"


def descargar(url: str) -> tuple[bytes, int]:
    """Pide el JSON a la API y devuelve (bytes crudos, codigo HTTP).

    Reintenta ante fallos de conexion con espera creciente. No reintenta ante
    un codigo HTTP de error: ese caso se decide arriba.
    """
    ultimo_error: Exception | None = None
    for intento in range(1, REINTENTOS + 1):
        try:
            r = requests.get(url, headers=CABECERAS, timeout=TIEMPO_ESPERA)
            registrar(f"GET {url} -> HTTP {r.status_code} ({len(r.content)} bytes)")
            return r.content, r.status_code
        except requests.exceptions.RequestException as e:
            ultimo_error = e
            espera = PAUSA_BASE * (2 ** (intento - 1))
            registrar(
                f"intento {intento}/{REINTENTOS} fallo ({type(e).__name__}); "
                f"reintento en {espera}s"
            )
            if intento < REINTENTOS:
                time.sleep(espera)
    raise ValidacionFallida(
        f"no se pudo contactar la API tras {REINTENTOS} intentos: {ultimo_error}"
    )


# --------------------------------------------------------------------------
# 2. Validacion de la respuesta (antes de guardar nada)
# --------------------------------------------------------------------------
def nombres_de_series(payload: dict) -> list[str]:
    """Extrae los nombres de las series que declara la respuesta.

    La API los publica dentro de 'config'. Si la estructura cambiara, se
    levanta ValidacionFallida con las claves que llegaron, en vez de suponer.
    """
    config = payload.get("config")
    if not isinstance(config, dict):
        raise ValidacionFallida(
            f"la respuesta no trae 'config'; claves recibidas: {sorted(payload)}"
        )

    series = config.get("series")
    if not isinstance(series, list) or not series:
        raise ValidacionFallida(
            f"'config' no trae la lista 'series'; claves de config: {sorted(config)}"
        )

    nombres = []
    for item in series:
        if isinstance(item, dict) and "name" in item:
            nombres.append(str(item["name"]))
        elif isinstance(item, str):
            nombres.append(item)
        else:
            raise ValidacionFallida(f"elemento de 'series' inesperado: {item!r}")
    return nombres


def verificar_identidad(nombres: list[str]) -> str:
    """Comprueba que la serie recibida sea la que se pidio, por su nombre.

    Este es el control que evita el error de la Unidad I: tomar una serie
    parecida. Aqui separa la version en moneda nacional de la de moneda
    extranjera, que comparte nombre corto.
    """
    if len(nombres) != 1:
        raise ValidacionFallida(
            f"se esperaba 1 serie y llegaron {len(nombres)}: {nombres}"
        )

    nombre = nombres[0]
    plano = normalizar(nombre)

    faltantes = [p for p in PALABRAS_OBLIGATORIAS if p not in plano]
    if faltantes:
        raise ValidacionFallida(
            f"el nombre de la serie no contiene {faltantes}. "
            f"Nombre recibido: {nombre!r}. Revisar el codigo {SERIE}."
        )

    prohibidas = [p for p in PALABRAS_PROHIBIDAS if p in plano]
    if prohibidas:
        raise ValidacionFallida(
            f"el nombre de la serie contiene {prohibidas}, lo que sugiere moneda "
            f"extranjera. Nombre recibido: {nombre!r}."
        )

    return nombre


def extraer_periodos(payload: dict) -> list[tuple[str, str]]:
    """Devuelve [(periodo, valor_como_texto), ...] sin convertir a numero.

    El crudo se guarda tal como llega: la conversion es trabajo de
    03_limpieza_datos.py.
    """
    periodos = payload.get("periods")
    if not isinstance(periodos, list) or not periodos:
        raise ValidacionFallida(
            f"la respuesta no trae 'periods'; claves recibidas: {sorted(payload)}"
        )

    filas: list[tuple[str, str]] = []
    for p in periodos:
        if not isinstance(p, dict) or "name" not in p or "values" not in p:
            raise ValidacionFallida(f"periodo con forma inesperada: {p!r}")
        valores = p["values"]
        if not isinstance(valores, list) or len(valores) != 1:
            raise ValidacionFallida(
                f"el periodo {p['name']!r} trae {len(valores)} valores y se "
                f"esperaba 1"
            )
        filas.append((str(p["name"]), str(valores[0])))
    return filas


def verificar_cobertura(filas: list[tuple[str, str]]) -> None:
    """Comprueba el numero de periodos, que no haya duplicados y los extremos."""
    if len(filas) != N_PERIODOS_ESPERADOS:
        raise ValidacionFallida(
            f"llegaron {len(filas)} periodos y se esperaban "
            f"{N_PERIODOS_ESPERADOS} (2018-01 a 2025-12)"
        )

    nombres = [f[0] for f in filas]
    if len(set(nombres)) != len(nombres):
        repetidos = sorted({n for n in nombres if nombres.count(n) > 1})
        raise ValidacionFallida(f"periodos duplicados: {repetidos}")

    if "2018" not in nombres[0]:
        raise ValidacionFallida(f"el primer periodo no es de 2018: {nombres[0]!r}")
    if "2025" not in nombres[-1]:
        raise ValidacionFallida(f"el ultimo periodo no es de 2025: {nombres[-1]!r}")

    sin_dato = [n for n, v in filas if not v.replace(".", "", 1).replace("-", "", 1).isdigit()]
    if sin_dato:
        registrar(f"aviso: {len(sin_dato)} periodos sin valor numerico: {sin_dato}")


# --------------------------------------------------------------------------
# 3. Guardado
# --------------------------------------------------------------------------
def guardar_crudos(contenido: bytes, filas: list[tuple[str, str]]) -> dict[str, str]:
    """Guarda el JSON original y el CSV derivado. Devuelve {archivo: hash}."""
    DIR_CRUDOS.mkdir(parents=True, exist_ok=True)
    base = f"{SERIE}_2018-2025_{MATRICULA}"

    ruta_json = DIR_CRUDOS / f"{base}.json"
    respaldar(ruta_json)
    ruta_json.write_bytes(contenido)

    ruta_csv = DIR_CRUDOS / f"{base}.csv"
    respaldar(ruta_csv)
    # lineterminator fijo: asi el hash no depende del sistema operativo.
    with ruta_csv.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f, lineterminator="\n")
        escritor.writerow(["periodo", "valor"])
        escritor.writerows(filas)

    return {ruta_json.name: sha256(ruta_json), ruta_csv.name: sha256(ruta_csv)}


# --------------------------------------------------------------------------
# Orquestacion
# --------------------------------------------------------------------------
def main() -> int:
    registrar("inicio")
    url = construir_url()

    try:
        contenido, estado = descargar(url)

        if estado != 200:
            raise ValidacionFallida(f"la API respondio HTTP {estado}, se esperaba 200")

        try:
            payload = json.loads(contenido)
        except json.JSONDecodeError as e:
            raise ValidacionFallida(f"la respuesta no es JSON valido: {e}") from e

        nombre = verificar_identidad(nombres_de_series(payload))
        registrar(f"serie verificada: {nombre!r}")

        filas = extraer_periodos(payload)
        verificar_cobertura(filas)
        registrar(f"periodos validados: {len(filas)} ({filas[0][0]} a {filas[-1][0]})")

        hashes = guardar_crudos(contenido, filas)
        for archivo, h in hashes.items():
            registrar(f"guardado {archivo} | SHA-256 {h}")

    except ValidacionFallida as e:
        registrar(f"ABORTADO sin guardar nada: {e}")
        return 1

    registrar("fin correcto")
    return 0


if __name__ == "__main__":
    sys.exit(main())
