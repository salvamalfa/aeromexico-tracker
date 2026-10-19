# Airline Monthly · preparación del 19 de octubre de 2026

Base de trabajo: `origin/master` en `7bbfb4d`, checkout original limpio.
Se creó el worktree `/workspace/airline-monthly` y la rama
`codex/airline-monthly-20261019`. Se comprobaron los PRs abiertos 136, 137 y
139; no se usaron como base ni se modificaron sus ramas. Los checkouts
originales público y privado conservaron estado limpio.

## Resultado preparado

M11 implementado como Airline Monthly, publicación mensual original para
Aeroméxico, Viva y Volaris. El piloto de septiembre tiene índice, señales,
análisis editorial, capacidad por mercado, resultados, agenda, fuentes y
archivo mensual. Los enlaces identifican edición y sección; un mes inexistente
se muestra como no disponible.

La página vive en `web/monthly.html` y `web/src/monthly/`. La preview utiliza
esos mismos archivos y el JSON público versionado; no hay otra implementación
del módulo. El [HTML autocontenido](../../prototypes/airline-monthly/septiembre-2026.html)
permite revisar sin exportar datos del warehouse ni conectar el chat.

El build habitual excluye página, datos y enlace de producto. La opción
`VITE_AIRLINE_MONTHLY_PREVIEW=true` los incluye para revisión local. Se comparó
una compilación ordinaria con otra desde un archivo Git de `origin/master`:
los 17 archivos resultantes fueron idénticos byte por byte. La compilación
optativa también se comprobó navegando desde Productos hasta la edición.

## Evidencia editorial

Se consultaron seis PDF originales públicos y se verificaron sus respuestas
HTTP 200 y hashes SHA-256. El JSON conserva URL, fecha de publicación,
consulta y localizador; los crudos quedaron fuera de Git.

| Documento | Fecha de publicación |
|---|---|
| Aeroméxico: tráfico de septiembre | 6 oct 2026 |
| Viva: tráfico de septiembre | 9 oct 2026 |
| Volaris: tráfico de septiembre | 6 oct 2026 |
| Aeroméxico: crédito sindicado | 30 sep 2026 |
| Aeroméxico: anuncio de resultados y conferencia | 30 sep 2026 |
| Volaris: anuncio de resultados y conferencia | 7 oct 2026 |

Se contrastaron cifras, fechas, unidades y definiciones con los documentos.
Los pasajeros de las compañías no se suman ni se usan para cuotas de mercado:
sus definiciones difieren. Se conservan ASM/RPM en millas y la ocupación
publicada. No se extrapolan ingresos o rentabilidad de tráfico. Hechos,
inferencias, eventos programados y límites se distinguen en la lectura.
No se incluyen estimaciones, datos de Amex ni información de tarjetahabientes.

El detalle por ruta de septiembre y la fecha de resultados de Viva quedan
pendientes de evidencia. No se representan como cero ni se asigna una fecha
supuestamente habitual. Resultados financieros posteriores al corte no se
añaden automáticamente a esta edición.

## Validación local

- TypeScript: `npm run check`, correcto. Vitest: **232 pruebas aprobadas**.
- Suite pública, con los dos pins canónicos de aprobación solo en el proceso:
  **1,693 aprobadas, 6 omitidas, 89 deseleccionadas y 29 subpruebas aprobadas**.
  Omisiones: no hay preview Pages fijada; cinco artefactos locales de Stage 4
  no se versionan. No se omitieron errores del nuevo módulo.
- Chromium, suite de interfaz: **17 aprobadas y 1 omitida**. La omisión
  corresponde a otra propuesta que no está en esta rama. Tras ampliar la
  agenda de Volaris se repitieron las **4 pruebas de Monthly**, todas correctas.
- Las 8 pruebas editoriales también pasaron tras ese ajuste de contenido.
- Pyflakes en `src/` y `scripts/`, formato de los dos módulos exigidos por CI,
  presupuestos del repo y `git diff --check`: correctos.
- El `site/` ya existente pasó `src.publish.verify` con los pins registrados.
  No se regeneró ni modificó ese sitio.

Se probaron lectura, enlaces a secciones, archivo, historial, recarga,
teclado, foco, mes inexistente y fuentes en la preview. En 320/390/1280 px
no hay desbordamiento horizontal de página; la tabla conserva desplazamiento
interno en móvil. No se solicitan recursos externos al leer el HTML servido
localmente. El build optativo se verificó además a 1280 y 390 px.

El entorno reutilizado inicialmente carecía de dependencias del chat; se
instaló el lockfile completo en un entorno propio. La primera corrida sin
pins falló al revalidar aprobaciones existentes; se repitió con los valores
canónicos documentados en el commit `d456eb8dc05e586d7119161c710db5ff47af0da3`,
solo en el entorno del subproceso. No se calcularon pins nuevos ni se cambiaron
variables externas, recibos o firmas. El Chromium utilizado corresponde al
Playwright del lockfile.

No se restauró información privada en este worktree. La suite con warehouse
y expedientes privados no se ejecutó; la preparación editorial no los usa.
Los resultados locales no equivalen a aprobar una nueva huella técnica.

## Revisión independiente

Otro agente realizó una revisión adversarial separada, contrastando fuentes y
ejecutando sus propias comprobaciones. Encontró tres problemas reproducibles:

1. El enlace para saltar al contenido entraba al router y sustituía la edición
   por la página no disponible. Se intercepta el enlace y se conserva la ruta.
2. La tabla expandía la página en móvil. Se permite reducir el ancho del
   contenedor y se conserva el scroll dentro de la tabla.
3. Un título infería una red más pequeña a partir de menos ASM. Se cambió a
   «Mayor ocupación con menor capacidad».

Los tres quedaron corregidos y comprobados por el revisor. También verificó
el incremento posterior de la agenda de Volaris. Cerró sin hallazgos P1/P2
abiertos. No es una revisión Claude ni una aprobación humana. Si no llega la
revisión automática de Codex, permanece la revisión cruzada exigida por
`AGENTS.md` antes de una eventual integración.

Chromium del cloud denegó abrir `file:///tmp/...` con
`ERR_BLOCKED_BY_ADMINISTRATOR`; no se cambiaron sus políticas. El autor probó
el mismo HTML mediante un servidor local, restringiendo las solicitudes al
documento; el revisor también comprobó el contenido con red bloqueada. La
lectura directa del archivo se verificó con jsdom.

## Límite de entrega

Código y edición: preparados para revisión. Datos o tesis activados: ninguno.
Aprobación editorial o técnica nueva: ninguna. Producción: sin publicación.
No se ejecutó el gate, no se despacharon workflows de despliegue ni se crearon
suscripciones, envíos, gastos o automatizaciones.

El [acuerdo activo](../airline-monthly-plan-20261019.md) documenta el calendario
19–23 de octubre en hora de Ciudad de México y las decisiones pendientes para
Salva. La preparación se adelantó sin esperar fechas artificiales. La
integración/publicación requieren su aprobación posterior y resolver la
revisión de huella técnica descrita en la documentación del módulo.
