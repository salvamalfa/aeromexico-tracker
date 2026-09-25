# Captura de agosto de 2026, lista para cruzar con AFAC

Fecha: 25 de septiembre de 2026.
Alcance: capturar agosto con AeroDataBox para todas las rutas, nacionales e
internacionales, con el mismo diseño que abril a julio, y dejar todo listo
para ajustar en cuanto AFAC publique la edición de agosto.
Autorización: explícita del operador para la captura de agosto (nacional e
internacional), incluida la reanudación tras la interrupción accidental.
Estado: **captura completa; ajuste pendiente de las marginales de AFAC.**
Nada se publica, no se toca `flight_evidence_v1` ni el Analysis Agent.

## Gasto

| Pasada | Diseño | Unidades |
|---|---|---:|
| Nacional | 58 aeropuertos × 7 días × 2 ventanas | 1,624 (134 antes de la interrupción + 1,490 al reanudar) |
| Internacional, núcleo | CUN, GDL, MEX, MTY, PVR, SJD × 31 días | 744 |
| Internacional, resto | 31 aeropuertos × 7 días (1, 5, 9, 13, 17, 21 y 25 de agosto) | 868 |
| **Total** | | **3,236** |

La primera ejecución se detuvo por accidente al cancelar otras tareas. La
reanudación reutilizó las 67 ventanas nacionales ya compradas y solo pagó las
faltantes.

## Qué quedó listo sin AFAC

- **Nacional.** Conteos de vuelos y semilla de ruta × aerolínea en
  `aeromexico-tracker-data/derived/aerodatabox/2026M08/`, solo agregados y sin
  respuestas del proveedor. La capacidad en asientos de Aerovías y Connect ya
  se integró a `derived/aerodatabox/fact_aeromexico_domestic_capacity_estimate.parquet`
  (135 celdas, 99.83 % de cobertura de modelo, 133 utilizables).
- **Internacional.** Semillas de las dos pasadas (`aerodatabox_international_seed_2026M08_{nucleo,resto}.parquet`)
  en `derived/aerodatabox_international/2026M08/`, y la capacidad en asientos de
  agosto dentro de `derived/aerodatabox_international/fact_aeromexico_international_capacity_estimate.parquet`.
  Las semillas son todo lo que el ajuste necesita; los Silver con modelo de
  avión son transitorios y caducan a los 7 días.
  Núcleo: 952 filas ruta × operador, 146 vuelos con escala en México
  reconstruidos. Resto: 344 filas, 9 ventanas vacías (aeropuertos sin vuelos
  internacionales en esa franja). Capacidad internacional de agosto: 99.94 %
  de cobertura de modelo, 142 de 143 celdas utilizables (3 vuelos en Pilatus
  PC-12, fuera de la flota comercial, sin mapear).

La prueba de aceptación nacional de agosto dio `REJECT` con 0 % de cobertura.
Es lo esperado mientras no existan marginales de agosto: no hay contra qué
medir, así que no es un defecto de la semilla.

## Cuándo sale AFAC

AFAC publicó julio el 27 de agosto; con el mismo rezago, agosto debería salir
**entre el 28 de septiembre y el 2 de octubre de 2026** en
<https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404>, como
`sase-agosto-2026-<fecha>.xlsx` (origen-destino) y
`resumen-agosto-2026-<fecha>.xlsx` (por aerolínea). gob.mx bloquea la
descarga automática; se bajan a mano o, como en julio, desde una copia del
Internet Archive. Hay que usar **la misma edición** de los dos archivos.

## Procedimiento cuando AFAC publique

Desde `aeromexico-tracker`, con los dos archivos en `data/bronze/afac_research/`:

```bash
# 1. Marginales nacionales: reemplaza 2026 completo con la edición de agosto.
#    Verificado con la edición de julio: reproduce los tres CSV byte a byte
#    y reconcilia rutas contra aerolíneas con 0 pasajeros de diferencia.
uv run python -m src.ingest.afac.margins --year 2026 \
  --routes data/bronze/afac_research/sase-agosto-2026-*.xlsx \
  --carriers data/bronze/afac_research/resumen-agosto-2026-*.xlsx

# 2. Marginales internacionales (REG INT + PAXREG), misma edición.
uv run python -m src.ingest.afac.international_margins --year 2026 \
  --routes data/bronze/afac_research/sase-agosto-2026-*.xlsx \
  --carriers data/bronze/afac_research/resumen-agosto-2026-*.xlsx

# 3. Ajuste internacional de agosto desde las semillas preservadas.
uv run python -m src.analytics.international_route_carrier --capture \
  ../aeromexico-tracker-data/derived/aerodatabox_international/2026M08/aerodatabox_international_seed_2026M08_nucleo.parquet \
  ../aeromexico-tracker-data/derived/aerodatabox_international/2026M08/aerodatabox_international_seed_2026M08_resto.parquet
uv run python -m src.analytics.international_review 2026M08 --out <ruta privada>
uv run python -m src.analytics.international_gold 2026M04,2026M05,2026M06,2026M07,2026M08

# 4. Ajuste nacional con soporte temporal, ahora incluyendo agosto.
cd ../aeromexico-tracker-data
uv run --project ../aeromexico-tracker python scripts/refit_aerodatabox_temporal_support.py \
  --tracker ../aeromexico-tracker \
  --gold-output derived/aerodatabox/fact_route_carrier_domestic_estimate.parquet \
  --periods 2026M03 2026M04 2026M05 2026M06 2026M07 2026M08
```

El paso 3 se ensayó con las semillas de julio copiadas fuera de Silver: reproduce la estimación vigente celda por celda (1,720 celdas, diferencia máxima 0). `international_gold` lee `estimate_` y `capture_` de `data/silver/international_route_carrier/`; si en ese clon ya no existen los de abril a julio, se restauran desde los paquetes derivados del repositorio privado (`international_route_carrier_estimate_*` y `international_capture_route_operator_*`).

Después se copian los Gold al `data/gold/` local, se reconstruye el warehouse
(`build_warehouse(max_stage=9)`) y se regenera Vuelos con
`python -m src.dashboard.build_flights`. Publicar sigue requiriendo una
instrucción explícita.

Si la edición de agosto revisa meses anteriores, los pasos 1 y 2 los
reemplazan (la edición es acumulada), y abril a julio deben reajustarse con
las mismas semillas para no mezclar ediciones.

## Límite del tablero

El mapa solo muestra trimestres completos. Agosto entra al tercer trimestre,
que se verá cuando septiembre también esté capturado y ajustado; mientras
tanto agosto queda disponible como mes suelto en las páginas de revisión.
