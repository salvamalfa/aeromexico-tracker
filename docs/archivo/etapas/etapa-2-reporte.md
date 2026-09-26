# Etapa 2 — BMV XBRL

Fecha de cierre: 2026-08-20
Estado: COMPLETA

## Qué se construyó

- Descubrimiento de reportes desde el catálogo HTML de BMV y resolución segura de
  enlaces del visor hacia los ZIP oficiales.
- Descarga inmutable del catálogo, los 31 ZIP disponibles y sus 31 miembros JSON,
  con hash, versión lógica y linaje en el manifiesto bronze.
- Parser offline del modelo XBRL JSON de BMV: conceptos, hechos numéricos,
  contextos, unidades, dimensiones, etiquetas ES/EN, extensiones y relaciones de
  presentación.
- Índice de 31 paquetes y tabla financiera con 53,614 hechos, incluidos 1,184
  trimestres derivados de acumulados YTD solo cuando no existe un trimestre directo.
- Catálogo documentado de 771 conceptos observados, incluidos 195 conceptos de
  extensiones mexicanas/CNBV.
- Conciliación AERO BMV–SEC para cinco líneas financieras y cuatro trimestres.
- Validadores de cobertura, claves naturales, linaje, ecuaciones contables y suma
  de trimestres contra anual.
- Fixture exacto de AERO 2026Q2 y tests de catálogo, seguridad ZIP, anclas,
  taxonomía, dimensiones y derivación YTD.

## Datos obtenidos

| Fuente | Periodos | Filas / archivos | Tamaño | Método de acceso |
|---|---|---:|---:|---|
| Catálogo BMV | Dos snapshots 2026-08-20 | 2 HTML | 8,434,253 bytes | httpx |
| AERO XBRL | 2025Q3–2026Q2 + anual 2025 | 5 ZIP + 5 JSON | 77,201,271 bytes | httpx |
| VOLAR XBRL | anual 2020–2025; trimestral 2021Q3–2026Q2 con huecos históricos descritos abajo | 26 ZIP + 26 JSON | 486,986,863 bytes | httpx |
| `bmv_packages_index.parquet` | 2020–2026Q2 | 31 | 19,125 bytes | parser offline |
| `bmv_financials.parquet` | 2020–2026Q2 | 53,614 | 2,611,360 bytes | parser offline |
| `bmv_concepts.parquet` | Todos los paquetes | 771 | 69,329 bytes | parser offline |
| `bmv_sec_reconciliation.parquet` | AERO 2025Q3–2026Q2 | 20 | 10,662 bytes | cálculo offline |
| `bmv_validation_checks.parquet` | 2021–2025 | 340 | 8,801 bytes | cálculo offline |

La Etapa 2 añadió 64 artefactos únicos al manifiesto y 572,622,387 bytes físicos a
bronze. Son dos versiones del catálogo dinámico, 31 ZIP y 31 JSON. La segunda
consulta cambió un byte del HTML y se registró correctamente como versión lógica 2;
ningún paquete financiero cambió. La tabla contiene 9,325 filas de AERO y 44,289
de VOLAR; 30,856 hechos conservan al menos una dimensión. Los 771 conceptos tienen
etiquetas tanto en español como en inglés.

### Cobertura real de VOLAR

El catálogo visible contiene 26 paquetes: anual 2020; 2021Q3, 2021Q4 y anual 2021;
Q1–Q4 y anual para cada año 2022–2025; y 2026Q1–2026Q2. No expone 2016–2019 ni
2020 trimestral, tampoco 2021Q1–Q2. Se descargó el 100% de lo publicado actualmente
en ese catálogo; los periodos ausentes no se estimaron.

## Validaciones ejecutadas

| Check | Resultado | Detalle |
|---|---|---|
| Suite completa | PASS | 55 tests; fixture BMV exacto de 1,263,900 bytes |
| Paquetes disponibles | PASS | 5/5 AERO y 26/26 VOLAR del catálogo actual |
| Integridad bronze | PASS | 64/64 artefactos con SHA-256; un cambio del catálogo, cero cambios de paquetes |
| Contrato silver | PASS | Cero valores de linaje nulos |
| Claves naturales | PASS | Cero hechos duplicados |
| Etiquetas | PASS | 771/771 conceptos con etiqueta ES y EN |
| P&L | PASS | 22 ecuaciones; cero fallos a tolerancia 0.1% |
| Balance | PASS | 22 ecuaciones; cero fallos a tolerancia 0.1% |
| Trimestre → anual | PASS | 296 sumas; cero fallos a tolerancia 0.1% |
| BMV ↔ SEC | PASS | 20 cruces; 14 <1% y 6 explicados por redondeo |
| Idempotencia de issues | PASS | Seis conflictos registrados una sola vez por ID estable |
| Reconstrucción offline | PASS | Dos parseos; hashes idénticos en los cinco Parquet BMV |

Las seis diferencias relativas mayores a 1% afectan importes pequeños —impuestos,
utilidad antes de impuestos y utilidad neta— que SEC presenta redondeados a millones
de USD. Todas tienen diferencia absoluta menor o igual a 366,000 USD; se explicaron
y quedaron registradas como advertencias, no se ajustaron los datos.

## Cifras ancla verificadas

| Métrica | Esperado | Obtenido | ¿Coincide? |
|---|---:|---:|---:|
| Ingreso AERO 2Q26 BMV | 1,479.356 M USD | 1,479.356 M USD | Sí |
| Activos AERO al 2Q26 | 7,379.438 M USD | 7,379.438 M USD | Sí |
| Ingreso AERO 2Q26 SEC | 1,479.0 M USD | 1,479.0 M USD | Sí |
| Diferencia ingreso BMV–SEC 2Q26 | <1% | 0.0241% | Sí |
| Utilidad operativa AERO 2Q26 BMV | 67.879 M USD | 67.879 M USD | Sí |
| Utilidad operativa AERO 2Q26 SEC | 67.9 M USD | 67.9 M USD | Sí |
| Assets = Liabilities + Equity | ±0.1% | diferencia máxima 0.0000% | Sí |

## Qué NO funcionó y por qué

- El formato publicado no coincide con el supuesto del plan: los ZIP contienen un
  JSON del visor, no archivos XML/XSD/linkbase separados. Se parseó el modelo
  semántico completo realmente publicado y se documentó la decisión.
- El portal actual no muestra la historia de VOLAR hasta 2016 esperada por el plan.
  Solo se pudo conservar la cobertura visible desde el anual 2020; no se inventaron
  ni extrapolaron periodos.
- El repositorio de referencia usa Selenium y separación manual de texto JSON de
  2018. Sirvió como pista histórica, no como base de implementación vigente.
- Seis de 20 comparaciones superan 1% relativo porque el denominador es pequeño y
  SEC redondea a millones. La diferencia absoluta máxima es 366,000 USD y ninguna
  queda sin explicación.
- El HTML del catálogo es dinámico: dos consultas produjeron hashes distintos por
  un byte. El versionado inmutable lo registró; los 31 ZIP conservaron sus hashes.

No se necesitó Playwright, navegador visible ni computer use. Tampoco fue necesario
instalar Arelle ni paquetes adicionales.

## Decisiones tomadas

- Preferir el HTML server-rendered y HTTP directo mientras BMV lo permita.
- Guardar por separado el ZIP y el JSON exacto para preservar tanto el contenedor
  original como una entrada auditable al parser offline.
- Considerar extensiones todos los conceptos fuera de `ifrs-full`/`ifrs-mc`,
  conservando su namespace real en vez de asumir que son exclusivamente del emisor.
- Derivar Q2/Q3/Q4 mediante diferencia de acumulados solo para estados aditivos y
  solo si el trimestre puro no está publicado; nunca derivar instantáneos.
- Conservar hechos dimensionales y no colapsarlos en la capa silver.
- Clasificar >1% como material para revisión, pero aceptar como explicado un cruce
  si la diferencia absoluta es como máximo 500,000 USD y proviene del redondeo SEC.

## Supuestos hechos

- El catálogo HTML actual representa el universo de paquetes públicamente
  disponibles desde ese punto de acceso de BMV.
- El JSON contenido en cada ZIP es la representación fuente que controla el visor
  BMV y debe tratarse como XBRL estructurado aunque el XML no se publique dentro.
- Los roles 310000, 410000 y 520000 corresponden a estados primarios aditivos aptos
  para derivación de periodos; los estados no aditivos quedan intactos.
- Un concepto fuera de `ifrs-full`/`ifrs-mc` se etiqueta como extensión, pero su
  namespace permite distinguir taxonomía mexicana/CNBV de una extensión específica
  del emisor.

## Preguntas para el usuario

Ninguna pendiente para cerrar la Etapa 2.

## Riesgos para la siguiente etapa

- AFAC puede requerir Playwright o computer use y formatos de archivo heterogéneos.
- La Etapa 3 exige decidir si Aeroméxico y Aeroméxico Connect se consolidan o se
  muestran separados; esa decisión se consultará antes de modelar el crosswalk.
- Si BMV cambia la estructura del JSON o deja de incluir las filas en el HTML, el
  fixture detectará el cambio, pero la ingesta requerirá la ruta de fallback.
- Los huecos históricos de VOLAR limitan comparaciones XBRL anteriores a 2021Q3.

## Comandos para reproducir

```powershell
just ingest          # red: refresca SEC + BMV y preserva bronze
just parse           # sin red: bronze -> silver SEC + BMV
just bmv-validate    # anclas, ecuaciones, linaje y cruce SEC
just test
just rebuild         # reconstrucción offline desde bronze
```
