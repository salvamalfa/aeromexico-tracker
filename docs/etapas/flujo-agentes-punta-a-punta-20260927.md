# Flujo de entrega autónoma para agentes

Fecha: 2026-09-27

## Decisión del dueño

Una petición de cambio en este proyecto autoriza a Codex, Claude y los demás
agentes a llevarla de principio a fin sin volver a pedir permisos rutinarios:
implementar, crear rama y PR, atender CI y revisiones, fusionar y, cuando el
cambio afecta al dashboard público, publicar `site/` en GitHub Pages y
comprobar la página. `AGENTS.md` es la regla operativa compartida; `CLAUDE.md`
la incorpora para Claude.

## Puertas que permanecen

- Usar una rama y PR revisable; nunca push directo a `master`, force-push o
  bypass del ruleset. Abrir en borrador, esperar checks `test` y `web`, atender
  hilos y fusionar con merge commit.
- Generar `site/` con `src.publish` desde un expediente actualmente aprobado;
  verificarlo con `src.publish.verify` y comprobar el deploy de Pages. En una
  corrección solo de interfaz, conservar los hashes de `site/data/v1/` y el
  `analysis_manifest`.
- Pedir autorización específica antes de aprobar análisis nuevos, activar
  evidencia candidata, publicar nuevas cifras que necesitan aprobación humana,
  consumir APIs pagadas, exponer datos privados o secretos, borrar datos de
  manera irreversible o saltar controles.

La autorización es común para agentes locales y de nube. Un clon de nube que
carece del warehouse o del expediente `analysis_runs/` debe conseguir un
entorno autorizado con esos insumos para ejecutar el gate; no puede sustituir
la aprobación con una reconstrucción simulada.

## Archivos actualizados y comprobación

Se armonizaron `AGENTS.md`, `CLAUDE.md`, la guía del subagente implementador,
`README.md`, `REPO_MAP.md` y `src/publish/README.md`. Se revisaron las
restricciones activas de publicación para evitar instrucciones contradictorias.
El cambio es documental: no modifica datos, código del dashboard ni `site/`.
