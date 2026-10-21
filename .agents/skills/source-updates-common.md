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
- No aprobar, revocar ni activar nuevas versiones de tesis Viva, Volaris o Industria. Se requiere la
  aprobación exacta del dueño por entidad, periodo y versión y el gate vigente.
  No simularla a partir del contenido o de pruebas verdes. La disponibilidad
  de tres reportes compatibles permite preparar Industria, no aprobarla.
  Conservar las tesis 2T26 de las tres entidades ya aprobadas y publicadas; esta
  restricción no exige desactivarlas ni repetir su aprobación.
- No activar noticias candidatas/evidencia, cron, Pages, Railway o auto-merge.
  Separar captura, candidato, aprobación y publicación en cada entrega.

## Reproducción de una ronda con varios adaptadores

`python -m src.source_updates.readiness --recipe <receta.json> --workspace
tmp/source-updates/<recibo-nuevo> --dry-run` valida todas las tareas antes de
leer sus insumos. La receta declara `required_items` y por tarea `id`, `product`,
`period`, `adapter`, `workspace`, `receipt_id`, `required` y `candidate_as_of`.
`as_of` es el corte de revisión de la ronda; `candidate_as_of` conserva el corte
inmutable de cada candidato histórico y no puede ser posterior al de la ronda.
No se pueden omitir tareas declaradas requeridas, reutilizar workspace ni
intercambiar producto/adaptador.

`--execute` comprueba offline candidatos existentes, verifica que sus archivos
no cambien y escribe un recibo de ronda inmutable; **no captura fuentes**.
`--check` vuelve a comprobar el mismo recibo y sus flags. Soporta `retained`,
`am_traffic_ir`, `h10`, `aerocivil` y `gdelt`; el registro de `retained` incluye
los productos admitidos por sus lectores. Los demás adaptadores se rechazan y
mantienen sus comandos específicos. Curación usa su auditor separado.

Usar en cada replay el `effective_as_of` exacto del recibo aceptado, incluida
su representación de zona. H.10, tráfico Aeroméxico, Aerocivil y los productos
retenidos rechazan un corte distinto o ausente antes de recalcular. Un nuevo
corte necesita una certificación nueva; no sobrescribir el recibo histórico.

Una tarea requerida fallida bloquea la ronda y conserva éxitos previos; las
opcionales pendientes se listan. `ready_for_review` solo acredita las tareas
declaradas y sus reproducciones, no disponibilidad actual, catálogo completo ni
preparación para activar automáticamente. Los productos no ejercitados y las
condiciones de fuente quedan explícitos; todas las activaciones siguen falsas.


## Originales retenidos y lote offline

`python -m src.source_updates.retained` dispone de adaptadores dedicados para
AFAC aeropuertos/países/marginales, ANAC, CAA, Aena, OMA, slots AICM, referencias
IASA/diccionario y cuatro documentos de rutas. La tabla de alcances y los roles
están en el [catálogo canónico](../../docs/catalogo-fuentes-calendario.md#certificación-de-originales-retenidos).
Son candidatos con contratos locales y linaje comprobado; no añaden tablas al
warehouse ni amplían los pasos del `build` genérico.

1. Seleccionar rutas exactas en `_manifest.jsonl` de Bronze. `retain` exige
   producto, roles y alias compatibles, URL pública admitida, bytes con el SHA
   original y sidecar coincidente. No relabelar `afac_research` ni otros alias.
2. Mostrar `retain --dry-run`; después `--execute` si el trabajo autoriza el
   candidato. Copia los originales sin cambiar `downloaded_at`; `retained_at`
   es otra fecha. No hace una captura, no revalida URLs ni comprueba la última
   publicación disponible. Nunca usar AeroDataBox ni fuentes privadas/inactivas.
3. `certify --retention <id> --period <periodo> --as-of <corte>` muestra el plan.
   `--execute` construye Silver/Gold aislados y un recibo inmutable. `--check`
   reconstruye en memoria y contrasta filas, hashes y linaje, sin red/escrituras.
   Los originales, notas de la fuente y roles de soporte se vuelven a verificar.
4. Para revisiones, seleccionar `--baseline baselines/<archivo.parquet>` en el
   comando individual. La comparación usa claves naturales y campos de valor;
   también las marcas y notas de estimación AFAC y todos los campos nativos del diccionario. El
   hash y selección del baseline quedan fijados en el recibo y en cada replay.
   Sin baseline se declara que no se compararon revisiones, aunque cambie SHA.
5. `python -m src.source_updates.retained_round --recipe <receta.json>
   --workspace tmp/source-updates/<lote-nuevo> --dry-run` orquesta el lote.
   `--execute` encadena retención → Bronze → Silver → Gold/linaje → replay por
   producto. Se detiene en el primer fallo y conserva salidas previas y recibo
   con etapa/objetivo/error. No reusa candidatos ni instala tareas. El lote no
   acepta baseline implícito: las comparaciones se preparan individualmente.

La revisión de periodo en snapshots de referencia o programación no convierte
su contenido en tráfico del mes/trimestre. FAA conserva la fecha de su propio
documento; slots conserva toda la temporada; países solo cajas acumuladas
exactas y documentos de rutas solo pasajes fechados. Un formato/edición fuera
del alcance revisado queda bloqueado para adaptar y probar antes de ejecutar.
