---
name: airline-update-coordinator
description: "Preparar rondas mensuales y trimestrales de Airline Tracker, agrupar fechas y ejecutar recetas candidatas con escritor único, sin activar horarios ni publicar."
---

# Coordinador mensual y trimestral

Aplicar [el contrato común](../source-updates-common.md). Leer la guía para Salva
y su apéndice en `docs/catalogo-fuentes-calendario.md`.

1. Cargar calendario bancario verificado, zona America/Mexico_City y corte con
   zona explícita. UTC se conserva para captura; los días se calculan en México.
   Año sin calendario verificado bloquea. No asumir solo lunes–viernes.
2. Calcular mensual en o después del 15. La incorporación de noticias va con
   esa ronda, sin refresh de datos diario/semanal. Avisar un reporte financiero
   confirmado es independiente: no esperar la ronda ni aprobar su contenido.
   Trimestral: dos hábiles estrictamente posteriores
   al último reporte financiero central confirmado, publicado y del trimestre
   solicitado, de Aeroméxico, Volaris y Viva. Anuncio o llamada no basta.
3. Si faltan reportes, dejar fecha trimestral nula y listar entidades disponibles
   para preparar paquetes independientes. No bloquearlas por complementarias
   atrasadas. Industria espera tres insumos compatibles y aprobación exacta.
4. Agrupar mensual/trimestral a <=7 días naturales, en la fecha posterior.
   Emparejar a la mensual más cercana; sin cadenas que difieran >7 días.
   Si esa espera afecta una entrega material, resolver el alcance con el dueño.
5. Ejecutar `plan` por familia y selección real de documentos. Unir una receta
   explícita de adquisición, pasos offline y controles por fuente/entidad/periodo.
   Ejecutar `round --recipe ... --workspace ... --dry-run`; ejecutar candidato
   solo con alcance autorizado. Para captura nueva añadir `--check-at-completion`; sin ello se conserva el corte histórico. Un escritor por lote, sin escrituras activas.
6. Inspeccionar recibos, faltantes, hashes, cambios de filas y cobertura; el
   coordinador no inventa periodos ni mide disponibilidad desde nombres Gold.
   Incluir todos los predecesores de pipeline en orden. Una transformación no
   puede omitir la validación Silver. BMV y el compuesto offline están habilitados en candidatos. Añadir `transform.gold_lineage` después de `transform.validate_stage6` para reconstruir catálogo y puente. Si faltan otros insumos, dejar el producto pendiente; no simular validación con archivos.
7. Proponer reintentos con `retry`, máximo dos reprogramaciones por lote.
   Ningún comando instala tareas, cron o automatizaciones. Mantener cuenta de
   reprogramaciones en el expediente del lote; no reiniciarla para eludir límite.
8. Entregar resumen y pendientes en español claro. Adjuntar evidencia técnica.
   Aprobación de calendario no aprueba contenido ni concede activación.

Antes de adquirir, `round` valida receta, pasos y dependencias, productos y
controles; no debe generar red ni Bronze para descubrir un error estático.
La fecha de un reporte central debe ser posterior al cierre del trimestre y
no posterior al corte. Una URL HTTPS válida es un control sintáctico: el campo
`confirmed` requiere que el responsable haya comprobado el documento real.

Para verificar una ronda con candidatos heterogéneos ya construidos, usar
`python -m src.source_updates.readiness --recipe <receta.json> --workspace
tmp/source-updates/<recibo> --dry-run`, después `--execute` y `--check` según
el [contrato común](../source-updates-common.md#reproducción-de-una-ronda-con-varios-adaptadores).
Declarar cada tarea requerida y conservar el corte original de su candidato.
Es reproducción offline; no sustituye `collect`, no acredita disponibilidad
de fuente desde Gold y no instala el calendario.

```bash
python -m src.source_updates calendar --start 2026-10 --months 3 --quarter 2026Q3 --as-of 2026-10-18T12:00:00-06:00
python -m src.source_updates plan --round combined --quarter 2026Q3 --as-of 2026-10-18T12:00:00-06:00
python -m src.source_updates round --recipe config/source_update_round.example.json --workspace tmp/source-updates/prueba --dry-run
```

`plan --round combined` conserva el objetivo mensual y el trimestral de cada
producto con ambas cadencias. Devuelve una fila por producto y periodo, con
`plan_item_id` único; `id` sigue identificando el producto. Conservar ambas filas:
deduplicar solo por `id` perdería trabajo trimestral. El plan no agenda ni ejecuta.


Para un lote explícito de originales ya retenidos, aplicar
`python -m src.source_updates.retained_round --recipe <receta.json>
--workspace tmp/source-updates/<lote> --dry-run` y el
[contrato común](../source-updates-common.md#originales-retenidos-y-lote-offline).
El modo `--execute` certifica y reproduce por producto, deteniéndose ante el
primer fallo. No sustituye colección de fuente ni comprueba última disponibilidad;
no llama a red, no programa este calendario y no activa datos/tesis/noticias.

Para aceptación global usar `python -m src.source_updates.global_readiness`
con `config/source_update_global.example.json` primero en `--dry-run`. Aplicar
la política aprobada de la guía: R por cadencia/periodo, C/O cuando se utilizan,
dependencias transitivas y Aerocivil como prerrequisito trimestral. Desde el
29/oct, la tarea editorial sustituye el proveedor obligatorio GDELT; RSS y
GDELT son descubrimiento opcional, con sus fallos intactos.
La receta vacía enumera faltantes; no es una ronda lista. No aportar resultados
sintéticos ni reducir checks para certificar un producto entero. Adaptadores sin
certificación completa se mantienen bloqueados (`unsupported`). Disponibilidad
desconocida sigue bloqueando incorporación, aunque pase un replay técnico.
`--execute` escribe solo el recibo inmutable; `--check` repite offline y rechaza
cambios de código, contratos, catálogo, festivos o candidatos. Conservar periodo
nativo/rezago explícito y vínculo físico de releases; nunca activar disparadores.


Para `banxico`, `fuel` y `equities`, el recibo integral mensual/trimestral se
produce con `series_candidate` (o `retained_round`, que lo selecciona por producto)
y se enlaza mediante `adapter=series`, no mediante
checks parciales ni `retained`. Aplicar el [contrato de series](../../../docs/catalogo-fuentes-calendario.md#certificación-de-series-retenidas-22-de-octubre).
Una reproducción de originales no comprueba disponibilidad actual ni calendario
completo de observaciones; mantener esas puertas bloqueadas y los demás R
pendientes. No omitir Aerocivil ni la tarea editorial requerida. La nueva política no
convierte una respuesta GDELT inválida en válida.

Registrar por separado reporte detectado, fuente primaria comprobada, usuario
avisado, datos incorporados y publicación/tesis autorizadas. No inferir un
estado desde otro ni repetir como novedad un reporte ya avisado. El mecanismo
de avisos existente tiene su propio responsable; este CLI no crea tareas.

## Un calendario con estados por tarea

`plan` incluye `calendar_count=1` y `calendar_tasks` con Noticias editorial y
los productos del mes/trimestre. Las vistas por familia filtran ese mismo plan.
`global_readiness` verifica todos los candidatos independientes aunque otro
falle; conserva `checks_passed` de cada tarea y muestra faltantes, incluida la
tarea editorial, en la misma lista. `data_tasks_ready` no significa que la ronda
esté completa: `core_ready` y `ready_for_calendar_incorporation` requieren todos
sus componentes y dependencias. No publicar ni activar automáticamente por esos flags.

Ejecutar la [skill de Noticias](../airline-update-news/SKILL.md#flujo-editorial-del-calendario)
para el mes declarado en la receta y añadir su binding `editorial_news` al
recibo global. Leer realmente web/editor y registrar observaciones antes del
candidato; el replay no es una búsqueda. En un trimestre separado la tarea
mensual figura `not_due_this_round`, salvo selección explícita. No crear otro
calendario, otra frecuencia o una aprobación implícita de contenido.

## Día oficial y números pendientes

Un reporte confirmado puede declarar `publication_precision="day"`,
`published_on="YYYY-MM-DD"` y `published_at=null`; nunca rellenar medianoche.
La alternativa existente con timestamp conserva su zona y conversión a México.
Sumar los dos hábiles estrictamente después del último día de reporte.

En la receta global, `documentary_evidence` vincula el original físico y tres
pasajes revisados —emisor, trimestre y día— mediante el lector documental
existente. Conserva SHA, manifiesto, sidecar y captura anterior al corte. La
interpretación de esos pasajes es una revisión explícita; ubicarlos no es una
aprobación automática. Puede proponer fecha aunque las cifras sigan pendientes,
pero no concede `core_ready` ni permite publicar o instalar disparadores. La
guía canónica documenta campos y evidencia real. Si faltan reportes, conservar
fecha nula; si falta el calendario bancario de un año, mantener el bloqueo.

Los componentes se aplican a su cadencia: tarea editorial a mensual, Aerocivil
a trimestral y ambos a combinada. Una ronda mensual completa no exige el
prerrequisito exclusivo trimestral. Todo producto realmente utilizado y sus
dependencias transitivas siguen verificándose, incluso si son de otra cadencia;
no se omiten por esa separación. Las pruebas de política con resultados
sintéticos no acreditan disponibilidad de una fuente real.
