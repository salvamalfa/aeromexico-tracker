# Continuidad de Airline Tracker sin capturas AeroDataBox recurrentes

Este plan conserva la decisión del **15 de octubre de 2026**, aprobada mediante el
[PR #133](https://github.com/salvamalfa/aeromexico-tracker/pull/133).
La procedencia de la
[ampliación posterior de cobertura](etapas/cobertura-vuelos-20261015.md)
se conserva en su bitácora. Para el estado publicado, consultar el
[README](../README.md) y el manifiesto del sitio; esta guía no sustituye las
aprobaciones de cada entrega.
El dueño sustituyó la propuesta de retirar el histórico: **se conserva todo el
snapshot publicado y el mapa muestra únicamente vuelos**. Las tarjetas
oficiales, pasajeros agregados, finanzas y cuatro tesis permanecen iguales.
El chat conserva el histórico con su procedencia y tipo de cifra. No hay
capturas AeroDataBox recurrentes, contrataciones ni activación automática de
modelos o actualizaciones programadas.

## Qué sabemos de AFAC y de la semilla

AFAC publica vuelos y pasajeros por **mes × par direccional de ciudades,
todas las aerolíneas** (`REG NAC`/`REG INT`), y marginales separadas por empresa.
Falta la celda **ruta × aerolínea × mes**. El workbook O-D de julio de 2026
conservado se reparseó con el adaptador: sus 4.263 filas de 2026 coinciden
exactamente con el CSV público. Fuente: [AFAC, Excel O-D julio 2026](https://www.gob.mx/cms/uploads/attachment/file/1100280/sase-julio-2026-27082026.xlsx).

El IPF actual ajusta **pasajeros**, usando marginales de pasajeros. Ese share
no es participación de vuelos: los tamaños de avión y la ocupación difieren.
Las frecuencias históricas publicadas vienen de conteos/muestras AeroDataBox,
expandidas según el calendario y sujetas a los filtros de cobertura de la
capacidad; no se obtienen convirtiendo pasajeros IPF en vuelos. Ver
[método canónico](estimacion-pasajeros-ruta-aerolinea.md),
`src/ingest/aerodatabox/{flights,__main__}.py`,
`src/analytics/{international_capacity,fleet_capacity}.py`.

Técnicamente es posible estimar una celda futura con **marginales de vuelos**
y una semilla congelada de oferta. No queda identificada como observación.
El prototipo calcula `vuelos AFAC de la ruta × share de frecuencias de abril`
por aerolínea, sin usar pasajeros. No reconcilia aún la marginal por empresa:
en junio hay 37.064 vuelos por rutas y 36.672 por empresas (392 de diferencia,
1,06 % del primer total). Los pasajeros de ambas marginales sí coinciden.
Hay que resolver ese alcance antes de un IPF de operaciones productivo;
reescalar no demuestra que sean el mismo universo.

La semilla nacional conservada abarca marzo–agosto de 2026, la internacional
abril–agosto; no septiembre. Los ajustes de pasajeros llegaron a julio.
Una semilla antigua no informa nuevas rutas, cierres, cambios de operador,
frecuencia o mezcla competitiva. Los ceros estructurales y faltantes se
mantienen explícitos; la masa no soportada no se reparte como si se observara.
Las diferencias entre semillas alternativas son sensibilidad, no intervalos
de confianza de vuelos realizados. Con los insumos actuales no se activan
estimaciones para meses nuevos.

## Qué se puede comparar con AICM

AICM conserva fechas, números y horarios UTC de **slots asignados con número AM**;
no confirma ejecución ni identifica por sí solo al operador efectivo.
AeroDataBox conserva agregados mensuales por ruta/operador; no quedan filas
individuales con fecha, hora, número y estado. El adaptador excluyó cancelaciones
explícitas y `IsCodeshared`, pero aceptó estados no confirmatorios y códigos
compartidos desconocidos. No es posible rehacer una deduplicación por vuelo,
alinear zonas horarias o dar una tasa de coincidencia vuelo a vuelo.
En la captura internacional agregada abril–julio, 38,9–41,7 % del peso tiene
estado no confirmatorio. Ese porcentaje no es una tasa de cancelación ni
una medición del histórico nacional.

El contraste disponible es mensual y direccional en MEX, como **proxy de marca
AM frente a Aerovías + Connect**, con los límites anteriores:

| Mes 2026 | Direcciones comunes | Slots en esas direcciones | Semilla expandida | Suma de diferencias absolutas por dirección |
|---|---:|---:|---:|---:|
| Abril | 89 | 10.245 | 10.572 | 2.261 |
| Mayo | 90 | 10.531 | 9.759 | 1.676 |
| Junio | 88 | 10.094 | 8.521 | 1.915 |

No se eliminaron duplicados de slots: ya eran únicos por fecha, dirección,
número, sufijo y horario. Las diferencias de conteo no permiten decidir qué
vuelos individuales coincidieron, se cancelaron o se operaron.

## Ensayo temporal retrospectivo: utilidad de AICM como covariable

Calibración en **abril**; validación en **mayo** contra salidas realizadas BTS
T-100, clase regular de pasajeros `F`, operador Aerovías. Se eligieron por
reglas previas las celdas MEX–EE. UU. con fuentes disponibles y ciudad AFAC
sin ambigüedad de aeropuerto: **12 direcciones/mes de 38 candidatas de abril**,
619 salidas BTS en mayo. AICM se usa como covariable de marca/programación,
no como prueba del operador de cada vuelo.

| Estimación retrospectiva de mayo | Error absoluto ponderado (WAPE) | Error absoluto medio por dirección/mes |
|---|---:|---:|
| Semilla de abril × vuelos agregados AFAC de mayo | 2,80 % | 1,44 vuelos |
| Slots AICM de mayo × razón BTS/slots aprendida en abril | 16,06 % | 8,28 vuelos |
| Combinación fija 50/50 de ambas | 9,37 % | 4,83 vuelos |

No se usaron celdas BTS de mayo para calibrar ni elegir el peso 50/50. El AFAC
del mes objetivo ya publicado es un insumo para desagregar; no se está
pronosticando un mes sin datos. El ensayo no muestra mejora al añadir AICM.
Es un ensayo retrospectivo, no una campaña prospectiva intocada: la semilla y
los crosswalks ya existían antes de este ensayo y su desarrollo tuvo contrastes
T-100. Es un solo mes, seis mercados, cobertura seleccionada y roles de fuente
parcialmente diferentes; no valida México completo, Volaris/Viva, rutas
nuevas ni la estabilidad de una semilla envejecida varios meses.

**Recomendación:** conservar el histórico etiquetado; explorar AFAC + semilla
como estimación de operaciones, con revisión de cobertura/universo, sensibilidad
y validación temporal adicional. Si se desarrolla, declarar periodo/edad de la
semilla, fracción de vuelos AFAC sin soporte y bandas de escenarios entre
semillas históricas estrictamente anteriores; no llamarlas intervalos de
confianza. Mantener AICM como programación y contraste
local en MEX. No añadirlo como una corrección validada de vuelos realizados.
Antes de reutilizar la semilla tras cancelar, revisar la
[frontera contractual documentada](cloud-development.md#proveedores-pagados-y-github).

## Auditoría de fuentes y uso de Gold

La meta de representación se comprueba con un denominador fijo de vuelos
regulares AFAC. Se muestran por separado observaciones, estimaciones y
programación. Una estimación conserva ese nombre aunque el total supere el
umbral. No se activa el calendario por completar una captura: faltan la
validación de capas, la revisión de cobertura y la aprobación de cifras nuevas.
El inventario general sigue en el
[catálogo de fuentes y calendario](catalogo-fuentes-calendario.md); esta sección
solo precisa su uso para vuelos.

- `fact_international_route_observations` ya aporta observaciones al mapa.
  Antes de ampliar operadores, se comprueban operador efectivo, servicio
  regular, dirección, mes, original y precedencia. Colombia puede sustituir una
  estimación existente; se conservan también las sustituciones que reducen el
  conteo. Una fila ausente no se convierte en cero.
- Para ANAC Brasil, verificar `GRUPO_DE_VOO=REGULAR`, `NATUREZA=INTERNACIONAL`
  y `DECOLAGENS` en el original permite revisar la clasificación de una
  observación ya contada. No añade vuelos al total amplio. Se conserva el
  calendario nativo descrito por la
  [metodología de ANAC](https://www.anac.gov.br/acesso-a-informacao/dados-abertos/areas-de-atuacao/voos-e-operacoes-aereas/dados-estatisticos-do-transporte-aereo/48-dados-estatisticos-do-transporte-aereo).
- Los datos de puntualidad CAA requieren cautela: sus
  [notas metodológicas](https://www.caa.co.uk/data-and-analysis/uk-aviation-market/flight-punctuality/uk-flight-punctuality-statistics-notes/)
  permiten atribución al responsable comercial y destinos finales con escalas.
  La marca comercial no acredita por sí sola el operador físico de un tramo.
- Aena aporta agregados por aerolínea y aeropuerto, o por mercado de todas las
  aerolíneas. No se cruzan para inventar una celda de operador y ruta. Una
  columna de salidas completamente nula sigue siendo no disponible.
- AICM y OMA aportan programación; AIFA y AFAC aportan márgenes o presencia
  cuando falta el cruce de operador y ruta. Esos productos sirven para
  contraste, pero no rellenan vuelos realizados sin evidencia adicional.
- Una nueva fuente de movimientos, como
  [ANAC Argentina](https://datos.transporte.gob.ar/dataset/aterrizajes-y-despegues-procesados-por-la-administracion-nacional-de-aviacion-civil-anac/archivo/7b6d0103-0a69-4c67-aed9-33cb58ae12f5),
  requiere comprobar calendario, operador y continuidad física. No se corrigen
  movimientos incompatibles por inferencia ni se toma la fecha de llegada
  extranjera como fecha de salida mexicana.

### Apéndice técnico: comparar candidatos sin activarlos

`scripts.research.flight_gap_options` ejecuta una comparación privada y sin red
con la misma base que `scripts.research.flight_representation`. Comprueba hashes
de capturas, conteo independiente de Colombia, registros originales de Brasil y
coincidencia con las celdas del mapa. Mantiene el denominador y el estimador;
no modifica Gold, el warehouse, exportadores, aprobaciones ni `site/`.

```bash
python -m scripts.research.flight_gap_options \
  --site /ruta/exportacion-retenida \
  --gold data/gold \
  --private-root /ruta/respaldo-privado \
  --bronze /ruta/bronze-retenido \
  --colombia /ruta/captura-colombia.json \
  --colombia-count /ruta/conteo-colombia.json \
  --out /ruta/privada/fuera-del-checkout-publico
```

Ambas capturas colombianas requieren su `.meta.json` con SHA-256. La ejecución
no sustituye la validación de linaje ni la integración del operador en el
exportador: esas tareas preceden a cualquier activación. Los resultados y
originales nuevos se revisan en el respaldo privado. No se copian a este plan.

## Reproducir sin red ni nuevas capturas

```bash
# Desde el respaldo privado; no usar --fix:
python verify_snapshot.py
python scripts/verify_derived.py
# Desde la raíz del repositorio público:
python -m scripts.research.afac_frozen_flights \
  --private-root /ruta/al/respaldo-privado \
  --out analysis_runs/research/afac-flights-20261015.json
```

El script queda versionado; resultados detallados y agregados del proveedor
permanecen ignorados/privados. Registra hashes de inputs públicos, agregados privados y de su código.
No exporta datos al dashboard, no escribe aprobaciones ni consume APIs.

## Pendientes

Completar fuentes de vuelos por operador y ruta; comprobar la cobertura con el
mismo universo antes de activar el calendario; revisar por separado los
candidatos y su integración. Conservar las bitácoras enlazadas mientras sean
procedencia del histórico o evidencia de un esfuerzo abierto. No retirar una
fuente por edad ni duplicar el catálogo general en nuevos reportes de estado.
