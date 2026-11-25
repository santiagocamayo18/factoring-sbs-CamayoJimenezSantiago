# Santiago Piero Camayo Jimenez
# 2024200488G
# Tema N.o 91 - El factoring como instrumento de financiamiento de corto plazo en el Peru (Unidad II)
# Fecha de extraccion: la que registre log_ejecucion.txt en cada corrida

"""Via 2 - Extraccion desde la SBS por dos mecanismos distintos.

Via 2a, descarga programatica: 192 archivos XLS del boletin de banca multiple
        (cuadros B-2359, saldos por modalidad, y B-2362, morosidad por modalidad)
        desde URL directas con patron conocido.

Via 2b, scraping de formulario: 96 consultas al portal SAEE, que entrega la tasa
        activa por tipo de credito y empresa bancaria. La pagina es un formulario
        ASP.NET, asi que hay que mantener sesion, reenviar los campos ocultos y
        parsear la tabla HTML del resultado.

Entradas : ninguna. Todos los parametros estan congelados como constantes.
Salidas  : datos_crudos/sbs_xls/<cuadro>-<mm><aaaa>.XLS       hasta 192 archivos
           datos_crudos/sbs_tasas/tasas_<aaaa>-<mm>.html      hasta  96 archivos
           log_ejecucion.txt

robots.txt verificado el 2026-11-25:
  www.sbs.gob.pe      -> el bloque "User-agent: *" no prohibe /app/pp/, sin Crawl-delay
  intranet2.sbs.gob.pe -> HTTP 404, no declara restricciones

Un archivo que ya existe no se vuelve a pedir. Un archivo que no pasa sus
validaciones no se guarda.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------
# Parametros congelados
# --------------------------------------------------------------------------
MATRICULA = "2024200488G"

ANIO_INICIO = 2018
ANIO_CORTE = 2025

# --- Interruptores de ejecucion -------------------------------------------
# MODO_DIAGNOSTICO: no descarga nada; solo abre el formulario de tasas y
#   muestra sus campos. Sirve si el descubrimiento automatico falla.
MODO_DIAGNOSTICO = False
# MODO_PRUEBA: baja solo los tres primeros meses de ANIO_DESDE, para comprobar
#   que todo funciona antes de soltar la corrida completa.
MODO_PRUEBA = True
# Tramos: permite correr año por año en vez de los ocho de una vez.
ANIO_DESDE = 2018
ANIO_HASTA = 2025
# Partes a ejecutar
HACER_XLS = True
HACER_TASAS = True

# --- Via 2a ---------------------------------------------------------------
URL_XLS = "https://intranet2.sbs.gob.pe/estadistica/financiera/{anio}/{carpeta}/{cuadro}-{cod}{anio}.XLS"
CUADROS = ("B-2359", "B-2362")

# Carpeta y codigo de cada mes, verificados contra enlaces reales del portal.
# Setiembre va sin "p", tanto en la carpeta como en el codigo.
MESES = (
    ("Enero", "en"), ("Febrero", "fe"), ("Marzo", "ma"), ("Abril", "ab"),
    ("Mayo", "my"), ("Junio", "jn"), ("Julio", "jl"), ("Agosto", "ag"),
    ("Setiembre", "se"), ("Octubre", "oc"), ("Noviembre", "no"), ("Diciembre", "di"),
)

# Firma de un archivo Excel 97-2003 (OLE2). Si el servidor devuelve una pagina
# de error con codigo 200, estos bytes no estaran y el archivo no se guarda.
FIRMA_XLS = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
TAMANIO_MINIMO_XLS = 10_000

# --- Via 2b ---------------------------------------------------------------
URL_TASAS = (
    "https://www.sbs.gob.pe/app/pp/EstadisticasSAEEPortal/Paginas/"
    "TIActivaTipoCreditoEmpresa.aspx?tip=B"
)
# El dato es un promedio de los ultimos 30 dias utiles terminados en la fecha
# consultada. La regla congelada es tomar el ultimo dia con datos de cada mes:
# se prueba el ultimo dia del mes y se retrocede hasta encontrar respuesta.
DIAS_RETROCESO = 10
TEXTO_OBLIGATORIO = "Descuentos"

# --- Cortesia con el servidor ---------------------------------------------
PAUSA = 1.5            # segundos entre solicitudes; el minimo exigido es 1
TIEMPO_ESPERA = 60
REINTENTOS = 3
PAUSA_REINTENTO = 3    # se duplica en cada reintento

CABECERAS = {
    "User-Agent": (
        "Mozilla/5.0 (proyecto academico UNCP, Finanzas I 055D; "
        "e_2024200488G@uncp.edu.pe)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/vnd.ms-excel,*/*",
    "Accept-Language": "es-PE,es;q=0.9",
}

# --- Rutas, siempre relativas ---------------------------------------------
RAIZ = Path(__file__).resolve().parent.parent
DIR_XLS = RAIZ / "datos_crudos" / "sbs_xls"
DIR_TASAS = RAIZ / "datos_crudos" / "sbs_tasas"
ARCHIVO_LOG = RAIZ / "log_ejecucion.txt"


class ValidacionFallida(Exception):
    """Algo no cuadra: no se guarda el archivo de esta iteracion.

    Es recuperable: puede que ese dia no haya reporte y el siguiente si.
    """


class ErrorEstructural(ValidacionFallida):
    """La pagina no tiene la forma que el script espera.

    No depende de la fecha pedida, asi que reintentar con otro dia solo
    desperdicia solicitudes. Detiene la via de inmediato.
    """


class FechaNoObedecida(ValidacionFallida):
    """El formulario respondio, pero con un mes distinto al pedido.

    Probar otro dia del mismo mes tampoco funcionaria, asi que se abandona el
    mes al primer intento. Si ocurre en varios meses seguidos, el problema es
    del envio y no de la fecha: entonces se detiene la via.
    """


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def registrar(mensaje: str) -> None:
    """Imprime en consola y agrega la linea a log_ejecucion.txt."""
    marca = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linea = f"[{marca}] 02_scraping_web | {mensaje}"
    print(linea, flush=True)
    ARCHIVO_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ARCHIVO_LOG.open("a", encoding="utf-8") as f:
        f.write(linea + "\n")


def sha256_bytes(contenido: bytes) -> str:
    """SHA-256 de lo que se acaba de descargar, antes de escribirlo."""
    return hashlib.sha256(contenido).hexdigest()


def meses_a_recorrer() -> list[tuple[int, int]]:
    """Devuelve [(anio, mes_1a12), ...] segun los interruptores de ejecucion."""
    pares: list[tuple[int, int]] = []
    for anio in range(max(ANIO_DESDE, ANIO_INICIO), min(ANIO_HASTA, ANIO_CORTE) + 1):
        for mes in range(1, 13):
            pares.append((anio, mes))
    if MODO_PRUEBA:
        pares = pares[:3]
    return pares


def pedir(sesion: requests.Session, metodo: str, url: str, **kwargs) -> requests.Response:
    """Solicitud con reintentos y espera creciente ante fallos de conexion.

    No reintenta ante un codigo HTTP de error: eso no se arregla insistiendo.
    """
    ultimo: Exception | None = None
    for intento in range(1, REINTENTOS + 1):
        try:
            return sesion.request(metodo, url, timeout=TIEMPO_ESPERA, **kwargs)
        except requests.exceptions.RequestException as e:
            ultimo = e
            espera = PAUSA_REINTENTO * (2 ** (intento - 1))
            registrar(
                f"  intento {intento}/{REINTENTOS} fallo ({type(e).__name__}); "
                f"reintento en {espera}s"
            )
            if intento < REINTENTOS:
                time.sleep(espera)
    raise ValidacionFallida(f"sin respuesta tras {REINTENTOS} intentos: {ultimo}")


# ==========================================================================
# VIA 2a - Descarga programatica de los cuadros XLS
# ==========================================================================
def url_del_cuadro(cuadro: str, anio: int, mes: int) -> str:
    """Arma la URL de un cuadro para un mes concreto."""
    carpeta, cod = MESES[mes - 1]
    return URL_XLS.format(anio=anio, carpeta=carpeta, cuadro=cuadro, cod=cod)


def validar_xls(contenido: bytes, url: str) -> None:
    """Comprueba que lo descargado sea de verdad un Excel 97-2003."""
    if len(contenido) < TAMANIO_MINIMO_XLS:
        raise ValidacionFallida(
            f"archivo demasiado pequenio ({len(contenido)} bytes): {url}"
        )
    if not contenido.startswith(FIRMA_XLS):
        raise ValidacionFallida(
            f"los primeros bytes no son los de un XLS; probablemente sea una "
            f"pagina de error devuelta con codigo 200: {url}"
        )


def descargar_cuadros(sesion: requests.Session) -> tuple[int, int, int]:
    """Descarga los XLS de los meses pedidos.

    Devuelve (guardados, omitidos_por_existir, fallidos).
    """
    DIR_XLS.mkdir(parents=True, exist_ok=True)
    guardados = omitidos = fallidos = 0

    for anio, mes in meses_a_recorrer():
        for cuadro in CUADROS:
            carpeta, cod = MESES[mes - 1]
            destino = DIR_XLS / f"{cuadro}-{cod}{anio}.XLS"

            if destino.exists():
                omitidos += 1
                continue

            url = url_del_cuadro(cuadro, anio, mes)
            try:
                r = pedir(sesion, "GET", url)
                if r.status_code != 200:
                    raise ValidacionFallida(f"HTTP {r.status_code} en {url}")
                validar_xls(r.content, url)

                destino.write_bytes(r.content)
                registrar(
                    f"{destino.name} | HTTP 200 | {len(r.content)} bytes | "
                    f"SHA-256 {sha256_bytes(r.content)}"
                )
                guardados += 1
            except ValidacionFallida as e:
                registrar(f"FALLO {destino.name}: {e}")
                fallidos += 1

            time.sleep(PAUSA)

    return guardados, omitidos, fallidos


# ==========================================================================
# VIA 2b - Scraping del formulario de tasas
# ==========================================================================
def campos_del_formulario(html: str) -> dict[str, str]:
    """Devuelve todos los campos ocultos del formulario ASP.NET.

    Son __VIEWSTATE, __EVENTVALIDATION y companiia. Hay que reenviarlos tal
    cual o el servidor rechaza la consulta.
    """
    sopa = BeautifulSoup(html, "lxml")
    campos = {}
    for inp in sopa.find_all("input", attrs={"type": "hidden"}):
        nombre = inp.get("name")
        if nombre:
            campos[nombre] = inp.get("value", "")
    return campos


def localizar_campos_fecha(html: str) -> tuple[str, str]:
    """Devuelve los dos campos del selector de fecha: (iso, visible).

    El portal usa un RadDatePicker de Telerik, que publica DOS cajas de texto
    que deben ir de acuerdo entre si:
        ctl00$cphContent$rdpDate            -> 2026-11-24   (la que lee el servidor)
        ctl00$cphContent$rdpDate$dateInput  -> 24/11/2026   (la que ve la persona)
    Enviar solo una deja al componente con la fecha anterior.

    El nombre no contiene la palabra "fecha" (rdp = RadDatePicker), asi que la
    deteccion se hace por la terminacion "$dateInput", que es estable en el
    componente, y no por el nombre del control, que el programador elige.
    """
    sopa = BeautifulSoup(html, "lxml")

    for inp in sopa.find_all("input"):
        nombre = inp.get("name", "")
        if nombre.endswith("$dateInput"):
            return nombre[: -len("$dateInput")], nombre

    # Respaldo: un campo de texto corriente que mencione la fecha.
    for inp in sopa.find_all("input"):
        if (inp.get("type") or "text").lower() not in ("text", "search"):
            continue
        etiqueta = f"{inp.get('name', '')} {inp.get('id', '')}".lower()
        if "fecha" in etiqueta or "date" in etiqueta:
            return inp["name"], ""

    raise ErrorEstructural(
        "no se encontro la caja de texto de la fecha. "
        "Poner MODO_DIAGNOSTICO = True y enviar la salida."
    )


def nombre_boton_consultar(html: str) -> str:
    """Descubre como se llama el boton Consultar."""
    sopa = BeautifulSoup(html, "lxml")
    for inp in sopa.find_all("input"):
        tipo = (inp.get("type") or "").lower()
        if tipo not in ("submit", "button"):
            continue
        valor = (inp.get("value") or "").lower()
        if "consult" in valor:
            return inp["name"]
    raise ErrorEstructural(
        "no se encontro el boton Consultar. "
        "Poner MODO_DIAGNOSTICO = True y enviar la salida."
    )


def fecha_declarada(html: str) -> str | None:
    """Extrae la fecha que la propia pagina dice estar mostrando.

    El subtitulo del reporte termina en "al DD/MM/AAAA". Comparar esa fecha con
    la pedida evita el error silencioso de guardar el reporte de otro dia.
    """
    m = re.search(r"al\s+(\d{2}/\d{2}/\d{4})", html)
    return m.group(1) if m else None


def validar_reporte(html: str, pedida: date) -> str:
    """Comprueba que el HTML sea un reporte util del mes pedido.

    Devuelve la fecha que declara la pagina. El portal puede ajustar la fecha
    al ultimo dia util, lo que es correcto; lo que no se acepta es un reporte
    de otro mes.
    """
    if TEXTO_OBLIGATORIO not in html:
        raise ValidacionFallida("el reporte no contiene filas de Descuentos")

    declarada = fecha_declarada(html)
    if declarada is None:
        raise ValidacionFallida("la pagina no declara la fecha del reporte")

    dd, mm, aaaa = (int(x) for x in declarada.split("/"))
    if (aaaa, mm) != (pedida.year, pedida.month):
        raise FechaNoObedecida(
            f"se pidio {pedida:%d/%m/%Y} y la pagina declara {declarada}, "
            f"que es de otro mes"
        )
    return declarada


def abrir_formulario(sesion: requests.Session) -> str:
    """Abre la pagina y devuelve su HTML, del que salen los campos del form."""
    r = pedir(sesion, "GET", URL_TASAS)
    if r.status_code != 200:
        raise ValidacionFallida(f"HTTP {r.status_code} al abrir el formulario")
    return r.text


def consultar_fecha(sesion: requests.Session, html_actual: str, fecha: date) -> str:
    """Envia el formulario para una fecha y devuelve el HTML del resultado.

    Recibe el HTML de la pagina tal como esta ahora, porque de ahi salen el
    __VIEWSTATE y el __EVENTVALIDATION vigentes. Como la respuesta de cada
    consulta trae los suyos, se pueden encadenar los 96 meses sobre una sola
    apertura: 97 solicitudes en vez de 192.
    """
    datos = campos_del_formulario(html_actual)
    iso, visible = localizar_campos_fecha(html_actual)
    boton = nombre_boton_consultar(html_actual)

    datos[iso] = fecha.strftime("%Y-%m-%d")
    if visible:
        datos[visible] = fecha.strftime("%d/%m/%Y")
        # El RadDateInput de Telerik no lee la caja de texto: lee este JSON
        # oculto. Si no se envia, el servidor se queda con su fecha por
        # defecto y devuelve el reporte de hoy, cosa que ya ocurrio.
        # El nombre usa guiones bajos, no "$", porque deriva del id.
        campo_estado = visible.replace("$", "_") + "_ClientState"
        if campo_estado in datos:
            datos[campo_estado] = json.dumps({
                "enabled": True,
                "emptyMessage": "",
                "validationText": fecha.strftime("%Y-%m-%d") + "-00-00-00",
                "valueAsString": fecha.strftime("%Y-%m-%d") + "-00-00-00",
                "minDateStr": "1000-01-01-00-00-00",
                "maxDateStr": "2099-12-31-00-00-00",
                "lastSetTextBoxValue": fecha.strftime("%d/%m/%Y"),
            })

    datos[boton] = "Consultar"
    datos.setdefault("__EVENTTARGET", "")
    datos.setdefault("__EVENTARGUMENT", "")

    time.sleep(PAUSA)
    r = pedir(sesion, "POST", URL_TASAS, data=datos)
    if r.status_code != 200:
        raise ValidacionFallida(f"HTTP {r.status_code} al consultar la fecha")
    return r.text


def descargar_tasas(sesion: requests.Session) -> tuple[int, int, int]:
    """Recorre los meses pedidos y guarda el HTML del reporte de cada uno.

    Para cada mes prueba el ultimo dia y retrocede dia a dia hasta obtener un
    reporte valido, con un maximo de DIAS_RETROCESO intentos. Asi no hace falta
    un calendario de feriados peruanos.
    """
    DIR_TASAS.mkdir(parents=True, exist_ok=True)
    guardados = omitidos = fallidos = 0

    # Estado del formulario: se abre una vez y se actualiza con la respuesta de
    # cada consulta, para no volver a pedir la pagina en cada mes.
    html_actual = abrir_formulario(sesion)
    meses_desobedecidos = 0

    for anio, mes in meses_a_recorrer():
        destino = DIR_TASAS / f"tasas_{anio}-{mes:02d}.html"
        if destino.exists():
            omitidos += 1
            continue

        ultimo_dia = calendar.monthrange(anio, mes)[1]
        guardado = False
        motivos: list[str] = []

        for atras in range(DIAS_RETROCESO):
            dia = ultimo_dia - atras
            if dia < 1:
                break
            fecha = date(anio, mes, dia)
            try:
                html = consultar_fecha(sesion, html_actual, fecha)
                html_actual = html  # el estado avanza con la ultima respuesta
                declarada = validar_reporte(html, fecha)
                contenido = html.encode("utf-8")
                destino.write_bytes(contenido)
                registrar(
                    f"{destino.name} | pedida {fecha:%d/%m/%Y} | "
                    f"declarada {declarada} | {len(contenido)} bytes | "
                    f"SHA-256 {sha256_bytes(contenido)}"
                )
                guardados += 1
                guardado = True
                break
            except ErrorEstructural:
                # La pagina no tiene la forma esperada. Probar otro dia no lo
                # arregla, asi que se corta la via en vez de gastar solicitudes.
                raise
            except FechaNoObedecida as e:
                # El formulario respondio con otro mes. Otro dia del mismo mes
                # daria igual, asi que se abandona este mes al primer intento.
                motivos.append(f"{fecha:%d/%m}: {e}")
                html_actual = abrir_formulario(sesion)
                break
            except ValidacionFallida as e:
                motivos.append(f"{fecha:%d/%m}: {e}")
                # Si la respuesta no sirvio, el estado puede haber quedado
                # inservible: se reabre la pagina para no arrastrar el problema.
                html_actual = abrir_formulario(sesion)
            time.sleep(PAUSA)

        if guardado:
            meses_desobedecidos = 0
        else:
            registrar(f"FALLO {destino.name} | " + " | ".join(motivos[:3]))
            fallidos += 1
            if motivos and "de otro mes" in motivos[-1]:
                meses_desobedecidos += 1
                if meses_desobedecidos >= 2:
                    raise ErrorEstructural(
                        "el formulario devuelve siempre la misma fecha en dos meses "
                        "seguidos: el envio no esta surtiendo efecto. Se detiene la "
                        "via para no gastar 96 consultas inutiles. Poner "
                        "MODO_DIAGNOSTICO = True y enviar la salida."
                    )

    return guardados, omitidos, fallidos


# ==========================================================================
# Diagnostico del formulario
# ==========================================================================
def diagnosticar(sesion: requests.Session) -> int:
    """Muestra los campos del formulario, sin descargar datos.

    Sirve cuando el descubrimiento automatico no encuentra la caja de fecha o
    el boton: con esta salida se corrige el script sin adivinar.
    """
    registrar("MODO_DIAGNOSTICO: abriendo el formulario de tasas")
    r = pedir(sesion, "GET", URL_TASAS)
    registrar(f"HTTP {r.status_code} | {len(r.content)} bytes")

    # Guardar el HTML tal cual: es mas fiable revisarlo entero que fiarse de
    # lo que quepa en la consola.
    DIR_TASAS.mkdir(parents=True, exist_ok=True)
    copia = DIR_TASAS / "_diagnostico_formulario.html"
    copia.write_bytes(r.content)
    registrar(f"HTML guardado en {copia}")

    sopa = BeautifulSoup(r.text, "lxml")

    titulo = sopa.find("title")
    registrar(f"titulo de la pagina: {titulo.get_text(strip=True) if titulo else '(ninguno)'}")

    formularios = sopa.find_all("form")
    registrar(f"formularios: {len(formularios)}")
    for f in formularios:
        registrar(f"  <form action={f.get('action')} method={f.get('method')}>")

    marcos = sopa.find_all(("iframe", "frame"))
    if marcos:
        registrar(f"AVISO: la pagina trae {len(marcos)} marco(s); el formulario podria vivir dentro:")
        for marco in marcos:
            registrar(f"  <{marco.name} src={marco.get('src')}>")

    entradas = sopa.find_all("input")
    registrar(f"se encontraron {len(entradas)} campos <input>:")
    for inp in entradas:
        tipo = inp.get("type", "(sin tipo)")
        nombre = inp.get("name", "(sin name)")
        ident = inp.get("id", "(sin id)")
        valor = (inp.get("value") or "")[:40]
        if tipo == "hidden" and len(inp.get("value") or "") > 40:
            valor = f"<{len(inp.get('value'))} caracteres>"
        print(f"    type={tipo:8s} name={nombre:45s} id={ident:45s} value={valor}")

    for selector in sopa.find_all("select"):
        registrar(f"  <select> name={selector.get('name')} id={selector.get('id')}")

    registrar(f"fecha que declara la pagina ahora: {fecha_declarada(r.text)}")
    registrar(f"contiene la palabra '{TEXTO_OBLIGATORIO}': {TEXTO_OBLIGATORIO in r.text}")
    return 0


# ==========================================================================
# Orquestacion
# ==========================================================================
def main() -> int:
    registrar("inicio")
    registrar(
        f"parametros: MODO_PRUEBA={MODO_PRUEBA} | tramo {ANIO_DESDE}-{ANIO_HASTA} | "
        f"{len(meses_a_recorrer())} meses | pausa {PAUSA}s"
    )

    sesion = requests.Session()
    sesion.headers.update(CABECERAS)

    try:
        if MODO_DIAGNOSTICO:
            return diagnosticar(sesion)

        total_fallidos = 0

        if HACER_XLS:
            registrar("--- via 2a: cuadros XLS del boletin ---")
            g, o, f = descargar_cuadros(sesion)
            registrar(f"via 2a: {g} guardados | {o} ya existian | {f} fallidos")
            total_fallidos += f

        if HACER_TASAS:
            registrar("--- via 2b: tasas por empresa bancaria ---")
            g, o, f = descargar_tasas(sesion)
            registrar(f"via 2b: {g} guardados | {o} ya existian | {f} fallidos")
            total_fallidos += f

    except ValidacionFallida as e:
        registrar(f"ABORTADO: {e}")
        return 1
    except KeyboardInterrupt:
        registrar("interrumpido por el usuario; lo descargado se conserva")
        return 130
    finally:
        sesion.close()

    if total_fallidos:
        registrar(f"fin con {total_fallidos} fallos; revisar las lineas FALLO del log")
        return 1

    registrar("fin correcto")
    return 0


if __name__ == "__main__":
    sys.exit(main())
