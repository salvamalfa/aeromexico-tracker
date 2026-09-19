# Analista v1 · Etapa 16

## Revisión editorial posterior: resumen y ensayo de negocio

La petición más reciente autoriza ampliar el resumen anterior, superando su
restricción de reproducción literal para esta nueva versión. Conservar la versión
original en su expediente. El resumen funciona como TLDR: cada conclusión debe
desarrollarse en el análisis completo, con cifras y explicaciones compatibles.
Para 2T26 se pasa de 187 a 218 palabras (+16.6%) y de cuatro a cinco conclusiones.

El detalle desarrolla la tesis del trimestre para un ejecutivo. Abrir párrafos
con ideas en negritas, explicar conceptos antes de siglas y eliminar comentarios
editoriales como «son miradas distintas» o «no sería correcto describirlos».
Conservar las atribuciones a la compañía y evitar inferencias nuevas. Los métodos,
fórmulas y restricciones técnicas permanecen en el expediente del agente.
`reader_private_section_keys` identifica secciones que conserva el registro
analítico y su auditoría, pero no se incorporan al lector del dashboard.

Presentación: cuerpo de 13 px en el modal, sin encabezado de estado «Análisis
aprobado · cifras del expediente al corte». Cerrar con una nota breve que indique
la ampliación futura con competencia, rutas y noticias, sujeta a revisar cobertura
y disponibilidad temporal. Esos temas todavía no aportan conclusiones al análisis.

## Extensiones de integración de Etapa 18

`context_claim_ids` ubica aclaraciones respaldadas inmediatamente después del
resumen. Sus claims pasan los mismos controles y forman parte de la versión y
de la auditoría. `emphasis` identifica frases literales adicionales para negritas;
se escapa todo HTML antes de aplicar el énfasis.

Los bindings aceptan `presentation: period_label` para etiquetas derivadas del
periodo del cálculo y `cents_short` exclusivamente para unidades
`cents_USD_per_ASK`. Este último conserva el texto literal solicitado y requiere
explicar el denominador en la aclaración visible.

`reported_percentages` permite extraer por Python un porcentaje directamente
reportado: cada alias exige `excerpt_id` y un `span` literal que contenga
exactamente un porcentaje. No se acepta un valor numérico proporcionado por el
modelo. El auditor revisa el periodo, denominador y significado del fragmento.

`literal_user_text` conserva título, viñetas con markdown y SHA-256 del original.
La validación exige coincidencia del texto renderizado y de cada negrita con el
original. Todos estos campos forman parte del hash de la nueva versión.

## Texto literal de 2T26 solicitado posteriormente

El usuario pidió conservar exactamente su redacción para este trimestre. La
propuesta vigente de texto está en `prototypes/etapa-17/propuesta_texto_usuario.html`,
con original y huella en `docs/referencias/etapa-17/literal_user_receipt.json` y
`analysis_runs/editorial_overrides`. Tiene prioridad editorial sobre la reescritura
de negocio anterior. Es una propuesta visual de autoría del usuario pendiente de
revisión; no importar auditorías de versiones anteriores ni conceder aprobación.
No reformular ese texto durante la siguiente etapa sin petición del usuario.

También se prohíben las construcciones retóricas «no es X, es Y» y «es Y, no X»
en toda redacción del agente. Expresar el hecho o límite directamente.

## Pauta editorial acordada en revisión de Etapa 17

Para todos los reportes: lectura de negocio, título directo, resumen en tres a
cinco viñetas con idea principal en negritas. Explicar el concepto antes de RASK,
CASK y otras siglas, que aparecen entre paréntesis. Mantener asiento-kilómetro
ofrecido como denominador; no confundirlo con asiento vendido o simple conteo de
asientos. El detalle también debe ser comprensible sin formación financiera.

Extensión compatible del esquema: `summary_format: business_bullets_v1`. Cada
claim del resumen lleva `lead`, un prefijo literal de `text_template`, sin cifras
ni marcado HTML. Python verifica que sea parte de la afirmación ya respaldada y
lo presenta en negritas; la lista utiliza elementos HTML semánticos. Las versiones
anteriores sin estos campos se siguen leyendo como párrafos. El contrato de consumo
conserva summary_format y summary_items para la futura integración.

En este perfil Python desarrolla «dólares» y «asiento-kilómetro ofrecido» en los
valores de la prosa. Si cambia el código de presentación o la skill, los registros
anteriores se conservan para consultar, pero requieren una versión actualizada y
auditada antes de aprobarse o consumirse; no se cambia silenciosamente su formato.

La preferencia cambia instrucciones y presentación, no autoriza publicación. Una
reescritura genera versión nueva y auditoría nueva; no hereda aprobación anterior.

Estado: implementado para revisión editorial; únicamente `draft`. Sin API propia,
auditor independiente, promoción de estados, Gold ni integración al dashboard.

## Invocación

Desde la raíz de Aeromexico Tracker, usar la skill
`.agents/skills/aeromexico-tracker-analysis/SKILL.md`. El descubrimiento automático
requiere abrir Codex en esta carpeta o una descendiente; desde el workspace padre
se puede pedir explícitamente leer esa skill por su ruta. Ubicación conforme a la
[documentación oficial](https://learn.chatgpt.com/docs/build-skills).

```powershell
.\.venv\Scripts\python.exe -m src.analysis_agent.analyst context --package analysis_runs/evidence/PAQUETE.json --calculations analysis_runs/quantitative/CALCULO.json --output analysis_runs/context.json
.\.venv\Scripts\python.exe -m src.analysis_agent.analyst import-draft --package analysis_runs/evidence/PAQUETE.json --calculations analysis_runs/quantitative/CALCULO.json --input analysis_runs/borrador.json --output prototypes/etapa-16/quarterly_analysis.html
```

Seleccionar los identificadores exactos, no el primer archivo de un glob ni el
trimestre como sustituto de versión. El comando vuelve a verificar originales,
pruebas temporales y cálculo reproducido. Un archivo antiguo con metadatos de
publicación inconsistentes queda rechazado. La preparación no llama al modelo:
Codex redacta con el contexto cerrado exportado y después importa su JSON.

## JSON de autoría

Campos superiores: `schema_version: analyst_v1`, `state: draft`, `language: es-MX`,
`period_id`, `package_id`, `evidence_fingerprint`, `calculation_fingerprint`,
`model` (nullable), `model_unavailable_reason`, `thesis_claim_id`,
`summary_claim_ids`, `claims`, `sections`.

Cada claim contiene `claim_id`, `type`, `text_template`, `bindings`, `evidence_ids`,
`support_calculation_ids`, `support_spans`, `confidence_reason`, `limitations`.
Tipos: observed_fact, accounting_decomposition, company_attribution, hypothesis.
Las secciones son operations, financial, spread, drivers, risks, questions,
methodology; cada una tiene key, title y claim_ids. Resumen: 150–250 palabras;
detalle: 600–1000. En v1 se rechaza una extensión fuera de rango; un trimestre con
evidencia demasiado limitada requiere adaptar justificadamente el contrato antes
de importar, nunca añadir relleno para superar el control.

Referencia numérica de ejemplo (identificadores ilustrativos, no importables):

```json
{
  "text_template": "El margen operativo fue de {{margin}}.",
  "bindings": {
    "margin": {"calculation_id": "calc_ID", "unit": "fraction", "period_id": "2026Q2"}
  }
}
```

Python verifica existencia, disponibilidad, periodo y unidad declarados, inserta
el formato y resuelve los insumos hasta métrica, registro, fragmento y artefacto.
`support_calculation_ids` respalda afirmaciones cualitativas sin forzar cifras en
la prosa. `evidence_ids` referencia excerpts del paquete. Las atribuciones requieren
`support_spans: [{excerpt_id, text}]`, con texto literal contenido en ese excerpt.
Las hipótesis requieren límites explícitos. Los dígitos fuera de referencias se
rechazan en la prosa; los metadatos y fragmentos originales mantienen sus cifras.

La correspondencia semántica no se demuestra por existencia de una cita. Una
referencia válida puede estar mal interpretada, y números escritos en palabras
pueden eludir el filtro de dígitos. Es materia de revisión editorial y auditoría
independiente de Etapa 17, no una garantía atribuida al control mecánico.

## Persistencia y reproducción

`analysis_runs/drafts/PERIODO/VERSION.json` conserva el JSON de autoría, huella
de contenido, versión, fecha UTC real, hash de skill, hash de código de validación
y presentación, y resultado mecánico. Versión = hash de contenido + instrucciones
+ código. Mismo contenido e implementación reutilizan registro; cualquier cambio
genera otro. Escritura completa antes de enlace atómico; originales no se sobrescriben.
No hay todavía números de versión secuenciales, eventos ni aprobaciones: Etapa 17.

El HTML es una copia de revisión regenerable. Solo permite destinos en
`analysis_runs` o `prototypes/etapa-16`; el comando no exporta al dashboard.
Las cifras financieras se presentan en millones USD, porcentajes con un decimal,
centavos por ASK con dos y capacidad/pasajeros escalados por Python. Esta
presentación no aumenta la precisión de la fuente. Los originales, fórmulas e
identificadores permanecen accesibles en evidencia.

El fondo azul identifica el bloque propuesto para consumo y sus modales. La zona
blanca de revisión y los estados de desarrollo no se incorporarán al dashboard.
El HTML no solicita red al abrirse; los documentos enlazados solo se abren a pedido.
