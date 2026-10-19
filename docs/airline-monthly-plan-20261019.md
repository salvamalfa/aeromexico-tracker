# Acuerdo de Airline Monthly · 19–23 de octubre de 2026

Salva autorizó: «Aplica M11 pero que sea Airline Monthly, no weekly».
Se prepara una publicación mensual propia para la plataforma existente, con
edición piloto de septiembre de 2026 —último mes completo— y archivo mensual.
Rama: `codex/airline-monthly-20261019`, independiente de Noticias y skills.

## Entrega acordada

Página de edición con índice, señales del mes, análisis, rutas y capacidad
cuando existan datos, resultados y agenda para Aeroméxico, Viva y Volaris.
Lectura clara en español, sin subtítulos de relleno ni textos innecesarios al
pie. Fuentes verificables y fechadas para toda noticia y cifra. Los huecos se
declaran; no se inventa contenido para llenar la edición. Las decisiones se
conversan por chat, sin formularios en el HTML.

No incluye correo, suscripciones nuevas, gasto, publicación de producción,
activación de tesis Viva/Volaris/Industria ni cambios en secretos, permisos,
protecciones, aprobaciones o snapshots ajenos. Preparar un PR no autoriza
integrarlo o publicarlo. El código, método y reproducción viven en la
[documentación del módulo](airline-monthly.md).

## Calendario comunicado

Las fechas se expresan en hora de Ciudad de México
(`America/Mexico_City`). Se puede adelantar trabajo seguro; no se espera una
fecha artificial para continuar ni se crean automatizaciones.

| Día | Compromiso |
|---|---|
| Lunes 19 | Estructura, inventario de fuentes y preguntas indispensables. |
| Martes 20 y miércoles 21 | Construcción y primera edición. |
| Jueves 22 | Pruebas de datos, enlaces, escritorio y móvil; revisión independiente. |
| Viernes 23 | HTML y versión para revisión. Publicar solo después de aprobación. |

La preparación técnica puede terminar antes del viernes. La agenda de la
edición conserva su corte fechado; resultados que aparezcan después requieren
una revisión de contenido, no se incorporan automáticamente.

## Fuentes disponibles y huecos

Se verificaron los originales de tráfico de septiembre: Aeroméxico y Volaris
del 6 de octubre; Viva del 9 de octubre. Aeroméxico aporta además el comunicado
de crédito y el anuncio de resultados, ambos del 30 de septiembre. Volaris
aporta su anuncio de resultados del 7 de octubre. El JSON
de la edición conserva enlaces, fechas, páginas y hashes. No se copian
textos de pago ni se utiliza información interna de Amex.

Los reportes consultados permiten capacidad y demanda agregadas por mercado,
pero no una tabla de frecuencias o pasajeros por ruta para septiembre.
Falta la fecha de resultados de Viva verificada para esta edición.
La agenda indica ese límite y no asigna fechas supuestas. Ninguno de estos
huecos impide revisar la edición piloto.

## Decisiones para Salva

1. Revisar y aprobar el contenido y la presentación del piloto. El módulo ya
   puede revisarse con los huecos anteriores visibles.
2. Autorizar por separado integración y publicación cuando corresponda;
   revisar la huella técnica de presentación antes de usar el gate existente.

No hay una pregunta indispensable que impida preparar el piloto autorizado.
No se pedirá contratación de datos ni se ampliará alcance para completar la
maqueta. Si se requiere ampliar la evidencia por ruta, se propondrá después
con fuentes y límites concretos.

Este plan permanece mientras el esfuerzo esté abierto. Al cerrarlo, conservar
las reglas vigentes en `docs/airline-monthly.md`, resumir el esfuerzo y enlazar
este documento con commit fijo en el archivo histórico, y retirarlo del árbol
según el ciclo de vida de `AGENTS.md`.
