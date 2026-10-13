# Desarrollo seguro desde GitHub y agentes de nube

Procedimientos cloud revisados: 2026-10-13. Los estados fechados abajo conservan
su corte histórico.

## Decisión

Sí es correcto usar GitHub como fuente común para que un agente de nube pueda
inspeccionar y modificar el proyecto cuando la PC local esté apagada. El código,
los contratos, Gold y artefactos públicos están integrados en `master` por el
PR #10, commit `652172dd8c5836849345bb980f797c47186b5de8`. Los insumos privados
están respaldados por separado en el repositorio privado
[`salvamalfa/aeromexico-tracker-data`](https://github.com/salvamalfa/aeromexico-tracker-data).

GitHub debe contener código, contratos, documentación, Gold públicos y
artefactos generados aprobados. No debe convertirse en copia de secretos,
respuestas crudas con licencia, estados privados de revisión o archivos
regenerables demasiado grandes.

## Qué debe quedar versionado

| Clase | GitHub | Motivo |
|---|---|---|
| `src/`, `tests/`, `config/`, `sql/` | Sí | Código y contratos necesarios para revisar y cambiar el sistema |
| `docs/`, `AGENTS.md`, `CLAUDE.md` | Sí | Contexto, reglas y decisiones para humanos y agentes |
| `data/gold/*.parquet` | Sí, si son públicos y licenciables | Son los extractos compactos que consume el dashboard |
| manifiestos de Bronze | Sí | Conservan URL, hash y procedencia sin redistribuir el crudo |
| prototipos HTML de revisión | Sí, si están aprobados o claramente marcados | Permiten inspección sin ejecutar toda la tubería |
| `.env`, claves y secretos | No | Deben vivir en secretos del entorno |
| `data/bronze/*` y `data/silver/` | No por defecto | Crudos e intermedios locales; pueden estar sujetos a licencia |
| `data/warehouse.duckdb` | No | Es regenerable y no es la interfaz pública |
| `analysis_runs/` | No | Es el expediente autoritativo local de aprobación y publicación |
| caché/respuestas crudas de APIs pagadas | No | La licencia puede limitar retención y redistribución |

## Estado confirmado al 2026-09-19

- El checkout público está limpio y `master` coincide con `origin/master` en
  `652172dd8c5836849345bb980f797c47186b5de8`.
- La suite integrada terminó con 429 pruebas aprobadas antes de la entrega.
- El repositorio privado contiene 1,879 archivos y 1,278,880,052 bytes bajo Git
  LFS, con manifiesto SHA-256.
- Un clon nuevo del respaldo pasó `git lfs fsck`, verificó los 1,879 hashes y
  restauró todos los archivos sin incluir `.env`.
- La copia de `warehouse.duckdb` se recreó lógicamente: conserva 43 tablas, 21
  vistas y los conteos por tabla del original, y omite páginas físicas obsoletas.
- La alerta de secret scanning del Parquet Gold fue revisada y cerrada como
  falso positivo; no había coincidencia en ninguna celda lógica.

El detalle reproducible está en
[`docs/archivo/mantenimiento-2026-09/entrega-github-datos-privados-20260919.md`](https://github.com/salvamalfa/aeromexico-tracker/blob/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/mantenimiento-2026-09/entrega-github-datos-privados-20260919.md).

## Qué podrá hacer un agente de nube

Con acceso únicamente al repositorio público, un agente podrá:

- entender la arquitectura y ejecutar la suite sobre Gold públicos;
- modificar ingestas, transformaciones, contratos y generadores;
- revisar la pestaña Vuelos y producir prototipos;
- preparar un adaptador y un `--dry-run` para una API;
- trabajar mediante PRs comparables y auditables.

Sin acceso al respaldo privado no podrá:

- reconstruir Bronze o Silver de fuentes manuales que no estén disponibles;
- usar una API pagada sin una clave configurada como secreto del entorno;
- reproducir una respuesta cruda que la licencia obliga a borrar;
- aprobar o republicar Analysis Agent sin el expediente autorizado de
  `analysis_runs/`.

Un agente autorizado para ambos repositorios puede restaurar Bronze, Silver,
quality, analytics, warehouse, modelos y `analysis_runs/`. Esa disponibilidad
no cambia su licencia ni el significado de las aprobaciones: el contenido
privado no debe copiarse al repositorio público y una restauración no autoriza
publicación.

## Restauración del respaldo privado

En Windows, usa una ruta corta y habilita rutas largas para el clon:

```powershell
git -c core.longpaths=true clone https://github.com/salvamalfa/aeromexico-tracker-data.git "C:\ruta\a\Aeromexico Tracker\aeromexico-tracker-data"
git -C "C:\ruta\a\Aeromexico Tracker\aeromexico-tracker-data" config core.longpaths true
git -C "C:\ruta\a\Aeromexico Tracker\aeromexico-tracker-data" lfs pull
Set-Location "C:\ruta\a\Aeromexico Tracker\aeromexico-tracker-data"
python verify_snapshot.py
python restore_snapshot.py --target "C:\ruta\a\Aeromexico Tracker\aeromexico-tracker"
```

El repo público y el privado viven como carpetas hermanas dentro de una
carpeta contenedora local (no versionada) `Aeromexico Tracker\`:
`aeromexico-tracker\` (público) y `aeromexico-tracker-data\` (privado); el
código resuelve el privado con la ruta relativa `../aeromexico-tracker-data`
desde el checkout público. Ver `LEEME.md` en esa carpeta contenedora para el
resto de la estructura (worktrees, temporales).

El repositorio privado excluye `.env`, secretos locales, cachés, logs,
temporales y entornos virtuales. Las claves deben configurarse en los secretos
del entorno nuevo. Cada actualización del snapshot debe volver a revisar
licencias, credenciales, manifiesto y restauración; Git LFS contabiliza cada
versión nueva de un objeto.

## Proveedores pagados y GitHub

Los términos vigentes de AeroDataBox distinguen `Contents` de `Derived Works`.
Una respuesta de API, una selección de campos o una tabla ligeramente
reformateada sigue siendo contenido del proveedor y no puede republicarse como
dataset. La retención estándar es de siete días. AeroDataBox anuncia retención
extendida mientras la suscripción permanezca activa para RapidAPI Mega,
API.Market Ultra 2 y Mega, y el plan directo Growth; otros planes directos
pueden permitir un periodo posterior a la cancelación. Una obra derivada debe
combinar múltiples observaciones o datos externos mediante un proceso no
trivial y no permitir reconstruir registros individuales; las obras derivadas
están exceptuadas de la restricción de caché, aunque siguen sujetas al resto de
los términos.

Para este proyecto, la implementación conservadora es:

1. Guardar respuestas crudas en `data/bronze/aerodatabox/` solo durante la
   ventana permitida por el plan documentado en la captura y nunca incluirlas
   en Git. Es Bronze temporal y también funciona como caché de reanudación;
   mientras la captura esté sujeta a retención estándar no forma parte del
   snapshot permanente.
2. Derivar conteos mensuales de vuelos por ruta y operador, agregados a un nivel
   que no permita reconstruir un vuelo individual.
3. Combinar esos conteos con marginales AFAC mediante un estimador versionado.
4. Versionar solo diagnósticos, metadatos y resultados que cumplan la definición
   contractual de obra derivada.
5. Registrar la versión de términos y del plan aplicable en cada captura.

Bronze describe el estado crudo del dato, no su plazo de conservación. Si una
captura se realiza con un plan que autoriza retención extendida, puede
conservarse en almacenamiento privado durante ese plazo, con acceso restringido
y una fecha de revisión ligada a la suscripción. Ese derecho adicional no
permite subir las respuestas crudas a Git ni compartirlas con terceros.

La clasificación contractual final debe confirmarse con AeroDataBox si se desea
publicar en GitHub el cubo de conteos de vuelos. El hecho de agregar por mes no
garantiza por sí solo que sea obra derivada.

Fuentes vigentes revisadas:

- [AeroDataBox API Pricing](https://aerodatabox.com/pricing/)
- [AeroDataBox Terms of Use](https://aerodatabox.com/terms)
- [Terms and marketplace plan update, 2026-09-07](https://aerodatabox.com/2026-09-terms-update)
- [Direct API access announcement](https://aerodatabox.com/direct-subscriptions)

## Configuración mínima de un entorno de nube

1. Revisar estado y cambios existentes en ambos repos; hacer `git fetch` y
   crear la rama o worktree desde el `origin/master` vigente. Conservar los
   checkouts anteriores. Mantener público y privado como carpetas hermanas.
2. Instalar Python 3.13 y las dependencias bloqueadas con
   `uv sync --all-extras --all-groups --locked`; en `web/`, `npm ci`. CI usa
   Node 22. Instalar el Chromium de la versión bloqueada de Playwright, sin
   apuntarlo a un navegador de otro major.
3. Usar Gold públicos para pruebas sin insumos privados. Para una restauración,
   materializar LFS y verificar hashes/derivados en el privado antes de copiar.
   Restaurar en un checkout aislado: `restore_snapshot.py` sobrescribe rutas
   existentes, incluidas algunas que pueden estar versionadas. No ejecutarlo
   sobre trabajo ajeno; revisar el estado Git después.
4. Comprobar el warehouse: su snapshot puede ser anterior a Gold público. Con
   los cuatro Gold privados ya verificados en destinos ignorados, la rutina
   existente `build_warehouse(max_stage=9)` reconstruye solo la base local
   desde Gold vigente; no consulta proveedores ni modifica aprobaciones.
5. Ejecutar la suite y checks indicados en `REPO_MAP.md` y `web/README.md`.
   Registrar fallos, errores y skips con causa; CI pública no demuestra que la
   suite con datos privados pase. No reconstruir una aprobación para pasarla.
6. Dashboard estático y pruebas offline no necesitan credenciales. Para los
   checks que verifican métricas financieras o evidencia aprobadas, usar los
   pins existentes registrados en `docs/chat/fase-2-decision-dueno.md`, limitados a
   ese proceso. No calcular un pin nuevo desde el recibo ni cambiar variables
   externas. Para una ingesta autorizada, usar el secreto existente y un
   destino ignorado; empezar por `--dry-run`.

### Shell Linux y preview local

En el cloud con raíz `/workspace`, la activación existente se carga con
`source /workspace/.cloud-setup/activate.sh` si está presente. La shell de una
tarea nueva puede no cargarla automáticamente. Las cachés deben ser
escribibles; una instalación nueva debe ejecutar `uv sync` explícitamente
aunque la activación exporte `UV_NO_SYNC=1`.

```bash
export UV_CACHE_DIR=/workspace/.cache/uv
export UV_PYTHON_INSTALL_DIR=/workspace/.local/share/uv/python
export PLAYWRIGHT_BROWSERS_PATH=/workspace/.cache/ms-playwright
uv sync --all-extras --all-groups --locked
uv run --no-sync playwright install chromium
cd web
npm ci --cache /workspace/.cache/npm
```

Tras la restauración y comprobación de los Gold privados, desde la raíz del
checkout público aislado:

```bash
uv run --no-sync python -c 'from src.transform.stage6_warehouse import build_warehouse; build_warehouse(max_stage=9)'
```

Para inspeccionar la versión publicada sin reconstruir datos ni ejecutar el
gate, servir `site/` con `python -m http.server 4173 --bind 127.0.0.1 --directory
site`. Para desarrollar `web/`, seguir su README. Declarar si el navegador es
del cloud o una sesión del usuario, qué herramienta se usó, y si se probaron
datos reales o fixtures. Si Chromium no confía en el certificado del proxy,
no desactivar TLS ni instalar confianza sin autorización: verificar los
archivos HTTPS por hash con un cliente que ya confíe y probar la copia local.

Si GitHub API/fetch funcionan pero el push falla en el hook LFS por falta de
credenciales, una sesión `gh` ya autorizada puede proporcionar su ayudante
solo para ese comando:

```bash
git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push -u origin <rama>
```

No imprimir el resultado del ayudante, crear tokens, desactivar hooks ni
guardar una configuración de credenciales persistente para resolverlo.

### Operación continua y límites de entrega

El dueño define objetivos y prioridades; el agente define criterios de
aceptación verificables y resuelve decisiones técnicas normales. Escalar
alternativas con impacto material de producto, nuevas cifras/evidencia,
consumo pagado, credenciales, accesos persistentes y cambios de seguridad.
Conservar decisiones y pendientes en sus documentos canónicos, sin duplicar
`ROADMAP.md`, los procedimientos del chat o la documentación privada.

Antes de push, comprobar los triggers del commit y el destino real:

| Destino | Trigger vigente al 13 oct 2026 | Consecuencia |
|---|---|---|
| CI pública | PR; push a `master`; `workflow_call` | `test` y `web` validan el commit del PR. |
| Pages | Push a `master` que cambie `site/**` o `.github/pages-preview.json`; despacho manual | Publica el sitio firmado tras verify y CI. También actualizar una preview en Pages modifica producción. |
| Railway | Fuente `master` y watch paths del servicio | Cambios de entradas Docker redespliegan el chat. `checkSuites=false`: no espera CI; no asumir que el merge es inocuo. |
| Datos privados | Capturas pagadas por despacho manual; retención cada seis horas | Push documental no captura datos ni consume API. |

Las fuentes y su periodicidad viven en `config/source_catalog.yaml`. El
workflow `refresh.yml` monitorea frescura y valida; no reemplaza la descarga
manual mensual de AFAC/AeroDataBox. Noticias del chat solo produce candidatos
por despacho manual. Los límites del snapshot/retención están en el README
privado; Railway, recuperación y controles del chat en `docs/chat/railway.md`.

Cerrar una preparación exige accesos comprobados sin secretos, dependencias
instalables, resultados explícitos de tests, QA del sitio y contraste con
fuentes, documentación revisable y pendientes concretos. Una auditoría inicial
queda en PR borrador para aprobación explícita antes de integrar y publicar;
no activa auto-merge, evidencia, proveedores ni cambios de infraestructura.

Evidencia de la preparación del 13 de octubre:
[`docs/etapas/cloud-readiness-20261013.md`](etapas/cloud-readiness-20261013.md).
