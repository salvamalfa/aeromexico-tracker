# Comprobantes de Etapa 17

La vista actual incorpora la pauta de negocio solicitada después de la primera
entrega. `business_receipt.json` y `business_browser_validation.json` corresponden a
esta revisión; `receipt.json` y las capturas sin prefijo business conservan el cierre
original. No confundir versiones ni trasladar su auditoría o una futura aprobación.

- [Vista de revisión](../../../prototypes/etapa-17/audited_analysis.html)
- [Contrato del auditor y aprobación](../../analysis-agent/auditor-v1.md)
- `receipt.json`: versiones, estados, hashes, pruebas y conservación de datos.
- `browser_validation.json`: comportamiento de la interfaz a tres anchos.
- Capturas en `docs/assets/etapa-17`.

Informes originales privados: `analysis_runs/audits/initial_review.json`,
`final_review.json`, `adversarial_review.json`, `technical_review.json`. Las dos
auditorías del contenido están además preservadas dentro de eventos inmutables.
Registros de borrador originales en `analysis_runs/drafts/2026Q2`; eventos y
proyección SQLite en `analysis_runs/lifecycle`. El archivo de revisión es
regenerable con `python -m src.analysis_agent.stage17_html`.

Las 289 pruebas se ejecutaron con el entorno `.venv` del proyecto mediante
`python -m pytest -q`. Las 22 pruebas específicas incluyen aprobaciones ficticias
en directorios temporales; no representan consentimiento del usuario.

Estado del piloto: validated. No existen eventos de aprobación o publicación reales.
