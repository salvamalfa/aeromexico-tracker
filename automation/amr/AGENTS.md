# Instrucciones de AMR

Lee `README.md` antes de trabajar en esta carpeta. Es código de referencia
versionado; las skills instaladas y las automatizaciones existentes conservan
la autoridad de ejecución. No instales ni actives estas copias automáticamente.

Mantén las tres skills como hermanas bajo `skills/`. Conserva scripts y esquemas
coherentes. Antes de entregar ejecuta el verificador de integridad y los dos
self-tests descritos en el README. Un cambio intencional de fuente requiere
revisar y actualizar su entrada de `source-manifest.json` con la procedencia real;
no alteres las huellas para esconder una divergencia.

No incluyas resultados de los libros, exports, identificadores privados,
credenciales, launchers, estado de corridas ni historia Git privada en un PR
público. `config/local.json` es una referencia local ignorada; no es un launcher.
La organización de archivos no autoriza cambiar horarios, frecuencia, capturas,
almacenamiento o supervisión, ni ejecutar búsquedas o ingestas.
