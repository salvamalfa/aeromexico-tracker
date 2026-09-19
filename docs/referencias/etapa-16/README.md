# Expediente de revisión · Etapa 16

- [Vista de revisión](../../../prototypes/etapa-16/quarterly_analysis.html)
- [Contrato y comandos](../../analysis-agent/analista-v1.md)
- `browser_validation.json`: comprobaciones de interfaz a tres anchos.
- `receipt.json`: versión exacta del piloto, hashes y resultado de reproducción.
- Capturas en `docs/assets/etapa-16`.

Paquete exacto:
`2026Q2_808256bfb7420d221a3f2f2383c4b95d9889110ad1545fd85f24df8d442a9ff1`.
Cálculo exacto:
`cf95b2ac44a26aa0fb08a1fe589ea5c522e8c9a01d12ffa740b6dc1b0c8eb4e0`.

Ambos originales están en `analysis_runs/evidence` y `analysis_runs/quantitative`.
La entrada editorial queda en `analysis_runs/stage16_input/pilot.json`; el contexto
cerrado exportado en esa misma carpeta. La versión original de autoría y sus
metadatos se conservan en `analysis_runs/drafts/2026Q2`. No copiar borradores a Gold.

Reproducir desde la raíz del proyecto:

```powershell
.\.venv\Scripts\python.exe -m src.analysis_agent.analyst import-draft --package analysis_runs/evidence/2026Q2_808256bfb7420d221a3f2f2383c4b95d9889110ad1545fd85f24df8d442a9ff1.json --calculations analysis_runs/quantitative/cf95b2ac44a26aa0fb08a1fe589ea5c522e8c9a01d12ffa740b6dc1b0c8eb4e0.json --input analysis_runs/stage16_input/pilot.json --output prototypes/etapa-16/quarterly_analysis.html
.\.venv\Scripts\python.exe -m pytest -q
```

El HTML es un borrador de revisión local, no un análisis autorizado. La validación
de referencias no certifica el significado de las afirmaciones.
