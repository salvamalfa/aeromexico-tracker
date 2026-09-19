# Expediente de revisión · Etapa 13

- `baseline.json`: cobertura vigente congelada antes de la extracción.
- `financial_review.json`: cifras, páginas, texto, IDs, fórmulas, cobertura y comprobaciones.
- `coverage.csv`, `gaps.csv`, `checks.csv`, `comparison.csv`: tablas exportadas.
- `artifact.json`: entrada canónica del reporte técnico de revisión, con narrativa y fuentes.
- `report_tables.json`: filas exactas consultadas por las tablas del lector; conserva campos
  adicionales para auditoría, aunque no todos aparecen como columnas visibles.
- `html_validation.json`: verificación del lector portátil, fuentes y modo sin red.
- `responsive_validation.json`: geometría y errores JavaScript a 360, 736 y 1440 px.
- `tests.xml`: resultado de las 217 pruebas del proyecto.
- `verification.ipynb`: cuaderno ejecutado, idempotencia y conservación de Gold.

Las fuentes oficiales están enlazadas en el HTML. Las copias Bronze no se alteran.
Las discrepancias verificadas se registran en `config/stage13_source_differences.json`.
El contexto temporal de publicación sigue pendiente de Etapa 14.

Desde la raíz del proyecto, con su entorno Python:

```powershell
python -m src.analysis_agent.stage13
python -m src.analysis_agent.stage13_report
python -m pytest -q
```

Para el HTML, indicar el directorio `skills/build-report/scripts` del plugin
Data Analytics instalado (Node ya disponible; no instala dependencias):

```powershell
python -m src.analysis_agent.stage13_html --tools-dir "RUTA_DEL_PLUGIN/skills/build-report/scripts"
```

La construcción usa el lector canónico, corrige únicamente su barra superior
para los scrollbars de Windows y ejecuta el verificador original antes de sustituir
el HTML final. Un fallo conserva la entrega anterior. La fecha del reporte identifica
esta entrega revisada; para otra entrega se debe actualizar junto con el expediente.

El cuaderno usa el entorno del proyecto con `nbformat`, `nbclient` e `ipykernel`.
No requiere red ni credenciales. Es un complemento de auditoría del HTML, no una UI
operativa ni una autorización de contenido trimestral.
