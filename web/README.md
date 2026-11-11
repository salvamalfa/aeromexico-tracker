# Interfaz de Airlines Tracker

Vite, TypeScript y Plotly presentan Lectura, Mercado, Economía y Noticias.
La interfaz consume JSON públicos; no ejecuta cálculos, modelos ni aprobaciones.

[`web/`](.) contiene el código; `web/dist/`, el build local.
[`site/`](../site/) conserva la publicación que despliega Pages.
Modifica el código o el generador del dato, no los compilados.

## Probar desde un clon público

Para ver la publicación con Python, desde la raíz:

```bash
python -m http.server 4173 --bind 127.0.0.1 --directory site
```

Abre [http://127.0.0.1:4173/](http://127.0.0.1:4173/).
Sirve el sitio existente sin reconstruir fuentes ni iniciar el backend del chat.

Para cambiar la interfaz con los datos públicos ya exportados, usa Node 22
(la versión de CI). Desde la raíz:

```bash
python -c "import shutil; shutil.copytree('site/data/v1', 'web/public/data/v1', dirs_exist_ok=True)"
python -c "import shutil; shutil.copy2('site/publication_manifest.json', 'web/public/publication_manifest.json')"
cd web
npm ci
npm run dev
```

Abre la URL de Vite. Los datos quedan ignorados por Git. El manifiesto local
permite consultar las lecturas; no lo incluyas en un PR como publicación nueva.

Exportar desde los generadores requiere insumos locales:

```bash
uv run python -m src.web_export --out web/public/data/v1 --allow-missing-analysis
```

Ejecútalo desde la raíz. `--allow-missing-analysis` solo omite análisis ausentes
en desarrollo. El export completo aún exige cuatro Gold privados de Vuelos
declarados en [`config/web_inputs.yaml`](../config/web_inputs.yaml).
Véanse [exportación](../src/web_export/README.md) y
[restauración autorizada](../docs/cloud-development.md).

## Dónde cambiar la interfaz

| Archivo o carpeta | Responsabilidad |
|---|---|
| `index.html`, `src/main.ts` | Estructura de la página y arranque de las vistas. |
| `src/state/period.ts` | Trimestre único, navegación y suscripciones. |
| `src/views/shell/` | Pestañas y selectores. |
| `src/views/executive/` | Lecturas, disponibilidad por entidad y citas. |
| `src/views/economy/` | Indicadores, gráficas y tabla financiera. |
| `src/views/flights/`, `src/views/market/` | Mercado: mapa, tráfico, participación y mezcla. |
| `src/views/news/`, `src/views/chat/` | Noticias y panel del chat opcional. |
| `src/styles/` y estilos de cada vista | Estilos comunes y locales. |
| `src/types/domain.ts` | Tipos internos escritos a mano. |
| `src/types/generated/` | Tipos generados; no editarlos a mano. |
| `src/lib/plotly.ts`, `src/lib/kpi-format.ts` | Gráficas y formato numérico. |

## Trimestre compartido y carga diferida

`src/state/period.ts` mantiene un solo `period_id` y un único par de
eventos para los botones de trimestre. Las vistas buscan ese identificador
en sus propios datos; no comparten índices de arreglos distintos.

Lectura y Economía se preparan al inicio. Mercado y Noticias se cargan cuando
su pestaña se abre, mediante `reader-tab-visible` e importaciones dinámicas.
Al abrir Mercado después de cambiar de trimestre, se consulta el periodo
vigente. Una ausencia se muestra como N/D; no se elige otro trimestre.

Lectura muestra los análisis aprobados de `publication_manifest.json`.
Su detalle conserva texto y citas y se cierra al cambiar de trimestre.
Los parámetros antiguos
`readingPeriod` y `sel_reading` no seleccionan una lectura independiente.
Cada fuente declara su propia cobertura.

## Datos que consume

Los archivos locales `web/public/data/v1/` se sirven como `data/v1/`;
Vite copia `public/` a la raíz de `dist/` al compilar.

- `executive.json`: registros financieros y vistas por entidad.
- `flights/quarters.json`: periodos, series y metadatos; las redes por
  periodo se solicitan cuando hacen falta.
- `official-routes.json`: mapa AFAC/BTS de contrato
  `official_route_network_v1`.
- `analysis/<period_id>.json` y `analysis/<entity_key>/<period_id>.json`:
  lecturas aprobadas con citas; una lectura ausente conserva su aviso.
- Archivos de Mercado y Noticias, según sus contratos.

Los esquemas y la frontera de privacidad viven en
[`contracts/web/`](../contracts/web/README.md).
Las citas solo exponen los campos públicos autorizados por su contrato;
nunca originales, cálculos o linaje privado.

## Mapa, indicadores y preguntas

El [mapa oficial](../docs/mapa-oficial.md) conserva el trimestre global.
Nacional e internacional sin EE. UU. usan AFAC; EE. UU. usa BTS T-100,
clases regulares F y G, con Grupo Aeroméxico, Volaris y Viva. Esa selección
no representa todo el mercado BTS. La fuente determina el universo y el grano.

Los vuelos dimensionan las rutas. «Más vuelos» muestra doce; «Todas», la red.
La búsqueda incluye rutas sin coordenadas y fuera del grupo principal.
Los totales conservan ceros explícitos y faltantes; el mapa dibuja valores
positivos con coordenadas. La ayuda identifica meses, sentidos y cobertura.
`map_scope`, `map_region` y `map_carriers` conservan filtros;
`sel_map` antiguo solo inicializa BTS. Se conservan los contratos históricos.

Las tarjetas usan `kpi-format.ts`: máximo un decimal, o enteros para conteos.
Redondea el número completo y conserva unidades, signos y faltantes.
Las tablas mantienen precisión; las ayudas incluyen definición y fuentes.

«Pregunta» adjunta al compositor el contexto del componente; solo Enviar
inicia la consulta. El mapa incluye dataset, trimestre, ámbito, grano y meses;
AFAC no hereda el filtro de aerolíneas de BTS. El backend debe aceptar la misma
versión de datos. El chat tiene autenticación y configuración propias:
[guía del chat](../docs/chat/README.md).

## Comandos y pruebas

Dentro de `web/`:

| Comando | Resultado |
|---|---|
| `npm ci` | Instala las dependencias bloqueadas. |
| `npm run dev` | Inicia Vite con recarga durante desarrollo. |
| `npm run check` | Valida TypeScript estricto sin emitir archivos. |
| `npm run test` | Ejecuta Vitest, incluidos los tipos generados. |
| `npm run build` | Compila en `dist/`; no publica. |
| `npm run preview` | Sirve esa compilación local. |
| `npm run gen:types` | Regenera tipos desde `contracts/web/*.schema.json`. |

```bash
cd web
npm run check
npm run test
npm run build
cd ..
uv run pytest -m browser -q tests/test_web_flights_smoke.py tests/test_web_page_smoke.py
uv run pytest --require-local-data -m "browser and local_data" -q tests/test_site_parity.py
```

Las pruebas de navegador sirven `dist/` con `web/serve.py` y datos sintéticos
de `tests/fixtures/web/`. La paridad de `site/` exige insumos locales.

Usa el Chromium del Playwright bloqueado. `PLAYWRIGHT_CHROMIUM_EXECUTABLE`
permite seleccionar un ejecutable existente. En Node 25,
`NODE_OPTIONS=--no-experimental-webstorage` evita sustituir el almacenamiento
de jsdom por el nativo. CI usa Node 22.

Plotly se importa desde `src/lib/plotly.ts`, con las trazas
`bar`, `scatter`, `scattergeo` y `choropleth`; no desde una variable global.
Versiones: `package-lock.json`.

## Tamaño del bundle

Mercado se descarga bajo demanda. Mide el build y sus respuestas HTTP;
las mediciones históricas no son un presupuesto vigente.

## Dependencias y avisos de seguridad

El [README anterior](https://github.com/salvamalfa/aeromexico-tracker/blob/72861902ee30feeb3d3c15b681ee897f5e1e6ab5/web/README.md#dependencias-y-avisos-de-seguridad)
conserva auditoría y mediciones históricas. Comprueba el lock y la publicación
actuales; aquella revisión no acredita su estado.

## Publicación y revisión editorial local

El [gate de publicación](../src/publish/README.md) exporta, compila y verifica
`site/` con las aprobaciones aplicables. Exige las entradas de compilación
confirmadas en Git. Pages despliega ese resultado; no reconstruye datos.
No copies `dist/` a `site/` a mano.

En desarrollo, `?period=2026Q3&review=1` puede leer una propuesta desde
`tmp/editorial-rerun/2026Q3.json`. El middleware solo existe en Vite
desarrollo; no exporta borradores, los aprueba ni modifica el sitio publicado.
