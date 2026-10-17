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

**Resultados del nuevo mapa pendientes:** los inventarios previos al export
no sustituyen el resultado del generador integrado. La tabla final debe
contrastarse con las dos previews compiladas, por mes y trimestre, nacional e
internacional, con todas sus rutas seleccionables y la vista inicial de 12
rutas por separado. No se promete un 95% para las tres aerolíneas.

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
