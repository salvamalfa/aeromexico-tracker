# Evidencia

Todo lo de esta carpeta es **reproducible** desde el commit base más los parches.
Cada archivo dice cómo se generó.

## Lo que está MEDIDO

| Archivo | Qué sostiene |
|---|---|
| `backtest_salida_canonica.txt` | Salida literal de `python -m src.analytics.route_carrier`. Es la fuente de las cifras **1.40 pp / 4.21 %** (semilla de asientos) y **1.98 pp / 5.96 %** (semilla de vuelos) |
| `backtest_resumen.json` | Mismo backtest con metadatos completos: versión del estimador, commit, parámetros, universo, periodos, filas evaluadas, versiones de numpy y pandas |
| `backtest_por_mes_seats.csv`, `backtest_por_mes_departures.csv` | Desglose mes a mes: rutas, observaciones, error en participación y en pasajeros |
| `invariancia_sesgo.json`, `invariancia_sesgo.csv` | Qué tipo de sesgo de cobertura sobrevive al ajuste. Sostiene la decisión de que la prueba de aceptación juzgue completitud y no dispersión |
| `pruebas_del_codigo_entregado.txt` | 89 pruebas de los cinco módulos entregados |
| `pruebas_suite_completa.txt` | Suite completa del repositorio, para contexto |

### Sobre la ponderación del error

El número canónico **1.98 pp** pondera por **tamaño de ruta** (pasajeros). Si se
pondera por número de observaciones da **1.97 pp**. Ambas son legítimas y
coinciden dentro de 0.01 pp; `backtest_resumen.json` trae la segunda y
`backtest_salida_canonica.txt` la primera. No son cifras en conflicto.

### Invariancia del sesgo

Promedio de tres semillas aleatorias, error en participación (pp):

| Tipo de sesgo inyectado | 1.00x | 1.30x | 2.00x | 2.80x |
|---|---:|---:|---:|---:|
| Por aerolínea, parejo en su red (columna) | 1.96 | 1.96 | 1.96 | 1.96 |
| Por ruta, parejo entre operadores (fila) | 1.96 | 1.96 | 1.96 | 1.96 |
| Por aerolínea **dentro** de cada ruta (interacción) | 1.96 | 2.33 | 3.83 | 5.21 |

Los escalados de fila y columna los cancela el IPF exactamente. Solo la
interacción degrada el resultado, y **no es identificable desde las marginales**.

## Lo que es SUPUESTO y no está verificado

Esto es lo más importante que Codex debe heredar sin ambigüedad.

1. **El error de 1.98 pp está medido sobre rutas México–Estados Unidos, no sobre
   el mercado doméstico mexicano.** El universo del backtest es BTS T-100, donde
   la verdad es pública. Que el doméstico se comporte igual es **una
   extrapolación**. El mercado transfronterizo tiene aerolíneas de red
   estadounidenses con perfiles de ocupación más dispares que los tres operadores
   nacionales, así que es razonable esperar que el doméstico salga mejor — pero
   **eso no está medido**. Convertirlo en medición requiere un trimestre de
   verdad doméstica.

2. **Ningún número de esta entrega proviene de AeroDataBox en producción.** El
   piloto se corrió sobre 40 de 58 aeropuertos en un solo martes con el tramo
   gratuito. Sus cifras de cobertura (100 % de vuelos con aerolínea, 99 % con
   aeropuerto de llegada) están en la documentación pero **no se incluyen
   respuestas crudas de la API** en esta entrega.

3. **La ventana histórica del proveedor está en disputa.** El tarifario dice 180
   días para el plan Starter; una consulta a 224 días funcionó en el tramo
   gratuito, documentado con el mismo límite; una a 379 devolvió cero. La
   medición solo acota entre 225 y 378 días.

4. **El muestreo semanal no está validado.** La ponderación por día de la semana
   está construida y probada, pero que una semana ponderada reproduzca el reparto
   del mes **no se ha medido contra datos reales**.

5. **Las cuatro pruebas de `stage9` que fallan en `pruebas_suite_completa.txt`
   son artefacto del entorno**, no regresión: este contenedor no tiene
   `data/silver/`, que `.gitignore` excluye. En un checkout local con la capa
   silver poblada deberían pasar. **No está verificado que pasen**; conviene
   fijar esa línea base antes de trabajar.
