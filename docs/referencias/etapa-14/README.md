# Expediente · Etapa 14

- `2026Q2_review.json`, `2021Q1_review.json`: paquete y anexo de revisión separado.
- `2026Q2_validation.json`, `2021Q1_validation.json`: comprobantes y ruta de la versión inmutable.
- `tests.xml`: 236 pruebas de regresión.
- `evidence_tests.xml`: 19 pruebas de evidencia, repetidas tras el último ajuste.
- `browser_validation.json`: interacción y geometría en tres anchos.
- `verification.ipynb`: cuaderno ejecutado de trazabilidad, aislamiento e idempotencia.

**No entregar los archivos `*_review.json` completos al analista.** Solo el paquete
inmutable de `analysis_runs/evidence` es la entrada futura autorizable. El anexo
`review_only` incluye metadatos de fuentes excluidas para la revisión humana.

Desde la raíz del proyecto, usando su entorno Python existente:

```powershell
python -m src.analysis_agent.evidence prepare 2026Q2
python -m src.analysis_agent.evidence prepare 2021Q1
python -m src.analysis_agent.stage14_html
python -m src.analysis_agent.evidence validate "analysis_runs/evidence/ID_DEL_PAQUETE.json"
python -m pytest -q tests/test_stage14_evidence.py
```

No instala dependencias, no descarga fuentes y no escribe en Gold. Los documentos
Bronze y las tablas Silver son los insumos locales para preparar; una versión ya
congelada puede validarse directamente contra Bronze sin reconstruir Silver.

El registro `source_registry` tiene 26 documentos: cuatro comunicados SEC con prueba
de versión y 22 PDF IR sin certificación histórica. Cada fecha desconocida permanece
nula con su motivo. Los localizadores son páginas para el diagnóstico IR y elementos
de tabla o párrafos para la evidencia SEC.

El HTML es una UI local de revisión, no un análisis trimestral ni una exportación
para consumo. Las fuentes oficiales se abren únicamente por acción del usuario.
