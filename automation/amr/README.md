# AMR: búsquedas con puntos y equivalencia en pesos

## Resumen

El código de referencia de AMR forma parte de Aerolíneas MX Tracker. Aquí se
versionan las tres skills de búsqueda vigentes, sus validadores y el contrato
del libro de puntos. La incorporación conserva las corridas configuradas:
no instala skills, no cambia frecuencias y no inicia búsquedas ni sincronizaciones.

La fuente de resultados es **AMR POINTS VALUE en Google Sheets**. No hay un
Excel local de puntos dentro del proyecto original. Un archivo `.xlsx` exportado
sería una copia de consulta con fecha de corte; nunca sustituye al libro remoto.

## Qué cambia para ti

| Contenido | Ubicación |
|---|---|
| Coordinación y recuperación | [run-amr-batch](skills/run-amr-batch/SKILL.md) |
| Búsqueda aislada de una ruta | [run-amr-worker](skills/run-amr-worker/SKILL.md) |
| Registro de destinos | [create-amr-automation](skills/create-amr-automation/SKILL.md) |
| Columnas y propiedad de las hojas | [Contrato del libro](data/sheets-contract.json) |
| Identificadores de ejemplo sin datos privados | [Configuración local de ejemplo](config/local.example.json) |
| Procedencia y huellas de las skills | [Manifiesto de fuentes](source-manifest.json) |

Las skills se mantienen como carpetas hermanas porque el validador y el registro
de destinos usan referencias entre ellas. Están fuera de `.agents/skills/`
para que esta copia no reemplace las skills instaladas por descubrimiento automático.

La copia recoge el perfil instalado al 6 de noviembre de 2026: un pool global de
hasta tres asignaciones, orden por la columna C y al menos 30 segundos entre
lanzamientos nuevos. Es una descripción del perfil auditado, no una orden para
reconfigurarlo. La instalación local y su automatización conservan la autoridad
de ejecución. El README anterior describía cuatro workers y lanes regionales;
permanece en el archivo local como historia y no se usa como configuración vigente.

## Riesgos

Los identificadores del libro y las hojas se sustituyen por `{{AMR_*}}` en tres
documentos. Los diez archivos restantes, incluidos scripts y esquemas, conservan
los bytes de la instalación auditada. El manifiesto registra ambas huellas.
Resolver un marcador no concede acceso al libro ni autoriza una corrida.

Este repositorio público contiene código y contratos. Los resultados, enlaces
privados, exportaciones de Excel, launchers y estado de ejecución permanecen en
el espacio local o en el respaldo privado autorizado. Su historia Git tampoco
se importa al público: podría contener datos aunque el árbol actual se limpiara.

El dashboard AMR anterior se conserva con su repositorio Git y sus cambios
locales dentro de la carpeta unificada. Su `quotes.json` y su HTML incluyen
observaciones de los libros; no se incorporan al público. Son una instantánea
derivada, no una conexión viva. La organización de fuentes no activa la vista de
Puntos ni publica sus datos en el dashboard de Tracker.

## Apéndice técnico

Desde la raíz del repositorio, estas comprobaciones son offline y no escriben
en Google Sheets ni abren el navegador:

```text
python automation/amr/scripts/verify_source.py
python automation/amr/skills/run-amr-batch/scripts/queue_decision.py --self-test
python automation/amr/skills/run-amr-batch/scripts/validate_worker_result.py --self-test
```

El segundo validador usa `jsonschema`, incluido en el entorno Python del
proyecto. Para comparar con una instalación autorizada, el verificador admite
`--installed-root <carpeta-de-skills>` y solo lee sus archivos.

Los identificadores de ejemplo se documentan en `config/local.example.json`.
La copia de consulta local se llama `config/local.json` y está ignorada por Git.
El acceso directo local al libro se guarda fuera del código público. Nada en
estas carpetas lee esa configuración para despachar trabajo automáticamente.

`Control_AMR` conserva la cola; `Control_AMR_Run`, el lease y cursor técnicos;
`Vuelos`, las observaciones. Las cabinas son `Main` y `Premier`. Todos los
viajes capturados son redondos. A:N son valores del coordinador; O:R pertenecen
a fórmulas del libro. El contrato conserva la distinción entre impuestos al
pagar con puntos y cargos e impuestos al pagar con dinero. No redefine fórmulas,
no reemplaza faltantes por cero y no recalcula el valor por punto histórico.

## Pendientes

La incorporación del dashboard y de observaciones a una salida pública requiere
una revisión del contenido y de su autorización de publicación. Esta entrega
prepara fuentes y organización; mantiene esas observaciones en su ubicación
privada y conserva todas las corridas tal como estaban configuradas.
