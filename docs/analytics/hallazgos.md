# Aeroméxico: hallazgos analíticos

## Executive Summary

- **El pronóstico mensual pasó un filtro real de desempeño.** El modelo `sarima` superó al ingenuo estacional en test: sMAPE 2.5% frente a 3.4%. Por ello se publican doce meses con bandas de 80% y 95%.
- **La red transfronteriza se separa en 3 perfiles de ruta.** La silueta es 0.325 y la estabilidad entre semillas es 1.000.
- **La evidencia ofrece siete lecturas de negocio, pero no todas tienen la misma fuerza.** Combustible y reacción bursátil quedan marcados con confianza baja por historia corta; concentración y estacionalidad de T-100 tienen mayor respaldo.
- **Quedan 17 anomalías sin evento cercano conocido.** Son una lista de investigación, no errores confirmados.

## Qué sí puede pronosticarse hoy

El modelo `sarima` superó al ingenuo estacional en test: sMAPE 2.5% frente a 3.4%. Por ello se publican doce meses con bandas de 80% y 95%.

La selección se hizo en validación y la publicación se decidió una sola vez con los últimos doce meses de test. No se reportan métricas de entrenamiento. Los otros indicadores trimestrales no se publican porque su historia es demasiado corta.

## Cómo se agrupa la operación

Las rutas se agruparon con k=3 porque produjo la mejor silueta entre 2 y 6 grupos sin clusters diminutos. El ejercicio de trimestres no se publicó: la muestra completa produjo grupos inestables o demasiado pequeños.

Los nombres de negocio se eligieron bajo la autoridad de decisión delegada por el usuario para esta ejecución. Se muestran explícitamente en el dashboard para revisión; no se presenta una etiqueta técnica como explicación.

El clustering de aerolíneas no se publicó: requería RASK y CASK ajustados por etapa, y esa etapa global comparable no está disponible. Fabricarla habría cambiado la conclusión.

## Siete estudios de alto valor

### Descomposición del spread RASK-CASK

El spread RASK-CASK cambió -0.68 centavos por ASK entre 2026Q1 y 2026Q2. Precio aportó +0.25, combustible -1.04 y el costo estructural residual +0.11; FX no puede aislarse con las divulgaciones disponibles y no se estimó.

Estimación principal: `-0.6835` centavos por ASK-km.

Confianza: **media**. Límite: Combustible es un proxy de gasto reportado por ASK; FX queda dentro del residual estructural y no se identifica por separado.

### Impacto de Categoría 2 de la FAA

Frente a Delta en las rutas México-EE.UU., la razón de ASM de Aeroméxico cambió -17.8% durante Categoría 2 respecto al periodo previo y +16.4% después de la recuperación de Categoría 1.

Estimación principal: `-0.1782` cambio relativo.

Confianza: **media**. Límite: Experimento natural descriptivo con Delta como control; choques simultáneos impiden una afirmación causal estricta.

### Aeroméxico frente a Volaris

En 2026M06, Aeroméxico tuvo 19.1% del mercado AFAC total frente a 26.2% de Volaris, una brecha de -7.1%.

Estimación principal: `-0.07058` puntos de participación.

Confianza: **alta**. Límite: La participación usa pasajeros AFAC totales; las métricas unitarias conservan la definición reportada de cada aerolínea y no están ajustadas por etapa.

### Sensibilidad al combustible

La elasticidad descriptiva de CASK ante combustible rezagado es +0.62, pero se basa en solo 7 trimestres y no es concluyente.

Estimación principal: `0.6236` de elasticidad.

Confianza: **baja**. Límite: Solo hay 7 trimestres utilizables; no se modelan variables omitidas ni coberturas de combustible.

### Reacción bursátil a resultados

En 2 publicaciones con historia bursátil suficiente, el retorno bruto promedio de AERO en ±5 sesiones fue -7.7%.

Estimación principal: `-0.07741` de retorno acumulado.

Confianza: **baja**. Límite: La historia bursátil de AERO comienza con el relisting de 2025 y gold no contiene un índice de mercado; son retornos brutos, no retornos anormales.

### Estacionalidad de la red

MEX<>SEA es la ruta con mayor sesgo de verano entre las rutas con al menos 24 meses: su índice estacional es 1.45 frente a su mes promedio.

Estimación principal: `1.446` de índice estacional.

Confianza: **alta**. Límite: T-100 cubre segmentos México-Estados Unidos, no la red global completa.

### Concentración de la red

En los últimos 12 meses T-100, el HHI por mercado fue 0.061 y 83.5% de las salidas observadas tocaron MEX.

Estimación principal: `0.06145` de HHI.

Confianza: **alta**. Límite: T-100 cubre segmentos México-Estados Unidos; la dependencia de MEX en la red global puede ser distinta.

## Qué dicen —y qué no dicen— los reportes

Se analizaron 11 documentos de Aeroméxico. El corpus describe longitud, legibilidad, densidad numérica y tono financiero. No infiere intenciones de la administración.

No se hizo comparación lingüística con Volaris y Delta porque sus textos no están en silver. Sus cifras operativas no sustituyen un corpus de reportes. Loughran-McDonald fue diseñado principalmente para 10-K estadounidenses y aquí se usa como referencia descriptiva.

## Próximas decisiones útiles

1. Vigilar cada mes si el error del modelo se mantiene por debajo del ingenuo estacional.
2. Revisar los nombres de cluster cuando entre un año adicional de rutas.
3. Incorporar textos de Volaris y Delta solo mediante fuentes primarias preservadas en bronze.
4. No interpretar la sensibilidad a combustible como cobertura o guía financiera hasta tener más trimestres y datos de hedging.

## Preguntas abiertas

- ¿La dependencia observada de MEX en T-100 coincide con la red global cuando exista una fuente pública comparable?
- ¿El modelo mensual conserva ventaja tras doce nuevos meses, o la ventaja fue específica de esta ventana?
- ¿Qué anomalías sin evento cercano corresponden a cambios operativos reales y cuáles a cobertura de fuente?

## Supuestos y límites

- La vista consolidada es el alcance predeterminado.
- COVID se conserva y se etiqueta; no se elimina.
- T-100 cubre segmentos que tocan Estados Unidos, no la red mundial.
- Las cifras SLA faltantes siguen faltantes.
- Los análisis causales se describen como naturales o descriptivos; no se convierten en causalidad por redacción.
