# BTS: refresco para auditar cobertura de vuelos

Corte: 17 de octubre de 2026. Candidato sin integración ni publicación; no
consulta AeroDataBox, no reajusta modelos y no cambia las tesis aprobadas.

## Fuente y procedimiento

El calendario oficial de BTS (`https://www.transtats.bts.gov/releaseinfo.asp`)
registra junio de T-100 International Segment All Carriers el 14 de septiembre
y julio el 9 de octubre. Eso no acredita que cada operador esté completo.

Se ejecutó `src.ingest.bts.t100.download_year` para 2026: formulario oficial,
geografía México, todos los meses y los 30 campos documentados por `FIELDS`.
La respuesta HTTP 200 `application/zip` se conserva sin reformatear, con
metadatos y evento de restatement. El ZIP nuevo contiene 12,459 filas y meses
enero–julio, frente al original retenido de enero–mayo. No se borra el original.

- Anterior: 2026-08-24T03:16:56.016705Z, 193,316 bytes,
  SHA-256 `590001141ec9907ef392d424bfae910cc7024e8bf6a32fdc5b3948878e2f64a6`.
- Nuevo: 2026-10-17T18:33:40.420808Z, 259,152 bytes,
  SHA-256 `bda94a69b9d8430163a96b33521300cf8f76ac6f0aa0761d67ce3250a184d568`.

Una segunda captura conservada a las 18:39:47 UTC devuelve el CSV de datos
idéntico byte a byte: SHA-256
`c14ab5dfa6e993115e5974f6aecd4fcaf0c90839b8192a4e166c1f3abbd3f5e5`.
El SHA del ZIP sí cambia porque BTS fecha sus miembros al construirlo; comparar
solo el contenedor no demuestra una revisión de cifras. La comparación de
celdas y CSV evita ese falso positivo. La asimetría de junio persiste.

`scripts/research/audit_bts_refresh.py --old <ZIP> --new <ZIP> --out <directorio>`
produce conteos por operador, mes, clase, ruta y sentido, además de comparar
las ediciones sin convertir celdas ausentes en cero. Usa `DEPARTURES_PERFORMED`;
las salidas conservan la clase original. F/G son regulares; L/P se informan
aparte. No se usa pasajeros ni `DEPARTURES_SCHEDULED` como vuelos realizados.

## Conteos confirmados en el CSV

| Operador BTS | Abril F | Mayo F | Junio F | Q2 F | Q2 L |
|---|---:|---:|---:|---:|---:|
| Aeromexico, AM, ID 19534 | 2,239 | 2,207 | 1,279 | 5,725 | 51 |
| Aerolitoral, 5D, ID 20250 | 460 | 408 | 361 | 1,229 | 0 |
| Aeroenlaces, VB, ID 21342 | 1,221 | 1,081 | 1,345 | 3,647 | 41 |
| Volaris México, Y4, ID 21351 | 3,648 | 3,568 | 3,813 | 11,029 | 0 |

No hay filas G/P de esos cuatro operadores en Q2. La suma regular AM + 5D es
6,954 y requiere agregación explícita como Grupo Aeroméxico; el parser conserva
ambos operadores separados. Aerolitoral sí reporta a BTS: el mapeo anterior
lo mantenía bajo la clave genérica `BTS_AIRLINE_ID_20250`, no dentro de AM.
El candidato corrige su identidad a `AEROMEXICO_CONNECT`, IATA 5D, ICAO SLI.

Abril/mayo de los cuatro operadores son idénticos entre ediciones al grano
operador–ruta–sentido–mes–clase. Para todas las aerolíneas hay cinco celdas nuevas
de mayo: AC NLU–DFW G (3), AC NLU–ORD G (5), E7 MEX–MIA G (21), E7 MIA–MEX G
(21) y RV CUN–PIT F (1); ninguna pertenece al objetivo de las tres aerolíneas.

## Límites y validación

Junio de AM tiene solo 297 regulares MX→US frente a 982 US→MX. Connect registra
180/181, Viva 672/673 y Volaris 1,906/1,907. La fuerte asimetría de AM debe
exponerse; no permite declarar el mes completo ni fabricar vuelos de regreso.
BTS cubre México–EE. UU., no toda la red internacional. Actualizarlo no acredita
por sí solo alcanzar el objetivo de cobertura del 95% contra AFAC.

La conciliación del ZIP anterior con Silver y Gold vigentes confirma AM 4,446 F
más 5 L y Connect 868 F en abril/mayo. Los 5,474 observados del mapa anterior
incluyen otras autoridades y no son un total BTS. La transformación conserva
los conteos: Silver nuevo 193,053 filas y fact candidato 193,008, tras agregar
configuraciones al grano contractual. Todas las sumas por operador–mes–clase
coinciden exactamente; los años 2015–2025 usan los originales retenidos.

Pruebas focalizadas: cuatro aprobadas, incluidas identidad AM/5D, conservación
de clase y vuelos realizados frente a programados. Contrato del fact validado,
Ruff y `git diff --check` correctos. No se ejecutó la suite completa ni CI en
esta rama auxiliar; la entrega funcional debe verificarlos en el head integrado
del PR de vuelos. No se activa ningún dato con este refresco.

## Objetivo del 95% y línea base

El encargo del dueño es aumentar la **representación de vuelos observados y
estimados**, nacionales e internacionales, frente a los vuelos regulares AFAC
del mismo trimestre y operador. No es una afirmación de cobertura observada
vuelo a vuelo. El informe presenta tres medidas separadas:

1. La solicitada: todos los vuelos observados más estimados representados sobre
   AFAC regular. Puede contener observaciones no regulares o de clase no
   confirmada; esa diferencia de universo se declara, sin alterar el encargo.
2. Una comparación adicional: observaciones de clase regular verificable más
   estimados retenidos sobre AFAC regular, con su propia brecha al 95%. Excluye
   L/P y observaciones de clase sin confirmar; los estimados siguen siendo
   estimados y no acreditan realización ni regularidad verificadas.
3. La proporción estrictamente observada: únicamente observaciones de clase
   regular verificable sobre AFAC regular, sin estimados.

Programación AICM y atribuciones de mercado se informan aparte; ninguna
contribuye a esos numeradores. Un 95% en una suma con estimados no equivale a
95% de vuelos regulares observados o validados.

La línea base es la publicación `40a63d1905`, no el borrador previo del PR #134:

| 2T26 publicado | Observados + estimados representados | AFAC regular nacional + internacional | Representación | Vuelos adicionales para ≥95% |
|---|---:|---:|---:|---:|
| Grupo Aeroméxico | 34.980 | 46.716 | 74,88% | 9.401 |
| Viva | 38.503 | 45.308 | 84,98% | 4.540 |
| Volaris México | 41.940 | 46.304 | 90,58% | 2.049 |

Los 5.486 programados internacionales AM publicados permanecen separados. El
objetivo entero se calcula con `ceil(0,95 × AFAC)`; no se ajusta la frecuencia
para alcanzarlo. Un resultado superior al 100% se conserva y señala como
inconsistencia entre universos/fuentes, sin truncar ni repartir diferencias.

Con el nacional **publicado**, incluso sustituir internacional por el total
AFAC sólo daría 92,94% para AM y 88,65% para Viva. El borrador anterior ya
recuperaba frecuencias nacionales del mismo mes: 30.055 AM, 35.291 Viva y
33.952 Volaris. Esos valores son estimaciones retenidas, no vuelos adicionales
observados. Con ese nacional, el techo teórico de Viva, aun suponiendo todo el
internacional AFAC, es 88,66%; faltan al menos 2.874 vuelos nacionales
sustentados para alcanzar el objetivo. El supuesto de internacional completo
no es un dato disponible ni una autorización para completar la red.

## Resultado del candidato base, sin fallback de EE. UU.

La primera compilación base, en `c5bbfb4eddfcc0868aae869a848026c0c29e3aa8`,
tiene el fallback de EE. UU. desactivado. El informe reproducible contrasta
144 filas de publicación, borrador anterior, base nueva y variante acotada.
Son resultados del
export real, después de la precedencia por celda; no el inventario previo.
No se integraron ni publicaron estos datos.

| 2T26 | Publicado amplio | Base amplia / AFAC | Aumento frente a publicación | Regular verificable + estimado / AFAC | Faltan para 95%, amplio / regular + estimado |
|---|---:|---:|---:|---:|---:|
| Grupo Aeroméxico | 34.980 (74,88%) | 43.595 / 46.716 (93,32%) | +8.615 | 43.302 / 46.716 (92,69%) | 786 / 1.079 |
| Viva | 38.503 (84,98%) | 39.869 / 45.308 (88,00%) | +1.366 | 39.828 / 45.308 (87,91%) | 3.174 / 3.215 |
| Volaris México | 41.940 (90,58%) | 45.753 / 46.304 (98,81%) | +3.813 | 45.753 / 46.304 (98,81%) | 0 / 0 |

**Volaris supera el 95% en ambas sumas con estimados; AM y Viva no.** Eso no
valida una cobertura observada del 95%: el nacional sigue siendo estimado y
persisten celdas en revisión. Las observaciones regulares verificables son
7.983 AM, 3.647 Viva y 11.029 Volaris: 17,09%, 8,05% y 23,82% del respectivo
AFAC combinado. No disponer de observado nacional no significa cero vuelos.

AM internacional pasa del inventario preliminar 13.483 a **13.540** amplios.
Ese inventario contenía sólo BTS F y estimaciones: los +57 se descomponen en
51 BTS L más un efecto neto de +6 al sustituir 1.265 estimados por 1.271
observados de autoridades, con precedencia por dirección y mes. No son 57
vuelos adicionales de autoridad. El export contiene 8.276 observados de toda
clase más 5.264 estimados; 293 observados no entran en la suma regular
verificada (51 BTS L y 242 ANAC/CAA de clase sin confirmar). Viva internacional
representa **4.578** amplios frente a 4.537 regulares + estimados; la diferencia
son 41 BTS L. Volaris internacional representa 11.801 en ambas sumas. No se
reclasifica esa diferencia de clase ni se cambia el objetivo solicitado.

Los programados AM son **1.212 internacionales** en la base, más **31.098**
en la capa nacional oficial separada; esta última conserva además 364 vuelos
atribuidos a la marca. No se suman al numerador del 95% ni a la capa nacional
estimada. La caída de programados internacionales frente a la publicación se
debe a la prioridad de celdas observadas/estimadas, no a una afirmación de
cancelaciones o menor operación.

### Desglose mensual y trimestral del candidato base

Cada celda nacional/internacional presenta el numerador amplio sobre AFAC y
su porcentaje. Las dos últimas columnas comparan ambos numeradores con el
AFAC combinado del periodo. No se extrapolan meses ni se recortan los excesos.

| Aerolínea | Periodo | Nacional amplio / AFAC | Internacional amplio / AFAC | Combinado amplio | Combinado regular verificable + estimado |
|---|---|---:|---:|---:|---:|
| Grupo Aeroméxico | 2026M04 | 11.023 / 10.967 (100,51%) | 4.935 / 4.840 (101,96%) | 100,96% | 100,54% |
| Grupo Aeroméxico | 2026M05 | 10.170 / 11.219 (90,65%) | 4.821 / 4.833 (99,75%) | 93,39% | 93,00% |
| Grupo Aeroméxico | 2026M06 | 8.862 / 10.008 (88,55%) | 3.784 / 4.849 (78,04%) | 85,12% | 84,00% |
| Grupo Aeroméxico | 2026Q2 | 30.055 / 32.194 (93,36%) | 13.540 / 14.522 (93,24%) | 93,32% | 92,69% |
| Viva | 2026M04 | 11.810 / 13.502 (87,47%) | 1.512 / 1.605 (94,21%) | 88,18% | 88,12% |
| Viva | 2026M05 | 11.864 / 13.625 (87,08%) | 1.363 / 1.455 (93,68%) | 87,71% | 87,62% |
| Viva | 2026M06 | 11.617 / 13.303 (87,33%) | 1.703 / 1.818 (93,67%) | 88,09% | 87,98% |
| Viva | 2026Q2 | 35.291 / 40.430 (87,29%) | 4.578 / 4.878 (93,85%) | 88,00% | 87,91% |
| Volaris México | 2026M04 | 11.218 / 11.446 (98,01%) | 3.889 / 3.894 (99,87%) | 98,48% | 98,48% |
| Volaris México | 2026M05 | 10.990 / 11.343 (96,89%) | 3.841 / 3.838 (100,08%) | 97,69% | 97,69% |
| Volaris México | 2026M06 | 11.744 / 11.712 (100,27%) | 4.071 / 4.071 (100,00%) | 100,20% | 100,20% |
| Volaris México | 2026Q2 | 33.952 / 34.501 (98,41%) | 11.801 / 11.803 (99,98%) | 98,81% | 98,81% |

Los excesos de abril AM y junio nacional Volaris permanecen visibles como
inconsistencias de representación frente a AFAC. La coincidencia exacta de
junio internacional Volaris con AFAC no prueba coincidencia vuelo a vuelo.
Ninguna cifra de esta tabla base incorpora las 731 frecuencias de la variante
opcional, cuyos resultados se presentan por separado a continuación.

### Todas las rutas frente a las 12 iniciales

La tabla siguiente corresponde a 2T26 base. «Todas» cuenta únicamente rutas
con cifra de vuelos. La presencia exportada sin volumen permanece N/D y se
informa aparte; no se usa para inflar la representación. El subtotal top 12
sólo describe la vista inicial, nunca el porcentaje de red.

| Aerolínea | Rutas «Todas» nacional / internacional | Vuelos amplios de las 12 iniciales, nacional / internacional |
|---|---:|---:|
| Grupo Aeroméxico | 56 / 104 | 17.074 / 4.894 |
| Viva | 147 / 55 | 11.269 / 2.507 |
| Volaris México | 151 / 88 | 9.495 / 4.405 |

### Variante opcional acotada: 14 celdas AM, 731 frecuencias

La primera compilación acotada, en `6cd28741027ea288382bf91286574182b16172d7`, admite exactamente el selector privado revisado; no habilita todo el
fallback histórico de EE. UU. Su hash SHA-256 es
`ca019c6c4ca925c4805e5c5cef990e15c639c5ddcaed16cccba3a75b03c88b2f`.
La base puede revisarse y aprobarse con esta opción desactivada.

Los nueve bundles JavaScript de ambas previews son idénticos byte a byte,
al igual que los ocho JSON ajenos a Vuelos. Sólo cambian cuatro documentos
internacionales: AM e Industria, junio y 2T26. Fuera de las direcciones/meses
del selector, sus componentes conservan los mismos valores y procedencia.
El control adicional del constructor valida la admisión opcional; con la
opción desactivada permanece inerte. La diferencia de commit de compilación
no representa dos versiones distintas del frontend ni cambios no relacionados.

| Grupo Aeroméxico, variante acotada | Amplio / AFAC | Regular verificable + estimado / AFAC | Faltan para 95%, amplio / regular + estimado |
|---|---:|---:|---:|
| Junio internacional | 4.515 / 4.849 (93,11%) | 4.349 / 4.849 (89,69%) | 92 / 258 |
| Junio nacional + internacional | 13.377 / 14.857 (90,04%) | 13.211 / 14.857 (88,92%) | 738 / 904 |
| 2T26 internacional | 14.271 / 14.522 (98,27%) | 13.978 / 14.522 (96,25%) | 0 / 0 |
| 2T26 nacional + internacional | 44.326 / 46.716 (94,88%) | 44.033 / 46.716 (94,26%) | 55 / 348 |

Abril y mayo AM, todo el nacional y los resultados de Viva/Volaris permanecen
idénticos a la base. AM conserva 8.276 observados de toda clase y 7.983
observados regulares verificables en 2T26. Sus estimados combinados pasan de
35.319 a 36.050; ninguna de esas 731 frecuencias nuevas se etiqueta observada.

Los programados internacionales AM bajan de 1.212 a **332**: las 14 celdas
sustituyen 880 programados por 731 estimados de otra fuente. Es precedencia
entre fuentes con cifras distintas, sin sumarlas ni interpretar su diferencia
como cancelaciones. Los 332 programados restantes tampoco completan el 95%.
El mapa conserva 104 rutas internacionales con cifra en 2T26; sus 12 iniciales
representan 5.391 vuelos amplios, frente a 4.894 en la base.

**La variante acotada tampoco alcanza el 95% combinado AM:** faltan 55 vuelos
en la medida amplia o 348 en regular verificable + estimados. No hay evidencia
admitida para fabricarlos, redistribuirlos o aceptarlos sólo por su proximidad
al objetivo. Viva sigue con una brecha de 3.174/3.215 y requiere mejorar el
nacional. Volaris supera el objetivo en ambas sumas mixtas, manteniendo los
límites de calidad ya expuestos. La conclusión no es que las tres aerolíneas
hayan logrado una cobertura observada del 95%.

## Precedencia y trazabilidad de los vuelos

La unidad de decisión es **operador × aeropuerto origen × aeropuerto destino
× mes**, antes de agregar mercado, trimestre o Grupo Aeroméxico. Una
observación gana a una estimación de esa misma celda. Un cero observado
explícito también gana; una fila ausente conserva su carácter de faltante.
Así, BTS de abril/mayo no impide representar un estimado admitido de junio ni
justifica duplicar ese estimado donde BTS ya observa el mismo sentido y mes.
Un sentido observado no genera su vuelta. La programación tampoco completa
una celda realizada; las programaciones de marca AM no se asignan a Aerovías o
Connect sin evidencia del operador.

`flight_components` conserva operador, ambos aeropuertos, mes, clase de cifra,
fuente, hashes disponibles y versión del estimador. BTS conserva además el
desglose por clase de servicio. El total mixto de un mercado no se etiqueta
íntegramente como observado. La suma estrictamente comparable a AFAC usa BTS
F/G y operaciones regulares identificadas de Aerocivil; L/P y observaciones
ANAC/CAA sin clase regular confirmada permanecen fuera de esa segunda suma.
El backtest de frecuencias de pasajeros usa sólo F, un universo más estrecho
que el numerador regular F/G del informe.

El nacional mantiene la admisión histórica por mercado–mes y usa una única
base de frecuencias direccionales en mes, ruta y trimestre. La corrección de
coherencia no acepta por sí sola 35 frecuencias AM adicionales cuya identidad
o modelo no puede verificarse, ni la celda Viva de cinco frecuencias sin
marginal de pasajeros. La semilla prestada de otro mes no se convierte en
frecuencia del mes seleccionado. Pasajeros, asientos y ocupación siguen sus
reglas previas; sus tasas de cobertura no miden vuelos.

## Semilla retenida y propuesta acotada de EE. UU.

Se verificaron el snapshot privado y los 11 manifiestos derivados. El cubo
nacional conserva 3.721 celdas direccionales marzo–julio y el internacional
4.018 abril–julio. Los registros individuales del proveedor expiraron; no se
hacen nuevas llamadas AeroDataBox ni nuevos ajustes. Frecuencias ponderadas
de muestreo, incluso las que tienen `completed_weight`, siguen siendo
**estimadas**, no una lista de vuelos individuales realizados.

Junio internacional conserva estado `review`: 38,84% del peso de semilla sin
estado completado y 29 rutas por encima del 120% de vuelos AFAC al comparar
el mismo universo del gate. El buen error en las celdas emparejadas con BTS no
valida las celdas sin fila BTS. Tampoco se añade la diferencia captura–Gold
completa: puede repetir observaciones existentes, mezclar aeropuertos de una
misma ciudad o incluir soporte aún no aceptado.

La variante base mantiene **desactivado** el fallback estimado de EE. UU. La
propuesta opcional acotada conserva sólo 14 celdas AM, con **731 frecuencias
estimadas retenidas**, que superan esta pantalla para revisión:

- Mismo operador, aeropuertos y sentido con BTS F tanto en abril como en mayo.
- Peso `completed` retenido positivo, sin reclasificarlo como observado.
- Semilla de la ruta entre todos los operadores no superior al 120% de AFAC.
- Frecuencia no superior al 120% del máximo BTS de abril/mayo, sin reescalarla.
- Sin observación de otro operador del grupo AM en esa misma dirección y mes.
- Sin códigos aeroportuarios de procedencia sin resolver; no se remapean SDM,
  IWS o CHA para introducir vuelos adicionales.

El umbral ruta/AFAC 1,20 ya existe en `assess_international_seed`; el límite
individual respecto a abril/mayo es una pantalla nueva, conservadora y no
calibrada. Ninguno es una probabilidad, un intervalo de confianza ni una
regla ajustada para llegar al 95%. La lista privada exacta y su recibo deben
acompañar la preview para reproducir su admisión. Las otras 294 frecuencias AM
permanecen en revisión; no se aceptan las 216 Viva ni las 44 Volaris de la
alternativa íntegra de EE. UU. Revisar esa opción es independiente de aprobar
la ampliación base.

La auditoría también identifica estimaciones **ya presentes** en la variante
base sobre rutas en revisión por exceso frente a AFAC. Mantenerlas como
histórico no certifica su calidad ni elimina el riesgo del numerador mixto.
AICM publica series y cumplimiento de slots, con excepciones de cancelaciones:
no acredita por sí solo vuelos realizados y no resuelve estas lagunas.

## Reproducir la comparación y criterios de cierre

Las previews se construyen desde entradas confirmadas y los pins externos
ya aprobados, sin generar recibos de producción ni nuevas aprobaciones:

```bash
python -m scripts.research.build_flight_coverage_preview \
  --out /ruta/privada/preview-base
python -m scripts.research.build_flight_coverage_preview \
  --out /ruta/privada/preview-acotada --include-existing-us-estimates \
  --us-estimate-admission /ruta/privada/selector-revisado.json
```

```bash
python -m scripts.research.flight_representation \
  --private-root /ruta/al/respaldo \
  --snapshot publicada /ruta/al/site-aprobado /ruta/al/gold-anterior \
  --snapshot pr-anterior /ruta/a/preview-anterior /ruta/al/gold-anterior \
  --snapshot base /ruta/a/preview-base /ruta/al/gold-nuevo \
  --snapshot apoyo-us /ruta/a/preview-acotada /ruta/al/gold-nuevo \
  --out /ruta/privada/fuera-del-checkout/informe
```

El CSV y JSON privados contienen cifras por entidad/ámbito/mes/trimestre,
desglose de clases, denominador AFAC, las tres proporciones y brechas separadas
al 95% para los dos numeradores que incluyen estimados, diferencia respecto a
la primera versión, número de rutas y subtotal de las 12 iniciales con cifra
de vuelos. `all_exported_routes` cuenta todo el JSON;
`all_selectable_routes`/`quantified_routes` corresponden a «Todas» en la tabla.
Las rutas exportadas sin volumen quedan N/D, se cuentan aparte y no entran en
«Todas» ni en las 12 iniciales. El JSON registra hashes de mapas, insumos Gold consultados,
script y workbooks oficiales. La exportación internacional publicada no
permite descomponer todos sus totales trimestrales por mes: esos comparativos
mensuales quedan N/D, sin distribuirlos. Los agregados recuperados del
borrador anterior sí se contrastan donde existe el archivo mensual.

La entrega requiere pruebas de conservación y precedencia, CI y revisión del
head final, más navegador en escritorio/móvil y contraste de todas las rutas
seleccionables. Debe mantener idénticos los datos ajenos a Vuelos y las cuatro
tesis aprobadas. Ni este reporte, ni la compilación de una preview, ni una
revisión técnica equivalen a integración, aprobación o publicación. El PR de
vuelos continúa separado de Mercado #135 y Noticias #136, sin activar
agosto ni alterar secretos o protecciones.


## Verificación y registro de cierre

Navegador del entorno cloud `airlines-tracker`, manejado por el agente con
Playwright Python y Chromium headless; no es el equipo del usuario. El cierre
repite **134 casos HTTP y 134 offline por variante** entre las cuatro entidades
y anchos 1440/390, contrastando todas las rutas con sus archivos de datos.
El inventario estático revisa los 765 documentos de periodo por variante y sus
componentes. La prueba distingue «Todas», las 12 iniciales, capas y tipos de
cifra; el registro final conserva los conteos exactos tras retirar mercados
nuevos que sólo tenían cero. Se verifican además los rankings comparables y
el cambio desde un periodo histórico internacional a un ámbito que no lo ofrece.
Las ocho piezas JSON ajenas a Vuelos y los nueve bundles JavaScript coinciden
entre variantes.

En ambas versiones autocontenidas se comprobaron las cuatro tesis aprobadas
con sus afirmaciones y citas, y los dos archivos de evidencia descargables;
no hubo peticiones externas. El QA de las rutas del archivo entregable usa
el mismo contraste que la versión HTTP.

El dashboard de producción responde HTTP 200 y sus seis totales Q2 por
aerolínea/ámbito coinciden con el informe publicado. Alternar aerolínea y
ámbito rápidamente reproduce un acceso a `world_geometry` con red nula.
El candidato cancela el render obsoleto y espera una red instalada: cinco
regresiones nuevas, 202 pruebas web y TypeScript pasan. La reparación sólo
forma parte del borrador; producción conserva su versión hasta aprobación.

La primera suite completa con el warehouse actualizado reprodujo un fallo
esperado de `test_stage12_diagnosis::test_outputs_match_snapshot_and_are_reproducible`:
el diagnóstico histórico exige el HTML, JSON y CSV fijados con el warehouse
anterior. No se regeneran ese expediente, las tesis ni sus aprobaciones para
adaptarlos a BTS nuevo. La paridad
`test_site_flights_and_executive_data_match_a_fresh_export` exige asimismo que
el export candidato coincida con `site/` aprobado, que se conserva intacto.
Ambos checks se informan como exclusiones justificadas, no como aprobados.

El resultado definitivo del head entregado se registra en
[los checks del PR #134](https://github.com/salvamalfa/aeromexico-tracker/pull/134/checks)
y en su comentario de cierre y revisión. Ese registro debe identificar el
commit, el conteo de la suite restante, sus dos exclusiones, la revisión
independiente y Codex. Un resultado de otro commit no sustituye los checks
vigentes. Las compilaciones iniciales usaron `c5bbfb4`/`6cd2874`; las recompilaciones
de cierre registran su propio commit en `preview-metadata.json` y en el
comentario del PR. La corrección de soporte temporal no cambia los
numeradores ni los denominadores de las tablas anteriores.

Continúan vigentes los límites de no integrar, no publicar y no activar
análisis. La revisión técnica y las previews no sustituyen la aprobación
explícita del propietario, incluida una decisión independiente para habilitar
el selector US. El expediente histórico del 15 de octubre no se reescribe.

Comando de la suite funcional restante, sin modificar los artefactos antiguos:

```bash
python -m pytest -m 'not browser' \
  -k 'not test_site_flights_and_executive_data_match_a_fresh_export and not test_outputs_match_snapshot_and_are_reproducible' -q
```


### Controles adicionales de la revisión de cierre

La disponibilidad temporal se distingue del alcance geográfico: una red puede
contener todos sus meses esperados y seguir representando sólo las fuentes y
mercados declarados. Los periodos completos vuelven a permitir comparaciones,
conservando `agent_eligible` y los límites de publicación retrospectiva.

Para una comparación de salidas con desglose moderno, cada operador y sentido
debe tener todos los meses esperados en ambos periodos, con fuentes y tipos
comparables. Un mes ausente no se interpreta como cero ni se presenta como
una caída de 20 frente a 60. Un cero explícito sí conserva soporte. Los
rankings del chat y la comparación previa del mapa aplican esta restricción;
el detalle de vuelos no se usa como prueba de soporte de pasajeros o asientos.
En Q2 se conservan las comparaciones BTS conciliadas y se recuperan las de ANAC y Aerocivil con evidencia completa en ambos años. Las pruebas cubren también CAA mensual, cero explícito y soporte parcial; los valores actuales no cambian. Los payloads legados sin detalle mantienen su política explícita anterior.

El auditor anterior `flight_coverage.py` también divide las rutas mixtas por
componente. BTS se concilia de forma independiente contra Gold por operador,
aeropuertos, dirección, mes, clase y hashes; Aerocivil por operador ICAO,
dirección, mes y hashes. No basta que los números de un componente sumen sus
propias clases. El CLI rechaza falta de evidencia o diferencias y conserva
F/G como regular verificable, con L/P separados. Las celdas ANAC/CAA sin clase
regular confirmada siguen excluidas de ese numerador.


Los mercados nuevos compuestos únicamente por celdas BTS observadas de cero no
se dibujan como rutas con vuelos. Las celdas cero siguen bloqueando el fallback estimado y permanecen
en los mercados con otras celdas positivas. Al cambiar aerolínea o ámbito,
el selector del mapa conserva únicamente periodos disponibles y vuelve a una
opción válida si el periodo anterior queda fuera del nuevo manifiesto.


### Comprobaciones locales posteriores con insumos idénticos

La verificación adicional del 17 de octubre sustituye el criterio anterior de
excluir dos checks. Se comparó `master 40a63d1905` con el candidato `30b82fd7cc`
usando los mismos **2,319 archivos** de `data/` y `analysis_runs/`, incluidos
warehouse, Gold y expediente. El checkout de master conservó su código exacto,
con los datos del candidato superpuestos deliberadamente para esta comparación;
no es una reproducción del warehouse histórico de producción. Los artefactos
esperados de Stage12 y `site/` eran idénticos en ambos árboles. Las dos pruebas
fallaron en ambos antes de regenerar. Se verificaron nuevamente los 2,319
hashes al terminar la comparación.

Se ejecutó el generador canónico `python -m src.analysis_agent.stage12`.
El único cambio semántico es `input_sha256.warehouse_content`, de
`116acd74a4352283f6cd477a46622e679cff1f13a3d214a5d7c5495269b36212` a
`d7c6497de5cec829f083f461613550ce5ce113280b91847f8398de0bc9f6e493`.
JSON y HTML se regeneran juntos; CSV, filas, cifras, conclusiones y estados
permanecen idénticos. El artefacto declara `diagnosis_not_analysis` y
`current_warehouse_not_point_in_time`; esta regeneración diagnóstica no importa,
audita, aprueba ni publica una tesis.

El export nuevo de Vuelos coincide byte a byte con la preview base entregada.
El export ejecutivo sólo cambia `/metadata/data_as_of`, de `13 sep 2026` a
`17 oct 2026`; sus cifras no cambian. La preview conserva los bytes ejecutivos
aprobados, incluidas esa fecha y las cuatro tesis. Se conserva fuera de `site/`
el diff exacto propuesto de vuelos/ejecutivo, con hashes antes/después, en el
expediente privado del PR de datos. No es un sitio firmado ni publicable.

La paridad de `site/` sigue siendo un fallo real: el sitio aprobado todavía
contiene los datos previos. El gate normal exige además la huella actual de
implementación para Industria, Viva y Volaris; sus registros históricos siguen
aprobados, pero sus huellas ya no coinciden en master ni en el candidato.
El contrato sólo admite `approve_analysis` para versión y `content_hash`
exactos: no existe aprobación separada de compilación. Reimportar con la nueva
huella crea una versión nueva, aun conservando la tesis. No se cambian el
ledger, las aprobaciones, `site/` ni los recibos para hacer pasar esa prueba.
La decisión mínima para la vía actual es preparar y auditar esas tres versiones
técnicas y obtener sus aprobaciones exactas; una autorización genérica para
Vuelos o para publicar no satisface ese contrato. Esta preparación no aplica
dicha parte y no declara listo el gate.

La suite local se vuelve a ejecutar con `--require-local-data -m 'not browser'`,
sin filtros `-k`: incluye ambas comprobaciones. Los conteos y el fallo pendiente
se registran con el commit en el comentario actualizado del PR. La cobertura de
navegador HTTP/offline y las entregas Library conservan sus identidades y
versiones: esta regeneración diagnóstica no cambia el dashboard entregado.

Para interpretar Q2 se distinguen dos numeradores sobre el mismo denominador
AFAC regular de cada aerolínea (AM 46,716; Viva 45,308; Volaris 46,304):

| Variante | AM amplia / regular comparable | Viva amplia / regular comparable | Volaris amplia / regular comparable |
| --- | ---: | ---: | ---: |
| Base | 43,595 / 43,302 | 39,869 / 39,828 | 45,753 / 45,753 |
| EEUU revisado | 44,326 / 44,033 | 39,869 / 39,828 | 45,753 / 45,753 |

«Amplia» suma observados y estimados aunque una parte observada sea no regular
o de clase sin confirmar. «Regular comparable» excluye esa parte observada;
conserva estimaciones declaradas, que no se convierten en operaciones regulares
verificadas. Así, AM EEUU es **94.88% amplio y 94.26% comparable**, Viva
**88.00% y 87.91%**, y Volaris **98.81% en ambos**. Ninguna de esas razones es
cobertura observada: sólo regular observado representa 17.09%, 8.05% y 23.82%,
respectivamente. La programación no entra en esos numeradores.

## Continuación autorizada, 18 de octubre

El propietario aprobó las tres identidades técnicas exactas de Industria,
Viva y Volaris para 2T26 después de sus auditorías independientes. El expediente
privado registra el consentimiento auténtico y los eventos 76–78. Se conserva
la precisión de la fecha fuente y se distingue de la hora real de recepción y
verificación; no se inventa una hora original del mensaje.

La huella de implementación sigue siendo
`140b79971bfbcc318e18fd1eeb18a3f071128c6764d891475565329a68e756bd`.
Se materializaron byte a byte los tres registros auditados y se ejecutó el gate
normal con cuatro `--record`, incluido el histórico de Aeroméxico. El sitio
firmado contiene 791 archivos y pasa `python -m src.publish.verify site/`.
El primer intento se detuvo en la caché npm no escribible antes del reemplazo;
la repetición completa usa la caché del workspace documentada en la guía cloud.

La comparación contra el sitio anterior confirma las cuatro tesis y sus
cifras/fuentes intactas. Aeroméxico conserva su payload exacto; las otras tres
sólo cambian versión, aprobación, auditoría y cabeza de eventos de su versión.
Los payloads financieros y de mercado son idénticos; en Ejecutivo sólo cambia
la fecha de actualización. El mapa usa la base; la opción adicional de
estimaciones de EEUU sigue desactivada. No hubo capturas pagadas, nuevos ajustes
de modelos ni activación de evidencia candidata.

El PR #134 registra la ejecución completa de pruebas, CI, revisión y
comprobación online del commit integrado. El respaldo privado conserva los
registros exactos, autorizaciones, cadena de eventos y recibos del gate; su
actualización es acotada y no rejuvenece el warehouse ni los modelos originales.

La primera suite completa del sitio firmado ejecutó las 1.696 pruebas sin
exclusiones: 1.689 pasaron, seis fallaron y una se omitió por no existir un pin
de preview Pages; 29 subtests pasaron. Paridad y narrativa aprobada quedaron
cerradas. El catálogo del chat alcanzó 28.580 bytes por la nueva lista mensual,
por encima de su límite de 16.000. Los otros fallos eran expectativas del sitio
anterior y la métrica de tamaño de la matriz diagnóstica F2.9.

La respuesta interna de `get_data_catalog` representa las listas largas como
rangos inclusivos de un mismo grano; separa huecos y conserva todos los IDs,
alias, unidades y límites. El catálogo HTTP y la selección interna de escenarios
siguen usando IDs individuales. No cambia el esquema de herramientas, el prompt,
el límite de transporte ni los fixtures/pins de la campaña histórica. La matriz
F2.9 se regenera sólo en la línea que mide bytes de herramientas offline; no se
recalifica una evaluación humana ni se ejecuta una campaña pagada.

Las expectativas reales de rutas se contrastan con la nueva base: GUA–MEX y
CDG–MTY usan estimaciones retenidas; MEX–SNA conserva 182 vuelos programados;
102 rutas tienen asientos para la consulta internacional de AM. El calendario
Q2 contiene los tres meses, con elegibilidad histórica todavía falsa; esto no
certifica cobertura mundial. Las pruebas sintéticas mantienen las restricciones
por métrica, operador/sentido, fuente y meses incompletos. La huella técnica de
las tres tesis permanece exactamente igual tras estas correcciones del backend.

La corrección pasa 79 pruebas focalizadas y los tres presupuestos del repositorio,
además de Ruff. La repetición del gate normal desde el commit corregido conserva
byte a byte todos los assets y datos del sitio: sólo cambia `code_commit` en el
manifest firmado. La versión de datos de las conversaciones también se conserva;
la copia base de Library no necesita otra sustitución por este cambio del backend.

Al marcar el PR listo, una segunda revisión automática detectó que el agregado
trimestral nacional conservaba el detalle mensual sólo del primer mes. Se
reprodujeron tres fallos y se concatenan ahora los detalles de los tres meses,
con copias independientes de `monthly` y `flight_components`. Las regresiones
comprueban comparación trimestral válida, mezcla de tipos de vuelos, rechazo
de detalle incompleto y meses/rutas ausentes como N/D; no inventan detalle para
los payloads históricos que carecen de él. Pasan las cuatro regresiones, los
tres presupuestos y una ronda ampliada de 83 pruebas. La matriz F2.9 queda
idéntica tras regenerarla y la huella aprobada permanece inalterada.

La revisión posterior señaló que el informe de representación comprobaba la
coherencia interna de componentes observados sin reconciliarlos con el Gold
proporcionado. Reutiliza ahora la comprobación independiente del auditor de
cobertura: operador, aeropuerto/sentido, mes, conteo, hashes y clases BTS. ANAC
y CAA también concilian conteos/hashes con Gold, conservando la regularidad
como no confirmada. Una celda BTS coherente de 101 vuelos frente a 100 en Gold
pasaba antes y se rechaza ahora. Pasan 72 pruebas focalizadas, incluidas 26
pruebas con Gold Parquet separado del candidato y falsificaciones coherentes.
Los 36 resultados reales y su CSV quedan idénticos; los artefactos de revisión
conservan su fecha y generador originales y la comprobación adicional queda
en el expediente privado. El cambio sólo afecta auditoría offline: no cambia
inputs de compilación, assets, datos publicados, backend ni aprobaciones, por
lo que conserva el sitio firmado del commit de código que lo generó.

La revisión siguiente detectó una ambigüedad de presentación: LAX–MEX en junio
mostraba 143 como total y «143 observados · 147 programados» como desglose.
La leyenda principal usa ahora los mismos componentes activos que el total;
la programación se conserva en una línea separada, «147 programados (fuera
del total)». Las rutas con sólo programación mantienen su propia cifra, y un
cero observado conserva su significado. Pasan 212 pruebas de frontend,
TypeScript y la compilación; se contrastó la fila real a 1440 y 390 píxeles.
Los totales de tarjetas y los datos permanecen intactos. Esta corrección sí
modifica la huella de presentación de las tres tesis por entidad: requiere
versiones técnicas nuevas, auditoría independiente y aprobación humana de sus
pares exactos. El PR vuelve a borrador; el sitio firmado anterior se conserva
como evidencia histórica y no se regenera ni integra con esas aprobaciones.

Después de fijar la corrección, Codex revisó el commit exacto sin hallazgos.
Las tres propuestas nuevas conservan texto, cifras, citas, prompt y cálculos;
la auditoría independiente revisó de nuevo 50 claims, 262 inputs y 577 nodos,
con tres dictámenes `pass`, 12 advertencias conservadas y cero bloqueos.
El expediente registra únicamente las auditorías 79–81 y, tras la decisión
humana posterior sobre esos pares exactos, las aprobaciones 82–84. El gate
normal regeneró 791 archivos desde `8992ad5` y el verificador del sitio pasó.
Los 770 JSON ajenos al análisis quedan idénticos a la base anterior; las cuatro
tesis conservan su contenido y sólo cambian los metadatos técnicos autorizados
de las tres versiones renovadas. La proyección privada incorpora 45 registros
canónicos válidos, conservando el historial y la exclusión documentada del
wrapper histórico inválido. No cambian Gold, modelos, capturas ni la opción US.

La suite completa de `d9da4b7` cerró con 1.733 pruebas y 29 subtests pasados,
más una omisión por preview Pages sin fijar. La revisión automática posterior
a marcar el PR listo detectó tres fallos que impidieron integrar ese artefacto:
la programación AICM se reducía a las celdas sin operación, la cobertura usaba
la unión de meses de operadores/sentidos distintos, y la cifra programada no
identificaba su fuente en la fila. Las correcciones se agrupan en el borrador.
Se conserva una fuente programada por celda como medida independiente, sin
sumarla a operaciones/estimaciones; la cobertura usa el mínimo por operador y
sentido conocidos, y la fila/pie nombran las fuentes de todos los componentes.
Las regresiones reprodujeron tres fallos Python y cuatro de frontend antes de
corregirlos. Después pasan 52 pruebas focalizadas Python, 218 de frontend,
TypeScript, Ruff y los tres presupuestos del repositorio. Los cambios de
interfaz vuelven a modificar la huella técnica: las aprobaciones 82–84 se
conservan para sus pares anteriores y no se trasladan. El sitio firmado de
`d9da4b7` queda como evidencia histórica, sin integrar ni publicar; la preview
corregida es explícitamente no firmada y no sustituye al gate normal.

La leyenda de programación también explicita su sentido: el total de ambos
sentidos permanece distinguible de un headline operativo unidireccional.

Una revisión adicional encontró que julio, disponible en las estimaciones,
seguía seleccionable al cambiar a la capa nacional oficial aunque esta sólo
tenía el segundo trimestre. El selector oficial ofrece ahora los trimestres
disponibles y los meses fechados de sus propias filas, y vuelve a un período
válido al cambiar de capa. Las otras entidades conservan julio estimado. Dos
regresiones fallaban antes; pasan las 221 pruebas de frontend, TypeScript y
la compilación. Chromium del entorno cloud comprobó el cambio de capa y de
entidad a 1440 y 390 píxeles, con rutas visibles y sin modificar el trimestre
financiero. Esta corrección se incorpora antes de congelar la huella conjunta
con las otras pestañas; no genera nuevas aprobaciones ni publica el sitio.

Para preparar una sola publicación conjunta, este PR conserva `site/` idéntico
al `master` productivo `40a63d1`. El sitio aprobado anterior de `d9da4b7` se
preserva íntegro en el expediente privado, con hash del archivo y commit de
origen; no se usa como artefacto de estas correcciones. El lector de snapshot
y el runtime real local (autenticación, worker y consulta con proveedor mock)
aceptan los 134 archivos firmados del baseline con sus pins ya aprobados.
Esto permite revisar primero el código sin disparar Pages. Railway puede
redesplegar el backend por sus patrones de entrada: cada integración debe
verificar su salud y conservar ese snapshot hasta el sitio conjunto final.
El gate normal, la suite completa y la comprobación productiva corresponden
al árbol final conjunto una vez aprobadas sus nuevas identidades exactas.

La CI de esa transición reprodujo cuatro expectativas de chat ligadas sólo
al sitio nuevo y una matriz documental desactualizada. Las pruebas distinguen
ahora los dos hashes de contrato firmados: el baseline conserva 75 rutas
consultables, cobertura BTS parcial y sumas no comparables N/D; el contrato
por componentes conserva 102 rutas y cobertura trimestral completa. Se
comprueban los conteos programados y valores por aerolínea exactos de cada
perfil, sin omisiones ni ampliar límites de tamaño. Pasan 34 pruebas con el
baseline (incluida la matriz regenerada con su generador) y las cuatro pruebas
afectadas contra el sitio D9 firmado preservado. Sólo cambian tests y
documentación: la huella de presentación corregida permanece congelada.
