# Diccionario de variables

**Santiago Piero Camayo Jiménez** · 2024200488G
Finanzas I (055D) · Unidad II · Tema N.º 91
*El factoring como instrumento de financiamiento de corto plazo en el Perú*

Archivo descrito: `datos_procesados/datos_procesados_2024200488G.csv`
Cobertura: mensual, enero 2018 a diciembre 2025 (96 meses)
Unidad de observación: **fecha × entidad × tipo de crédito**
Filas: 6 324 · Entidades: 20 bancos · Tipos de crédito: 4

---

## Llave

| Columna | Tipo | Descripción |
|---|---|---|
| `fecha` | texto `AAAA-MM` | Mes de referencia del dato, en formato ISO reducido. |
| `entidad` | texto | Identificador corto y estable del banco, generado por `codigo/entidades.py`. Es estable ante los cambios de razón social: Continental y BBVA comparten el identificador `bbva`. |
| `tipo` | texto | Tipo de crédito: `corporativo`, `grandes`, `medianas`, `pequenas`. |

Las tres columnas juntas identifican una fila sin repeticiones. El script `03_limpieza_datos.py` lo comprueba en cada corrida.

## Etiquetas para impresión

| Columna | Tipo | Descripción |
|---|---|---|
| `entidad_nombre` | texto | Nombre legible del banco, con la razón social anterior entre paréntesis cuando cambió dentro del periodo. |
| `tipo_nombre` | texto | Nombre legible del tipo de crédito. |

## Variables sustantivas

| Columna | Unidad | Fuente | Definición y advertencias |
|---|---|---|---|
| `monto_negociado_miles` | miles de soles | SBS, cuadro **B-2359** | **Variable 1.** Saldo de factoring más descuentos, columna *Total* (moneda nacional más extranjera convertida al tipo de cambio del mes). Las dos modalidades se suman porque las entidades no las clasifican igual: hay bancos que registran en descuentos lo que otros registran en factoring, de modo que cualquiera de las dos por separado describiría mal el mercado. Es un **acervo** a fin de mes, no un flujo de operaciones nuevas. |
| `tasa_descuento_pct` | por ciento anual | SBS, **portal SAEE** | **Variable 2.** Tasa de la modalidad *Descuentos*, en moneda nacional. El portal no publica una tasa de factoring: publica la de descuentos, que es el precio al que la banca compra documentos por cobrar y por tanto su equivalente directo. Es un **flujo**: el promedio de las operaciones realizadas en los últimos 30 días útiles, expresado en términos efectivos anuales. Vacío cuando el banco no colocó operaciones de esa modalidad en el mes. |
| `deudores` | número de relaciones | SBS, cuadro **B-230803** | **Variable 3.** Número de deudores del tipo de crédito en ese banco. **No se puede sumar entre bancos para obtener empresas:** la nota 1/ del cuadro advierte que el total consolida, de modo que una empresa que debe a tres bancos cuenta tres veces en las filas y una sola en el total. Interpretar como *relaciones deudor-banco*. |
| `morosidad_tipo_pct` | por ciento | SBS, cuadro **B-2362** | **Variable 4.** Morosidad del tipo de crédito completo, es decir cartera atrasada sobre cartera total del segmento. Es la que usa el modelo, por su cobertura (75,3 % de las filas). |
| `tasa_referencia_pct` | por ciento anual | BCRP, serie **PN07809NM** | **Variable 5.** Tasa de interés preferencial corporativa a 90 días en moneda nacional, en términos efectivos anuales. Es la única variable que no varía entre entidades: mide el costo de referencia del dinero de corto plazo para todo el sistema, y por eso se repite en todas las filas del mismo mes. |

## Variables complementarias

| Columna | Unidad | Fuente | Definición |
|---|---|---|---|
| `saldo_factoring_miles` | miles de soles | B-2359 | El componente de factoring de `monto_negociado_miles`, por separado. |
| `saldo_descuentos_miles` | miles de soles | B-2359 | El componente de descuentos, por separado. Las dos columnas suman exactamente `monto_negociado_miles`. |
| `morosidad_factoring_pct` | por ciento | B-2362 | Morosidad de la modalidad factoring específicamente. Más fiel al tema pero mucho más dispersa: solo el 35,7 % de las filas tiene dato, porque la mayoría de bancos deja guion. Se reporta como descriptivo. |
| `tasa_tipo_pct` | por ciento anual | portal SAEE | Tasa promedio de todo el tipo de crédito, no solo de la modalidad descuentos. Sirve para construir el diferencial entre el precio del descuento y el precio general del segmento. |
| `tipo_cambio` | soles por dólar | B-2359 | Tipo de cambio contable del mes que declara el propio cuadro. Se conserva porque permite comprobar la aritmética: `Total = MN + ME × tipo_cambio`. |
| `opera_factoring` | 0 o 1 | derivada | Vale 1 si `monto_negociado_miles > 0`. Permite separar a los bancos que operan en el mercado de los que no, sin tener que rehacer el panel. |

## Convenciones de los valores ausentes

El guion del archivo de origen **no significa lo mismo en todos los cuadros**, y confundirlos distorsionaría los promedios:

- En el **B-2359** (saldos) la ausencia de cifra es un **cero contable**: el banco no tiene esa cartera. Se registra como `0`.
- En el **B-2362** (morosidad) y en el **portal de tasas**, el guion es **dato faltante**: el banco no reportó. Se registra como vacío. Un banco sin cartera atrasada informa `0,00`; el que no reporta deja guion.
- El portal usa además `s.i.` ("sin información"), que también se trata como dato faltante.

## Fuentes y rutas exactas

| Vía | Fuente | Recurso |
|---|---|---|
| 1 · API | BCRP, BCRPData REST | `https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PN07809NM/json/2018-1/2025-12` |
| 2 · Descarga programática | SBS, cuadros estadísticos | `https://intranet2.sbs.gob.pe/estadistica/financiera/{año}/{Mes}/{cuadro}-{mes}{año}.XLS` para B-2359, B-2362 y B-230803 |
| 2 · Scraping | SBS, portal SAEE | `https://www.sbs.gob.pe/app/pp/EstadisticasSAEEPortal/Paginas/TIActivaTipoCreditoEmpresa.aspx?tip=B` |

Nombre completo de la serie del BCRP, tal como la devuelve la API:
*Tasas de interés activas y pasivas promedio de las empresas bancarias en MN (términos efectivos anuales) — Activas — Preferencial Corporativa a 90 días*

## Entidades

Los 20 bancos del panel y sus equivalencias están declarados en `codigo/entidades.py`. Cuatro cambiaron de razón social dentro del periodo, y la equivalencia se verificó por aritmética de meses sobre el inventario de las cuatro fuentes, no por parecido de nombre:

| Antes | Después | Meses | Comprobación |
|---|---|---|---|
| Banco Continental | BBVA Perú | 17 + 79 | = 96 |
| Banco Financiero | Banco Pichincha | 7 + 89 | = 96 |
| Banco de Comercio | BANCOM | 69 + 27 | = 96 |
| Banco Azteca | Alfin Banco | 46 + 50 | = 96 |

Si los meses no sumaran exactamente 96 habría un solapamiento o un hueco, y la equivalencia sería falsa.
