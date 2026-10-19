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

## Identificadores numerados separados · 23:17 UTC

La revisión añadió `T 2 en 2026`. Se normalizan identificadores Q/T separados
de su número antes de la guardia temporal y de la búsqueda de texto. Así,
T 2 conserva `t2` y Q 400 conserva `q400`: las consultas válidas de terminal
o modelo no se convierten en todas las noticias del año por perder ambos
tokens. Pasan **100 regresiones**, que comprueban también cero coincidencias
en el índice aprobado cuando no existe evidencia de esos identificadores.

La suite sobre51352d9 terminó con **793 pruebas aprobadas en179.11s**,
verificando HEAD limpio y huella idénticos antes/después. Es distinta de
las ejecuciones locales previas sobre árbol modificado. La siguiente suite
se inicia de igual modo después del commit actual. Su huella propuesta es
`582ae0f80b7aaa67a2256f57ea504f307ee83a483abe82d94baba2d9c18ad2d6`,
sin aprobación ni promoción;6534f876/88–90 permanecen íntegros en136.

## Identificadores literales y año corto

La misma comprobación conserva T100 (BTS), T-100 y Q-400 como identificadores
de texto. Para un año corto después de T/Q se exige un separador o conector:
T100 y Q400 no se interpretan como trimestre de2000; T1 de00 y Q4/00 sí piden
fechas explícitas. Un año de cuatro dígitos puede permanecer unido, como
T22026. Esto evita una lista especial de modelos: se distingue la estructura
del año de un identificador numérico literal. Pasan **104 regresiones**;
Ruff pasa. La normalización conserva espacios y guiones en esos identificadores
sin perder su token de búsqueda.

Huella propuesta actual:
`c42824ba16c2a2e48bd1c4953b0f878cc4cab56bcc401ff6d8f235af87b89b81`.
Se inician suite y CI del commit siguiente; no se atribuyen a esta huella
los793resultados del HEAD51352d9. La aprobación6534f876 sigue vigente para
su cohorte original, no trasladada a ninguna propuesta.

## Puntuación tipográfica · 23:29 UTC

La revisión añadió T–2/Q–400. Se normalizan los caracteres Unicode de guion
y el signo menos antes de reconocer fechas e identificadores, y se conserva
el token Q/T numerado cuando el separador es otra puntuación o guion bajo.
La matriz comprueba ocho guiones en trimestres, modelos, terminales y rangos
de publicación, además de identificadores con punto/guion bajo. Pasan
**139 regresiones**. El rango abril–junio conserva sus extremos exactos y
excluye julio; las consultas de modelos sin evidencia siguen dando cero,
sin perder el token y devolver todo el año.

La suite anterior sobrea66c416 pasó **806 pruebas en180.17s**, con recibos
de HEAD limpio al inicio/final. Huella propuesta actual:
`7b4f369da6737c267d5dfa1f39eafd616cd7ea66318ebfb11be5f2bcab26679b`.
Se ejecutan de nuevo suite y revisión del commit actual por este cambio de
código; no es una duplicación de revisión sobre el mismo HEAD. La cohorte
aprobada6534f876/88–90 sigue intacta y no se traslada.

## Separadores anteriores y tema del archivo · 23:57 UTC

La revisión pidió `2-T`/`2/T`; el mismo separador de puntuación y conectores
se aplica ahora también entre el número y T/Q. Se comprueba que una cantidad
antes de Q400/T100 sigue siendo una búsqueda literal de ese identificador.

Se conserva además el flujo real del botón del archivo: `sobre 2T26` es el
tema de un reporte, y `sobre Q2 challenges` busca un titular aprobado;
`publicadas en 2T26` sigue exigiendo fechas de publicación explícitas. Cuando
el archivo ya seleccionó un mes ISO antes de `sobre`, ese texto de tema no
reabre el intervalo por contener `desde`, otro día o un día semanal. Una
segunda cláusula `publicadas` permanece visible y se valida como periodo.
La extracción de aerolíneas y temas conserva la consulta completa.

Pasan **183 regresiones nuevas** y **642 pruebas** junto con las matrices
anteriores de fecha/aerolínea/hora (0.54s), Ruff y diff-check. La suite limpia
previa sobre9fc24e4 pasó **841 pruebas en177.45s**. La suite completa actual
se ejecuta después del commit, con recibos de HEAD limpio al inicio/final.

Huella propuesta actual:
`be03c5ad3d40b1edef54d45163e6cfea96182821a41b469a238ebf71507898be`.
La propuesta sigue sin auditar como nueva cohorte canónica ni aprobar; la
autorización6534f876 de21:16:59 y sus pares88–90 permanecen vigentes e intactos.
No se ejecuta un nuevo gate ni se integran136/139.

## Calendario visible tras el tema · 19 de octubre, 00:20 UTC

La revisión exacta de19267cd encontró otra forma de publicación (`publicaron`
y `publicación`). Se retira el enmascarado amplio del tema después de un
mes ISO: solo las etiquetas trimestrales que describen el tema quedan fuera
de la extracción del periodo. Todos los otros días, meses y calificadores
siguen visibles; una segunda cláusula o un calendario ambiguo pide aclaración.
Esto reemplaza la conducta descrita en el corte anterior para `desde`, días
semanales o fechas adicionales. La frontera también reconoce las formas de
publicar y el sustantivo publicación. Se conservan los temas simples 2T26 y
Q2 challenges del archivo.

Pasan **191 regresiones** (0.18s) y **650 pruebas** al incluir las tres
matrices previas (0.52s). La suite limpia anterior885/177.63s corresponde
exclusivamente a19267cd; la siguiente se ejecuta después del nuevo commit.
Huella propuesta `7adcf2ea8f9120571cc1ab78b3de0111c7e0bbfc1078da0f73fac039dffa0c10`.
No se crean registros, auditorías ni aprobaciones financieras, ni otro gate.
La autorización original6534f876/88–90 sigue vigente para sus pares exactos.
