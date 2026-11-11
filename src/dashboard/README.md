# Datos del dashboard de Airlines Tracker

Este módulo prepara los datos que consumen la interfaz y los exportadores.
La página se implementa en [`web/`](../../web/README.md); los archivos de
[`site/`](../../site/) son el resultado compilado y publicado.

## Dónde hacer cada cambio

| Necesidad | Módulo |
|---|---|
| Lectura y economía unitaria | `executive_summary.py`: construye registros financieros y vistas por entidad. |
| Red y tráfico de vuelos | `flights.py`, `domestic_routes.py`, `international_routes.py` y módulos de entidades: construyen el detalle por red y aerolínea. |
| Campos de Vuelos que llegan a la web | `flights_html.py::integration_flight_payload`: selecciona las columnas públicas. Un campo fuera de esa lista se descarta. |
| Participación y demanda | `market.py` y `market_demand.py`: preparan los datos de mercado y aeropuertos. |
| Mapa de fuentes oficiales | `official_routes.py`: construye la red AFAC/BTS; su exportación y activación tienen controles separados. |
| Noticias | `news.py`: construye el contenido del archivo de noticias. |
| Calidad y preparación | `data.py`, `check_manual_freshness.py`, `validate_stage8.py` y `prepare.py`: consultan, preparan y validan datos; no implementan la interfaz. |

Las entradas son los Parquet de `data/gold/` y el warehouse local
`data/warehouse.duckdb`. Las salidas son estructuras Python que
[`src/web_export/`](../web_export/README.md) convierte en JSON validados.
[`src/publish/`](../publish/README.md) compila la web y prepara `site/`.

Edita el módulo que genera el dato o la vista, no el HTML compilado.
Mantén la diferencia entre reportado, calculado, observado y estimado;
un faltante no es cero. La reconstrucción de un candidato no lo aprueba.

## Comandos

Desde la raíz del repositorio:

```bash
python -m src.dashboard.build_flights
just dashboard-validate
uv run pytest -q tests/test_flights_prototype.py tests/test_international_routes.py tests/test_stage11_executive_prototype.py
```

`build_flights` reconstruye Vuelos y su evidencia candidata después de cambiar
fuentes o el generador. No activa `flight_evidence_v1` ni publica el resultado.
La exportación completa puede necesitar Gold privados y warehouse; un clon
público no contiene todos esos insumos.

Consulta [la guía de Vuelos](../../docs/etapas/vuelos-pasajeros-traspaso-20260913.md),
[el método de estimación](../../docs/estimacion-pasajeros-ruta-aerolinea.md),
[el mapa oficial](../../docs/mapa-oficial.md) y
[el mapa del repositorio](../../REPO_MAP.md) antes de ampliar una fuente o métrica.
