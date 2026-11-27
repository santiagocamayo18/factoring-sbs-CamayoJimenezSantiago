# Santiago Piero Camayo Jimenez
# 2024200488G
# Tema N.o 91 - El factoring como instrumento de financiamiento de corto plazo en el Peru (Unidad II)
# Fecha de ejecucion: la que registre log_ejecucion.txt

"""Verificacion de celdas contra el HTML crudo del portal de tasas de la SBS.

Responde una sola pregunta, y la responde mirando la fuente en vez de razonar:
el valor 51,11 que aparece repetido doce veces para Banco de Comercio, ¿esta
asi en lo que publico la SBS, o lo esta fabricando el lector?

Si en el crudo tambien sale doce veces, el dato es de la SBS, el lector esta
bien y lo que toca es decidir como tratar un atipico. Si en el crudo hay
valores variados, el defecto es del lector y hay que corregir
03_limpieza_datos.py y regenerar el panel.

Hace tres cosas, de la mas concluyente a la mas detallada:

  A) COLISIONES. Comprueba, mes a mes, que ningun banco quede asignado a dos
     columnas. Es el sospechoso numero uno: Banco de Comercio se llamo
     "Comercio" hasta 2023 y "Bancom" despues, y si algun mes el portal
     mostrara las dos, el diccionario se quedaria con la ultima en silencio.

  B) INVENTARIO DE VALORES. Recorre los 96 meses y lista todos los valores
     distintos que trae el crudo para cada banco revisado, con cuantas veces
     aparece cada uno. Un precio de mercado da muchos valores distintos; una
     constante que se cuela da pocos y muy repetidos.

  C) VOLCADO. Para unos casos puntuales imprime la cabecera con los indices de
     columna, que columna se le asigno al banco y el texto crudo de la celda,
     para verlo con los ojos.

Este script NO modifica nada: abre los HTML crudos solo para leer.

Entradas : datos_crudos/sbs_tasas/tasas_*.html
Salidas  : salidas/verificacion_fuente_tasas.txt  (y lo mismo en consola)
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# Este script vive en codigo/verificacion/, un nivel mas abajo que los cuatro
# del flujo principal, asi que la raiz del proyecto queda tres niveles arriba.
RAIZ = Path(__file__).resolve().parent.parent.parent
# La carpeta codigo/ no esta en la ruta de busqueda de Python cuando el script
# se ejecuta desde aqui, de modo que hay que agregarla para poder importar
# entidades.py y cargar 03_limpieza_datos.py.
CODIGO = Path(__file__).resolve().parent.parent
if str(CODIGO) not in sys.path:
    sys.path.insert(0, str(CODIGO))
ARCHIVO_SALIDA = RAIZ / "salidas" / "verificacion_fuente_tasas.txt"
ARCHIVO_LOG = RAIZ / "log_ejecucion.txt"

# 03_limpieza_datos.py empieza con un numero, y en Python un modulo no puede
# llamarse asi: "import 03_limpieza_datos" es un error de sintaxis. Por eso se
# carga por ruta. Se reutiliza su codigo a proposito, para verificar el lector
# de verdad y no una copia parecida que podria no tener el mismo defecto.
_spec = importlib.util.spec_from_file_location("limpieza", CODIGO / "03_limpieza_datos.py")
L = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(L)

import entidades  # noqa: E402

# Bancos a revisar. comercio es el sospechoso; bbva es el control, un banco
# grande y normal con el que comparar lo que es un comportamiento sano.
ENTIDADES_REVISADAS = ("comercio", "bbva")

# Casos puntuales que el diagnostico marco, mas uno de control.
CASOS = (
    ("2022-03", "comercio", "grandes", "descuentos"),
    ("2022-04", "comercio", "corporativo", "descuentos"),
    ("2023-03", "comercio", "corporativo", "encabezado"),
    ("2025-06", "comercio", "grandes", "descuentos"),
    ("2021-05", "bbva", "corporativo", "encabezado"),
)

lineas: list[str] = []


def di(texto: str = "") -> None:
    print(texto, flush=True)
    lineas.append(texto)


def registrar(mensaje: str) -> None:
    marca = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linea = f"[{marca}] verificar_fuente_tasas | {mensaje}"
    print(linea, flush=True)
    with ARCHIVO_LOG.open("a", encoding="utf-8") as f:
        f.write(linea + "\n")


def mapa_de_columnas(nombres: list[str]) -> dict[str, list[int]]:
    """{entidad: [columnas]}. Una lista, no un numero, para ver colisiones.

    El lector del panel guarda un solo numero por entidad; si dos columnas
    cayeran en la misma entidad, se quedaria con la ultima sin avisar. Aqui se
    guardan todas justamente para poder detectarlo.
    """
    mapa: dict[str, list[int]] = defaultdict(list)
    for c, nombre in enumerate(nombres):
        try:
            entidad = entidades.identificar(nombre)
        except entidades.EntidadDesconocida:
            continue
        if entidad is not None:
            mapa[entidad].append(c)
    return mapa


def recorrer() -> tuple[list[str], dict, dict]:
    """Lee los 96 HTML y devuelve (colisiones, valores crudos, nombres vistos)."""
    colisiones: list[str] = []
    # valores[(entidad, tipo, campo)] = Counter de textos crudos
    valores: dict[tuple[str, str, str], Counter] = defaultdict(Counter)
    # nombres_vistos[entidad] = Counter de como se llamo en la cabecera
    nombres_vistos: dict[str, Counter] = defaultdict(Counter)

    for anio, mes in L.meses_del_periodo():
        etiqueta_mes = f"{anio}-{mes:02d}"
        ruta = L.DIR_TASAS / f"tasas_{etiqueta_mes}.html"
        if not ruta.exists():
            continue
        try:
            nombres, etiquetas, datos, _ = L.leer_tasas(ruta)
        except L.LecturaFallida as e:
            colisiones.append(f"{etiqueta_mes}: no se pudo leer ({e})")
            continue

        mapa = mapa_de_columnas(nombres)
        for entidad, cols in mapa.items():
            if len(cols) > 1:
                cuales = ", ".join(f"col {c} = {nombres[c]!r}" for c in cols)
                colisiones.append(f"{etiqueta_mes}: {entidad} cae en {len(cols)} columnas -> {cuales}")
        for c, nombre in enumerate(nombres):
            try:
                e = entidades.identificar(nombre)
            except entidades.EntidadDesconocida:
                continue
            if e in ENTIDADES_REVISADAS:
                nombres_vistos[e][nombre] += 1

        tipo_actual = None
        for etiqueta, fila in zip(etiquetas, datos):
            cabecera = L.encabezado_de_tipo(etiqueta)
            if cabecera is not None:
                tipo_actual = cabecera if cabecera in L.TIPOS_INCLUIDOS_ID else None
                campo = "encabezado"
            elif tipo_actual is not None and L.modalidad_de(etiqueta) == "descuentos":
                campo = "descuentos"
            else:
                continue
            if tipo_actual is None:
                continue
            for entidad in ENTIDADES_REVISADAS:
                for c in mapa.get(entidad, []):
                    crudo = fila[c] if c < len(fila) else "(columna fuera de rango)"
                    valores[(entidad, tipo_actual, campo)][crudo] += 1
    return colisiones, valores, nombres_vistos


def volcar_caso(etiqueta_mes: str, entidad_buscada: str, tipo: str, campo: str) -> None:
    """Imprime la cabecera, la columna asignada y la celda cruda de un caso."""
    ruta = L.DIR_TASAS / f"tasas_{etiqueta_mes}.html"
    di("")
    di("-" * 78)
    di(f"{etiqueta_mes} | {entidad_buscada} | {tipo} | {campo}")
    di("-" * 78)
    if not ruta.exists():
        di(f"  no existe {ruta.name}")
        return
    nombres, etiquetas, datos, declarada = L.leer_tasas(ruta)
    mapa = mapa_de_columnas(nombres)
    cols = mapa.get(entidad_buscada, [])
    di(f"  fecha que declara el archivo: {declarada}")
    di(f"  columnas en la cabecera: {len(nombres)}")
    di("  cabecera completa:")
    for c, n in enumerate(nombres):
        marca = "  <-- ASIGNADA" if c in cols else ""
        di(f"      col {c:3d}  {n!r}{marca}")
    if not cols:
        di(f"  {entidad_buscada} NO aparece en la cabecera de este mes")
        return

    tipo_actual = None
    for i, (etiqueta, fila) in enumerate(zip(etiquetas, datos)):
        cabecera = L.encabezado_de_tipo(etiqueta)
        if cabecera is not None:
            tipo_actual = cabecera if cabecera in L.TIPOS_INCLUIDOS_ID else None
            este = "encabezado"
        elif tipo_actual is not None and L.modalidad_de(etiqueta) == "descuentos":
            este = "descuentos"
        else:
            continue
        if tipo_actual != tipo or este != campo:
            continue
        di("")
        di(f"  fila {i} del crudo, etiqueta {etiqueta!r}")
        for c in cols:
            crudo = fila[c] if c < len(fila) else "(fuera de rango)"
            di(f"      celda de {entidad_buscada} (col {c}): {crudo!r}")
        di(f"      fila completa ({len(fila)} celdas): {fila}")
        return
    di("  no se encontro esa fila en este mes")


def main() -> int:
    registrar("inicio")
    ARCHIVO_SALIDA.parent.mkdir(parents=True, exist_ok=True)

    di("VERIFICACION DE CELDAS CONTRA EL HTML CRUDO DEL PORTAL SAEE")
    di(f"Generado el {datetime.now():%Y-%m-%d %H:%M:%S}")
    di(f"Bancos revisados: {', '.join(ENTIDADES_REVISADAS)}")

    colisiones, valores, nombres_vistos = recorrer()

    di("")
    di("=" * 78)
    di("A) COLISIONES DE COLUMNA")
    di("=" * 78)
    if colisiones:
        di(f"  {len(colisiones)} meses con problema. ESTO ES UN DEFECTO DEL LECTOR:")
        for c in colisiones[:30]:
            di(f"    {c}")
        if len(colisiones) > 30:
            di(f"    ... y {len(colisiones) - 30} mas")
    else:
        di("  ninguna: cada banco cae en una sola columna en los 96 meses")

    di("")
    di("  como se llamo cada banco revisado en la cabecera:")
    for entidad in ENTIDADES_REVISADAS:
        di(f"    {entidad}:")
        for nombre, n in sorted(nombres_vistos[entidad].items(), key=lambda x: -x[1]):
            di(f"        {n:3d} meses  {nombre!r}")

    di("")
    di("=" * 78)
    di("B) VALORES DISTINTOS EN EL CRUDO")
    di("=" * 78)
    di("  Un precio de mercado da muchos valores distintos y poco repetidos.")
    di("  Una constante que se cuela da pocos valores y muy repetidos.")
    for entidad in ENTIDADES_REVISADAS:
        for tipo in L.TIPOS_INCLUIDOS_ID:
            for campo in ("descuentos", "encabezado"):
                cuenta = valores.get((entidad, tipo, campo))
                if not cuenta:
                    continue
                total = sum(cuenta.values())
                con_dato = {k: v for k, v in cuenta.items() if k not in ("-", "")}
                di("")
                di(f"  {entidad} | {tipo} | {campo}")
                di(f"      {total} meses, {len(con_dato)} valores distintos con dato, "
                   f"{cuenta.get('-', 0)} meses en guion")
                for valor, n in sorted(cuenta.items(), key=lambda x: -x[1])[:12]:
                    aviso = "   <-- SE REPITE MUCHO" if n >= 5 and valor not in ("-", "") else ""
                    di(f"        {n:3d} x  {valor!r}{aviso}")
                if len(cuenta) > 12:
                    di(f"        ... y {len(cuenta) - 12} valores mas")

    di("")
    di("=" * 78)
    di("C) VOLCADO DE CASOS PUNTUALES")
    di("=" * 78)
    for caso in CASOS:
        volcar_caso(*caso)

    ARCHIVO_SALIDA.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    registrar(f"informe escrito en {ARCHIVO_SALIDA}")
    registrar("fin")
    return 0


if __name__ == "__main__":
    sys.exit(main())
