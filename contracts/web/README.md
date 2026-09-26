# `contracts/web`

JSON Schemas (draft 2020-12) and the privacy boundary for everything the
front-end publishes. Fuente única de verdad de la forma pública de los datos;
ver `docs/arquitectura/auditoria-arquitectura-20260926.md` §4.2 y Fase 2.

## Responsabilidad

- `flights.schema.json` describe **exactamente** el payload que hoy se
  embebe en el HTML publicado: la salida de
  `src.dashboard.flights_html.integration_flight_payload(build_flight_payload())`
  (`schema_version: flight_dashboard_payload_v1`, llamado `v1` en esta fase).
  No describe el payload interno completo de `build_flight_payload()` (que
  incluye `forecast`, `sources`, `agent_eligibility`, más detalle por ruta):
  ese es el payload de la página de revisión autónoma
  (`standalone_flight_payload`), fuera de alcance de P3.
- `executive.schema.json` describe la salida de
  `src.dashboard.executive_summary.build_executive_payload()`, embebida sin
  transformación adicional.
- `analysis.schema.json` (P4b; citas en P6a) describe exactamente lo que
  `src.analysis_agent.lifecycle.consumer_payload(record)` autoriza para un
  periodo con aprobación vigente — el mismo contrato de entrega que
  `stage18` usa antes de tocar el HTML — menos cualquier sección que el
  propio borrador marque como privada para lectores
  (`reader_private_section_keys`). Cada `claim` también trae `citations`
  (`label`/`href`/`title`/`value`): un port de
  `src.analysis_agent.reader_ui.py::cite()` sobre `verified_inputs()` que
  exporta únicamente lo que `cite()` ya hace público (URL de la fuente —
  restringida por patrón a `www.sec.gov`/`sec.gov`/`ir.aeromexico.com` —
  y el texto visible del tooltip). Nunca sale un excerpt, una fuente
  completa, un nodo de cálculo ni linaje. Ver `src/web_export/analysis.py`.
- `privacy.yaml` fija la frontera pública/privada: aerolíneas permitidas en
  `carrier_key` (`AEROMEXICO`, `AEROMEXICO_CONNECT`, `AEROMEXICO_GROUP`),
  nombres de campo prohibidos en cualquier nivel del payload, y el tamaño
  máximo por archivo exportado.

## Entradas / salidas

- **Entradas:** ninguna; son artefactos versionados a mano que documentan un
  contrato existente. Cambiarlos es una decisión de producto, no un efecto
  secundario de tocar `src/dashboard/`.
- **Salidas:** consumidos por `tests/test_web_contracts.py`,
  `tests/test_web_privacy.py` y `src/web_export/` (que valida cada archivo
  exportado contra el esquema y las reglas de privacidad antes de escribirlo).

## Comando de prueba focalizada

```
uv run pytest -q tests/test_web_contracts.py tests/test_web_privacy.py
```

Los casos marcados `local_data` validan el payload real (necesitan el
warehouse local); los demás corren en CI contra
`tests/fixtures/web/*.json` (fixtures sintéticas públicas).

## Evolucionar el contrato

1. Cambia el generador en `src/dashboard/` (nunca el HTML producido).
2. Actualiza el `.schema.json` correspondiente para que describa la nueva
   forma; si agregas un campo sensible, agrégalo también a
   `privacy.yaml::forbidden_fields` si no debe ser público.
3. Corre `uv run pytest -q tests/test_web_contracts.py tests/test_web_privacy.py`
   (con datos locales para el caso `local_data`, sin ellos para confirmar que
   la fixture sintética sigue pasando).
4. Si el cambio afecta lo que exporta `src/web_export/`, actualiza también
   su código y su README.
