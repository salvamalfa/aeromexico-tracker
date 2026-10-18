# Propuesta tras la revisión final de Noticias · 18 de octubre de 2026

Corte de preparación: 22:40 UTC. No es una publicación ni una renovación
de aprobación. El PR #136 conserva su HEAD aprobado y el sitio firmado anterior.

## Hallazgos reproducidos y cambio propuesto

La revisión de Codex sobre `2e23b0fd03fa4b5339dc776ecc01127aabb0ee7e`
señaló dos problemas P2. Al agrupar fuentes de una historia, la tarjeta
conservaba solo las etiquetas de la primera fuente: una búsqueda de Connect
podía llevar a una tarjeta que el filtro de Connect no encontraba. Además,
`2026Q2`, `Q2 2026` y `2T26` podían convertirse en una búsqueda sin límite,
en un año completo o en texto libre, incluyendo noticias de julio.

La propuesta valida compañías antes de agrupar cada fuente y conserva la
unión de compañías y temas de la historia, sin heredar aprobación de una fuente
candidata. La notación trimestral compacta pide inicio y fin explícitos en
ISO; no se infiere el trimestre ni se utiliza como palabra de búsqueda.
Los intervalos explícitos de publicación siguen funcionando.

Se reprodujeron 21 fallos y dos casos correctos con la implementación
congelada; después pasan las 23 regresiones nuevas (0.05 s). Incluyen orden
inverso de fuentes, búsqueda de Connect y tarjeta coherentes, compañía
desconocida en fuente secundaria, nueve formatos compactos con límites
opcionales y un intervalo abril–junio que excluye julio. Ruff pasa. La suite
ampliada de Noticias y CI/Codex del commit de propuesta se cierran por separado;
este corte no les atribuye resultados anticipados.

## Límite de activación y conservación

La huella propuesta es
`5675b289769cdc08ddf7e50686d69bb31da03730cfc2084cd453f2ec89a4d24d`.
La aprobada sigue siendo
`6534f8760546e9649996ffbd75fc5cbe73ecbcd3d96c58de3c4b9b14782e9aee`.
El alcance conservador incluye todo `src/**/*.py`; estos dos archivos de
runtime cambian la identidad aunque no alteren textos ni cifras financieras.
No se trasladan los eventos 88–90 a esta huella, no se importan nuevas
aprobaciones y no se ejecuta el gate con la propuesta.

Para activarla hace falta congelar el código corregido, cerrar CI y revisión
exactas y preparar una nueva cohorte técnica auditada para aprobación expresa
del dueño. Después se ejecutaría el gate y la aceptación productiva normal.
El PR de la propuesta permanece en borrador; #136 no se integra con sus dos
hilos abiertos. Los PRs #134, #138 y #135 ya integrados conservan el sitio y
pin anteriores; Railway #135 está SUCCESS con snapshot anterior exacto.

El manifiesto firmado conserva SHA256
`b33d97eb52e0dc744ee7d029eddb5c0b3edfa43f67a0484f9ca0466cc7ab2a84`,
el ledger continúa en 90 y los respaldos privados #33/#34 permanecen íntegros.
No se activan candidatas, skills #137, cron ni estimaciones adicionales.
