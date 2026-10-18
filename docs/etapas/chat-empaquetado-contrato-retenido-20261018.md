# Chat: cierre de archivos del runtime · 18 de octubre de 2026

Corte de preparación de la corrección, 22:06 UTC. El PR #138 corrige el
empaquetado necesario para la integración coordinada de Vuelos, Mercado y
Noticias; este informe no acredita un despliegue terminado.

## Problema reproducido

El merge de Vuelos `480d31c` conservó `site/` y el pin de Pages idénticos a
`40a63d1`. Su imagen nueva no pudo cargar ese snapshot: faltaban
`src.publish.manifest`, ahora importado por el lector, y el contrato histórico
exacto de Vuelos. Las comprobaciones de salud devolvieron error por snapshot
no disponible; Railway conservó el backend anterior. Su endpoint productivo
respondió HTTP200 con snapshot `35e86ade…`, sin cambiar el sitio visible.

La primera prueba de archivos admitidos por COPY y `.dockerignore` reprodujo
`Contract hash mismatch or exact version unavailable: flights.schema.json`.
Una materialización aislada del runtime reprodujo también
`ModuleNotFoundError: No module named 'src.publish'`; las pruebas habituales
desde el checkout completo no detectaban esa omisión.

## Corrección y límites

La imagen incorpora solamente `src/publish/__init__.py`, `manifest.py` y
`contracts/web/versions/17fb7e131da94435190bea925fe9733e298754d04e9b9c5e76fbbea8bef119a7/flights.schema.json`.
Los dos módulos usan dependencias ya incluidas. El contrato conserva sus bytes
y su hash, ya admitidos por el resolver estricto. Se añaden negaciones
explícitas para esos archivos y sus directorios; el contexto mantiene deny-all.

No cambian `src/`, contratos, datos, prompts, dependencias bloqueadas,
variables, secretos, protecciones o aprobaciones. No se incluye el gate,
`analysis_runs/`, warehouse ni fuentes privadas en la imagen. Las tres
identidades técnicas aprobadas del sitio conjunto permanecen iguales al
incorporar esta corrección de Docker.

## Validación registrada

- Regresión del contrato: falla antes y pasa después de la inclusión exacta.
- Tres pruebas de contexto pasan (5.77 segundos en el primer cierre completo).
- La prueba nueva materializa los COPY del stage runtime respetando el contexto,
  importa el lector desde ese árbol en otro proceso y carga el snapshot público.
  Comprueba que no hay fallback al checkout, gate ni insumos privados. El
  identificador calculado coincide con el del sitio de origen.
- El smoke de dependencias aisladas de CI continúa separado: estas pruebas
  modelan el contenido de la imagen, no afirman haber ejecutado Docker local.

Antes de integrar se requieren `test`/`web` y Codex del HEAD exacto. Después se
debe observar Railway SUCCESS para el commit integrado y HTTP200 con el mismo
snapshot firmado anterior, antes de continuar a Mercado. La publicación final
de Noticias exige además el cierre de la suite completa del sitio conjunto,
su CI/revisión y la verificación real de Pages y Railway. Los recibos finales
y resultados de integración se conservan en el PR y en el respaldo privado.

No se ejecutaron turnos pagados, capturas, cron ni activaciones de evidencia.
