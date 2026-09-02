# Recorrido narrado — Aeroméxico Tracker

Este recorrido está pensado para una conversación de portafolio de 10–12 minutos. El orden no es técnico: empieza por la respuesta, recorre los impulsores y termina mostrando por qué la evidencia es confiable y cómo se construyó.

## 1. Resumen ejecutivo — qué pasó

Abre en `2026Q2`. La primera lectura es que los ingresos crecieron con capacidad casi plana: la mejora vino más de monetización y mezcla que de poner muchos más asientos. Las seis tarjetas muestran escala, rentabilidad, demanda y economía unitaria; cada una explica por qué importa, cómo interpretar una subida o bajada y qué comparación puede engañar.

El punto de partida es US$1,479 millones de ingreso, margen EBITDAR ajustado de 17.9%, ocupación de 84.9%, TRASM de 16.0 centavos, CASM ex combustible de 10.0 centavos y spread RASK−CASK de 0.43 centavos por ASK-km.

## 2. Economía unitaria — dónde se ganó o perdió el margen

RASK y CASK se leen juntos. Entre `2026Q1` y `2026Q2` el spread cayó 0.68 centavos: el ingreso unitario aportó +0.25, el combustible restó 1.04 y el residual estructural aportó +0.11. FX aparece como no identificado porque las divulgaciones disponibles no permiten aislarlo; no se estimó para cerrar el waterfall.

El toggle de ajuste por etapa no inventa datos. Cuando la etapa comparable no existe, la vista explica por qué no puede producir una versión ajustada.

## 3. Capacidad y demanda — crecer bien o crecer mal

La página contrasta ASM con RPM y después baja a pasajeros mensuales AFAC, desglose doméstico/internacional y flota. La interpretación central es sencilla: si la oferta crece más rápido que la demanda, la ocupación y eventualmente el yield pueden quedar bajo presión. Las series conservan eventos relevantes como anotaciones verticales.

## 4. Competencia — compararse sin falsa precisión

La advertencia superior es parte del análisis: Aeroméxico, Volaris, Viva y Ryanair usan IFRS; Delta usa US-GAAP; Ryanair cierra su año fiscal en marzo; y no existe etapa promedio global comparable. Por eso el mapa RASK–CASK se presenta sin ajuste SLA y el clustering de aerolíneas no se publica.

En junio de 2026, Aeroméxico tuvo 19.1% de los pasajeros AFAC totales frente a 26.2% de Volaris. Esto describe escala en México, no rentabilidad ni calidad de red.

## 5. Red y rutas — dónde está concentrada la exposición

El mapa esquemático usa T-100 local, sin teselas externas, y pondera líneas por asientos. La red observada tiene HHI de 0.061; 83.5% de las salidas del corte T-100 toca MEX. Los clusters describen 407 observaciones ruta-año como Ocio estacional, Alta frecuencia y Conectividad equilibrada.

La sección de Categoría 2 compara la razón de ASM Aeroméxico/Delta: −17.8% durante el periodo frente al previo y +16.4% después. Es evidencia descriptiva tipo experimento natural, no una afirmación causal estricta.

## 6. Finanzas — resultado, costos, balance y mercado

La página separa P&L, estructura de costos, balance y acción. SEC/comunicados controla métricas operativas; BMV XBRL conserva estados financieros y reexpresiones. Las discrepancias no se esconden: se mandan a Salud de datos.

El event study solo cuenta con dos publicaciones posteriores al relisting con ventana completa. El retorno bruto promedio de ±5 sesiones fue −7.7%; no se llama retorno anormal porque no hay benchmark de mercado gold.

## 7. Forecast — señal futura con error visible

La gráfica reúne observado, backtest y doce meses futuros. Las bandas de 80% y 95% nunca se ocultan. SARIMA obtuvo MAPE de 2.58%, sMAPE de 2.50% y MASE de 0.174 en un test de doce meses; el naive estacional tuvo sMAPE de 3.36%.

El escenario jet fuel +20% es ilustrativo, no guidance: usa una elasticidad descriptiva con solo siete trimestres y confianza baja. El dashboard dice esto al lado de la cifra.

## 8. Lenguaje de reportes — qué palabras cambiaron

El corpus contiene once documentos de Aeroméxico. Se muestran proporciones positivas, negativas y de incertidumbre del diccionario Loughran-McDonald, longitud y cambios de vocabulario. No se infiere intención, confianza ni veracidad. La comparación con peers está ausente porque sus textos no fueron ingeridos; las cifras operativas no los sustituyen.

## 9. Salud de datos — cuánto confiar

Esta es la página de control. Expone fechas por fuente, cobertura, 23 issues abiertos, 66 restatements y la mezcla reportado/derivado. También lista lo que todavía no se conoce: etapa promedio global, textos de peers y guidance estructurado. Una ausencia sigue siendo ausencia.

## 10. Estructura de datos — cómo se construye la evidencia

El embudo sigue la información desde 19 fuentes públicas activas hasta el producto final. Las tarjetas hablan primero de negocio; al abrirlas aparecen responsables, cobertura, frecuencia, archivos preservados, contratos y controles. Los ejemplos de parsing muestran con evidencia real cómo un porcentaje, una moneda o un trimestre publicado se convierten en datos comparables.

La segunda mitad es un esquema estrella interactivo. Al elegir un hecho solo se iluminan las dimensiones, vistas y páginas que sus contratos realmente conectan. Los nombres técnicos permanecen ocultos hasta pedirlos. Así se puede explicar la arquitectura sin presentar 31 tablas amontonadas ni mantener un diagrama manual que envejezca separado del modelo.

## 11. Glosario — cómo leer cada KPI

El glosario renderiza `dim_metric`: definición, fórmula, unidad, interpretación al subir o bajar, rangos cuando existen y advertencias. Es la prueba de que la explicación no vive escondida en código ni depende de un LLM en tiempo de ejecución.

## Cierre sugerido

El valor del proyecto no es una predicción aislada ni una pantalla bonita. Es la cadena completa y ahora visible: fuente pública preservada, transformación reproducible, contratos, conciliación, analítica con gates y un dashboard que muestra tanto el hallazgo como sus límites.
