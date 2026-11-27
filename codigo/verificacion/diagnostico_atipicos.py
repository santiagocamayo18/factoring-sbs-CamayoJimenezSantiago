# Santiago Piero Camayo Jimenez
# 2024200488G
# Tema N.o 91 - El factoring como instrumento de financiamiento de corto plazo en el Peru (Unidad II)
# Fecha de ejecucion: la que registre log_ejecucion.txt

"""Diagnostico de los valores atipicos que reporto la validacion del panel.

Este script NO modifica nada. Solo lee la base procesada y
describe lo que encuentra, para decidir con datos a la vista si los valores
extremos son atipicos reales de la fuente o un defecto del lector.

La diferencia importa y no es academica:
  - si son atipicos reales, la decision es de tratamiento (recortar, usar
    mediana, declararlos en el articulo) y se documenta;
  - si son un defecto del lector, hay que arreglar 03_limpieza_datos.py y
    volver a generar el panel, porque entonces habria mas celdas mal leidas
    que las que se ven.

Como se distingue una cosa de la otra, con lo que imprime este script:
  - Un atipico real suele venir con monto negociado minusculo: un banco con
    una sola operacion chica arrastra el promedio del mes. Ademas aparece
    disperso, en pocos meses y pocas entidades.
  - Un defecto del lector suele ser sistematico: afecta a muchas entidades el
    mismo mes, o a la misma entidad todos los meses, o a un tipo de credito
    entero.

Entradas : datos_procesados/datos_procesados_<codigo>.csv
Salidas  : salidas/diagnostico_atipicos.txt  (y el mismo texto en consola)
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------
# Parametros congelados
# --------------------------------------------------------------------------
MATRICULA = "2024200488G"

# Rangos que se consideran plausibles para el segmento no minorista.
# No son reglas de la SBS: son el criterio economico con el que se revisa, y
# por eso estan declarados aqui arriba y no escondidos en el codigo.
# Una tasa efectiva anual de credito corporativo, a gran empresa o a mediana
# empresa vive entre 2 % y 30 %; la morosidad de esos segmentos rara vez pasa
# de 20 %. Lo que caiga fuera no es necesariamente un error: es lo que hay
# que mirar.
RANGOS = {
    "tasa_descuento_pct": (2.0, 30.0),
    "tasa_tipo_pct": (2.0, 30.0),
    "morosidad_factoring_pct": (0.0, 20.0),
    "morosidad_tipo_pct": (0.0, 20.0),
}

MAX_FILAS_LISTADAS = 20

# Este script vive en codigo/verificacion/, un nivel mas abajo que los cuatro
# del flujo principal, asi que la raiz del proyecto queda tres niveles arriba.
RAIZ = Path(__file__).resolve().parent.parent.parent
ARCHIVO_PANEL = RAIZ / "datos_procesados" / f"datos_procesados_{MATRICULA}.csv"
ARCHIVO_SALIDA = RAIZ / "salidas" / "diagnostico_atipicos.txt"
ARCHIVO_LOG = RAIZ / "log_ejecucion.txt"

lineas: list[str] = []


def di(texto: str = "") -> None:
    """Imprime en consola y guarda la linea para el informe."""
    print(texto, flush=True)
    lineas.append(texto)


def registrar(mensaje: str) -> None:
    marca = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linea = f"[{marca}] diagnostico_atipicos | {mensaje}"
    print(linea, flush=True)
    with ARCHIVO_LOG.open("a", encoding="utf-8") as f:
        f.write(linea + "\n")


def describir(df: pd.DataFrame, columna: str) -> None:
    """Imprime la distribucion de una variable.

    Los percentiles cuentan la historia que el minimo y el maximo esconden:
    si el percentil 99 es 14 y el maximo 238, el extremo es una anecdota; si
    el percentil 99 ya es 80, el problema es de fondo.
    """
    s = pd.to_numeric(df[columna], errors="coerce").dropna()
    if s.empty:
        di(f"  {columna:26s}  sin datos")
        return
    p = s.quantile([0.01, 0.25, 0.50, 0.75, 0.99])
    di(
        f"  {columna:26s} n={len(s):5d}  min={s.min():8.2f}  p1={p[0.01]:7.2f}  "
        f"p25={p[0.25]:7.2f}  mediana={p[0.50]:7.2f}  p75={p[0.75]:7.2f}  "
        f"p99={p[0.99]:7.2f}  max={s.max():8.2f}"
    )


def listar_fuera_de_rango(df: pd.DataFrame, columna: str) -> pd.DataFrame:
    """Devuelve las filas fuera del rango plausible, de la peor a la menos mala."""
    bajo, alto = RANGOS[columna]
    v = pd.to_numeric(df[columna], errors="coerce")
    fuera = df[v.notna() & ((v < bajo) | (v > alto))].copy()
    if fuera.empty:
        return fuera
    centro = (bajo + alto) / 2
    fuera["_desvio"] = (pd.to_numeric(fuera[columna], errors="coerce") - centro).abs()
    return fuera.sort_values("_desvio", ascending=False)


def informar_columna(df: pd.DataFrame, columna: str) -> int:
    """Imprime el detalle de una variable y devuelve cuantas filas fallan."""
    bajo, alto = RANGOS[columna]
    fuera = listar_fuera_de_rango(df, columna)
    con_dato = pd.to_numeric(df[columna], errors="coerce").notna().sum()

    di("")
    di("-" * 78)
    di(f"{columna}   (rango plausible {bajo} a {alto})")
    di("-" * 78)
    if fuera.empty:
        di(f"  ninguna de las {con_dato} filas con dato se sale del rango")
        return 0

    di(
        f"  {len(fuera)} filas fuera de rango, sobre {con_dato} con dato "
        f"({100 * len(fuera) / con_dato:.2f} %)"
    )

    # Concentracion: esto es lo que distingue un atipico de un defecto.
    di("")
    di(f"  entidades afectadas: {fuera['entidad'].nunique()} de {df['entidad'].nunique()}")
    for ent, n in fuera["entidad"].value_counts().head(6).items():
        meses_ent = df[df["entidad"] == ent]["fecha"].nunique()
        di(f"      {ent:28s} {n:4d} filas malas de {meses_ent * 3:4d} suyas")
    di(f"  meses afectados    : {fuera['fecha'].nunique()} de {df['fecha'].nunique()}")
    peores = fuera["fecha"].value_counts()
    di(f"      el peor mes es {peores.index[0]} con {peores.iloc[0]} filas")
    por_tipo = {str(k): int(v) for k, v in fuera["tipo"].value_counts().items()}
    di(f"  por tipo de credito: {por_tipo}")

    di("")
    di(f"  las {min(len(fuera), MAX_FILAS_LISTADAS)} peores:")
    di(
        f"      {'fecha':8s} {'entidad':24s} {'tipo':12s} {'valor':>9s} "
        f"{'monto S/ mil':>13s} {'deudores':>9s}"
    )
    for _, f in fuera.head(MAX_FILAS_LISTADAS).iterrows():
        monto = pd.to_numeric(pd.Series([f["monto_negociado_miles"]]), errors="coerce").iloc[0]
        deud = pd.to_numeric(pd.Series([f["deudores"]]), errors="coerce").iloc[0]
        di(
            f"      {f['fecha']:8s} {str(f['entidad'])[:24]:24s} {str(f['tipo']):12s} "
            f"{pd.to_numeric(pd.Series([f[columna]]), errors='coerce').iloc[0]:9.2f} "
            f"{0 if pd.isna(monto) else monto:13,.0f} "
            f"{'' if pd.isna(deud) else int(deud):>9}"
        )

    # El monto es la clave de la interpretacion.
    montos = pd.to_numeric(fuera["monto_negociado_miles"], errors="coerce").fillna(0)
    todos = pd.to_numeric(df["monto_negociado_miles"], errors="coerce").fillna(0)
    di("")
    di(f"  monto negociado de las filas malas : mediana S/ {montos.median():,.0f} mil")
    di(f"  monto negociado de todas las filas : mediana S/ {todos.median():,.0f} mil")
    di(f"  filas malas con monto cero         : {int((montos == 0).sum())} de {len(fuera)}")
    return len(fuera)


def main() -> int:
    registrar("inicio")
    if not ARCHIVO_PANEL.exists():
        registrar(f"ABORTADO: no existe {ARCHIVO_PANEL}")
        return 1

    df = pd.read_csv(ARCHIVO_PANEL, dtype={"fecha": str})
    ARCHIVO_SALIDA.parent.mkdir(parents=True, exist_ok=True)

    di("DIAGNOSTICO DE VALORES ATIPICOS DEL PANEL")
    di(f"Generado el {datetime.now():%Y-%m-%d %H:%M:%S}")
    di(f"Panel: {ARCHIVO_PANEL.name}, {len(df)} filas, "
       f"{df['fecha'].nunique()} meses, {df['entidad'].nunique()} entidades")
    di("")
    di("=" * 78)
    di("DISTRIBUCION DE CADA VARIABLE")
    di("=" * 78)
    for c in ("monto_negociado_miles", "tasa_descuento_pct", "deudores",
              "morosidad_factoring_pct", "tasa_referencia_pct",
              "tasa_tipo_pct", "morosidad_tipo_pct"):
        describir(df, c)

    di("")
    di("=" * 78)
    di("FILAS FUERA DEL RANGO PLAUSIBLE")
    di("=" * 78)
    total = sum(informar_columna(df, c) for c in RANGOS)

    # Los ceros negativos son redondeos de la fuente, no datos raros.
    di("")
    di("-" * 78)
    di("ceros negativos (redondeo de la SBS, no un valor negativo de verdad)")
    di("-" * 78)
    for c in ("morosidad_factoring_pct", "morosidad_tipo_pct", "tasa_descuento_pct"):
        v = pd.to_numeric(df[c], errors="coerce")
        n = int(((v < 0) & (v > -0.000001)).sum())
        n_neg = int((v <= -0.000001).sum())
        di(f"  {c:26s} {n:4d} ceros negativos, {n_neg:4d} negativos de verdad")

    di("")
    di("=" * 78)
    di(f"TOTAL DE FILAS FUERA DE RANGO: {total} sobre {len(df)} del panel "
       f"({100 * total / len(df):.2f} %)")
    di("=" * 78)

    ARCHIVO_SALIDA.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    registrar(f"informe escrito en {ARCHIVO_SALIDA}")
    registrar("fin")
    return 0


if __name__ == "__main__":
    sys.exit(main())
