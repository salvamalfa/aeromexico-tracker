# Instrucciones para Claude y otros agentes de nube

Lee primero [`AGENTS.md`](AGENTS.md) (reglas compartidas con otros agentes,
incluida la autorización permanente para implementar, crear y fusionar PRs,
publicar cambios rutinarios en Pages y verificar el resultado) y
[`docs/cloud-development.md`](docs/cloud-development.md):

@AGENTS.md

Para el árbol, comandos y recetas, usa [`REPO_MAP.md`](REPO_MAP.md). Para el
trabajo abierto, [`ROADMAP.md`](ROADMAP.md); para tareas de varios pasos, la
sesión coordinadora puede delegar paquetes al subagente `implementador`.

Un clon de nube no trae `data/bronze/`, `data/silver/`, el warehouse ni
`analysis_runs/`: son locales e ignorados. La autorización para publicar
cambios rutinarios no sustituye esos insumos ni el gate de `src.publish`;
coordina la ejecución en un entorno autorizado que los tenga. No subas claves
ni respuestas crudas de proveedores. Para evidencias candidatas, aprobaciones
humanas y demás acciones de mayor riesgo, aplica los límites de `AGENTS.md`.
