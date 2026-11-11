# Precios y puntos

Este lector usa instantáneas de los libros de Google Sheets después de comprobar
su escritura. Conserva el archivo fuente completo en Bronze. No consulta sitios,
no escribe hojas ni programa corridas. Su agregado público pasa por un gate separado.

Los archivos de entrada viven en `data/bronze/fare_quotes/`. Cada JSON incluye
`provider`, `spreadsheet_id`, `sheet_name`, `range`, `fetched_at`, `format` y
`values`. Los formatos son `fare_capture_v2`, `amr_legacy_v1` y
`doters_legacy_v1`. Las cabeceras del formato nuevo son las de la hoja de captura;
los formatos históricos tienen una asignación explícita de columnas.

```powershell
python -m src.fare_quotes
$env:VITE_LOCAL_FARES='true'
cd web
npm run dev -- --host 127.0.0.1 --port 4179 --strictPort
```

Silver conserva observaciones, fuentes de cada fila y una cuarentena de errores.
Gold es `data/gold/local_fare_quotes.json`, privado e ignorado por Git. Las
instantáneas repetidas no duplican una observación; reutilizar una identidad de
captura con valores distintos pone ambas versiones en cuarentena. Bronze nunca
se modifica. Los datos históricos ambiguos conservan componentes y puntos, pero
su precio final queda nulo. No se suman impuestos a un importe ambiguo.

`redemption_cash_mxn` es el pago final adicional del canje, cuando está
confirmado. `redemption_carrier_mxn` e `redemption_taxes_mxn` son componentes
independientes. No se sustituyen entre sí ni se suman para fingir un total.
Volaris exige puntos nulos; un cero se rechaza y en pantalla se ve «No aplica».

La vista se añade al final de Mercado únicamente en el modo local. Usa el único
selector global y filtra por trimestre de consulta en Ciudad de México. Una
cotización puede pertenecer a un trimestre aún sin resultados financieros: las
otras vistas conservan su estado sin datos. El servidor sólo entrega el archivo
privado a conexiones de esta PC. `site/` y el exportador público no cambian.

Una búsqueda con aeropuertos alternos puede tener un aeropuerto diferente en la
URL y en el vuelo elegido. Esa diferencia exige evidencia separada del resumen
del vuelo seleccionado. Se conserva en
`data/bronze/fare_quote_verifications/`, con identidad de captura y hash de la
evidencia original. El lector nunca cambia la URL ni deduce el aeropuerto.

El alcance de 36 rutas está en
[`config/fare_capture_scope.json`](../../config/fare_capture_scope.json): doce
rutas destacadas por volumen en cada ámbito del mapa. Conserva versión, hash,
periodo y meses del mapa. AFAC nacional e internacional usa ciudades y todas las
aerolíneas; sus candidatos de aeropuerto y la operación por proveedor deben
verificarse antes de capturar. BTS EE. UU. identifica aeropuertos, pero su
histórico tampoco acredita disponibilidad actual.

Validación: pruebas focalizadas de importación, puntos nulos, fechas, deduplicación,
conflictos y componentes; TypeScript y suite web. Para Node 25, la suite web debe
usar `NODE_OPTIONS=--no-experimental-webstorage` para que jsdom aporte su propio
almacenamiento. La validación general del repositorio requiere los extras del
entorno (`uv sync --locked --extra analytics --group chat-runtime`). Los precios reales y la
disponibilidad siguen siendo responsabilidad de cada coordinador de captura.


## Agregado público y tooltip

`python -m src.fare_quotes --public-out web/public/data/v1` reconstruye Silver,
Gold privado y `fare-averages.json`, sin publicar. El exportador sólo permite
medias y conteos: no entrega libros, filas individuales, vuelos ni horarios.
Agrupa trimestre de consulta, proveedor, par de aeropuertos, tarifa, condiciones,
horizonte de compra en meses y diferencia entre fechas de ida y regreso.
Cada importe usa su propio conteo de observaciones no nulas. Los pares dinero y
puntos tienen otro conteo; no se usan puntos por acumular como precio del canje.
El histórico ambiguo y las observaciones sin tarifa documentada quedan fuera de
las medias, aunque compartan otras condiciones.

Los sidecars de `data/bronze/fare_quote_field_reviews/` pueden excluir campos
no confirmados sin cambiar Bronze ni el precio en dinero confirmado. Exigen
identidad, hash de la instantánea y fecha de revisión. Primero se reúnen las
lecturas idénticas de una observación y todas sus procedencias; después se aplica
la revisión efectiva más reciente respaldada por alguna de esas lecturas. La
revisión posterior se añade como otro archivo. La proyección canónica prevalece sobre una
proyección histórica de la misma observación, conservando ambas en Silver.

El tooltip del mapa conserva las métricas de tráfico y añade columnas de dinero
y puntos, con base, tarifa, condiciones y horizonte. México, Santa Lucía y Toluca
usan su crosswalk explícito y mantienen MEX, NLU y TLC separados. Si una consulta
corresponde a un trimestre sin tráfico publicado, el mapa puede usar la última
red previa como referencia, rotulada con su periodo real. El selector global
sigue siendo único; un trimestre de tarifas no crea datos financieros.

El modo `python -m src.publish --fare-quotes-only --fare-input <Gold privado>
--record <cada expediente aprobado> --out site` conserva el sitio servido,
reproduce sus autoridades y fuentes antes y después del build y sólo añade el
agregado contratado y sus pruebas de publicación. El verificador público vuelve
a verificar la publicación base completa y rechaza cambios a sus datos,
aprobaciones o contratos. Sólo se permiten el nuevo producto de tarifas y los
archivos de interfaz. No crea ni modifica aprobaciones financieras.

La preparación de esta entrega tiene pruebas focalizadas de datos y gate, suite
web y revisión visual del tooltip. La suite general local está limitada por
pruebas que necesitan enlaces simbólicos, sin privilegio disponible en Windows.
El cierre requiere CI Linux del commit final, datos finales de los coordinadores
y revisión independiente antes de integrar o desplegar.

<!-- document-lifecycle:v1
{"files": [{"path": ".gitignore", "disposition": "update", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "REPO_MAP.md", "disposition": "update", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "config/fare_capture_scope.json", "disposition": "keep", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "config/publish/fare-quotes-policy.json", "disposition": "keep", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "contracts/web/fare-averages.schema.json", "disposition": "keep", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "scripts/check_pages_publication.py", "disposition": "update", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "src/fare_quotes/README.md", "disposition": "keep", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "src/fare_quotes/__init__.py", "disposition": "keep", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "src/fare_quotes/__main__.py", "disposition": "keep", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "src/fare_quotes/aggregate.py", "disposition": "keep", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "src/fare_quotes/normalize.py", "disposition": "keep", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "src/publish/README.md", "disposition": "update", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "src/publish/fare_release.py", "disposition": "keep", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "src/publish/fare_scope.py", "disposition": "keep", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "src/publish/gate.py", "disposition": "update", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "src/publish/manifest.py", "disposition": "update", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "src/publish/verify.py", "disposition": "update", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "src/web_export/fare_averages.py", "disposition": "keep", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "tests/test_check_pages_publication.py", "disposition": "update", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "tests/test_fare_averages.py", "disposition": "keep", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "tests/test_fare_quotes.py", "disposition": "keep", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "tests/test_publish_fare_scope.py", "disposition": "keep", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "web/index.html", "disposition": "update", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "web/src/main.ts", "disposition": "update", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "web/src/state/period.ts", "disposition": "update", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "web/src/types/generated/fare-averages.ts", "disposition": "keep", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "web/src/types/vite-env.d.ts", "disposition": "update", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "web/src/views/fares/local-fares.css", "disposition": "keep", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "web/src/views/fares/local-fares.test.ts", "disposition": "keep", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "web/src/views/fares/local-fares.ts", "disposition": "keep", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "web/src/views/flights/fare-averages.test.ts", "disposition": "keep", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "web/src/views/flights/fare-averages.ts", "disposition": "keep", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "web/src/views/flights/flights.css", "disposition": "update", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "web/src/views/flights/official-map-chart.ts", "disposition": "update", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "web/src/views/flights/official-map.ts", "disposition": "update", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}, {"path": "web/vite.config.ts", "disposition": "update", "reason": "Fuente, contrato o verificacion de tarifas; detalles privados conservados y agregados publicos sujetos al gate."}]}
-->
