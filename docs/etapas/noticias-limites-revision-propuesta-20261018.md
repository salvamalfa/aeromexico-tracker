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

## Revisión de la propuesta · 22:45 UTC

Codex señaló que el detector inicial también rechazaba `T2` del AICM y el
modelo `Q400`. Se restringió a las estructuras trimestrales con año y a
`Q` con un solo dígito de trimestre; `T1`/`T2` solas y los modelos de avión
conservan su búsqueda de texto. Las 28 regresiones pasan, incluidas las
cinco nuevas de terminales/modelos. La suite anterior de Noticias pasó
725 pruebas en 181.42 s antes de este ajuste; no se le atribuye el ajuste
posterior sin volver a comprobarlo.

La primera huella propuesta `5675b289…` queda superada. La propuesta actual
es `c4c46c392f7827e8d5043b43521c1929c77d7a3d263ffde0f4a8afec8dead713`;
ninguna de las dos está aprobada. Se requieren CI y Codex del HEAD nuevo.
La huella aprobada6534f876, sus tres pares, ledger90 y el sitio firmado
permanecen intactos en #136.

## Cierre de variantes separadas

La revisión siguiente pidió cubrir también `2026 T2`, `T2 2026` y
`T2 de 2026`. El detector admite ambos órdenes con separadores cuando el
token lleva año; las terminales `T2 del AICM`, `T2 en 2026` y el modelo
`Q400` siguen siendo texto libre. Se amplió la matriz a veinte notaciones,
con y sin límites suministrados, y siete consultas aeronáuticas: **52
regresiones aprobadas**. La suite previa de 730 pruebas pasó en 180.51 s
con el HEAD anterior; la suite y CI del ajuste actual se informan por separado.

La huella propuesta vigente es
`47e5ceea0ed632a4c7a342b58e39b6d1b1bb48e59a3c50e65e3bf7807b89313d`.
Las propuestas5675b289 y c4c46c39 quedan superadas sin aprobación. El alcance
de activación continúa detenido y no se traslada el consentimiento6534f876.

## Guardia de periodo ambiguo · 22:58 UTC

La revisión añadió `2026 de T2`. Se cubren `de`/`del` después del año y
se pide aclaración cuando coexisten un año y una etiqueta T sin contexto
explícito de terminal/aeropuerto. Así, otras palabras de unión no amplían
silenciosamente al año. `T2 del AICM en 2026` y `terminal T2 en 2026`
conservan texto libre, al igual que Q400. Se añaden también 2Q26/2Q2026.
Pasan **64 regresiones** (0.07 s), con veinticinco formatos, límites
opcionales, siete consultas aeronáuticas y dos consultas ambiguas.

La suite previa754 pasó en 180.99 s sobre0e66a47. El código candidato
actual cambia la huella a
`8234f2d6bf1d68c3f264443efcdcad6d09ae2795baf2f16183e11325104f3425`;
las huellas de las propuestas anteriores quedan superadas, nunca importadas
como nuevas aprobaciones. La aprobación6534f876 sigue vigente exclusivamente
para sus pares88–90 y el sitio firmado anterior. Los pares prospectivos
calculados durante la revisión no se deben presentar como solicitud de
aprobación: primero se congela la corrección y se completan sus auditorías.

## Atribución conservadora de operadores · 23:03 UTC

La unión de compañías propuesta inicialmente podía hacer que archivo y chat
combinaran compañía de una fuente con tema de otra. Se adopta la otra salida
aceptada por la revisión original: **rechazar una historia con conjuntos de
compañías incompatibles**, para que se revise su agrupación antes de exportar
o buscar. Las fuentes con atribución consistente conservan la unión de temas,
buscables con esa misma compañía. No se cambia la API ni se atribuye una
noticia del grupo a Connect.

Pasan las **66 regresiones**, incluidos ambos órdenes de fuentes y el rechazo
en archivo/chat del caso Connect/combustible cruzado. La suite anterior766
pasó en179.28s sobre8f19638; la nueva suite y CI/revisión del ajuste actual
se comprueban por separado. La huella propuesta actual es
`4c2e9fa9f34eeeda5c82e6b958ca9e893a995da808e9c0724d705000b390ddbc`.
Todas las propuestas anteriores siguen superadas y sin aprobación. El
expediente autorizado6534f876 permanece íntegro, sin nuevo gate ni promoción.

## Conectores compartidos en las etiquetas

La revisión pidió también `2T de 2026`/`2Q del 2026`. Los tres órdenes de
etiqueta usan ahora el mismo conector opcional `de`/`del`, espacios, barras
y guiones, y se rechaza la etiqueta número+T/Q sin ampliar a un año cuando
hay palabras intermedias. Se preservan los términos Q100/Q200/Q300/Q400
antes de reconocer Q con año. Pasan **91 regresiones** (0.08 s); Ruff pasa.
La suite previa768 pasó en181.77s con el código4c2e9fa9. La suite siguiente
se inicia después del commit, sobre checkout limpio, y no se anticipa su
resultado en este corte.

Huella propuesta vigente:
`7efbf4d5061b6395d50e2ac131a3f18281073b292375e16e41964cf24e6031f7`.
La autorización original6534f876 y sus pares88–90 siguen íntegros; no
autoriza esta propuesta distinta y no se ha pedido todavía consentimiento
sobre pares nuevos sin auditoría. Las referencias a commits de las suites
locales anteriores identifican el código equivalente: se iniciaron con las
modificaciones en el árbol de trabajo y se comprometieron después; no son
afirmaciones de HEAD limpio al inicio. El expediente de cierre registra esa
procedencia por huella de runtime y las comprobaciones de CI de HEAD exacto.
