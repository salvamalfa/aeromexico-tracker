# Corrección de evidencia del scorer del chat

El scorer de respuestas compatibles ahora valida y combina todas las llamadas
exitosas a consultas, comparaciones y series del turno. Antes, una llamada
posterior podía ocultar filas devueltas por llamadas anteriores. El scorer
comprueba las versiones fijadas, el contexto y los argumentos de cada llamada,
exige las celdas solicitadas por consultas y comparaciones, conserva solo
periodos realmente devueltos por series y rechaza duplicados conflictivos o
alcances combinados que un plan no pueda representar.

La corrección mide evidencia reproducible del snapshot público. Las preguntas
de ambigüedad, rechazo y seguridad siguen pendientes de revisión humana; este
cambio no elige un modelo ni aprueba calidad o publicación.

Validación offline: pruebas sintéticas del normalizador, del verificador y del
callback live, más Ruff sobre los archivos modificados. No se hicieron llamadas
a proveedores.
