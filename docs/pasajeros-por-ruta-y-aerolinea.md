# ¿Se puede obtener pasajeros por aerolínea y ruta nacional en México?

**Respuesta corta: el dato existe, se produce cada mes y la ley obliga a publicarlo,
pero ninguna fuente pública gratuita lo publica cruzado.** AFAC publica las dos
*marginales* del cubo —pasajeros por ruta y pasajeros por aerolínea— nunca la celda
`ruta × aerolínea`. Este documento prueba esa afirmación abriendo cada archivo, no
citándolo de oídas, y entrega las cifras que sí pudieron verificarse.

Cobertura: **17 meses** —2024M01 a 2025M03 y 2026M01 a 2026M02—, que es todo lo
que pudo descargarse en este entorno. Los casos de ruta se trabajan sobre 2025Q1
por ser el trimestre completo más reciente. En la sección
[Qué no logré verificar](#qué-no-logré-verificar) se explica por qué no fue 2026Q2.

---

## 1. Fuentes investigadas y qué trae cada una

Cada fila se comprobó descargando el archivo y leyendo sus encabezados, no a partir
de su descripción.

| Fuente | Dimensiones reales | ¿Cruza ruta × aerolínea? |
|---|---|---|
| AFAC — *Estadística operacional origen-destino* (`sase-*.xlsx`) | `origen × destino × mes` → vuelos, pasajeros, carga. Hojas `REG NAC`, `REG INT`, `FLET NAC`, `FLET INT` | **No.** No existe columna de aerolínea |
| AFAC — *Resumen operacional por aerolínea* (`resumen-*.xlsx`) | `empresa × mes` en 9 hojas (`PAXREG`, `VLOSREG`, `CARGREG`, `OPREG`, …) | **No.** Ninguna hoja tiene origen/destino |
| AFAC — *Boletín mensual de estadística operacional* (PDF, 28 pp.) | Aerolínea, región, RPK/ASK/PLF, top-ten de destinos y de países | **No.** El top-ten de destinos no se desglosa por aerolínea |
| DATATUR — `DB_AFAC.zip` (19,578 filas, 2016M01–2026M07) | `año × tipo × servicio × región × aerolínea × mes` → pasajeros | **No.** Sin origen/destino |
| DATATUR — boletines `AFAC_AAAA_MM.pdf` | Aerolínea × mes, nacional e internacional | **No** |
| AICM — *AICM en Cifras* (PDF, 14 pp.) | Totales del aeropuerto por terminal, llegadas/salidas, carga | **No.** Ni aerolínea ni ruta |
| AFAC — *Estadística operativa de aeropuertos* (`producto-aeropuerto-*.xlsx`) | `aeropuerto × mes` | **No** |
| Workbooks anuales AFAC 1992–2025 (inventario del repo) | Hojas `VLOSREG/PAXREG/CARGREG/OPREG/…` en las 34 anualidades | **No.** Ninguna anualidad incluyó jamás una hoja O-D |
| US DOT — BTS T-100 | `ruta × aerolínea × mes` → pasajeros, asientos, salidas | **Sí**, pero solo segmentos que tocan EE. UU. Cero filas doméstico-MX |

Conclusión del barrido: **no hay fuente pública gratuita que cruce ruta y aerolínea
para vuelos nacionales mexicanos.**

## 2. Prueba de que el cubo sí existe

Las dos publicaciones de AFAC son dos vistas del mismo microdato. Comparando mes
a mes la suma de todas las rutas del servicio regular nacional contra la suma de
todas las aerolíneas, sobre los 17 meses que pudieron descargarse
(2024M01–2025M03 y 2026M01–2026M02):

| Resultado | Meses |
|---|---:|
| Coinciden **exactamente**, al pasajero | **15 de 17** |
| Difieren | 2 — 2025M02 por 10 pasajeros, 2025M03 por 36 |
| Desviación relativa máxima | **0.0007 %** |

Quince meses de coincidencia exacta entre dos publicaciones distintas, elaboradas
por áreas distintas y en formatos distintos, no ocurren por casualidad. Solo
ocurren si ambas se cortan de **la misma tabla, que ya trae juntas la ruta y la
empresa**. AFAC tiene el cruce; no lo publica.

Los dos meses que difieren tienen explicación probable de reexpresión: el
workbook origen-destino de marzo de 2025 se publicó el 28/04/2025, mientras que
la base larga de DATATUR se actualizó el 27/08/2026, de modo que el lado de
aerolíneas ya incorpora correcciones que el lado de rutas todavía no refleja.

El respaldo legal coincide: el **artículo 84 de la Ley de Aviación Civil** obliga
a las concesionarias y permisionarias a entregar *mensualmente* a AFAC «informes,
bitácoras, estadísticas, reportes […] y todos aquellos datos que permitan
transparentar su funcionamiento», y añade que AFAC «dará seguimiento a la
información presentada y **la publicará trimestralmente**».

## 3. Por qué no se puede reconstruir el cruce con álgebra

Tentación obvia: si conozco el total por ruta y el total por aerolínea, ¿puedo
despejar las celdas? **No.** El sistema está masivamente subdeterminado y se puede
demostrar con un contraejemplo concreto.

Aerus movió 5,881 pasajeros nacionales en 2025Q1. Buscando subconjuntos de rutas de
baja densidad cuya suma dé exactamente esa cifra, aparecen **al menos dos
particiones distintas**, ambas perfectamente compatibles con las dos marginales
publicadas:

- `CANCUN–MERIDA` + `MERIDA–PUERTO ESCONDIDO` + `MATAMOROS–MONTERREY` + `CANCUN–COZUMEL` + `MONTERREY–SAN LUIS POTOSI`
- `MERIDA–PUERTO ESCONDIDO` + `QUERETARO–SAN LUIS POTOSI` + `MERIDA–PUERTO VALLARTA` + `MONTERREY–SAN LUIS POTOSI` + `AGUASCALIENTES–SAN LUIS POTOSI`

Las marginales **no identifican** la asignación. Cualquier desglose obtenido así es
una hipótesis, no un dato.

También se descartó empíricamente el atajo de identificar al operador por tamaño de
avión (pasajeros/vuelo): la hoja `REG NAC` mezcla aerolíneas de carga en servicio
regular, que aparecen con muchos vuelos y cero pasajeros. Ejemplo: `CANCUN–MERIDA`
registra 124 vuelos y 95 pasajeros en 2025Q1.

## 4. Tabla entregada

`fuente` remite a un archivo descargable; `estado` indica el nivel de comprobación.

### 4.1 Ruta investigada de principio a fin — Tijuana ↔ Uruapan, 2025Q1

Es una ruta de **operador único**: Uruapan no tiene ninguna otra ruta nacional con
pasajeros en 2025Q1, y Volaris es la única aerolínea con vuelo directo publicado.
Al ser monopolio, el total AFAC de la ruta *es* el dato de la aerolínea.

| Ruta | Aerolínea | Mes | Pasajeros | Vuelos | Fuente | Estado |
|---|---|---|---:|---:|---|---|
| Tijuana → Uruapan | Volaris | 2025-01 | 5,701 | 41 | AFAC `sase-marzo-2025`, hoja `REG NAC` | Total verificado; operador inferido |
| Tijuana → Uruapan | Volaris | 2025-02 | 5,990 | 44 | ídem | ídem |
| Tijuana → Uruapan | Volaris | 2025-03 | 6,203 | 50 | ídem | ídem |
| Uruapan → Tijuana | Volaris | 2025-01 | 6,852 | 41 | ídem | ídem |
| Uruapan → Tijuana | Volaris | 2025-02 | 6,663 | 44 | ídem | ídem |
| Uruapan → Tijuana | Volaris | 2025-03 | 7,097 | 50 | ídem | ídem |
| **Tijuana ↔ Uruapan** | **Volaris (100 %)** | **2025Q1** | **38,506** | **270** | | |

Cadena de comprobación:

1. **Total de la ruta**: primario y exacto, de la hoja `REG NAC` del workbook O-D de AFAC.
2. **Exclusividad**: Uruapan aparece con una sola ruta nacional con pasajeros en todo
   el trimestre (`data/reference/afac_od_nacional_regular.csv`).
3. **Identidad del operador**: Volaris publica la ruta en su propio sitio y los
   agregadores de vuelos reportan un único operador con 100 % de las reservas.
4. **Consistencia de flota**: 142.6 pasajeros por vuelo encaja con un A320neo de
   Volaris (186 asientos → 77 % de ocupación). Ninguna otra aerolínea nacional opera
   equipo compatible con esa cifra en esa ruta.

El eslabón 3 es el único que **no** proviene de una fuente regulatoria primaria: la
exclusividad se sostiene en fuentes comerciales actuales, no en un registro oficial
mes a mes. Se marca como inferido, no como verificado.

### 4.2 Cruce verificado por cierre — Aéreo Calafia, 2024

Al ampliar el panel a 2024 apareció en el workbook origen-destino una ciudad
escrita en minúsculas, `Los Cabos`, distinta de `SAN JOSÉ DEL CABO`. Es diminuta
—6,268 pasajeros en todo 2024—, solo vuela a Mazatlán y Culiacán, y desaparece
después de julio de 2024.

Ese perfil coincide con el de una sola aerolínea. Contrastando los pasajeros de
las rutas de `Los Cabos` contra el total nacional de Aéreo Calafia que AFAC
publica por separado:

| Mes | Rutas `Los Cabos` | Aéreo Calafia (AFAC) | Diferencia |
|---|---:|---:|---:|
| 2024M01 | 1,058 | 1,102 | −44 |
| 2024M02 | 703 | 703 | **0** |
| 2024M03 | 985 | 985 | **0** |
| 2024M04 | 1,018 | 1,018 | **0** |
| 2024M05 | 788 | 820 | −32 |
| 2024M06 | 744 | 744 | **0** |
| 2024M07 | 972 | 972 | **0** |

Cinco de siete meses cuadran **exactamente al pasajero**. El faltante de mayo lo
explica por completo la ruta `CIUDAD JUAREZ–CULIACAN`, activa solo en enero y
mayo de 2024 con 26 y **32** pasajeros. Quedan 18 pasajeros de enero sin
asignar; no se forzó ninguna hipótesis para cerrarlos.

De ahí se sigue que `Los Cabos` en la nomenclatura de AFAC es **Cabo San Lucas
(CSL)**, y que esas rutas son íntegramente de Aéreo Calafia. Es el segundo cruce
doméstico verificado del proyecto, y el único obtenido **solo con las dos
publicaciones de AFAC**, sin recurrir a fuentes comerciales: el cierre entre
marginales identifica al operador cuando una aerolínea es la única en un
subconjunto aislado de la red.

El método no generaliza —lo intenté con Aerus y produjo dos soluciones distintas
igualmente válidas, como muestra la sección 3—, pero funciona cuando el
subconjunto está aislado y el total nacional de la aerolínea es pequeño.

### 4.3 Otras rutas de operador único candidato, 2025Q1

Mismo criterio (ciudad con una sola ruta nacional con pasajeros). Los totales son
verificados; la atribución a aerolínea queda **sin verificar**.

| Ruta (ambos sentidos) | Pasajeros 2025Q1 | Vuelos | Pax/vuelo | Operador indicado por fuentes comerciales |
|---|---:|---:|---:|---|
| Ciudad del Carmen ↔ México | 41,039 | 334 | 122.9 | Aeroméxico / Aeroméxico Connect (sin resolver) |
| Manzanillo ↔ México | 37,002 | 359 | 103.1 | Aeroméxico |
| Tijuana ↔ Uruapan | 38,506 | 270 | 142.6 | Volaris |
| Loreto ↔ Tijuana | 13,473 | 106 | 127.1 | Volaris (sin confirmar) |

Nota importante: incluso en una ruta de «una sola aerolínea», AFAC contabiliza
**Aeroméxico (Aerovías de México)** y **Aeroméxico Connect (Aerolitoral)** como
permisionarias distintas. Una ruta operada solo por el grupo Aeroméxico puede seguir
partiéndose en dos filas del lado de la aerolínea.

### 4.4 Ruta troncal competida — México ↔ Cancún, 2025Q1

La ruta doméstica más grande del país. El total es verificado; **el desglose por
aerolínea no es obtenible de ninguna fuente pública**.

| Ruta | Aerolínea | Mes | Pasajeros | Vuelos | Fuente | Estado |
|---|---|---|---:|---:|---|---|
| México → Cancún | *todas, sin desglose* | 2025-01 | 142,919 | 887 | AFAC `sase-marzo-2025`, `REG NAC` | Total verificado |
| México → Cancún | *todas, sin desglose* | 2025-02 | 125,944 | 814 | ídem | ídem |
| México → Cancún | *todas, sin desglose* | 2025-03 | 139,155 | 879 | ídem | ídem |
| Cancún → México | *todas, sin desglose* | 2025-01 | 151,564 | 890 | ídem | ídem |
| Cancún → México | *todas, sin desglose* | 2025-02 | 131,032 | 814 | ídem | ídem |
| Cancún → México | *todas, sin desglose* | 2025-03 | 142,710 | 880 | ídem | ídem |
| **México ↔ Cancún** | **sin desglose público** | **2025Q1** | **833,324** | **5,164** | | |

Las aerolíneas que operaron el par (Aeroméxico, Viva Aerobus, Volaris, y según el
periodo Mexicana y Magnicharters) son identificables por horarios publicados, pero
**sus pasajeros respectivos no lo son**. Cualquier cifra de reparto que circule para
esta ruta proviene de datos comerciales o de estimación, no de una fuente verificable.

### 4.5 Contraste: la misma tabla sí existe cuando el regulador la publica

Para dimensionar qué se está perdiendo, la misma consulta sobre una ruta
internacional, con datos del US DOT, sale completa y verificada:

| Ruta | Aerolínea | Mes | Pasajeros | Fuente | Estado |
|---|---|---|---:|---|---|
| México → Los Ángeles | Grupo Aeroméxico | 2025-01 | 22,703 | BTS T-100 Segment | Verificado |
| México → Los Ángeles | Volaris | 2025-01 | 7,748 | ídem | Verificado |
| México → Los Ángeles | Viva Aerobus | 2025-01 | 7,077 | ídem | Verificado |
| México → Los Ángeles | Delta Air Lines | 2025-01 | 5,674 | ídem | Verificado |
| México → Los Ángeles | Grupo Aeroméxico | 2025-02 | 15,303 | ídem | Verificado |
| México → Los Ángeles | Volaris | 2025-02 | 5,379 | ídem | Verificado |
| México → Los Ángeles | Viva Aerobus | 2025-02 | 5,022 | ídem | Verificado |
| México → Los Ángeles | Delta Air Lines | 2025-02 | 4,662 | ídem | Verificado |
| México → Los Ángeles | American Airlines | 2025-02 | 122 | ídem | Verificado |
| México → Los Ángeles | Grupo Aeroméxico | 2025-03 | 19,065 | ídem | Verificado |
| México → Los Ángeles | Volaris | 2025-03 | 6,030 | ídem | Verificado |
| México → Los Ángeles | Viva Aerobus | 2025-03 | 5,355 | ídem | Verificado |
| México → Los Ángeles | Delta Air Lines | 2025-03 | 5,090 | ídem | Verificado |
| México → Los Ángeles | American Airlines | 2025-03 | 3,842 | ídem | Verificado |

Es exactamente la tabla pedida —ruta, aerolínea, mes, pasajeros, fuente verificable—
y existe para rutas México–EE. UU. porque **el regulador estadounidense publica el
cubo completo**. La limitación mexicana es de política de publicación, no técnica.

## 5. Cómo obtener el desglose para el resto de las rutas nacionales

En orden de rigor decreciente.

### Vía 1 — Solicitud de transparencia a AFAC (recomendada)

Es la única ruta que entrega el dato **oficial y completo** sin costo.

- **Sujeto obligado**: Agencia Federal de Aviación Civil.
- **Canal**: Plataforma Nacional de Transparencia (`plataformadetransparencia.org.mx`).
- **Fundamento**: artículo 84 de la Ley de Aviación Civil (obligación de entrega
  mensual por las aerolíneas y de publicación trimestral por AFAC).
- **Plazo legal**: 20 días hábiles, prorrogables por 10 más.
- **Redacción sugerida**: «Solicito, en formato abierto (XLSX o CSV), la estadística
  operacional de servicio regular nacional desagregada simultáneamente por par de
  ciudades origen-destino, permisionaria o concesionaria, y mes, para el periodo
  [enero–marzo de 2025], indicando vuelos realizados, asientos ofrecidos y pasajeros
  transportados. Es la misma base con la que se construyen las publicaciones
  "Estadística operacional origen-destino" y "Resumen operacional por aerolínea".»
- **Punto clave**: citar explícitamente que ambas publicaciones se derivan de la
  misma base cierra la salida de «la información no existe en la forma solicitada».
  La reconciliación de la sección 2 es la evidencia de que sí existe.
- **Si se niega**: recurso de revisión ante el órgano garante. La causal más probable
  sería secreto comercial por permisionaria; en ese caso conviene pedir versión
  pública o agregación a nivel grupo aeroportuario.

### Vía 2 — Datos comerciales

Cubren todas las rutas de inmediato, con costo y con restricciones de redistribución.

- **Cirium Diio Mi** y **OAG Traffic Analytics**: pasajeros estimados por ruta y
  aerolínea, derivados de MIDT/reservas.
- **IATA Data Solutions (DDS)**: cupones de boleto; máxima cobertura O&D real.
- Advertencia: son **estimaciones de mercado**, no el conteo regulatorio. No cuadran
  con AFAC y no deben mezclarse con cifras AFAC en la misma columna.

### Vía 3 — Estimación reproducible desde datos abiertos

Cuando no hay presupuesto ni tiempo para la solicitud. Es una **estimación**, debe
etiquetarse como tal y nunca presentarse como cifra verificada.

1. Tomar el total de pasajeros por ruta y mes de AFAC (`sase`) — dato duro.
2. Construir asientos por ruta × aerolínea × mes desde horarios publicados
   (itinerarios de las aerolíneas, o ADS-B histórico vía OpenSky para vuelos reales).
3. Repartir el total AFAC en proporción a los asientos de cada aerolínea.
4. Calibrar con dos anclas verificables: el total nacional por aerolínea del boletín
   AFAC y, en rutas transfronterizas, el factor de ocupación real por aerolínea de
   BTS T-100.
5. Publicar bandas, no puntos. El supuesto fuerte —mismo factor de ocupación para
   todas las aerolíneas de la ruta— es falso: las de bajo costo suelen volar más
   llenas que las de servicio completo.

**Rutas monopólicas**: la vía 3 sobra. Basta identificar las rutas con un solo
operador y asignarles el total de AFAC, como en la sección 4.1. En 2025Q1 solo cuatro
ciudades tienen una única ruta nacional con pasajeros, así que este atajo cubre una
parte pequeña del mapa; extenderlo requiere una fuente de itinerarios para detectar
monopolios en rutas de ciudades multi-destino.

## 6. Qué no logré verificar

Se declara explícitamente, sin rellenar huecos.

1. **El desglose por aerolínea de cualquier ruta nacional competida.** No existe en
   ninguna fuente pública gratuita. Es el hueco central y no se cerró.
2. **El trimestre 2026Q2.** El archivo O-D de AFAC existe y está identificado
   (`sase-julio-2026-27082026.xlsx`, adjunto 1100280 de gob.mx), pero el CDN de
   gob.mx responde a las descargas de `.xlsx` con un *challenge* anti-bot de F5. Los
   PDF del mismo host sí descargan; los `.xlsx`, no. Chromium tampoco pudo resolverlo
   en este entorno. Los `.xlsx` obtenidos vienen del Internet Archive, que solo tiene
   hasta `sase-febrero-2026`. Por eso el trimestre trabajado es 2025Q1. En una máquina
   con navegador normal el archivo se descarga sin problema.
3. **La exclusividad histórica de Volaris en Tijuana–Uruapan mes a mes.** Se apoya en
   itinerarios comerciales actuales y en consistencia de flota, no en un registro
   regulatorio de operadores por ruta y mes. Es una inferencia documentada.
4. **El operador de Ciudad del Carmen ↔ México y de Loreto ↔ Tijuana.** No se resolvió
   entre Aeroméxico y Aeroméxico Connect en el primer caso, ni se confirmó Volaris en
   el segundo.
5. **La lista completa de aerolíneas que operaron México ↔ Cancún en cada mes de
   2025Q1.** Los itinerarios consultados son actuales; no se verificó la nómina
   histórica mes a mes.
6. **Un precedente concreto de solicitud de transparencia ya resuelta** con este
   desglose. No se localizó un folio público que confirme que AFAC entrega el cruce.
   La Vía 1 se sostiene en el fundamento legal y en la evidencia de que el dato
   existe, no en un precedente observado.
7. **La conciliación del servicio de fletamento.** En abril de 2020 `DB_AFAC` reporta
   331 pasajeros de fletamento nacional (Eurus Aviation) mientras la hoja `FLET NAC`
   del workbook O-D reporta 805 vuelos y **cero** pasajeros en todas sus rutas. Las
   dos publicaciones **no** cuadran para fletamento, a diferencia del servicio
   regular. No se determinó la causa.

## 7. Archivos generados

| Archivo | Contenido |
|---|---|
| `data/reference/afac_od_nacional_regular.csv` | 10,051 filas `period_id, origen, destino, vuelos, pasajeros` del servicio regular nacional, 17 meses (2024M01–2025M03, 2026M01–2026M02), de la hoja `REG NAC` de los workbooks O-D |
| `data/reference/afac_carrier_domestic.csv` | 143 filas `period_id, carrier_name, pasajeros`, los mismos 17 meses, de la base larga de DATATUR |
| `data/reference/afac_city_iata_crosswalk.csv` | 58 ciudades AFAC ↔ IATA, verificadas contra `dim_airport` |
| `data/reference/afac_carrier_crosswalk.csv` | 9 nombres AFAC ↔ `carrier_key` |

## 8. Fuentes

- AFAC, *Estadísticas*: <https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404>
- AFAC, *Estadística operacional origen-destino* (workbook usado, 2025Q1):
  `https://www.gob.mx/cms/uploads/attachment/file/992928/sase-marzo-2025-28042025.xlsx`
  — copia archivada: <https://web.archive.org/web/20250504104724id_/https://www.gob.mx/cms/uploads/attachment/file/992928/sase-marzo-2025-28042025.xlsx>
- AFAC, *Estadística mensual por origen-destino* (serie histórica): <https://www.gob.mx/afac/acciones-y-programas/estadistica-mensual-operativa-monthly-traffic-statistics>
- AFAC, *Estadística mensual por aerolínea*: <https://www.gob.mx/afac/acciones-y-programas/estadistica-mensual-por-aerolinea-monthly-airline-statistics>
- AFAC, *Boletín mensual de estadística operacional*: <https://www.gob.mx/afac/acciones-y-programas/boletin-mensual>
- DATATUR, catálogo AFAC y base larga: <https://datatur.sectur.gob.mx/SitePages/afac.aspx>
- DATATUR, boletín marzo 2025 (totales por aerolínea 2025Q1): <https://datatur.sectur.gob.mx/Documentoscompartidos/afac/AFAC_2025_03.pdf>
- AICM, *AICM en Cifras*: <https://www.aicm.com.mx/estadisticas>
- Ley de Aviación Civil, art. 84: <https://www.diputados.gob.mx/LeyesBiblio/pdf/LAC.pdf>
- Plataforma Nacional de Transparencia: <https://www.plataformadetransparencia.org.mx/>
- US DOT, BTS T-100 Segment: <https://www.transtats.bts.gov/>
- Volaris, ruta Tijuana–Uruapan: <https://www.volaris.com/es-mx/vuelos-desde-tijuana-a-uruapan>
