# Desarrollo seguro desde GitHub y agentes de nube

Fecha de revisión: 2026-09-19.

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
[`docs/etapas/entrega-github-datos-privados-20260919.md`](etapas/entrega-github-datos-privados-20260919.md).

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
git -c core.longpaths=true clone https://github.com/salvamalfa/aeromexico-tracker-data.git C:\amx-data
git -C C:\amx-data config core.longpaths true
git -C C:\amx-data lfs pull
Set-Location C:\amx-data
python verify_snapshot.py
python restore_snapshot.py --target "C:\ruta\al\Aeromexico Tracker"
```

El repositorio privado excluye `.env`, secretos de Streamlit, cachés, logs,
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

1. Clonar la rama de trabajo o el PR.
2. Instalar Python 3.13, `uv` y Chromium con `just setup`.
3. Crear secretos desde `.env.example`; nunca escribir valores en archivos
   versionados.
4. Ejecutar `just test` antes de editar y anotar cualquier diferencia de línea
   base.
5. Para tareas sin Bronze/Silver, trabajar contra `data/gold/` y declarar esa
   limitación en el PR.
6. Para una ingesta, usar un secreto del proveedor y un destino temporal
   ignorado; correr primero `--dry-run`.
