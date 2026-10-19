# Contrato común de actualización por fuente

Estas skills preparan candidatos. Una captura no aprueba datos, tesis, noticias
ni publicación. Leer primero `AGENTS.md`, el catálogo aprobado en
`docs/catalogo-fuentes-calendario.md`, `config/source_catalog.yaml` y la
política ejecutable `src/source_updates/catalog.py`. La guía para Salva está al
principio del catálogo; estas instrucciones son referencia interna.

Los alias de una institución abarcan varias capas. Para capturar, usar
`bronze_source_systems` de `recipe`: empresas SEC requieren `sec`; tráfico
GAP/ASUR admite sus alias aeroportuarios, con `sec_edgar` en la receta; el
adaptador de aerolíneas AFAC requiere `afac`. No intercambiar una etiqueta
Silver por un alias Bronze ni renombrar originales para eludir el control.
Los pasos deben incluir sus predecesores en orden. Un archivo preexistente no
sustituye una validación; una dependencia no disponible bloquea la construcción.

## Procedimiento

1. Confirmar rama, alcance, periodo cerrado y corte con zona explícita. Trabajar
   en `tmp/source-updates/<lote>/`; no restaurar sobre trabajo ajeno.
2. Ejecutar `python -m src.source_updates plan --round monthly --as-of <ISO-con-zona>
   --family <familia>` (para trimestral añadir `--quarter YYYYQn`). El plan
   muestra cobertura y brechas; no descarga ni comprueba frescura Gold.
3. Seleccionar catálogos y documentos con URLs reales del dominio permitido.
   Consultar primero `recipe --product <producto>`: resuelve la entrada canónica,
   formato, procedimiento y limitaciones de `config/source_update_acquisition.json`.
   Para `fuel`, `banxico`, `h10` y `equities`, `recipe --output round --period <periodo>
   --as-of <corte>` emite selección, parámetros y controles listos para probar.
   Para índices HTML admitidos, `recipe --output selection` evita redactar la
   selección a mano; no descarga los documentos descubiertos ni certifica su mes.
   Para descubrir enlaces, usar `purpose=catalog` y `extension=html`;
   la captura guarda los enlaces, pero no sigue ni inventa publicaciones.
   Para nuevas publicaciones seleccionar después `purpose=data`.
   Cada elemento declara producto, alias exacto, entidad, periodo, URL,
   extensión y modo. Ver `config/source_update_round.example.json`.
   Usar `relative_dir` cuando el parser exige una estructura concreta (por
   ejemplo `afac/2026/06`); conservar los nombres lógicos esperados por el parser.
4. Ejecutar `collect --selection <seleccion.json> --workspace <ruta> --dry-run`.
   Revisar llamadas máximas y destinos. Si el alcance de la sesión autoriza
   capturar esa fuente pública, usar `--execute`. Las pruebas públicas reales conservan sus recibos; no generalizar su alcance a fuentes no probadas.
5. Registrar en el recibo periodo solicitado, publicación conocida o nula,
   captura UTC, URL, SHA-256, original y estado. Un catálogo no es un reporte.
   Revalidar URLs seleccionadas aunque existan: el contenido igual se deduplica;
   el cambiado conserva original y revisión. El escritor único usa bloqueo
   exclusivo de sistema de archivos. No ejecutar varios escritores del mismo lote.
6. Construir solo pasos explícitos con `build --workspace <ruta>
   --steps <lista> --dry-run`, después `--execute` si procede. La ejecución
   es otro proceso con red bloqueada y rutas del candidato. Reutiliza parsers y
   contratos existentes. No invocar `just ingest`, `just rebuild` ni
   analítica/modelos completos como sustituto de una actualización acotada.
7. Ejecutar `check --workspace <ruta> --specification <controles.json>`.
   Bronze: verificar hashes. Silver: contrato, grano, dominio, linaje, fuente,
   entidad y periodo realmente presente. Gold: contrato y linaje directo o puente completo validado con `transform.gold_lineage`.
   En aeropuertos, declarar `operator_group=GAP/ASUR/OMA`; para
   `fact_airport_group_traffic`, usar `airport_group_key` con ese valor.
   Un hash agregado exige reconstruir catálogo y puente contra Bronze mediante el gate existente. Las declaraciones sin artefacto no acreditan linaje documental.
   Declarar `value_columns`; conservar N/D, no llenar con cero. Comparar
   contra una copia previa explícita con `baseline_file`, `revision_keys`
   naturales y valores: altas, bajas, cambios y sin cambios. Los cambios de
   archivo no prueban revisiones de cifras.
8. Registrar por producto último disponible, validado y publicado por Tracker
   por separado. Este coordinador nunca infiere el publicado desde Gold.
   Calcular rezago de publicación solo si hay fecha de publicación explícita;
   de lo contrario conservar nulo. La antigüedad del dato no es el rezago
   de publicación. Un periodo presente no garantiza que esté completo:
   comprobar meses esperados, universos, días cubiertos y reconciliaciones.
9. Entregar resultados y bloqueos para revisión. `round --recipe <receta.json>
   --workspace <ruta> --dry-run` reúne captura, construcción y controles;
   con `--execute` se detiene al fallar captura o construcción. Para captura nueva usar explícitamente `--check-at-completion`; conserva el corte pedido y registra el corte efectivo. Sin esa opción el corte histórico rechaza capturas posteriores. Los controles
   solo certifican su alcance explícito, no una ronda completa ni su publicación.

## Fallos y permisos

- 403, TLS, desafío, timeout o archivo inválido = fallo de acceso/contenido.
  Conservar último dato aceptado. No declarar ausencia de reporte ni cero.
- Fecha futura oficial: propuesta a +2 hábiles. Fallo técnico: siguiente hábil.
  Fecha desconocida: un intento dentro de 7 días o siguiente ronda mensual.
  `retry` produce propuestas, no tareas; a las dos reprogramaciones bloquea.
- No nuevas llamadas AeroDataBox, pagos, suscripciones, secretos, credenciales,
  cambios de seguridad ni borrado del histórico retenido.
- SEC se importa manualmente aquí; no leer ni configurar identidad/secretos.
  Aena solo por exportaciones manuales autorizadas, sin login automatizado.
- No aprobar, revocar ni activar tesis Viva, Volaris o Industria. Se requiere la
  aprobación exacta del dueño por entidad, periodo y versión y el gate vigente.
  No simularla a partir del contenido o de pruebas verdes. La disponibilidad
  de tres reportes compatibles permite preparar Industria, no aprobarla.
- No activar noticias candidatas/evidencia, cron, Pages, Railway o auto-merge.
  Separar captura, candidato, aprobación y publicación en cada entrega.
