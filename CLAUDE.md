# Instrucciones para Claude y otros agentes de nube

Lee primero [`AGENTS.md`](AGENTS.md) y
[`docs/cloud-development.md`](docs/cloud-development.md). Son las instrucciones
operativas y de procedencia del proyecto.

Antes de proponer o editar código, ejecuta `git status --short --branch`, revisa
la historia reciente y abre el reporte de etapa relacionado. Conserva los
cambios existentes y edita generadores en vez de HTML generado.

No asumas que un archivo ignorado existe en un clon de nube. `data/bronze/`,
`data/silver/`, el warehouse, secretos y `analysis_runs/` son locales. Los Gold,
el código, los contratos, los reportes y los prototipos aprobados deben ser
suficientes para inspección y cambios reproducibles dentro de sus límites.

No subas claves ni respuestas crudas de proveedores. No publiques, actives
evidencia o cambies aprobaciones humanas sin una instrucción explícita.
