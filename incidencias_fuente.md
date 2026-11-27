# Incidencias de fuente

**Santiago Piero Camayo Jiménez** · 2024200488G
Finanzas I (055D) · Unidad II · Tema N.º 91

Este documento registra los hechos que afectaron la extracción o la
interpretación de los datos. Ninguno impidió el rastreo, de modo que no hubo
que solicitar sustitución de fuente al amparo del numeral 2.4.3. Las dos
incidencias de fondo son cambios en la forma de reportar de la propia fuente,
y se documentan porque **condicionan la lectura de la serie**.

---

## Incidencia 1 · Caída temporal del portal de la SBS

**Cuándo.** La noche del 20 de noviembre de 2026, durante la etapa de prueba
de la vía 2.

**Qué pasó.** Las descargas del dominio `intranet2.sbs.gob.pe` empezaron a
devolver `ERR_HTTP2_PROTOCOL_ERROR` desde el navegador y `RemoteDisconnected`
desde Python. El mismo archivo se había descargado con éxito poco antes, a
las 22:45 del mismo día.

**Diagnóstico.** La falla era del servidor, no del cliente: el recurso existía
y había respondido minutos antes con la misma petición. No fue un bloqueo
dirigido ni una restricción de rastreo.

**Qué se hizo.** No se solicitó sustitución, porque el portal se restableció.
La incidencia se convirtió en un requisito de diseño: `02_scraping_web.py`
reintenta con espera creciente y distingue entre un fallo transitorio, que se
reintenta, y un fallo estructural, que aborta de inmediato en vez de insistir
contra un servidor caído.

**Cumplimiento de las reglas de rastreo.** Se verificó `robots.txt` antes de
extraer: `www.sbs.gob.pe` permite la ruta `/app/pp/` y no declara
`Crawl-delay`; `intranet2.sbs.gob.pe` no publica `robots.txt`. El script
mantiene una pausa de 1,5 segundos entre solicitudes —por encima del mínimo
de 1 segundo que exige la consigna—, envía un User-Agent identificable y
guarda en caché lo ya descargado para no repetir peticiones. El número de
solicitudes se redujo de 288 a 97 reutilizando la sesión.

---

## Incidencia 2 · Reclasificación de los tipos de crédito, vigente desde octubre de 2024

**Norma.** Resolución SBS N.º 02368-2023. El Artículo Sexto, literal iv),
dispone que el cambio rige **desde el 1 de octubre de 2024**.

**Qué cambió.** La definición de crédito a mediana empresa pasó de un criterio
de **deuda** (S/ 300 000 o más) a uno de **ventas anuales** (S/ 5 millones o
más). Los deudores medianos que venden menos de S/ 5 millones se
reclasificaron como pequeña empresa.

**Cómo se detectó.** No se leyó primero la norma: se vio primero en los datos.
Entre septiembre y octubre de 2024, con cobertura completa en ambos meses,
el segmento de medianas empresas pierde el 77 % de sus deudores y el 47 % de
su monto, mientras el total del mercado apenas se mueve. La búsqueda de la
causa llevó a la resolución, cuya fecha de vigencia coincide exactamente con
el escalón.

**Magnitud, en millones de soles** (promedio de jul–sep 2024 contra oct–dic 2024):

| Tipo | Antes | Después | Flujo |
|---|---|---|---|
| Corporativo | 6 661 | 7 762 | +1 101 |
| Grandes empresas | 5 112 | 3 691 | −1 420 |
| Medianas empresas | 1 516 | 1 061 | −454 |
| Pequeñas empresas | 202 | 899 | +697 |
| **Neto** | | | **−78** |

**Qué se hizo.** Se incluyó **pequeñas empresas** como cuarto tipo del panel.
Como las empresas se movieron de medianas a pequeñas, incluir ese segundo
segmento cierra el universo: nadie entra ni sale, solo cambian de casilla. El
saldo neto de los cuatro tipos es de −78 millones sobre un mercado de 13 490,
esto es **−0,6 %**, lo que confirma numéricamente la reclasificación.

`03_limpieza_datos.py` recalcula esa prueba en cada corrida y la escribe en
`salidas/informe_limpieza.txt`. Si el saldo neto superara el 5 %, el script
avisa de que hay algo más que una reclasificación.

**Consecuencia para el análisis.** El tipo de crédito no es comparable antes y
después de octubre de 2024. Las figuras descriptivas cubren los 96 meses con
el quiebre marcado; el modelo se estima sobre la ventana anterior al quiebre.

---

## Incidencia 3 · El Banco de Crédito deja de reportar factoring, desde enero de 2025

**Qué pasó.** En enero de 2025, el BCP reporta `0` en la fila *Factoring* del
cuadro B-2359, en los cuatro tipos de crédito, tras haber reportado S/ 3 244
millones en diciembre de 2024. El BCP concentra el 39 % del mercado.

**Cómo se verificó.** Con `codigo/verificacion/verificar_quiebre_bcp.py`, que
compara los dos cuadros fila por fila. La prueba decisiva es el renglón que
encabeza cada bloque, que es el total del tipo de crédito:

| Fila, créditos corporativos | dic-2024 | ene-2025 | Cambio |
|---|---|---|---|
| Factoring | 2 966 | 0 | −2 966 |
| Otros créditos corporativo | 1 393 | 4 201 | **+2 808** |
| **Total del tipo** | 40 923 | 40 866 | **−57** |

El total del crédito corporativo del banco cae 0,1 %. De cada sol que pierde
el factoring, el total pierde dos céntimos. **La cartera no salió del balance:
se trasladó a la fila "Otros créditos corporativo"**, que absorbe el 95 % de
la caída. En grandes empresas ocurre lo mismo a menor escala, con un 85 % de
cobertura.

**No fue un cambio normativo.** Ningún otro banco lleva su factoring a cero
entre esos dos meses: Santander baja 110 millones, Citibank 77 y Scotiabank
74, variaciones corrientes, e Interbank incluso sube 7. De los 3 517 millones
que pierde el sistema, 3 244 son del BCP, el 92 %. Es una decisión de reporte
de una entidad, no un cambio de instructivo contable, y por eso no hay norma
que citar.

**Consecuencia.** Desde enero de 2025 las estadísticas públicas de factoring
de la SBS subestiman el mercado en unos S/ 3 000 millones. El modelo se
estima hasta septiembre de 2024, con lo que la ventana queda además anterior
a esta incidencia.

---

## Incidencia 4 · Valores atípicos de Banco de Comercio en el portal de tasas

**Qué se observó.** El valor 51,11 % aparece doce veces como tasa de descuento
de Banco de Comercio, repartidas entre 2020 y 2025 y en dos tipos de crédito
distintos. Una tasa de mercado no se repite idéntica a dos decimales durante
seis años, de modo que se sospechó un defecto del lector.

**Cómo se verificó.** Con `codigo/verificacion/verificar_fuente_tasas.py`, que
recorre los 96 archivos HTML crudos y lista todos los valores distintos que
publica la fuente. En el crudo el 51,11 aparece exactamente las mismas doce
veces, y cinco casos puntuales coinciden celda por celda con lo que escribió
el panel. **El dato es de la SBS; el lector es correcto.**

**Interpretación.** El portal publica tasas efectivas **anuales** de las
operaciones realizadas en los últimos 30 días útiles. Anualizar un plazo muy
corto infla la cifra: una letra descontada a 7 días con una comisión plana de
0,8 % equivale a `(1,008)^(365/7) − 1 ≈ 51,5 %`. Banco de Comercio es un banco
pequeño; si en un mes coloca una o dos operaciones de su producto estándar, el
promedio del mes es la tasa de ese producto, y por eso se repite. Esta es una
interpretación propia, no un dato confirmado por la SBS.

**Qué se hizo.** Los valores se conservan en el panel, que es un registro fiel
de la fuente. El tratamiento se aplica en el análisis: winsorización al
percentil 1 y 99, que recorta sin borrar observaciones. Se reportan los
resultados con y sin tratamiento; la correlación entre ambas series agregadas
es 0,99983 y la diferencia máxima en 96 meses es de 0,195 puntos porcentuales.
