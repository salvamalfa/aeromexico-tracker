# EDA — hallazgos antes de modelar

## Resumen

La serie mensual de pasajeros sí es apta para modelos sencillos y auditables. Las métricas trimestrales de Aeroméxico son útiles para descripción, pero su historia pública comparable todavía es demasiado corta para sostener pronósticos responsables.

## Diez observaciones de negocio

1. **Hay 138 meses continuos de pasajeros AFAC.** La cobertura va de 2015M01 a 2026M06; es la base principal del pronóstico.
2. **La estacionalidad mueve aproximadamente 627,662 pasajeros entre el mes estacionalmente más fuerte y el más débil.** Eso equivale a 45.0% de la tendencia mediana.
3. **El mes estacionalmente más fuerte es el 7 y el más débil el 2.** La planeación de capacidad debe leer los cambios contra ese patrón, no contra una línea plana.
4. **La relación lineal mensual más alta observada con una variable macro es inpc con 6 meses de rezago (+0.75).** Es asociación descriptiva, no causalidad.
5. **El mayor quiebre estadístico candidato aparece en 2022M03.** La lista de quiebres incluye el régimen 2020-2023, consistente con COVID, salida de Interjet y Categoría 2.
6. **COVID se conserva como información.** No se eliminaron 2020-2021: el modelo ve el choque y la recuperación, con una regla explícita de régimen en la documentación.
7. **Las métricas trimestrales de Aeroméxico tienen entre 3 y 9 observaciones según el indicador.** Ocho trimestres no justifican modelos complejos.
8. **La comparación de costos por etapa de vuelo sigue bloqueada.** Las filas SLA son nulas porque no existe etapa promedio global comparable; no se sustituyó con la subred México-EE.UU.
9. **T-100 sí permite estudiar rutas y el episodio FAA con una historia larga.** Su alcance es la red que toca Estados Unidos, no toda la red global.
10. **Los datos faltantes se tratan como faltantes, nunca como cero.** Esta regla se mantiene en cobertura, modelos, texto y estudios.

## Tratamiento del régimen COVID

Se conserva la historia completa y se identifica marzo de 2020 a diciembre de 2021 como régimen extraordinario. El objetivo es evitar que la recuperación se borre y, al mismo tiempo, impedir que un modelo la interprete como estacionalidad normal.

## Fuentes y alcance

Los resultados provienen de las vistas gold consolidadas, AFAC, T-100 y variables macro preservadas por el pipeline. Las tablas intermedias de esta EDA quedan en `data/analytics/` para reproducir cada cifra.
