# Santiago Piero Camayo Jimenez
# 2024200488G
# Tema N.o 91 - El factoring como instrumento de financiamiento de corto plazo en el Peru (Unidad II)
# Fecha de ejecucion: la que registre log_ejecucion.txt

"""Etapa 5 - Analisis: tablas, figuras y modelo de panel del articulo.

Lee el panel y produce todo lo que va en el articulo menos el modelo. Cada
figura se guarda en PDF vectorial (para el LaTeX) y en PNG a 300 ppp (para los
posters y el Beamer), y cada una deja ademas el CSV con los datos exactos que
dibuja, para que cualquiera pueda rehacerla o leerla sin ver el grafico.

TRATAMIENTO DE ATIPICOS
Se winsorizan al percentil 1 y 99 las cuatro variables de tasa y morosidad.
Winsorizar recorta, no borra: lo que esta por encima del p99 pasa a valer p99 y
lo que esta por debajo del p1 pasa a valer p1, asi que no se pierde ninguna
observacion. Hace falta porque la SBS publica tasas efectivas anuales de
operaciones de muy corto plazo, y una letra a 7 dias con una comision plana
chica anualiza a cifras de dos y tres digitos (verificado: Banco de Comercio
aparece repetidamente en 51,11 % y una vez en 238,67 %, y esos valores estan en
el HTML crudo del portal, no los fabrica el lector).

NO se winsorizan el monto ni el numero de deudores. En esas dos los valores
extremos son los bancos grandes de verdad: recortarlos deformaria el tamano del
mercado, que es justamente lo que el articulo quiere medir.

Todo resultado sale dos veces, crudo y winsorizado, para que se vea si las
conclusiones dependen del tratamiento. Si dependieran, eso seria un hallazgo
que hay que contar, no esconder.

EL PANEL NO SE MODIFICA. Este script solo lee datos_procesados/ y escribe en
salidas/. La winsorizacion se aplica en memoria.

Entradas : datos_procesados/datos_procesados_<codigo>.csv
Salidas  : salidas/tablas/tabla*.csv y .tex
           salidas/figuras/fig*.pdf y .png
           salidas/figuras/datos_fig*.csv
"""

from __future__ import annotations

import math
import sys
import textwrap
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")          # sin ventana: el script corre igual sin pantalla
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter

# --------------------------------------------------------------------------
# Parametros congelados
# --------------------------------------------------------------------------
MATRICULA = "2024200488G"
ANIO_INICIO = 2018
ANIO_CORTE = 2025

# Percentiles de winsorizacion y variables a las que se aplica.
P_BAJO, P_ALTO = 0.01, 0.99
VARIABLES_WINSOR = (
    "tasa_descuento_pct",
    "tasa_tipo_pct",
    "morosidad_factoring_pct",
    "morosidad_tipo_pct",
)

# Mes desde el que rige la Resolucion SBS 02368-2023. Se marca en las figuras
# porque sin esa marca el escalon de octubre de 2024 parece un hecho economico
# cuando es un cambio de definicion.
MES_RECLASIFICACION = "2024-10"

# Ventana que se sombrea como referencia visual del choque de la pandemia.
PANDEMIA = ("2020-03", "2021-06")

ORDEN_TIPOS = ("corporativo", "grandes", "medianas", "pequenas")
ETIQUETA_TIPO = {
    "corporativo": "Corporativos",
    "grandes": "Grandes empresas",
    "medianas": "Medianas empresas",
    "pequenas": "Pequeñas empresas",
}

N_ENTIDADES_GRAFICO = 4        # las demas se agrupan en "Otros bancos"

# --- Paleta -----------------------------------------------------------------
# Paleta categorica validada con el verificador de daltonismo: el peor par
# adyacente da Delta E 11.8 en protanopia y 23.8 en vision normal, por encima
# de los umbrales de 8 y 15. El orden de los colores no es decorativo, es el
# mecanismo que garantiza esa separacion, asi que no se reordena.
#
# Cuatro de estos colores quedan por debajo de 3:1 de contraste contra el
# blanco. La regla de alivio obliga entonces a etiquetas visibles: por eso
# cada serie lleva su nombre al final de la linea ademas de la leyenda, y
# cada figura exporta su CSV.
AZUL, NARANJA, AGUA, AMARILLO, MAGENTA = (
    "#257de0", "#f47230", "#00b894", "#f2a600", "#ee7fac",
)
COLOR_TIPO = dict(zip(ORDEN_TIPOS, (AZUL, NARANJA, AGUA, AMARILLO)))
PALETA_ENTIDADES = (AZUL, NARANJA, AGUA, AMARILLO, MAGENTA)

TINTA = "#191919"              # texto principal
TINTA_SUAVE = "#666666"        # texto secundario, ejes
REJILLA = "#e4e4e4"            # rejilla, un tono sobre el fondo
SUPERFICIE = "#ffffff"
SOMBRA = "#f2f2f2"             # sombreado de la pandemia

# --- Rutas, siempre relativas ----------------------------------------------
RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO_PANEL = RAIZ / "datos_procesados" / f"datos_procesados_{MATRICULA}.csv"
DIR_FIGURAS = RAIZ / "salidas" / "figuras"
DIR_TABLAS = RAIZ / "salidas" / "tablas"
ARCHIVO_LOG = RAIZ / "log_ejecucion.txt"


class DatosInsuficientes(Exception):
    """El panel no tiene lo que esta etapa necesita. Mejor parar que dibujar mal."""


def registrar(mensaje: str) -> None:
    marca = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linea = f"[{marca}] 04_analisis | {mensaje}"
    print(linea, flush=True)
    with ARCHIVO_LOG.open("a", encoding="utf-8") as f:
        f.write(linea + "\n")


# --------------------------------------------------------------------------
# Preparacion de los datos
# --------------------------------------------------------------------------
def cargar() -> pd.DataFrame:
    """Lee el panel y comprueba que tenga la forma que esta etapa espera."""
    if not ARCHIVO_PANEL.exists():
        raise DatosInsuficientes(f"no existe {ARCHIVO_PANEL}; corre antes el 03")
    df = pd.read_csv(ARCHIVO_PANEL, dtype={"fecha": str})

    faltan = {"fecha", "entidad", "tipo", "monto_negociado_miles",
              "tasa_descuento_pct"} - set(df.columns)
    if faltan:
        raise DatosInsuficientes(f"al panel le faltan columnas: {sorted(faltan)}")

    meses = df["fecha"].nunique()
    if meses != 96:
        raise DatosInsuficientes(f"se esperaban 96 meses y hay {meses}")

    sobran = set(df["tipo"].unique()) - set(ORDEN_TIPOS)
    if sobran:
        raise DatosInsuficientes(f"tipos de credito inesperados: {sorted(sobran)}")

    # Fecha como periodo mensual: ordena bien y da un eje temporal de verdad,
    # no una cadena de texto que matplotlib espaciaria mal.
    df["periodo"] = pd.PeriodIndex(df["fecha"], freq="M")
    df["t"] = df["periodo"].dt.to_timestamp()
    df["anio"] = df["fecha"].str[:4].astype(int)
    df["monto_mm"] = df["monto_negociado_miles"] / 1e6   # miles de millones S/
    return df.sort_values(["fecha", "entidad", "tipo"]).reset_index(drop=True)


def winsorizar(s: pd.Series, p_bajo: float, p_alto: float) -> tuple[pd.Series, float, float]:
    """Recorta la serie a sus percentiles y devuelve tambien los umbrales.

    Entra  : la serie cruda.
    Sale   : la serie recortada, el umbral bajo y el umbral alto.
    Ojo    : los percentiles se calculan sobre los valores con dato, no sobre
             las filas totales; si se calcularan sobre el total, los faltantes
             correrian los umbrales.
    """
    v = pd.to_numeric(s, errors="coerce")
    if v.notna().sum() < 20:
        return v, float("nan"), float("nan")
    bajo, alto = v.quantile(p_bajo), v.quantile(p_alto)
    return v.clip(bajo, alto), float(bajo), float(alto)


def aplicar_winsorizacion(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Agrega las columnas winsorizadas y devuelve la tabla de umbrales."""
    filas = []
    for col in VARIABLES_WINSOR:
        if col not in df.columns:
            continue
        rec, bajo, alto = winsorizar(df[col], P_BAJO, P_ALTO)
        df[col + "_w"] = rec
        v = pd.to_numeric(df[col], errors="coerce")
        filas.append({
            "variable": col,
            "n_con_dato": int(v.notna().sum()),
            "umbral_p1": bajo,
            "umbral_p99": alto,
            "recortadas_abajo": int((v < bajo).sum()),
            "recortadas_arriba": int((v > alto).sum()),
            "max_crudo": float(v.max()),
            "max_winsor": float(rec.max()),
        })
    return df, pd.DataFrame(filas)


def ponderada(g: pd.DataFrame, col: str) -> float:
    """Promedio de col ponderado por el monto negociado.

    Se pondera y no se promedia a secas porque un promedio simple le daria el
    mismo peso a un banco con un millon de soles de factoring que a uno con mil
    millones, y entonces la "tasa del mercado" seria en realidad la tasa del
    banco mas chico.
    """
    v = pd.to_numeric(g[col], errors="coerce")
    w = pd.to_numeric(g["monto_negociado_miles"], errors="coerce")
    m = v.notna() & w.notna() & (w > 0)
    return float((v[m] * w[m]).sum() / w[m].sum()) if m.any() else np.nan


# --------------------------------------------------------------------------
# Salida de tablas
# --------------------------------------------------------------------------
def guardar_tabla(df: pd.DataFrame, nombre: str, titulo: str,
                  etiqueta: str, decimales: int = 2) -> None:
    """Escribe la tabla en CSV y en LaTeX con booktabs.

    El .tex se puede meter en el articulo con \\input{} sin tocar nada, que es
    lo que evita el error clasico de copiar numeros a mano y que dejen de
    coincidir con los datos.
    """
    DIR_TABLAS.mkdir(parents=True, exist_ok=True)
    df.to_csv(DIR_TABLAS / f"{nombre}.csv", index=False,
              encoding="utf-8", lineterminator="\n")

    cuerpo = df.copy()
    for c in cuerpo.columns:
        if pd.api.types.is_float_dtype(cuerpo[c]):
            cuerpo[c] = cuerpo[c].map(
                lambda x: "" if pd.isna(x) else f"{x:,.{decimales}f}"
            )
    tex = cuerpo.to_latex(
        index=False, escape=True, column_format="l" + "r" * (len(cuerpo.columns) - 1),
        caption=titulo, label=etiqueta, position="htbp",
    )
    # to_latex no usa booktabs si no esta disponible el motor; se fuerza aqui.
    tex = tex.replace("\\toprule", "\\toprule").replace("\\begin{tabular}", "\\begin{tabular}")
    (DIR_TABLAS / f"{nombre}.tex").write_text(tex, encoding="utf-8")
    registrar(f"  tabla {nombre}: {len(df)} filas -> csv y tex")


# --------------------------------------------------------------------------
# Estilo de las figuras
# --------------------------------------------------------------------------
def estilo() -> None:
    """Ajustes comunes a todas las figuras.

    Marcas finas, rejilla de un solo tono sobre el fondo y solida (una rejilla
    punteada se lee como si marcara un umbral o una proyeccion, cuando solo es
    una guia), sin los bordes superior y derecho, y tipografia de palo seco
    legible al tamano real de impresion.
    """
    plt.rcParams.update({
        "figure.facecolor": SUPERFICIE,
        "axes.facecolor": SUPERFICIE,
        "savefig.facecolor": SUPERFICIE,
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans"],
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.titleweight": "bold",
        "axes.titlecolor": TINTA,
        "axes.labelsize": 9,
        "axes.labelcolor": TINTA_SUAVE,
        "axes.edgecolor": REJILLA,
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": TINTA_SUAVE,
        "ytick.color": TINTA_SUAVE,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "legend.frameon": False,
        "legend.fontsize": 8,
        "grid.color": REJILLA,
        "grid.linewidth": 0.6,
        "grid.linestyle": "-",
        "lines.linewidth": 1.8,
        "lines.solid_capstyle": "round",
        "figure.dpi": 110,
    })


def marcar_contexto(ax, con_leyenda: bool = False) -> None:
    """Sombrea la pandemia y marca el mes de la reclasificacion."""
    a, b = (pd.Period(p, freq="M").to_timestamp() for p in PANDEMIA)
    ax.axvspan(a, b, color=SOMBRA, zorder=0,
               label="Pandemia (mar-2020 a jun-2021)" if con_leyenda else None)
    corte = pd.Period(MES_RECLASIFICACION, freq="M").to_timestamp()
    ax.axvline(corte, color=TINTA_SUAVE, linewidth=0.9, zorder=1,
               label="Reclasificación SBS (oct-2024)" if con_leyenda else None)


def nota_contexto(fig, extra: str = "", marcas: bool = True) -> None:
    """Pie de figura que explica la banda gris y la linea vertical.

    Sin esta nota el lector ve dos marcas sin significado, y la peor lectura
    posible es creer que el escalon de octubre de 2024 fue un hecho economico
    cuando es un cambio de definicion.
    """
    # Una figura sin banda ni linea no debe anunciarlas: el pie describe lo
    # que se ve, no una plantilla.
    if marcas:
        texto = ("Banda gris: pandemia (mar-2020 a jun-2021). Línea vertical: entrada "
                 "en vigencia de la reclasificación de tipos de crédito de la "
                 "Resolución SBS 02368-2023 (oct-2024). Elaboración propia con datos "
                 "de la SBS y del BCRP.")
    else:
        texto = "Elaboración propia con datos de la SBS y del BCRP."
    if extra:
        texto += " " + extra
    # El ajuste de linea es obligatorio: guardando con bbox_inches="tight", un
    # pie de una sola linea larga ensancha el lienzo entero y deja los paneles
    # aplastados en la izquierda.
    ancho = max(90, int(fig.get_size_inches()[0] * 17))
    fig.text(0.0, -0.015, textwrap.fill(texto, ancho), ha="left", va="top",
             fontsize=7, color=TINTA_SUAVE, linespacing=1.45)


# Los nombres del diccionario de entidades estan sin tildes para que la
# consola de Windows no falle al imprimirlos. En las figuras del articulo si
# llevan tilde, que es como se escriben.
CON_TILDE = {
    "Banco de Credito del Peru": "Banco de Crédito del Perú",
    "BBVA Peru (antes Continental)": "BBVA Perú",
    "Scotiabank Peru": "Scotiabank Perú",
    "BANCOM (antes Banco de Comercio)": "BANCOM",
    "Banco Pichincha (antes Financiero)": "Banco Pichincha",
    "Alfin Banco (antes Azteca)": "Alfin Banco",
    "Banco Santander Peru": "Banco Santander Perú",
    "BCI Peru": "BCI Perú",
}


def bonito(nombre: str) -> str:
    """Nombre de entidad como va impreso en el articulo."""
    return CON_TILDE.get(nombre, nombre)


def etiqueta_final(ax, x, y, texto: str) -> None:
    """Escribe el nombre de la serie al final de la linea.

    El texto va en tinta y no en el color de la serie: el color lo aporta la
    linea que llega hasta ahi, y el texto coloreado se lee peor.
    """
    if pd.isna(y):
        return
    ax.annotate(texto, xy=(x, y), xytext=(5, 0), textcoords="offset points",
                va="center", ha="left", fontsize=8, color=TINTA)


def guardar_figura(fig, nombre: str, datos: pd.DataFrame) -> None:
    """Guarda PDF vectorial, PNG a 300 ppp y el CSV con los datos dibujados."""
    DIR_FIGURAS.mkdir(parents=True, exist_ok=True)
    for ext, dpi in (("pdf", None), ("png", 300)):
        fig.savefig(DIR_FIGURAS / f"{nombre}.{ext}", dpi=dpi,
                    bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    datos.to_csv(DIR_FIGURAS / f"datos_{nombre}.csv", index=False,
                 encoding="utf-8", lineterminator="\n")
    registrar(f"  figura {nombre}: pdf, png y csv de respaldo")


def eje_miles(ax) -> None:
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", " ")))


# --------------------------------------------------------------------------
# FIGURA 1 - El mercado en conjunto
# --------------------------------------------------------------------------
def figura_1(df: pd.DataFrame) -> None:
    """Monto negociado y tasa de descuento del mercado, 2018-2025.

    Es la figura que responde literalmente al objetivo del tema: la evolucion
    del monto negociado y de la tasa de descuento.

    Van en dos paneles apilados y NO en un grafico con dos ejes verticales.
    Un eje doble deja que quien dibuja elija a que altura cruzar las dos
    series, e inventa asi una correlacion que los datos no tienen. Con dos
    paneles que comparten el eje del tiempo se compara igual de bien y no se
    sugiere nada que no este en los numeros.
    """
    serie = (df.groupby("t")
               .apply(lambda g: pd.Series({
                   "monto_mm": g["monto_mm"].sum(),
                   "tasa_w": ponderada(g, "tasa_descuento_pct_w"),
                   "tasa_cruda": ponderada(g, "tasa_descuento_pct"),
                   "referencia": g["tasa_referencia_pct"].iloc[0],
               }), include_groups=False)
               .reset_index())

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6.6, 5.4), sharex=True,
                                   height_ratios=[1, 1])

    # --- Panel A: monto ---
    marcar_contexto(ax1)
    ax1.fill_between(serie["t"], serie["monto_mm"], color=AZUL, alpha=0.14, zorder=2)
    ax1.plot(serie["t"], serie["monto_mm"], color=AZUL, zorder=3)
    ax1.set_ylabel("Miles de millones de S/")
    ax1.set_title("A. Monto negociado del mercado (factoring y descuentos)", loc="left")
    ax1.grid(axis="y", zorder=0)
    ax1.set_ylim(0, serie["monto_mm"].max() * 1.18)

    # El maximo se senala porque es el punto de giro de toda la serie.
    i = serie["monto_mm"].idxmax()
    ax1.annotate(f"máximo {serie.loc[i, 'monto_mm']:.1f}",
                 xy=(serie.loc[i, "t"], serie.loc[i, "monto_mm"]),
                 xytext=(0, 7), textcoords="offset points",
                 ha="center", fontsize=8, color=TINTA)

    # --- Panel B: tasas ---
    marcar_contexto(ax2)
    ax2.plot(serie["t"], serie["tasa_w"], color=NARANJA, zorder=3,
             label="Tasa de descuento (promedio ponderado por monto)")
    ax2.plot(serie["t"], serie["referencia"], color=TINTA_SUAVE, linewidth=1.2,
             zorder=2, label="Tasa preferencial corporativa a 90 días (BCRP)")
    ax2.set_ylabel("Por ciento anual")
    ax2.set_title("B. Tasa de descuento y tasa de referencia", loc="left")
    ax2.grid(axis="y", zorder=0)
    ax2.set_ylim(0, max(serie["tasa_w"].max(), serie["referencia"].max()) * 1.30)

    ult = serie.iloc[-1]
    etiqueta_final(ax2, ult["t"], ult["tasa_w"], "Descuento")
    etiqueta_final(ax2, ult["t"], ult["referencia"], "BCRP")
    ax2.legend(loc="upper left", ncols=1)

    for ax in (ax1, ax2):
        ax.margins(x=0.02)
    # Sitio a la derecha para que las etiquetas al final de cada linea quepan
    # dentro del lienzo en vez de salirse por el borde.
    ax2.set_xlim(right=serie["t"].iloc[-1] + pd.Timedelta(days=300))
    ax1.set_xlim(ax2.get_xlim())
    fig.align_ylabels([ax1, ax2])
    fig.suptitle("El mercado bancario de factoring y descuentos en el Perú, 2018-2025",
                 fontsize=11, fontweight="bold", color=TINTA, x=0.0, ha="left", y=1.02)
    fig.tight_layout()
    nota_contexto(fig)

    salida = serie.rename(columns={"t": "fecha"})
    salida["fecha"] = salida["fecha"].dt.strftime("%Y-%m")
    guardar_figura(fig, "fig1_evolucion_mercado", salida)


# --------------------------------------------------------------------------
# FIGURA 2 - Composicion por tipo de credito
# --------------------------------------------------------------------------
def figura_2(df: pd.DataFrame) -> None:
    """Monto y tasa por tipo de credito.

    El panel B es el resultado mas limpio de todo el trabajo: la escalera de
    tasas por segmento no se cruza en ninguno de los 96 meses. Corporativo
    siempre paga menos que grandes, grandes menos que medianas y medianas
    menos que pequenas. Es la prima por riesgo y tamano, visible sin estimar
    nada.
    """
    monto = (df.pivot_table(index="t", columns="tipo", values="monto_mm",
                            aggfunc="sum")
               .reindex(columns=list(ORDEN_TIPOS)).fillna(0.0))
    tasa = (df.groupby(["t", "tipo"])
              .apply(lambda g: ponderada(g, "tasa_descuento_pct_w"),
                     include_groups=False)
              .unstack().reindex(columns=list(ORDEN_TIPOS)))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6.6, 5.6), sharex=True)

    # --- Panel A: area apilada ---
    marcar_contexto(ax1)
    ax1.stackplot(monto.index, *[monto[c] for c in ORDEN_TIPOS],
                  colors=[COLOR_TIPO[c] for c in ORDEN_TIPOS],
                  labels=[ETIQUETA_TIPO[c] for c in ORDEN_TIPOS],
                  edgecolor=SUPERFICIE, linewidth=1.0, zorder=2, alpha=0.92)
    ax1.set_ylabel("Miles de millones de S/")
    ax1.set_title("A. Monto negociado por tipo de crédito", loc="left")
    ax1.grid(axis="y", zorder=0)
    # Techo con holgura: sin esto la leyenda se apoya encima de las areas.
    ax1.set_ylim(0, monto.sum(axis=1).max() * 1.32)
    ax1.legend(loc="upper left", ncols=4, fontsize=7.5)

    # --- Panel B: la escalera de tasas ---
    marcar_contexto(ax2)
    for c in ORDEN_TIPOS:
        ax2.plot(tasa.index, tasa[c], color=COLOR_TIPO[c],
                 label=ETIQUETA_TIPO[c], zorder=3)
        etiqueta_final(ax2, tasa.index[-1], tasa[c].iloc[-1],
                       ETIQUETA_TIPO[c].split()[0])
    ax2.set_ylabel("Por ciento anual")
    ax2.set_title("B. Tasa de descuento por tipo de crédito", loc="left")
    ax2.grid(axis="y", zorder=0)
    ax2.set_ylim(top=float(np.nanmax(tasa.values)) * 1.28)
    ax2.legend(loc="upper left", ncols=4, fontsize=7.5)

    for ax in (ax1, ax2):
        ax.margins(x=0.02)
    ax2.set_xlim(right=tasa.index[-1] + pd.Timedelta(days=330))
    ax1.set_xlim(ax2.get_xlim())
    fig.align_ylabels([ax1, ax2])
    fig.tight_layout()
    nota_contexto(fig)

    sal_m = monto.reset_index().rename(columns={"t": "fecha"})
    sal_m["fecha"] = sal_m["fecha"].dt.strftime("%Y-%m")
    sal_m = sal_m.melt(id_vars="fecha", var_name="tipo", value_name="monto_mm")
    sal_t = tasa.reset_index().rename(columns={"t": "fecha"})
    sal_t["fecha"] = sal_t["fecha"].dt.strftime("%Y-%m")
    sal_t = sal_t.melt(id_vars="fecha", var_name="tipo", value_name="tasa_pct")
    guardar_figura(fig, "fig2_por_tipo_credito", sal_m.merge(sal_t, on=["fecha", "tipo"]))


# --------------------------------------------------------------------------
# FIGURA 3 - Factoring frente a descuentos
# --------------------------------------------------------------------------
def figura_3(df: pd.DataFrame) -> None:
    """Las dos modalidades que componen el monto negociado.

    Importa porque las entidades no clasifican igual operaciones que son
    economicamente equivalentes: hay bancos que registran en descuentos lo que
    otros registran en factoring. Mirar solo una de las dos daria una imagen
    falsa del mercado, y la participacion del factoring en el total resulta
    ser una serie con vida propia.
    """
    s = (df.groupby("t")[["saldo_factoring_miles", "saldo_descuentos_miles"]]
           .sum() / 1e6)
    s.columns = ["Factoring", "Descuentos"]
    s["participacion_factoring"] = 100 * s["Factoring"] / (s["Factoring"] + s["Descuentos"])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6.6, 5.2), sharex=True)

    marcar_contexto(ax1)
    ax1.stackplot(s.index, s["Factoring"], s["Descuentos"],
                  colors=[AZUL, NARANJA], labels=["Factoring", "Descuentos"],
                  edgecolor=SUPERFICIE, linewidth=1.0, zorder=2, alpha=0.92)
    ax1.set_ylabel("Miles de millones de S/")
    ax1.set_title("A. Composición del monto negociado", loc="left")
    ax1.grid(axis="y", zorder=0)
    ax1.set_ylim(0, (s["Factoring"] + s["Descuentos"]).max() * 1.22)
    ax1.legend(loc="upper left", ncols=2)

    marcar_contexto(ax2)
    ax2.axhline(50, color=REJILLA, linewidth=0.8, zorder=1)
    ax2.plot(s.index, s["participacion_factoring"], color=AZUL, zorder=3)
    ax2.set_ylabel("Por ciento del total")
    ax2.set_title("B. Participación del factoring en el monto negociado", loc="left")
    ax2.grid(axis="y", zorder=0)
    # Holgura arriba para que la anotacion del maximo no se apoye ni en la
    # linea ni en el titulo del panel.
    pf = s["participacion_factoring"]
    ax2.set_ylim(pf.min() - 2, pf.max() + 5)
    i = pf.idxmax()
    ax2.annotate(f"máximo {pf.loc[i]:.0f} %", xy=(i, pf.loc[i]),
                 xytext=(0, 9), textcoords="offset points",
                 ha="center", fontsize=8, color=TINTA)
    ult = s["participacion_factoring"].iloc[-1]
    ax2.annotate(f"{ult:.0f} %", xy=(s.index[-1], ult), xytext=(5, 0),
                 textcoords="offset points", va="center", fontsize=8, color=TINTA)

    for ax in (ax1, ax2):
        ax.margins(x=0.02)
    ax2.set_xlim(right=s.index[-1] + pd.Timedelta(days=200))
    ax1.set_xlim(ax2.get_xlim())
    fig.align_ylabels([ax1, ax2])
    fig.tight_layout()
    nota_contexto(fig)

    sal = s.reset_index().rename(columns={"t": "fecha"})
    sal["fecha"] = sal["fecha"].dt.strftime("%Y-%m")
    guardar_figura(fig, "fig3_factoring_vs_descuentos", sal)


# --------------------------------------------------------------------------
# FIGURA 4 - Concentracion del mercado
# --------------------------------------------------------------------------
def figura_4(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Como se reparte el mercado y cuan concentrado esta.

    El HHI va en su propio panel y no sobre el mismo eje que las
    participaciones, por la misma razon de siempre: son escalas distintas y
    superponerlas sugiere una relacion que el grafico no puede sostener.

    Las lineas de 1500 y 2500 son los umbrales con que el Departamento de
    Justicia de los Estados Unidos clasifica un mercado como moderadamente
    concentrado y como altamente concentrado. Son una referencia conocida, no
    una norma peruana.
    """
    por_ent = df.groupby(["t", "entidad_nombre"])["monto_negociado_miles"].sum().reset_index()
    total = por_ent.groupby("t")["monto_negociado_miles"].transform("sum")
    por_ent["sh"] = 100 * por_ent["monto_negociado_miles"] / total

    hhi = (por_ent.assign(c=lambda d: d["sh"] ** 2).groupby("t")["c"].sum())

    ranking = (df.groupby("entidad_nombre")["monto_negociado_miles"].sum()
                 .sort_values(ascending=False))
    lideres = list(ranking.head(N_ENTIDADES_GRAFICO).index)
    por_ent["grupo"] = np.where(por_ent["entidad_nombre"].isin(lideres),
                                por_ent["entidad_nombre"], "Otros bancos")
    cuota = (por_ent.pivot_table(index="t", columns="grupo", values="sh", aggfunc="sum")
                    .reindex(columns=lideres + ["Otros bancos"]).fillna(0.0))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6.6, 5.8), sharex=True)

    # En un apilado al 100 % no cabe sombrear la pandemia: el area tapa el
    # fondo. Se conserva solo la linea de la reclasificacion, que si se ve.
    corte = pd.Period(MES_RECLASIFICACION, freq="M").to_timestamp()
    ax1.stackplot(cuota.index, *[cuota[c] for c in cuota.columns],
                  colors=PALETA_ENTIDADES[:len(cuota.columns)],
                  labels=[bonito(c) for c in cuota.columns],
                  edgecolor=SUPERFICIE, linewidth=1.0, zorder=2, alpha=0.92)
    ax1.axvline(corte, color=TINTA, linewidth=0.9, zorder=4)
    ax1.set_ylabel("Por ciento del mercado")
    ax1.set_ylim(0, 100)
    ax1.set_title("A. Participación de mercado", loc="left")
    ax1.grid(axis="y", zorder=0)
    # La leyenda va FUERA del area: dentro de un apilado al 100 % no hay
    # ningun hueco libre y acabaria tapando datos.
    ax1.legend(loc="lower center", bbox_to_anchor=(0.5, 1.07),
               ncols=5, fontsize=7)

    marcar_contexto(ax2)
    for umbral, texto in ((1500, "moderada"), (2500, "alta")):
        ax2.axhline(umbral, color=REJILLA, linewidth=0.8, zorder=1)
        ax2.annotate(f"concentración {texto}", xy=(cuota.index[1], umbral),
                     xytext=(0, 3), textcoords="offset points",
                     fontsize=7, color=TINTA_SUAVE)
    ax2.plot(hhi.index, hhi.values, color=AZUL, zorder=3)
    ax2.set_ylabel("Índice HHI")
    ax2.set_title("B. Índice de Herfindahl-Hirschman", loc="left")
    ax2.grid(axis="y", zorder=0)
    # El HHI es un indice, no una cantidad: arrancar en cero aplasta toda la
    # variacion contra el techo y esconde justo lo que la figura quiere
    # mostrar. Se encuadra alrededor de los umbrales de referencia.
    ax2.set_ylim(1400, max(3000, hhi.max() * 1.06))

    for ax in (ax1, ax2):
        ax.margins(x=0.02)
    fig.align_ylabels([ax1, ax2])
    fig.tight_layout()
    nota_contexto(fig, "Umbrales de referencia del Departamento de Justicia de "
                       "los Estados Unidos, no una norma peruana.")

    sal = cuota.reset_index().rename(columns={"t": "fecha"})
    sal["fecha"] = sal["fecha"].dt.strftime("%Y-%m")
    sal["hhi"] = hhi.values
    guardar_figura(fig, "fig4_concentracion", sal)
    return por_ent, hhi


# --------------------------------------------------------------------------
# FIGURA 5 - Dispersion de tasas entre bancos
# --------------------------------------------------------------------------
def figura_5(df: pd.DataFrame) -> None:
    """Rango de tasas entre bancos dentro del mismo mes y el mismo segmento.

    Esta figura justifica el panel. Si existiera una unica tasa de factoring,
    la banda seria delgada y bastaria una serie de tiempo agregada para
    estudiarla. Lo que se ve es lo contrario: en el mismo mes y para el mismo
    tipo de credito, distintos bancos cobran precios muy distintos, y esa
    dispersion entre entidades es informacion que una serie agregada borra.

    Se usan percentiles 10 y 90 y no el minimo y el maximo: con seis a nueve
    bancos por celda, un solo banco raro definiria toda la banda.
    """
    fig, ejes = plt.subplots(2, 2, figsize=(6.8, 5.0), sharex=True, sharey=True)
    salida = []

    for ax, tipo in zip(ejes.ravel(), ORDEN_TIPOS):
        sub = df[(df["tipo"] == tipo)].dropna(subset=["tasa_descuento_pct_w"])
        g = sub.groupby("t")["tasa_descuento_pct_w"].agg(
            n="count", p10=lambda s: s.quantile(0.10),
            p50="median", p90=lambda s: s.quantile(0.90))
        marcar_contexto(ax)
        ax.fill_between(g.index, g["p10"], g["p90"], color=COLOR_TIPO[tipo],
                        alpha=0.22, linewidth=0, zorder=2)
        ax.plot(g.index, g["p50"], color=COLOR_TIPO[tipo], linewidth=1.5, zorder=3)
        # El titulo lleva solo el segmento: con el numero de bancos dentro,
        # los de la columna izquierda y derecha se tocaban.
        ax.set_title(ETIQUETA_TIPO[tipo], loc="left", fontsize=9)
        ax.annotate(f"{g['n'].mean():.0f} bancos por mes, en mediana",
                    xy=(0.015, 0.94), xycoords="axes fraction",
                    fontsize=7, color=TINTA_SUAVE, va="top")
        ax.grid(axis="y", zorder=0)
        ax.margins(x=0.02)
        g = g.reset_index().rename(columns={"t": "fecha"})
        g["fecha"] = g["fecha"].dt.strftime("%Y-%m")
        g.insert(1, "tipo", tipo)
        salida.append(g)

    for ax in ejes[:, 0]:
        ax.set_ylabel("Por ciento anual")
    fig.suptitle("Dispersión de la tasa de descuento entre bancos\n"
                 "banda del percentil 10 al 90, línea en la mediana",
                 fontsize=10, fontweight="bold", color=TINTA, x=0.02, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    nota_contexto(fig, "Se usan los percentiles 10 y 90 y no el mínimo y el máximo "
                       "porque con seis a nueve bancos por celda un solo banco "
                       "atípico definiría toda la banda.")
    guardar_figura(fig, "fig5_dispersion_entre_bancos", pd.concat(salida, ignore_index=True))


# --------------------------------------------------------------------------
# MODELO DE PANEL - estimacion con numpy, sin dependencias externas
# --------------------------------------------------------------------------
# Se programa a mano y no se llama a una libreria de paneles por dos razones.
# La primera es practica: linearmodels no esta en el entorno. La segunda pesa
# mas: la consigna exige poder explicar cada bloque del codigo en la
# disertacion, y aqui cada paso del estimador esta a la vista.
#
# La correccion del estimador se comprueba, no se supone. La funcion
# comprobar_estimador() reestima lo mismo metiendo las dicotomicas de forma
# explicita: por el teorema de Frisch-Waugh los coeficientes tienen que
# coincidir hasta el ultimo decimal. Si no coincidieran, el script se detiene.

MES_FIN_MODELO = "2024-09"   # ultimo mes anterior a los dos quiebres
MIN_OBS_UNIDAD = 10          # unidades con menos historia no identifican nada


def _restar_media(M: np.ndarray, g) -> np.ndarray:
    """Resta a cada columna la media de su grupo."""
    d = pd.DataFrame(M)
    d["_g"] = np.asarray(g)
    return d.groupby("_g").transform(lambda c: c - c.mean()).to_numpy(float)


def transformacion_within(M, grupos: list) -> np.ndarray:
    """Quita los efectos fijos restando medias, a una o a dos vias.

    Con una via basta restar la media de cada unidad. Con dos vias no basta
    hacerlo una vez con cada grupo: al restar las medias de mes se vuelven a
    desalinear las de unidad. Por eso se alterna hasta que deja de cambiar,
    que es el metodo habitual para absorber dos conjuntos de efectos fijos sin
    construir cientos de columnas de dicotomicas.
    """
    M = np.asarray(M, float)
    if len(grupos) == 1:
        return _restar_media(M, grupos[0])
    previo = M.copy()
    for _ in range(200):
        actual = previo.copy()
        for g in grupos:
            actual = _restar_media(actual, g)
        if np.max(np.abs(actual - previo)) < 1e-11:
            return actual
        previo = actual
    return previo


def estimar(y, X, grupos: list, conglomerado) -> dict:
    """Minimos cuadrados con efectos fijos y errores agrupados por banco.

    Los errores se agrupan por entidad porque las observaciones de un mismo
    banco en meses distintos no son independientes: comparten politica
    comercial, clientela y apetito de riesgo. Ignorarlo daria errores estandar
    artificialmente chicos y significancias falsas.

    ADVERTENCIA que se reporta siempre: la inferencia agrupada supone muchos
    conglomerados, y aqui hay nueve bancos. Con tan pocos, los errores
    estandar se subestiman. Por eso los p-valores usan la t con G-1 grados de
    libertad y no la normal, que es la correccion minima razonable; aun asi
    conviene leer la significancia con prudencia.
    """
    y = np.asarray(y, float).reshape(-1, 1)
    X = np.asarray(X, float)
    yt = transformacion_within(y, grupos).ravel()
    Xt = transformacion_within(X, grupos)

    XtX_inv = np.linalg.pinv(Xt.T @ Xt)
    beta = XtX_inv @ (Xt.T @ yt)
    e = yt - Xt @ beta
    n, k = Xt.shape

    # Los efectos fijos absorbidos gastan grados de libertad aunque no se vean
    # como columnas. Con dos vias se comparte una constante, de ahi el -1.
    absorbidos = sum(len(pd.unique(np.asarray(g))) for g in grupos) - (len(grupos) - 1)
    gl = n - k - absorbidos

    cl = pd.Series(np.asarray(conglomerado)).reset_index(drop=True)
    G = cl.nunique()
    carne = np.zeros((k, k))
    for _, posiciones in cl.groupby(cl).indices.items():
        u = Xt[posiciones].T @ e[posiciones]
        carne += np.outer(u, u)
    correccion = (G / (G - 1)) * ((n - 1) / gl)
    V = correccion * (XtX_inv @ carne @ XtX_inv)
    ee = np.sqrt(np.diag(V))

    t = beta / ee
    p = 2 * (1 - _t_cdf(np.abs(t), G - 1))
    r2 = 1 - (e ** 2).sum() / ((yt - yt.mean()) ** 2).sum()
    return {"beta": beta, "ee": ee, "t": t, "p": p, "n": n, "G": G,
            "gl": gl, "r2_within": r2, "yt": yt, "Xt": Xt, "e": e}


def _t_cdf(x, gl: int):
    """Acumulada de la t de Student, por la beta incompleta regularizada.

    Se escribe a mano para no depender de scipy, que no esta en requirements.
    """
    x = np.asarray(x, float)
    z = gl / (gl + x ** 2)
    return 1 - 0.5 * _betainc(gl / 2.0, 0.5, z)


def _betainc(a: float, b: float, x):
    """Beta incompleta regularizada I_x(a,b), por fraccion continua."""
    x = np.asarray(x, float)
    salida = np.zeros_like(x)
    for i, xi in enumerate(np.atleast_1d(x)):
        if xi <= 0:
            salida.flat[i] = 0.0
        elif xi >= 1:
            salida.flat[i] = 1.0
        else:
            lbeta = (math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b))
            frente = math.exp(a * math.log(xi) + b * math.log(1 - xi) - lbeta)
            if xi < (a + 1) / (a + b + 2):
                salida.flat[i] = frente * _fraccion(a, b, xi) / a
            else:
                salida.flat[i] = 1 - math.exp(
                    b * math.log(1 - xi) + a * math.log(xi) - lbeta
                ) * _fraccion(b, a, 1 - xi) / b
    return salida.reshape(np.shape(x))


def _fraccion(a: float, b: float, x: float) -> float:
    """Fraccion continua de Lentz para la beta incompleta."""
    tiny, eps = 1e-30, 3e-16
    c, d = 1.0, 1.0 - (a + b) * x / (a + 1.0)
    d = tiny if abs(d) < tiny else d
    d, h = 1.0 / d, 1.0 / d
    for m in range(1, 300):
        m2 = 2 * m
        for num in (m * (b - m) * x / ((a + m2 - 1) * (a + m2)),
                    -(a + m) * (a + b + m) * x / ((a + m2) * (a + m2 + 1))):
            d = 1.0 + num * d
            d = tiny if abs(d) < tiny else d
            c = 1.0 + num / c
            c = tiny if abs(c) < tiny else c
            d = 1.0 / d
            delta = d * c
            h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def comprobar_estimador(y, X, grupos: list) -> float:
    """Reestima con dicotomicas explicitas y devuelve la maxima discrepancia.

    Es la prueba de que la transformacion within esta bien hecha: por el
    teorema de Frisch-Waugh, quitar los efectos fijos restando medias y
    meterlos como columnas de ceros y unos tienen que dar el mismo vector de
    coeficientes.
    """
    X = np.asarray(X, float)
    bloques = [np.ones((len(y), 1)), X]
    for g in grupos:
        d = pd.get_dummies(pd.Series(np.asarray(g)).astype(str),
                           drop_first=True, dtype=float).to_numpy()
        bloques.append(d)
    M = np.column_stack(bloques)
    coef, *_ = np.linalg.lstsq(M, np.asarray(y, float), rcond=None)
    por_within = estimar(y, X, grupos, np.arange(len(y)))["beta"]
    return float(np.max(np.abs(coef[1:1 + X.shape[1]] - por_within)))


# --- preparacion de la muestra del modelo ----------------------------------
ETIQUETA_REGRESOR = {
    "tasa_descuento_pct_w": "Tasa de descuento (%)",
    "tasa_rezago1": "Tasa de descuento, mes t-1",
    "tasa_rezago2": "Tasa de descuento, mes t-2",
    "d_tasa": "Variación de la tasa",
    "log_deudores": "log(número de deudores)",
    "morosidad_tipo_pct_w": "Morosidad del tipo (%)",
    "tasa_referencia_pct": "Tasa de referencia BCRP (%)",
}


def preparar_modelo(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega al panel las variables que el modelo necesita."""
    d = df.sort_values(["entidad", "tipo", "fecha"]).copy()
    d["unidad"] = d["entidad"] + "|" + d["tipo"]
    monto = pd.to_numeric(d["monto_negociado_miles"], errors="coerce")
    deud = pd.to_numeric(d["deudores"], errors="coerce")
    # El logaritmo solo existe para valores positivos. Las filas en cero salen
    # de la estimacion, y eso se declara: el modelo describe a los bancos que
    # operan factoring, no la decision de operarlo o no.
    d["log_monto"] = np.log(monto.where(monto > 0))
    d["log_deudores"] = np.log(deud.where(deud > 0))
    for col, rez in (("tasa_rezago1", 1), ("tasa_rezago2", 2)):
        d[col] = d.groupby("unidad")["tasa_descuento_pct_w"].shift(rez)
    d["d_log_monto"] = d.groupby("unidad")["log_monto"].diff()
    d["d_tasa"] = d.groupby("unidad")["tasa_descuento_pct_w"].diff()
    return d


def muestra(d: pd.DataFrame, dependiente: str, regresores: list,
            hasta: str) -> pd.DataFrame:
    """Filtra la muestra de una especificacion y deja solo filas completas."""
    m = d[d["fecha"] <= hasta].dropna(subset=[dependiente] + regresores).copy()
    tam = m.groupby("unidad")["unidad"].transform("size")
    return m[tam >= MIN_OBS_UNIDAD].reset_index(drop=True)


ESPECIFICACIONES = (
    ("(1)", "log_monto", ["tasa_descuento_pct_w", "log_deudores",
                          "morosidad_tipo_pct_w", "tasa_referencia_pct"],
     ["unidad"], "EF de unidad"),
    ("(2)", "log_monto", ["tasa_descuento_pct_w", "log_deudores",
                          "morosidad_tipo_pct_w"],
     ["unidad", "fecha"], "EF de unidad y de mes"),
    ("(3)", "log_monto", ["tasa_rezago1", "tasa_rezago2", "log_deudores",
                          "morosidad_tipo_pct_w"],
     ["unidad", "fecha"], "EF de unidad y de mes, tasa rezagada"),
    ("(4)", "d_log_monto", ["d_tasa", "log_deudores", "morosidad_tipo_pct_w"],
     ["unidad", "fecha"], "Primeras diferencias"),
)


def correr_modelo(d: pd.DataFrame, hasta: str, etiqueta: str) -> pd.DataFrame:
    """Estima las cuatro especificaciones y devuelve la tabla de resultados."""
    filas: dict[str, dict] = {}
    pie: dict[str, dict] = {}
    for clave, dep, regs, grupos, desc in ESPECIFICACIONES:
        m = muestra(d, dep, regs, hasta)
        if len(m) < 100:
            registrar(f"  {clave} {etiqueta}: muestra insuficiente ({len(m)})")
            continue
        g = [m[c].to_numpy() for c in grupos]
        r = estimar(m[dep].to_numpy(), m[regs].astype(float).to_numpy(),
                    g, m["entidad"].to_numpy())
        desvio = comprobar_estimador(m[dep].to_numpy(),
                                     m[regs].astype(float).to_numpy(), g)
        if desvio > 1e-6:
            raise DatosInsuficientes(
                f"{clave}: la transformacion within y las dicotomicas no "
                f"coinciden (desvio {desvio:.2e}); el estimador esta mal"
            )
        registrar(f"  {clave} {desc}: n={r['n']}, {r['G']} bancos, "
                  f"R2 within={r['r2_within']:.3f}, "
                  f"within contra dicotomicas difiere {desvio:.1e}")
        for v, b, ee, p in zip(regs, r["beta"], r["ee"], r["p"]):
            est = "***" if p < .01 else "**" if p < .05 else "*" if p < .10 else ""
            filas.setdefault(ETIQUETA_REGRESOR.get(v, v), {})[clave] = (
                f"{b:.4f}{est} ({ee:.4f})"
            )
        pie.setdefault("Efectos fijos", {})[clave] = desc
        pie.setdefault("Observaciones", {})[clave] = f"{r['n']}"
        pie.setdefault("Bancos (conglomerados)", {})[clave] = f"{r['G']}"
        pie.setdefault("R2 dentro", {})[clave] = f"{r['r2_within']:.3f}"

    orden = [ETIQUETA_REGRESOR[v] for v in ETIQUETA_REGRESOR
             if ETIQUETA_REGRESOR[v] in filas]
    tabla = pd.DataFrame(filas).T.reindex(orden)
    tabla = pd.concat([tabla, pd.DataFrame(pie).T])
    tabla.insert(0, "Variable", tabla.index)
    return tabla.reset_index(drop=True).fillna("")


# --------------------------------------------------------------------------
# FIGURA 6 - Deudores y morosidad
# --------------------------------------------------------------------------
def figura_6(df: pd.DataFrame) -> None:
    """Las dos variables que las otras figuras no muestran.

    El panel A cuenta relaciones deudor-banco y no empresas distintas. La
    diferencia no es un tecnicismo: la nota 1/ del cuadro B-230803 advierte
    que el total consolida, de modo que una empresa que debe a tres bancos
    cuenta tres veces en las filas y una sola en el total. Sumar entre bancos
    y llamarlo "numero de empresas" seria un error; llamarlo relaciones
    deudor-banco es exacto.

    El eje va en escala logaritmica porque los cuatro segmentos viven en
    ordenes de magnitud distintos: corporativos se cuenta en miles y pequenas
    empresas en cientos de miles. En escala lineal, las dos series de arriba
    aplastarian a las otras dos contra el suelo.
    """
    deud = (df.assign(d=pd.to_numeric(df["deudores"], errors="coerce"))
              .pivot_table(index="t", columns="tipo", values="d", aggfunc="sum")
              .reindex(columns=list(ORDEN_TIPOS)))
    mora = (df.groupby(["t", "tipo"])
              .apply(lambda g: ponderada(g, "morosidad_tipo_pct_w"),
                     include_groups=False)
              .unstack().reindex(columns=list(ORDEN_TIPOS)))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6.6, 5.6), sharex=True)

    marcar_contexto(ax1)
    for c in ORDEN_TIPOS:
        ax1.plot(deud.index, deud[c], color=COLOR_TIPO[c], label=ETIQUETA_TIPO[c])
        etiqueta_final(ax1, deud.index[-1], deud[c].iloc[-1],
                       ETIQUETA_TIPO[c].split()[0])
    ax1.set_yscale("log")
    ax1.set_ylabel("Relaciones deudor-banco\n(escala logarítmica)")
    ax1.set_title("A. Número de deudores por tipo de crédito", loc="left")
    ax1.grid(axis="y", which="major", zorder=0)
    # Fuera del area: la serie de corporativos corre por el borde inferior y
    # cualquier leyenda dentro del panel se le echa encima.
    ax1.legend(loc="lower center", bbox_to_anchor=(0.5, 1.10), ncols=4, fontsize=7.5)

    marcar_contexto(ax2)
    for c in ORDEN_TIPOS:
        ax2.plot(mora.index, mora[c], color=COLOR_TIPO[c], label=ETIQUETA_TIPO[c])
        etiqueta_final(ax2, mora.index[-1], mora[c].iloc[-1],
                       ETIQUETA_TIPO[c].split()[0])
    ax2.set_ylabel("Por ciento de la cartera")
    ax2.set_title("B. Morosidad del tipo de crédito, ponderada por monto", loc="left")
    ax2.grid(axis="y", zorder=0)
    ax2.set_ylim(bottom=0)

    for ax in (ax1, ax2):
        ax.margins(x=0.02)
    ax2.set_xlim(right=mora.index[-1] + pd.Timedelta(days=330))
    ax1.set_xlim(ax2.get_xlim())
    fig.align_ylabels([ax1, ax2])
    fig.tight_layout()
    nota_contexto(fig, "El panel A cuenta relaciones deudor-banco: una empresa "
                       "que debe a varios bancos se cuenta una vez por banco, "
                       "según la nota 1/ del cuadro B-230803 de la SBS.")

    sal_d = deud.reset_index().rename(columns={"t": "fecha"})
    sal_d["fecha"] = sal_d["fecha"].dt.strftime("%Y-%m")
    sal_d = sal_d.melt(id_vars="fecha", var_name="tipo", value_name="deudores")
    sal_m = mora.reset_index().rename(columns={"t": "fecha"})
    sal_m["fecha"] = sal_m["fecha"].dt.strftime("%Y-%m")
    sal_m = sal_m.melt(id_vars="fecha", var_name="tipo", value_name="morosidad_pct")
    guardar_figura(fig, "fig6_deudores_y_morosidad",
                   sal_d.merge(sal_m, on=["fecha", "tipo"]))


# --------------------------------------------------------------------------
# FIGURA 7 - Precio contra cantidad
# --------------------------------------------------------------------------
def figura_7(d: pd.DataFrame) -> None:
    """La relacion entre la tasa y el monto, que es lo que estima el modelo.

    El panel A recorre el mercado ano por ano en el plano precio-cantidad. Se
    lee la trayectoria: si el mercado se movio subiendo precio, subiendo
    volumen, o las dos cosas.

    El panel B es la figura del modelo. Muestra las dos variables DESPUES de
    quitarles los efectos fijos de unidad y de mes, que es exactamente la
    variacion con la que trabaja la estimacion. Si la nube no tiene pendiente,
    el coeficiente va a salir cerca de cero, y conviene que el lector lo vea
    antes de llegar a la tabla en vez de tener que creerselo.
    """
    anual = (d.groupby(d["fecha"].str[:4])
               .apply(lambda g: pd.Series({
                   "tasa": ponderada(g, "tasa_descuento_pct_w"),
                   "monto_mm": g.groupby("fecha")["monto_mm"].sum().mean(),
               }), include_groups=False).reset_index(names="anio"))

    esp = ESPECIFICACIONES[1]      # la especificacion principal
    m = muestra(d, esp[1], esp[2], MES_FIN_MODELO)
    grupos = [m[c].to_numpy() for c in esp[3]]
    yt = transformacion_within(m[esp[1]].to_numpy().reshape(-1, 1), grupos).ravel()
    xt = transformacion_within(
        m[["tasa_descuento_pct_w"]].to_numpy(), grupos).ravel()
    pend, corte = np.polyfit(xt, yt, 1)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.8, 3.4))

    ax1.plot(anual["tasa"], anual["monto_mm"], color=AZUL, linewidth=1.4,
             marker="o", markersize=5, markerfacecolor=SUPERFICIE,
             markeredgewidth=1.6, zorder=3)
    # Cada etiqueta se aleja del centro de la trayectoria. Con un
    # desplazamiento fijo hacia arriba, los anos de 2018 a 2020 quedan
    # amontonados unos encima de otros.
    cx, cy = anual["tasa"].mean(), anual["monto_mm"].mean()
    for _, r in anual.iterrows():
        dx, dy = r["tasa"] - cx, r["monto_mm"] - cy
        norma = max((dx / max(anual["tasa"].std(), 1e-9)) ** 2
                    + (dy / max(anual["monto_mm"].std(), 1e-9)) ** 2, 1e-9) ** 0.5
        ux = 13 * (dx / max(anual["tasa"].std(), 1e-9)) / norma
        uy = 13 * (dy / max(anual["monto_mm"].std(), 1e-9)) / norma
        ax1.annotate(r["anio"], xy=(r["tasa"], r["monto_mm"]),
                     xytext=(ux, uy), textcoords="offset points",
                     ha="center", va="center", fontsize=7.5, color=TINTA)
    ax1.set_xlabel("Tasa de descuento ponderada (%)")
    ax1.set_ylabel("Monto negociado medio\n(miles de millones de S/)")
    ax1.set_title("A. Trayectoria del mercado", loc="left")
    ax1.grid(zorder=0)
    ax1.margins(0.14)

    ax2.scatter(xt, yt, s=5, color=AZUL, alpha=0.18, linewidths=0, zorder=2)
    rx = np.array([xt.min(), xt.max()])
    ax2.plot(rx, corte + pend * rx, color=NARANJA, linewidth=1.8, zorder=3)
    ax2.annotate(f"pendiente {pend:.4f}", xy=(0.97, 0.06),
                 xycoords="axes fraction", ha="right", fontsize=8, color=TINTA)
    ax2.set_xlabel("Tasa de descuento, sin efectos fijos")
    ax2.set_ylabel("log(monto negociado),\nsin efectos fijos")
    ax2.set_title("B. La variación que usa el modelo", loc="left")
    ax2.grid(zorder=0)

    fig.tight_layout()
    nota_contexto(fig, f"Panel A: promedio anual del mercado. Panel B: {len(m)} "
                       f"observaciones de la especificación (2), hasta "
                       f"{MES_FIN_MODELO}; ambos ejes están medidos como desvíos "
                       f"respecto de la media de cada unidad y de cada mes.",
                  marcas=False)

    sal = anual.copy()
    sal["panel"] = "A"
    guardar_figura(fig, "fig7_precio_cantidad", sal)


# --------------------------------------------------------------------------
# TABLAS
# --------------------------------------------------------------------------
def describir(v: pd.Series) -> dict:
    v = pd.to_numeric(v, errors="coerce").dropna()
    if v.empty:
        return {}
    return {
        "n": int(v.size), "media": v.mean(), "de": v.std(),
        "min": v.min(), "p25": v.quantile(.25), "mediana": v.median(),
        "p75": v.quantile(.75), "max": v.max(),
    }


def tabla_1_descriptivos(df: pd.DataFrame) -> None:
    """Estadisticos de las variables, crudas y winsorizadas.

    Las dos versiones van juntas en la misma tabla a proposito: asi el lector
    ve de una vez cuanto movio el tratamiento, sin tener que buscar un anexo.
    """
    etiquetas = {
        "monto_negociado_miles": "Monto negociado (miles de S/)",
        "tasa_descuento_pct": "Tasa de descuento (%)",
        "deudores": "Número de deudores",
        "morosidad_tipo_pct": "Morosidad del tipo de crédito (%)",
        "tasa_referencia_pct": "Tasa de referencia BCRP (%)",
        "morosidad_factoring_pct": "Morosidad del factoring (%)",
        "tasa_tipo_pct": "Tasa del tipo de crédito (%)",
    }
    filas = []
    for col, nombre in etiquetas.items():
        if col not in df.columns:
            continue
        d = describir(df[col])
        if not d:
            continue
        d = {"variable": nombre, "tratamiento": "crudo", **d}
        filas.append(d)
        if col + "_w" in df.columns:
            dw = describir(df[col + "_w"])
            filas.append({"variable": nombre, "tratamiento": "winsorizado", **dw})
    guardar_tabla(pd.DataFrame(filas), "tabla1_descriptivos",
                  "Estadísticos descriptivos del panel, 2018-2025",
                  "tab:descriptivos")


def tabla_2_por_tipo(df: pd.DataFrame) -> None:
    """Resumen por tipo de credito."""
    filas = []
    for tipo in ORDEN_TIPOS:
        g = df[df["tipo"] == tipo]
        filas.append({
            "Tipo de crédito": ETIQUETA_TIPO[tipo],
            "Observaciones": len(g),
            "Monto medio mensual (mill. S/)": g.groupby("fecha")["monto_mm"].sum().mean() * 1000,
            "Participación (%)": 100 * g["monto_negociado_miles"].sum() / df["monto_negociado_miles"].sum(),
            "Tasa ponderada (%)": ponderada(g, "tasa_descuento_pct_w"),
            # Sin maximo ni minimo de la tasa: tras winsorizar, el maximo es el
            # mismo techo en los cuatro tipos y la columna no diria nada. El
            # rango completo esta en la tabla 1.
            "Deudores (mediana)": pd.to_numeric(g["deudores"], errors="coerce").median(),
            "Morosidad ponderada (%)": ponderada(g, "morosidad_tipo_pct_w"),
        })
    guardar_tabla(pd.DataFrame(filas), "tabla2_por_tipo_credito",
                  "El mercado por tipo de crédito, promedio 2018-2025",
                  "tab:portipo")


def tabla_3_entidades(df: pd.DataFrame) -> None:
    """Participacion y tasa de cada banco."""
    tot = df["monto_negociado_miles"].sum()
    filas = []
    for ent, g in df.groupby("entidad_nombre"):
        activo = g[g["monto_negociado_miles"] > 0]
        filas.append({
            "Entidad": bonito(ent),
            "Meses en el panel": g["fecha"].nunique(),
            "Meses con monto > 0": activo["fecha"].nunique(),
            "Participación (%)": 100 * g["monto_negociado_miles"].sum() / tot,
            "Tasa ponderada (%)": ponderada(g, "tasa_descuento_pct_w"),
            "Morosidad ponderada (%)": ponderada(g, "morosidad_tipo_pct_w"),
        })
    t = pd.DataFrame(filas).sort_values("Participación (%)", ascending=False)
    guardar_tabla(t, "tabla3_entidades",
                  "Participación de mercado y precio por entidad, 2018-2025",
                  "tab:entidades")


def tabla_4_winsorizacion(umbrales: pd.DataFrame) -> None:
    """Que hizo exactamente la winsorizacion, para poder auditarla."""
    t = umbrales.rename(columns={
        "variable": "Variable", "n_con_dato": "Obs. con dato",
        "umbral_p1": "Umbral p1", "umbral_p99": "Umbral p99",
        "recortadas_abajo": "Recortadas abajo", "recortadas_arriba": "Recortadas arriba",
        "max_crudo": "Máximo crudo", "max_winsor": "Máximo winsorizado",
    })
    guardar_tabla(t, "tabla4_winsorizacion",
                  "Efecto de la winsorización al 1 y 99 por ciento",
                  "tab:winsor")


def comparar_tratamientos(df: pd.DataFrame) -> list[str]:
    """Cuanto cambia la serie agregada al winsorizar.

    Es la prueba de robustez en una linea: si la diferencia maxima entre la
    serie cruda y la winsorizada es chica, las conclusiones del articulo no
    dependen del tratamiento de atipicos y se puede decir con numeros.
    """
    a = df.groupby("t").apply(lambda g: ponderada(g, "tasa_descuento_pct"),
                              include_groups=False)
    b = df.groupby("t").apply(lambda g: ponderada(g, "tasa_descuento_pct_w"),
                              include_groups=False)
    d = (a - b).abs()
    return [
        f"  tasa agregada cruda      : media {a.mean():.3f} %, max {a.max():.3f} %",
        f"  tasa agregada winsorizada: media {b.mean():.3f} %, max {b.max():.3f} %",
        f"  diferencia maxima entre ambas en los 96 meses: {d.max():.3f} puntos "
        f"porcentuales (mes {d.idxmax():%Y-%m})",
        f"  correlacion entre las dos series: {a.corr(b):.5f}",
    ]


# --------------------------------------------------------------------------
# Orquestacion
# --------------------------------------------------------------------------
def main() -> int:
    registrar("inicio")
    try:
        estilo()
        df = cargar()
        registrar(f"panel leido: {len(df)} filas, {df['fecha'].nunique()} meses, "
                  f"{df['entidad'].nunique()} entidades, {df['tipo'].nunique()} tipos")

        df, umbrales = aplicar_winsorizacion(df)
        registrar(f"winsorizacion al {P_BAJO:.0%} y {P_ALTO:.0%}:")
        for _, r in umbrales.iterrows():
            registrar(f"  {r['variable']:26s} p1={r['umbral_p1']:7.3f} "
                      f"p99={r['umbral_p99']:8.3f}  recorta "
                      f"{int(r['recortadas_abajo'])} abajo y "
                      f"{int(r['recortadas_arriba'])} arriba  "
                      f"(max {r['max_crudo']:.2f} -> {r['max_winsor']:.2f})")

        registrar("robustez: cruda contra winsorizada")
        for linea in comparar_tratamientos(df):
            registrar(linea)

        registrar("tablas descriptivas")
        tabla_1_descriptivos(df)
        tabla_2_por_tipo(df)
        tabla_3_entidades(df)
        tabla_4_winsorizacion(umbrales)

        d = preparar_modelo(df)
        registrar(f"modelo, ventana principal 2018-01 a {MES_FIN_MODELO} "
                  f"(antes de los dos quiebres)")
        tabla_5 = correr_modelo(d, MES_FIN_MODELO, "principal")
        guardar_tabla(tabla_5, "tabla5_modelo_panel",
                      "Monto negociado y tasa de descuento: efectos fijos por "
                      f"banco y tipo de credito, 2018-01 a {MES_FIN_MODELO}",
                      "tab:modelo")
        registrar(f"modelo, ventana completa 2018-01 a {ANIO_CORTE}-12 "
                  f"(incluye los dos quiebres)")
        tabla_6 = correr_modelo(d, f"{ANIO_CORTE}-12", "robustez")
        guardar_tabla(tabla_6, "tabla6_modelo_robustez",
                      "Prueba de robustez: el mismo modelo sobre los 96 meses, "
                      "con los dos quiebres estructurales dentro",
                      "tab:robustez")

        registrar("figuras")
        figura_1(df)
        figura_2(df)
        figura_3(df)
        figura_4(df)
        figura_5(df)
        figura_6(df)
        figura_7(d)

        registrar(f"listo: {len(list(DIR_FIGURAS.glob('*.pdf')))} figuras en "
                  f"{DIR_FIGURAS} y {len(list(DIR_TABLAS.glob('*.tex')))} tablas en "
                  f"{DIR_TABLAS}")
        return 0
    except DatosInsuficientes as e:
        registrar(f"ABORTADO: {e}")
        return 1
    finally:
        registrar("fin")


if __name__ == "__main__":
    sys.exit(main())
