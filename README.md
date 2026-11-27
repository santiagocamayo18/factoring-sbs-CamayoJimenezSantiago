# El factoring como instrumento de financiamiento de corto plazo en el Perú

**Santiago Piero Camayo Jiménez** · Código 2024200488G
Escuela Profesional de Economía · Facultad de Economía · UNCP
Finanzas I (055D) · Periodo 2026-II · **Unidad II · Tema N.º 91**

Repositorio: <https://github.com/santiagocamayo18/factoring-sbs-CamayoJimenezSantiago>

---

## Qué hace este repositorio

Construye, desde cero y con código, un **panel mensual del mercado bancario
peruano de factoring y descuentos** entre enero de 2018 y diciembre de 2025, y
genera con él todas las tablas y figuras del artículo.

El objetivo del tema es analizar la evolución del monto negociado y de la tasa
de descuento. Para eso se combinan dos vías de extracción independientes:

| Vía | Fuente | Qué aporta |
|---|---|---|
| **1 · API** | BCRP, BCRPData REST | Tasa preferencial corporativa a 90 días (serie `PN07809NM`) |
| **2 · Descarga programática** | SBS, cuadros estadísticos | Saldos por modalidad, morosidad y número de deudores |
| **2 · Scraping** | SBS, portal SAEE | Tasa de descuento por banco y tipo de crédito |

**Resultado:** 6 324 observaciones, 96 meses, 20 bancos, 4 tipos de crédito.
Las dos vías participan en resultados del artículo: la vía 1 aparece en la
Figura 1, en la Tabla 1 y como regresor en la columna (1) de la Tabla 5.

---

## Cómo ejecutarlo

### Requisitos

Python 3.11 o superior. Las dependencias están en `requirements.txt`:

```
pip install -r requirements.txt
```

Con Anaconda:

```
conda create -n finanzas_pt python=3.11
conda activate finanzas_pt
pip install -r requirements.txt
```

**No hace falta ninguna clave de API.** El servicio BCRPData es público y no
requiere autenticación. El archivo `.env.example` se entrega igual, con los
nombres de las variables de entorno que el proyecto reconoce, por si se
quisiera apuntar a otro servidor.

### Orden de ejecución

Los scripts se corren **en orden** desde la raíz del proyecto. Cada uno deja
constancia de lo que hizo en `log_ejecucion.txt`.

```
python codigo/01_extraccion_api.py      # vía 1 · unos segundos
python codigo/02_scraping_web.py        # vía 2 · unos 15 minutos
python codigo/03_limpieza_datos.py      # limpieza y unión · 1 a 3 minutos
python codigo/04_analisis.py            # tablas y figuras · unos 20 segundos
```

`02_scraping_web.py` tiene dos interruptores al inicio del archivo:
`MODO_PRUEBA` descarga solo tres meses para comprobar que todo funciona antes
de la corrida larga, y `MODO_DIAGNOSTICO` guarda el formulario del portal para
inspeccionarlo. Ambos deben estar en `False` para la corrida completa.

`03_limpieza_datos.py` tiene `MODO_INVENTARIO`: en `True` recorre los archivos
crudos y levanta el censo de entidades y etiquetas con el que se construyó
`codigo/entidades.py`; en `False`, que es como se entrega, genera el panel.

### Scripts auxiliares

En `codigo/verificacion/` hay tres programas que **no forman parte del flujo**
y solo se usan para auditar los datos. No modifican nada: leen y reportan.

```
python codigo/verificacion/diagnostico_atipicos.py      # distribución y valores extremos
python codigo/verificacion/verificar_fuente_tasas.py    # contrasta celdas contra el HTML crudo
python codigo/verificacion/verificar_quiebre_bcp.py     # compara dos cuadros fila por fila
```

---

## Estructura

```
codigo/
  01_extraccion_api.py        vía 1: BCRPData REST
  02_scraping_web.py          vía 2: cuadros XLS y portal SAEE
  03_limpieza_datos.py        inventario, limpieza, unión y validación
  04_analisis.py              tablas, figuras y modelo de panel
  entidades.py                diccionario de bancos, importado por 03 y 04
  verificacion/               auditoría de los datos (fuera del flujo)
datos_crudos/
  bcrp/                       JSON y CSV tal como salen de la API
  sbs_xls/                    288 archivos XLS tal como salen de la SBS
  sbs_tasas/                  96 archivos HTML tal como salen del portal
datos_procesados/
  datos_procesados_2024200488G.csv            el panel
  datos_procesados_2024200488G_agregado.csv   el mismo panel a fecha + entidad
salidas/
  figuras/                    7 figuras en PDF y PNG, con su CSV de respaldo
  tablas/                     6 tablas en CSV y en LaTeX
  inventario_fuentes.txt      censo de entidades y etiquetas de las 4 fuentes
  informe_limpieza.txt        cobertura, validaciones y prueba de reclasificación
  diagnostico_atipicos.txt    distribución de cada variable
  verificacion_*.txt          resultados de las auditorías
diccionario_variables.md
incidencias_fuente.md
requirements.txt
.env.example
log_ejecucion.txt
```

**Los datos crudos no se editan nunca.** Son la evidencia primaria. Se abren
solo para leer, y de cada uno se recalcula el SHA-256 al leerlo, para encadenar
la evidencia con el log de la extracción.

---

## Parámetros congelados

Ningún script usa fechas dinámicas del tipo «hoy». El periodo está declarado
como constante al inicio de cada archivo:

| Parámetro | Valor | Dónde |
|---|---|---|
| `FECHA_INICIO` | `2018-1` | `01_extraccion_api.py` |
| `FECHA_CORTE` | `2025-12` | `01_extraccion_api.py` |
| `ANIO_DESDE` / `ANIO_HASTA` | 2018 / 2025 | `02_scraping_web.py` |
| `ANIO_INICIO` / `ANIO_CORTE` | 2018 / 2025 | `03_limpieza_datos.py`, `04_analisis.py` |
| `SERIE` | `PN07809NM` | `01_extraccion_api.py` |
| `CUADROS` | `B-2359`, `B-2362`, `B-230803` | `02_scraping_web.py` |

---

## Fechas de extracción

| Etapa | Fecha y hora |
|---|---|
| Vía 1 · API del BCRP | 2026-11-24 23:09:21 |
| Vía 2 · Cuadros XLS y portal SAEE | 2026-11-25, entre las 11:18 y las 23:24 |
| Limpieza y análisis | Limpieza: 2026-11-27 03:16:46 · Análisis: 2026-11-27 03:34:18 |

La vía 1 se reejecutó el 2026-11-25 a las 00:00:05 y devolvió un archivo byte
por byte idéntico, con los mismos hashes SHA-256. La vía 2 se ejecutó en varias
corridas del mismo día: las primeras en modo prueba, las últimas completas.
Las fechas y horas exactas de cada corrida están en `log_ejecucion.txt`.

---

## Hashes SHA-256 de verificación

Se declaran los archivos entregados. Conforme al numeral 2.4.5 de la consigna,
el hash se coteja **contra el archivo entregado**, nunca contra el resultado de
una reejecución posterior: las fuentes financieras se actualizan y revisan sus
series hacia atrás, de modo que una reejecución legítima puede producir un
archivo distinto.

**Base procesada**

| Archivo | SHA-256 |
|---|---|
| `datos_procesados_2024200488G.csv` | `d536314f2831052616ca07fe1029c2ea63167a701053665383074a81978a19a3` |
| `datos_procesados_2024200488G_agregado.csv` | `787a7b5e0a7790ba36be79dc19795dc3c61515930d3ead438876f8b1f793154a` |

**Datos crudos de la vía 1**

| Archivo | SHA-256 |
|---|---|
| `PN07809NM_2018-2025_2024200488G.json` | `076dcf5adbf2c2a4c8250a7beb4e15a96de0b9ee37318ccfdfda7d74621b8179` |
| `PN07809NM_2018-2025_2024200488G.csv` | `f14a6909d0236f5b802d0c5d485d1a1c4f034d6c6ca8badb3c9ced2b34a57d0b` |

Los hashes de los 384 archivos crudos de la vía 2 quedan registrados en
`log_ejecucion.txt` en el momento en que se descargaron.

Para recalcular cualquiera:

```
certutil -hashfile datos_procesados\datos_procesados_2024200488G.csv SHA256
```

---

## Qué produce el análisis

**Siete figuras**, cada una en PDF vectorial, PNG a 300 ppp y un CSV con los
datos exactos que dibuja:

1. Evolución del monto negociado y de la tasa de descuento del mercado
2. Monto y tasa por tipo de crédito
3. Factoring frente a descuentos
4. Concentración del mercado y HHI
5. Dispersión de la tasa entre bancos
6. Número de deudores y morosidad
7. Relación entre precio y cantidad

**Seis tablas**, en CSV y en LaTeX con `booktabs`, listas para `\input{}`:
descriptivos, resumen por tipo de crédito, participación por entidad, efecto de
la winsorización, modelo de panel y prueba de robustez.

---

## Decisiones metodológicas y limitaciones

Lo que sigue está documentado con más detalle en `incidencias_fuente.md`.

**Dos quiebres estructurales.** La Resolución SBS 02368-2023 cambió la
clasificación de los tipos de crédito desde octubre de 2024, y el Banco de
Crédito dejó de reportar factoring como tal desde enero de 2025. Las figuras
descriptivas cubren los 96 meses con ambos quiebres marcados; **el modelo se
estima sobre enero de 2018 a septiembre de 2024**, ventana anterior a los dos.

**Acervo frente a flujo.** El monto negociado es un saldo a fin de mes; la tasa
de descuento es el precio de las operaciones realizadas en los últimos 30 días
útiles. No son el mismo tipo de objeto, y eso condiciona la interpretación de
cualquier relación entre ambos.

**Tratamiento de atípicos.** Se winsorizan al percentil 1 y 99 las variables de
tasa y morosidad, que recorta sin borrar observaciones. No se winsorizan el
monto ni el número de deudores: ahí los valores extremos son los bancos grandes
de verdad. Todos los resultados se reportan con y sin tratamiento.

**Pocos conglomerados.** El modelo agrupa los errores estándar por banco, y
solo nueve bancos publican tasa de descuento y tienen monto positivo a la vez.
La inferencia agrupada supone muchos conglomerados; con nueve, los errores
estándar se subestiman. Los p-valores usan la t con G−1 grados de libertad, que
es la corrección mínima razonable, y aun así la significancia debe leerse con
prudencia.

**El estimador se autocomprueba.** El modelo de panel está programado con
numpy. Antes de dar un resultado, reestima lo mismo con las variables
dicotómicas explícitas: por el teorema de Frisch-Waugh los coeficientes tienen
que coincidir, y si la diferencia superara `1e-6` el script se detiene. En la
corrida entregada la discrepancia máxima fue del orden de `1e-14`.

---

## Declaración del uso de inteligencia artificial

Se utilizó IA generativa como asistente para escribir y depurar el código de
extracción, limpieza y análisis, conforme a lo que autoriza la consigna. Las
decisiones metodológicas —qué variables usar, qué fuentes, cómo tratar los
atípicos, qué ventana estimar— se tomaron y se justifican en el artículo. Los
datos no fueron generados ni completados por IA en ningún punto: todos
provienen de las fuentes oficiales citadas y son verificables contra ellas.

El contenido redactado se humanizó para no exceder el umbral de similitud del
10 % que fija la consigna.

---

## Fuentes

Banco Central de Reserva del Perú. (2026). *BCRPData: Tasas de interés activas
y pasivas promedio de las empresas bancarias en MN — Preferencial corporativa a
90 días* [Serie PN07809NM]. <https://estadisticas.bcrp.gob.pe/estadisticas/series/api>

Superintendencia de Banca, Seguros y AFP. (2026). *Créditos directos por tipo
de crédito, modalidad y moneda* [Cuadro B-2359]. <https://intranet2.sbs.gob.pe/estadistica/financiera/>

Superintendencia de Banca, Seguros y AFP. (2026). *Morosidad según tipo y
modalidad de crédito por empresa bancaria* [Cuadro B-2362]. <https://intranet2.sbs.gob.pe/estadistica/financiera/>

Superintendencia de Banca, Seguros y AFP. (2026). *Número de deudores según
tipo de crédito* [Cuadro B-230803]. <https://intranet2.sbs.gob.pe/estadistica/financiera/>

Superintendencia de Banca, Seguros y AFP. (2026). *Tasa de interés activa anual
por tipo de crédito y empresa bancaria* [Portal SAEE]. <https://www.sbs.gob.pe/app/pp/EstadisticasSAEEPortal/Paginas/TIActivaTipoCreditoEmpresa.aspx?tip=B>

Superintendencia de Banca, Seguros y AFP. (2023). *Resolución SBS N.º
02368-2023*. <https://intranet2.sbs.gob.pe/dv_int_cn/2290/v2.0/Adjuntos/2368-2023.pdf>

Las fechas de consulta de cada archivo constan en `log_ejecucion.txt`.
