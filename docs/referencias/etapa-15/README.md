# Expediente · Etapa 15

- `calculations.json`: valores, fórmulas, intervalos, referencias, contrastes y restricciones.
- `tests.xml`: resultado de las 250 pruebas.
- `browser_validation.json`: navegación y geometría de la vista local.
- `verification.ipynb`: cuaderno ejecutado de reproducibilidad y conservación de datos.

Desde el entorno Python del proyecto:

```powershell
python -m src.analysis_agent.quantitative "analysis_runs/evidence/ID_DEL_PAQUETE.json"
python -m src.analysis_agent.stage15_html
python -m pytest -q tests/test_stage15_quantitative.py
```

El paquete debe superar la validación temporal y no estar bloqueado. Las unidades
de entrada deben coincidir con el contrato del motor. Los valores y resultados no
se editan a mano: un cambio de evidencia o de código produce una huella diferente.

`validated` se refiere a ejecución aritmética y controles implementados; no es
aprobación humana ni certificación de equivalencia financiera de CASK. Revisar siempre
`analysis_constraints`, los contrastes `not_reconciled` y los valores `unavailable`.

El detalle de cada nodo termina en identificadores de métrica del paquete temporal;
allí se encuentran los fragmentos y originales Bronze. El HTML es una UI de revisión,
no una narrativa ni una exportación al dashboard.
