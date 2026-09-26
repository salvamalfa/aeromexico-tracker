# Instrucciones para Claude y otros agentes de nube

Lee primero [`AGENTS.md`](AGENTS.md) (reglas compartidas con otros agentes,
incluida la autorización permanente para PRs) y
[`docs/cloud-development.md`](docs/cloud-development.md):

@AGENTS.md

Para el árbol, comandos y recetas, usa [`REPO_MAP.md`](REPO_MAP.md). Para el
trabajo abierto, [`ROADMAP.md`](ROADMAP.md); para tareas de varios pasos, la
sesión coordinadora delega cada paquete al subagente `implementador`.

Un clon de nube no trae `data/bronze/`, `data/silver/`, el warehouse ni
`analysis_runs/`: son locales e ignorados. No subas claves ni respuestas
crudas de proveedores; no publiques `site/`, actives evidencia ni cambies
aprobaciones humanas sin instrucción explícita del dueño.
