# Desarrollo de Airlines Tracker desde GitHub

El repositorio público permite revisar el código, consultar los datos publicados
y desarrollar la interfaz. Reconstruir todas las fuentes y repetir aprobaciones
requiere insumos privados adicionales. Esta guía separa ambas rutas.

## Qué puedes reproducir

| Con un clon público | Con insumos privados verificados y acceso autorizado |
|---|---|
| Servir `site/`, la publicación conservada. | Reconstruir Bronze, Silver y warehouse desde originales retenidos. |
| Modificar la interfaz con los JSON públicos de `site/data/v1/`. | Ejecutar los exportadores completos que requieren Gold privados. |
| Ejecutar pruebas públicas y de navegador con datos sintéticos. | Repetir pruebas `local_data`, fuentes y expedientes de aprobación. |
| Revisar contratos, modelos, transformaciones y procedencia. | Recuperar el estado de `analysis_runs/` sin crear aprobaciones nuevas. |

El respaldo privado es
[`salvamalfa/aeromexico-tracker-data`](https://github.com/salvamalfa/aeromexico-tracker-data),
con Git LFS. El acceso al código no concede acceso a ese respaldo.
Restaurarlo no autoriza a publicar ni a consumir una API pagada.

Para ver el dashboard desde la raíz, sin reconstruirlo:

```bash
python -m http.server 4173 --bind 127.0.0.1 --directory site
```

Para modificar la interfaz con el mismo conjunto de datos, sigue
[`web/README.md`](../web/README.md). El export completo con
`--allow-missing-analysis` aún exige los Gold privados de Vuelos:
esa opción solo omite los análisis ausentes en desarrollo.

## Qué se conserva en cada repositorio

| Contenido | Destino |
|---|---|
| Código, pruebas, contratos, configuración y documentación | Repositorio público. |
| Gold públicos, compactos y con derechos de redistribución | Repositorio público. |
| Manifiestos de procedencia permitidos | Público, sin redistribuir los originales. |
| `site/` y prototipos aprobados o identificados como revisión | Público, con su alcance y estado. |
| Bronze, Silver, warehouse, modelos y derivados privados | Respaldo privado, sujeto a licencia y retención. |
| `analysis_runs/` | Expediente privado de revisión, aprobación y publicación. |
| `.env`, credenciales y claves | Secretos del entorno; fuera de ambos repositorios. |
| Cachés, temporales, entornos y registros de ejecución prescindibles | Locales; fuera del respaldo. |

No copies respuestas licenciadas, fuentes privadas ni expedientes de aprobación
a un PR público. Las reglas canónicas están en [`AGENTS.md`](../AGENTS.md).

## Preparar un entorno

1. Revisa `git status` y conserva cambios existentes. Actualiza las referencias
   remotas y crea una rama o un worktree desde `origin/master`.
2. Usa Python 3.13 y Node 22, como CI. Instala las dependencias bloqueadas:
   `uv sync --all-extras --all-groups --locked` y, dentro de `web/`, `npm ci`.
3. Instala el Chromium de la versión bloqueada de Playwright. Si necesitas
   seleccionar un navegador existente, consulta la variable documentada en
   [la guía web](../web/README.md).
4. Ejecuta los controles correspondientes al alcance:
   [comandos del repositorio](../REPO_MAP.md), [pruebas web](../web/README.md)
   y [verificación de publicación](../src/publish/README.md).
5. Registra fallos y omisiones con su causa. Que pase CI pública no demuestra
   que se hayan repetido fuentes o pruebas privadas.
6. El dashboard estático y las pruebas sin red no necesitan credenciales.
   Una ingesta autorizada usa secretos del entorno y un destino ignorado;
   comienza con `--dry-run`.

Los controles de métricas financieras y evidencia aprobadas usan los pins
existentes del [registro de aprobación auditado](https://github.com/salvamalfa/aeromexico-tracker/blob/d456eb8dc05e586d7119161c710db5ff47af0da3/docs/chat/fase-2-decision-dueno.md),
solo para su alcance. No calcules un pin nuevo desde un recibo del repositorio
ni cambies aprobaciones para superar una prueba.

### Cachés y shell en Linux

Si existe, carga `source /workspace/.cloud-setup/activate.sh`.
Una shell nueva puede no hacerlo automáticamente. Las cachés deben ser
escribibles. Ejecuta la instalación explícita aunque el entorno defina
`UV_NO_SYNC=1`:

```bash
export UV_CACHE_DIR=/workspace/.cache/uv
export UV_PYTHON_INSTALL_DIR=/workspace/.local/share/uv/python
export PLAYWRIGHT_BROWSERS_PATH=/workspace/.cache/ms-playwright
export npm_config_cache=/workspace/.cache/npm
uv sync --all-extras --all-groups --locked
uv run --no-sync playwright install chromium
cd web
npm ci --cache /workspace/.cache/npm
```

## Restaurar insumos privados

Mantén los repositorios público y privado como carpetas hermanas:
`aeromexico-tracker/` y `aeromexico-tracker-data/`.
El código busca el respaldo mediante `../aeromexico-tracker-data`.

En Windows, usa una ruta corta y habilita rutas largas. Receta existente:

```powershell
git -c core.longpaths=true clone https://github.com/salvamalfa/aeromexico-tracker-data.git "C:\ruta\a\Aeromexico Tracker\aeromexico-tracker-data"
git -C "C:\ruta\a\Aeromexico Tracker\aeromexico-tracker-data" config core.longpaths true
git -C "C:\ruta\a\Aeromexico Tracker\aeromexico-tracker-data" lfs pull
Set-Location "C:\ruta\a\Aeromexico Tracker\aeromexico-tracker-data"
python verify_snapshot.py
python restore_snapshot.py --target "C:\ruta\a\Aeromexico Tracker\aeromexico-tracker"
```

Materializa LFS y verifica hashes y derivados antes de restaurar.
`restore_snapshot.py` sobrescribe rutas, incluidas algunas versionadas:
úsalo en un checkout aislado, conserva trabajo ajeno y revisa el estado Git después.
El archivo `LEEME.md` de la carpeta contenedora local describe su organización;
no forma parte del repositorio público.

El warehouse restaurado puede ser anterior a Gold público. Después de verificar
los cuatro Gold privados y restaurarlos en sus destinos ignorados, reconstruye
solo la base local desde Gold vigente:

```bash
uv run --no-sync python -c 'from src.transform.stage6_warehouse import build_warehouse; build_warehouse(max_stage=9)'
```

Este paso no consulta proveedores ni cambia aprobaciones. No reconstruye por sí
solo los originales que falten. Cada actualización del respaldo debe revisar
licencias, credenciales, manifiesto y restauración. Git LFS contabiliza cada
versión nueva de un objeto.

<a id="proveedores-pagados-y-github"></a>

## Datos pagados y licencias

Antes de capturar o reutilizar contenido de un proveedor, revisa los términos
vigentes y el plan contratado. El análisis retenido del 15 de octubre de 2026
sobre [AeroDataBox](https://aerodatabox.com/terms) distingue:

- Respuestas y tablas ligeramente reformateadas, sujetas a retención ordinaria
  de siete días salvo permisos o excepciones aplicables.
- Respaldos, que no conceden por sí mismos una nueva fuente de uso general.
- Derivados con procesamiento no trivial que no permiten reconstruir registros
  individuales; una etiqueta `derived_work_indefinite` no prueba esa condición.

Ese análisis no acredita derechos actuales ni reutilización general tras cancelar.
No publiques originales ni borres históricos automáticamente. La continuidad
sin capturas recurrentes está en [el plan de fuentes](plan-salida-aerodatabox.md).

## Verificar y entregar

La [política de trabajo](../AGENTS.md) define permisos, revisión, integración
y publicación. Los cambios rutinarios solicitados pueden seguir ese flujo;
datos nuevos, aprobaciones, proveedores pagados y accesos requieren su
autorización específica. Una preparación sin encargo funcional termina en
auditoría y PR borrador; no activa integración ni publicación.

Comprueba los disparadores reales antes del push:

| Destino | Efecto que debes comprobar |
|---|---|
| CI pública | PR, push a `master` y `workflow_call` validan los cambios con los checks `test` y `web`. |
| Pages | Un cambio de `site/**`, de `.github/pages-preview.json` o un despacho manual puede publicar. Una vista previa también modifica el contenido servido. |
| Railway | La rama y rutas vigiladas del servicio pueden redesplegar el chat. `checkSuites=false` no espera CI. |
| Respaldo privado | Capturas pagadas por despacho manual y retención periódica tienen sus propios controles; un push documental no es una captura. |

La configuración efectiva vive en los workflows y en
[la operación de Railway](chat/railway.md). Fuentes y periodicidad se declaran
en `config/source_catalog.yaml`; `refresh.yml` verifica frescura y datos,
no reconstruye originales manuales ausentes ni publica `site/`.
Las búsquedas de noticias del chat producen candidatos, no aprobaciones.
No interpretes una periodicidad documentada como prueba de una captura ejecutada.

Distingue cuatro resultados: código preparado, datos validados, aprobación
vigente y versión realmente servida. Un build local no acredita el despliegue.
En pruebas de navegador, declara entorno y si usaste datos reales o sintéticos.
Si el navegador no confía en el proxy, no desactives TLS: verifica los archivos
por hash con un cliente que ya confíe y revisa una copia local.

Si el push falla solo por el ayudante de credenciales de LFS, una sesión
`gh` ya autorizada puede resolver ese comando:

```bash
git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push -u origin <rama>
```

No imprimas credenciales, crees tokens, desactives controles ni guardes una
configuración persistente para resolverlo.

## Antecedentes

La [preparación del entorno](etapas/cloud-readiness-20261013.md) conserva
la evidencia del 13 de octubre. La [verificación inicial del respaldo](https://github.com/salvamalfa/aeromexico-tracker/blob/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/mantenimiento-2026-09/entrega-github-datos-privados-20260919.md)
conserva los resultados del 19 de septiembre. Sus conteos y estados describen
esas ejecuciones, no el estado de una instalación actual.
