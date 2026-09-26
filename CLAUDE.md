# Instrucciones para Claude y otros agentes de nube

Lee primero [`AGENTS.md`](AGENTS.md) y
[`docs/cloud-development.md`](docs/cloud-development.md). Son las instrucciones
operativas y de procedencia del proyecto. `AGENTS.md` es la fuente única de
reglas compartidas con otros agentes (incluida la autorización permanente para
suscribirte a tus PRs y fusionarlos); se importa aquí para que Claude Code la
cargue siempre:

@AGENTS.md

Para orientarte en el árbol antes de editar, usa [`REPO_MAP.md`](REPO_MAP.md):
qué vive dónde, comandos y recetas paso a paso para los cambios típicos.

Antes de proponer o editar código, ejecuta `git status --short --branch`, revisa
la historia reciente y abre el reporte de etapa relacionado. Conserva los
cambios existentes y edita generadores en vez de HTML generado.

No asumas que un archivo ignorado existe en un clon de nube. `data/bronze/`,
`data/silver/`, el warehouse, secretos y `analysis_runs/` son locales. Los Gold,
el código, los contratos, los reportes y los prototipos aprobados deben ser
suficientes para inspección y cambios reproducibles dentro de sus límites.

No subas claves ni respuestas crudas de proveedores. No publiques, actives
evidencia o cambies aprobaciones humanas sin una instrucción explícita.

La migración de arquitectura P0–P8 está **cerrada** y no debe retomarse. El
único trabajo abierto vive en la tabla "Remediación de la auditoría" de
[`docs/arquitectura/migracion-estado.md`](docs/arquitectura/migracion-estado.md):
si hay un paquete ahí marcado **pendiente** o **en curso**, continúalo con el
subagente `migrador`. Nunca retomes un paquete marcado **fusionado** o
**completado**.
