# Santiago Piero Camayo Jimenez
# 2024200488G
# Tema N.o 91 - El factoring como instrumento de financiamiento de corto plazo en el Peru (Unidad II)
# Fecha de ejecucion: la que registre log_ejecucion.txt

"""Verificacion del quiebre del Banco de Credito en enero de 2025.

El panel muestra que el BCP pasa de S/ 3 244 millones de factoring en
diciembre de 2024 a cero en enero de 2025, y que su total de factoring mas
descuentos cae a la mitad. Como el BCP es el 39 % del mercado, de que sea una
cosa o la otra depende si la serie de 2025 sirve o no.

Hay dos explicaciones posibles y este script las distingue:

  (1) RECLASIFICACION INTERNA. El banco movio esa cartera a otra fila del
      mismo cuadro, por ejemplo a Prestamos. Entonces el total del tipo de
      credito casi no cambia, y la caida del factoring aparece como subida en
      otra modalidad. La cartera sigue existiendo; lo que cambio es la
      etiqueta, y hay que decirlo en el articulo.

  (2) SALIDA REAL. La cartera dejo de estar en el balance. Entonces el total
      del tipo cae en una magnitud parecida a la del factoring.

La prueba es el renglon que encabeza cada bloque, que es el total del tipo de
credito. Si ese total se mueve poco mientras el factoring se va a cero, es (1).

Compara ademas la columna Total Banca Multiple, para saber si fue solo el BCP
o todo el sistema, y revisa a los demas bancos uno por uno.

NO modifica nada: abre los dos XLS crudos solo para leer.

Entradas : datos_crudos/sbs_xls/B-2359-di2024.XLS
           datos_crudos/sbs_xls/B-2359-en2025.XLS
Salidas  : salidas/verificacion_quiebre_bcp.txt (y lo mismo en consola)
"""

from __future__ import annotations

import importlib.util
import sys
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
ARCHIVO_SALIDA = RAIZ / "salidas" / "verificacion_quiebre_bcp.txt"
ARCHIVO_LOG = RAIZ / "log_ejecucion.txt"

# 03_limpieza_datos.py empieza con un numero y no se puede importar con un
# import normal. Se reutiliza su codigo a proposito: si escribiera un lector
# nuevo podria no tener el mismo comportamiento y la verificacion no probaria
# nada sobre el panel que ya generamos.
_spec = importlib.util.spec_from_file_location("limpieza", CODIGO / "03_limpieza_datos.py")
L = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(L)

import entidades  # noqa: E402

MES_ANTES = ("B-2359-di2024.XLS", "dic-2024")
MES_DESPUES = ("B-2359-en2025.XLS", "ene-2025")
ENTIDAD = "credito"                 # el BCP, segun entidades.py

# Caida minima del factoring, como fraccion del total del tipo, para que el
# veredicto signifique algo. Por debajo de este umbral el vaiven mensual
# corriente de las otras filas es mayor que lo que se quiere medir, y el
# cociente se vuelve ruido: en pequenas empresas, una caida de 5 millones
# sobre una cartera de 19 423 daria un cociente de 56 que no dice nada.
MIN_CAIDA_RELATIVA = 0.01

lineas: list[str] = []


def di(texto: str = "") -> None:
    print(texto, flush=True)
    lineas.append(texto)


def registrar(mensaje: str) -> None:
    marca = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linea = f"[{marca}] verificar_quiebre_bcp | {mensaje}"
    print(linea, flush=True)
    with ARCHIVO_LOG.open("a", encoding="utf-8") as f:
        f.write(linea + "\n")


def leer_bloques(ruta: Path, entidad: str) -> dict[str, dict[str, float]]:
    """Devuelve {tipo: {etiqueta de fila: monto en millones}} de una entidad.

    Incluye TODAS las modalidades, no solo factoring y descuentos, porque la
    pregunta es justamente a que otra fila se fue la cartera. La clave
    "__total__" guarda el renglon que encabeza el bloque, que es el total del
    tipo de credito.
    """
    df = L.leer_xls(ruta)
    fila = L.fila_de_encabezado(df)
    columnas = L.columnas_totales_2359(df, fila)
    if entidad not in columnas:
        raise L.LecturaFallida(f"{ruta.name}: {entidad} no aparece en el cuadro")
    _, _, c_total = columnas[entidad]

    bloques: dict[str, dict[str, float]] = {}
    tipo_actual = None
    for i in range(fila + 2, len(df)):
        etiqueta = df.iat[i, 0]
        if not (isinstance(etiqueta, str) and etiqueta.strip()):
            continue
        etiqueta = etiqueta.strip()
        cabecera = L.encabezado_de_tipo(etiqueta)
        valor = L.a_numero(df.iat[i, c_total])
        valor = 0.0 if valor is None else valor / 1e3      # miles -> millones

        if cabecera is not None:
            tipo_actual = cabecera if cabecera in L.TIPOS_INCLUIDOS_ID else None
            if tipo_actual is not None:
                bloques[tipo_actual] = {"__total__": valor}
            continue
        if tipo_actual is not None:
            bloques[tipo_actual][etiqueta] = valor
    return bloques


def comparar(antes: dict, despues: dict, titulo: str) -> None:
    """Imprime el antes y el despues de cada bloque y emite un veredicto."""
    di("")
    di("=" * 78)
    di(titulo)
    di("=" * 78)

    for tipo in L.TIPOS_INCLUIDOS_ID:
        a, b = antes.get(tipo, {}), despues.get(tipo, {})
        if not a or not b:
            continue
        di("")
        di(f"{L.NOMBRES_TIPO[tipo].upper()}   (millones de soles, columna Total)")
        di(f"  {'fila del cuadro':38s} {MES_ANTES[1]:>11s} {MES_DESPUES[1]:>11s} {'cambio':>11s}")

        etiquetas = list(dict.fromkeys(list(a) + list(b)))
        for etq in etiquetas:
            va, vb = a.get(etq, 0.0), b.get(etq, 0.0)
            marca = ""
            if L.modalidad_de(etq) == "factoring":
                marca = "  <--"
            nombre = "TOTAL DEL TIPO" if etq == "__total__" else etq[:38]
            di(f"  {nombre:38s} {va:11,.0f} {vb:11,.0f} {vb - va:+11,.0f}{marca}")

        # --- veredicto ---
        tot_a, tot_b = a.get("__total__", 0.0), b.get("__total__", 0.0)
        fact_a = sum(v for k, v in a.items() if L.modalidad_de(k) == "factoring")
        fact_b = sum(v for k, v in b.items() if L.modalidad_de(k) == "factoring")
        caida = fact_a - fact_b
        cambio_total = 100 * (tot_b - tot_a) / tot_a if tot_a else float("nan")

        subidas = sorted(
            ((etq, b.get(etq, 0.0) - a.get(etq, 0.0))
             for etq in etiquetas
             if etq != "__total__" and L.modalidad_de(etq) != "factoring"),
            key=lambda x: -x[1],
        )
        di("")
        di(f"  el factoring cae {caida:,.0f} millones; el total del tipo cambia "
           f"{tot_b - tot_a:+,.0f} millones ({cambio_total:+.1f} %)")
        if subidas and subidas[0][1] > 0:
            etq, sube = subidas[0]
            cobertura = f" ({100 * sube / caida:.0f} % de la caida)" if caida > 0 else ""
            di(f"  la fila que mas sube es «{etq}» con {sube:+,.0f} millones{cobertura}")

        if caida <= 0:
            di("  VEREDICTO: en este tipo el factoring no cayo.")
            continue

        # La comparacion correcta no es contra el TAMANO del total sino contra
        # la CAIDA del factoring. Un banco grande puede perder toda su cartera
        # de factoring y que eso sea un 4 % de su credito total: mirar ese 4 %
        # haria concluir "casi no se movio" cuando en realidad se fue entera.
        peso = caida / tot_a if tot_a else 0.0
        if peso < MIN_CAIDA_RELATIVA:
            di(f"  la caida del factoring es el {100 * peso:.2f} % de la cartera "
               f"del tipo, por debajo del {100 * MIN_CAIDA_RELATIVA:.0f} % minimo")
            di("  SIN VEREDICTO: el monto es demasiado pequeno. La variacion normal")
            di("  de las otras filas de un mes a otro es mayor que la caida que se")
            di("  quiere explicar, asi que cualquier conclusion seria ruido.")
            continue

        salida = (tot_a - tot_b) / caida
        di(f"  de cada sol que pierde el factoring, el total del tipo pierde "
           f"{salida:.2f}")
        if salida < 0.25:
            di("  VEREDICTO: reclasificacion interna. El total del tipo se queda")
            di("  donde estaba, asi que la cartera sigue en el balance y lo que")
            di("  cambio fue la fila en que el banco la reporta.")
        elif salida > 0.75:
            di("  VEREDICTO: salida real. El total del tipo cae casi lo mismo que")
            di("  el factoring, de modo que esa cartera dejo el balance y no se")
            di("  mudo a otra fila.")
        else:
            di("  VEREDICTO: mixto. Parte de la cartera cambio de fila y parte")
            di("  dejo el balance. Hay que mirar el detalle fila por fila.")


def revisar_los_demas(ruta_a: Path, ruta_b: Path) -> None:
    """Dice que otros bancos movieron su factoring entre los dos meses."""
    di("")
    di("=" * 78)
    di("LOS DEMAS BANCOS: variacion del factoring entre los dos meses")
    di("=" * 78)
    df_a, df_b = L.leer_xls(ruta_a), L.leer_xls(ruta_b)
    col_a = L.columnas_totales_2359(df_a, L.fila_de_encabezado(df_a))
    col_b = L.columnas_totales_2359(df_b, L.fila_de_encabezado(df_b))

    filas = []
    for ent in sorted(set(col_a) & set(col_b)):
        try:
            a = leer_bloques(ruta_a, ent)
            b = leer_bloques(ruta_b, ent)
        except L.LecturaFallida:
            continue
        fa = sum(v for t in a.values() for k, v in t.items()
                 if L.modalidad_de(k) == "factoring")
        fb = sum(v for t in b.values() for k, v in t.items()
                 if L.modalidad_de(k) == "factoring")
        filas.append((entidades.nombre_legible(ent), fa, fb, fb - fa))

    filas.sort(key=lambda x: x[3])
    di(f"  {'entidad':38s} {MES_ANTES[1]:>11s} {MES_DESPUES[1]:>11s} {'cambio':>11s}")
    for n, fa, fb, d in filas:
        aviso = "  <-- se va a cero" if fa > 100 and fb == 0 else ""
        di(f"  {n[:38]:38s} {fa:11,.0f} {fb:11,.0f} {d:+11,.0f}{aviso}")
    di("")
    di(f"  total del sistema: {sum(f[1] for f in filas):,.0f} -> "
       f"{sum(f[2] for f in filas):,.0f} millones "
       f"({sum(f[3] for f in filas):+,.0f})")


def main() -> int:
    registrar("inicio")
    ARCHIVO_SALIDA.parent.mkdir(parents=True, exist_ok=True)
    ruta_a = L.DIR_XLS / MES_ANTES[0]
    ruta_b = L.DIR_XLS / MES_DESPUES[0]
    for r in (ruta_a, ruta_b):
        if not r.exists():
            registrar(f"ABORTADO: no existe {r}")
            return 1

    di("VERIFICACION DEL QUIEBRE DEL BANCO DE CREDITO EN ENERO DE 2025")
    di(f"Generado el {datetime.now():%Y-%m-%d %H:%M:%S}")
    di(f"Fuentes: {MES_ANTES[0]} y {MES_DESPUES[0]}")
    di(f"  sha256 {MES_ANTES[0]}: {L.sha256_archivo(ruta_a)}")
    di(f"  sha256 {MES_DESPUES[0]}: {L.sha256_archivo(ruta_b)}")

    try:
        comparar(leer_bloques(ruta_a, ENTIDAD), leer_bloques(ruta_b, ENTIDAD),
                 f"{entidades.nombre_legible(ENTIDAD)}, todas las modalidades")
        revisar_los_demas(ruta_a, ruta_b)
    except (L.LecturaFallida, entidades.EntidadDesconocida) as e:
        registrar(f"ABORTADO: {e}")
        return 1

    ARCHIVO_SALIDA.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    registrar(f"informe escrito en {ARCHIVO_SALIDA}")
    registrar("fin")
    return 0


if __name__ == "__main__":
    sys.exit(main())
