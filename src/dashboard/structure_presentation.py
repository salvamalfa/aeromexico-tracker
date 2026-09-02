"""Business labels for the data-structure page.

This registry is intentionally presentation-only: it may name or group real
metadata keys, but it cannot declare URLs, fields, grains, or relationships.
Those remain owned by the source catalog, contracts, SQL, and pipeline registry.
"""

from __future__ import annotations


SOURCE_GROUPS: tuple[dict[str, object], ...] = (
    {
        "group_key": "sec_ir",
        "label": "SEC / EDGAR y Aeroméxico IR",
        "summary": "Estados financieros, resultados y tráfico publicados por la compañía.",
        "source_keys": ("sec_edgar", "aeromexico_ir"),
    },
    {
        "group_key": "bmv",
        "label": "Bolsa Mexicana de Valores",
        "summary": "Estados financieros IFRS estructurados y sus reexpresiones.",
        "source_keys": ("bmv",),
    },
    {
        "group_key": "afac",
        "label": "AFAC / DATATUR",
        "summary": "Pasajeros por aerolínea, mercado y tipo de servicio en México.",
        "source_keys": ("afac",),
    },
    {
        "group_key": "bts",
        "label": "BTS T-100",
        "summary": "Pasajeros, asientos y operación por ruta entre México y Estados Unidos.",
        "source_keys": ("bts_t100",),
    },
    {
        "group_key": "fx",
        "label": "Banxico y Reserva Federal",
        "summary": "Tipo de cambio para contexto macroeconómico y conversiones monetarias.",
        "source_keys": ("banxico_sie", "federal_reserve_h10"),
    },
    {
        "group_key": "fuel",
        "label": "EIA",
        "summary": "Referencia pública del precio de combustible de aviación.",
        "source_keys": ("eia",),
    },
    {
        "group_key": "airports",
        "label": "Aeropuertos y geografía",
        "summary": "Tráfico del AICM, AIFA y OMA, más ubicación de aeropuertos y rutas.",
        "source_keys": ("aicm", "aifa", "oma_ir", "ourairports"),
    },
    {
        "group_key": "market",
        "label": "Mercado bursátil",
        "summary": "Precio y volumen de AERO y de los comparables con ticker disponible.",
        "source_keys": ("yahoo_finance",),
    },
    {
        "group_key": "peers",
        "label": "Aerolíneas comparables",
        "summary": "Resultados y estadísticas públicas de Viva Aerobus y Ryanair.",
        "source_keys": ("viva_ir", "ryanair_ir"),
    },
    {
        "group_key": "context",
        "label": "Regulación, noticias y lenguaje",
        "summary": "Contexto FAA, titulares públicos y vocabulario financiero para interpretar reportes.",
        "source_keys": ("faa_iasa", "gdelt", "google_news", "loughran_mcdonald"),
    },
)


# An artifact button is allowed only when the canonical source URL identifies a
# deliberately selected, stable public file and the Bronze artifact catalog
# contains that exact URL.  Never choose an arbitrary "latest" row per source.
FEATURED_ARTIFACT_SOURCE_KEYS = frozenset(
    {"eia", "aicm", "aifa", "faa_iasa", "loughran_mcdonald", "viva_ir"}
)


TABLE_PRESENTATION: dict[str, dict[str, object]] = {
    "dim_carrier": {"label": "Aerolíneas y grupos", "role": "who", "purpose": "Define quién reporta y cómo se agrupan las entidades aéreas."},
    "dim_period": {"label": "Meses, trimestres y años", "role": "when", "purpose": "Hace comparables los periodos calendario y fiscales."},
    "dim_metric": {"label": "Definición de métricas", "role": "what", "purpose": "Explica cada KPI, su unidad y la forma válida de consolidarlo."},
    "dim_route": {"label": "Rutas y mercados", "role": "where", "purpose": "Identifica pares origen-destino y mercados bidireccionales."},
    "dim_airport": {"label": "Aeropuertos físicos", "role": "where", "purpose": "Ubica aeropuertos reales sin mezclar totales de operadores."},
    "dim_airport_group": {"label": "Grupos aeroportuarios", "role": "where", "purpose": "Representa los portafolios de OMA, GAP y ASUR por separado."},
    "dim_events": {"label": "Eventos relevantes", "role": "context", "purpose": "Ordena hechos regulatorios, corporativos y de mercado usados como contexto."},
    "dim_fx_period": {"label": "Tipo de cambio por periodo", "role": "when", "purpose": "Resume tipos promedio y de cierre para conversiones consistentes."},
    "dim_fuel_period": {"label": "Combustible por periodo", "role": "when", "purpose": "Resume la referencia de jet fuel para comparar presión de costos."},
    "fx_business_calendar": {"label": "Calendario cambiario", "role": "when", "purpose": "Distingue días publicados y valores arrastrados del tipo de cambio."},
    "fuel_business_calendar": {"label": "Calendario de combustible", "role": "when", "purpose": "Distingue días publicados y valores arrastrados de jet fuel."},
    "dim_source": {"label": "Catálogo de fuentes", "role": "trust", "purpose": "Describe quién publica cada dato, su cobertura y sus limitaciones."},
    "dim_source_priority": {"label": "Precedencia de fuentes", "role": "trust", "purpose": "Decide de forma reproducible qué publicación prevalece cuando se superponen."},
    "fact_carrier_metrics": {"label": "Desempeño financiero y operativo", "role": "facts", "purpose": "Concentra las métricas de aerolíneas en formato largo y versionado."},
    "fact_route_traffic": {"label": "Operación por ruta", "role": "facts", "purpose": "Mide capacidad, pasajeros y vuelos por ruta y mes."},
    "fact_airport_traffic": {"label": "Tráfico por aeropuerto", "role": "facts", "purpose": "Conserva pasajeros y operaciones de cada aeropuerto físico."},
    "fact_airport_group_traffic": {"label": "Tráfico por grupo aeroportuario", "role": "facts", "purpose": "Conserva totales de operadores sin tratarlos como aeropuertos."},
    "fact_market_data": {"label": "Mercado bursátil", "role": "facts", "purpose": "Organiza precios, volumen, rendimientos y volatilidad por ticker."},
    "fact_macro": {"label": "Entorno macro y combustible", "role": "facts", "purpose": "Reúne tipo de cambio y jet fuel por periodo comparable."},
    "fact_data_quality_issues": {"label": "Incidencias de calidad", "role": "trust", "purpose": "Mantiene el ledger canónico de discrepancias, faltantes y controles."},
    "fact_forecasts": {"label": "Pronósticos publicados", "role": "analysis", "purpose": "Guarda backtests, escenarios futuros e intervalos de incertidumbre."},
    "dim_model_performance": {"label": "Desempeño de modelos", "role": "analysis", "purpose": "Compara modelos contra baselines fuera de muestra."},
    "fact_report_language": {"label": "Lenguaje de reportes", "role": "analysis", "purpose": "Describe tono, legibilidad y vocabulario sin inferir intención."},
    "fact_anomalies": {"label": "Anomalías para investigar", "role": "analysis", "purpose": "Señala observaciones inusuales sin convertirlas automáticamente en errores."},
    "dim_cluster_assignments": {"label": "Perfiles de rutas y periodos", "role": "analysis", "purpose": "Agrupa observaciones similares y conserva la estabilidad del ejercicio."},
    "fact_study_results": {"label": "Estudios de negocio", "role": "analysis", "purpose": "Resume hallazgos, confianza y limitaciones de análisis específicos."},
    "fact_route_traffic_summary": {"label": "Rutas preparadas para el dashboard", "role": "analysis", "purpose": "Acota el tráfico de rutas al grano y horizonte usados por la interfaz."},
    "fact_spread_decomposition": {"label": "Descomposición del margen unitario", "role": "analysis", "purpose": "Separa precio, combustible y residual sin forzar componentes desconocidos."},
    "fact_dashboard_coverage": {"label": "Cobertura del dashboard", "role": "trust", "purpose": "Mide qué periodos y métricas están presentes para cada aerolínea."},
    "dim_source_artifact": {"label": "Archivos públicos preservados", "role": "trust", "purpose": "Cataloga cada descarga Bronze, su hash y sus versiones lógicas."},
    "bridge_record_lineage": {"label": "Puente de trazabilidad", "role": "trust", "purpose": "Relaciona cada registro con sus archivos, padres o declaración de curación."},
}


FEATURED_GOLD_TABLES = frozenset(
    {
        "dim_carrier",
        "dim_period",
        "dim_metric",
        "dim_route",
        "dim_airport",
        "dim_airport_group",
        "fact_carrier_metrics",
        "fact_route_traffic",
        "fact_airport_traffic",
        "fact_airport_group_traffic",
        "fact_market_data",
        "fact_macro",
        "fact_forecasts",
        "fact_anomalies",
        "fact_study_results",
    }
)
