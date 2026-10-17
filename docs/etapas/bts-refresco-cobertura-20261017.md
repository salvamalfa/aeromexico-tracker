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

La preview base compilada en `c5bbfb4eddfcc0868aae869a848026c0c29e3aa8`
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

Compilada en `6cd28741027ea288382bf91286574182b16172d7`, la segunda
preview admite exactamente el selector privado revisado; no habilita todo el
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


## Verificación de la preview base y pendientes de cierre

Navegador del entorno cloud `airlines-tracker`, manejado por el agente con
Playwright Python y Chromium headless; no es el equipo del usuario. La base
pasa **134 casos HTTP** entre las cuatro entidades y anchos 1440/390, con
**14.244 registros de rutas** contrastados en las selecciones. El inventario
estático revisa 765 documentos de periodo, 41.267 rutas exportadas y 118.846
componentes; 44 rutas no tienen cifra de vuelos. La prueba distingue «Todas»,
las 12 iniciales, capas y tipos de cifra.

La primera suite completa con el warehouse actualizado reprodujo un fallo
esperado de `test_stage12_diagnosis::test_outputs_match_snapshot_and_are_reproducible`:
el diagnóstico histórico exige el HTML, JSON y CSV fijados con el warehouse
anterior. No se regeneran ese expediente, las tesis ni sus aprobaciones para
adaptarlos a BTS nuevo. La paridad
`test_site_flights_and_executive_data_match_a_fresh_export` exige asimismo que
el export candidato coincida con `site/` aprobado, que se conserva intacto.
Ambos checks se informan como exclusiones justificadas, no como aprobados.

**Pendiente de cierre:** QA de navegador de la variante opcional acotada,
conteo de la suite restante, CI y revisión del head final. Los resultados anteriores de
la rama auxiliar no sustituyen esas comprobaciones. Continúan vigentes los
límites de no integrar, no publicar y no activar análisis.


Los resultados definitivos de CI y la revisión automática deben consultarse en
[los checks del PR #134](https://github.com/salvamalfa/aeromexico-tracker/pull/134/checks)
y [su revisión](https://github.com/salvamalfa/aeromexico-tracker/pull/134).
El head de código verificado para estas compilaciones es `6cd28741027ea288382bf91286574182b16172d7`;
**CI y revisión de ese head siguen pendientes en este corte**. No se atribuye
un resultado verde al head nuevo por haberlo obtenido en una entrega anterior.
El conteo final de la suite se incorporará al terminar la ejecución, conservando
los dos checks excluidos y la evidencia de sus insumos históricos.

Comando de la suite funcional restante, sin modificar los artefactos antiguos:

```bash
python -m pytest -m 'not browser' \
  -k 'not test_site_flights_and_executive_data_match_a_fresh_export and not test_outputs_match_snapshot_and_are_reproducible' -q
```
