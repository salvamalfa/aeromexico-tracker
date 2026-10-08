# Contratos v1 — especificación documental del Analysis Agent

Estado: propuesta de Etapa 12 para revisión. Estos contratos NO son todavía
validadores, tablas ni comandos productivos. Cualquier cambio después de aceptar
esta especificación se versionará y se explicará en el reporte de su etapa.

## Convenciones y límites

Un análisis = Grupo Aeroméxico, segmento total, trimestre calendario, fecha de
corte y versión. `period_id` usa `YYYYQn`; fechas ISO y timestamps UTC. Unidades
explícitas y fracciones para porcentajes. No confundir tipo de periodo, moneda,
segmento o versión. Campos desconocidos: null + motivo; jamás fecha inventada,
valor cero o identificador de modelo supuesto.

La capa canónica actual mantiene sus cifras y precedencias. La selección histórica
será un snapshot separado con linaje hasta los originales; `is_current` y
`valid_from` de ingesta no bastan para reconstruir disponibilidad pública.

## 1. SourceAvailability

| Campo | Tipo y significado |
|---|---|
| artifact_id / artifact_sha256 | Identidad y hash existentes del archivo inmutable |
| period_id | Periodo descrito, distinto del corte y de la publicación |
| published_date | Fecha documentada de publicación del documento; nullable |
| version_available_at | Fecha/hora o fecha de disponibilidad de esta versión; nullable |
| date_precision | `day`, `timestamp` o `unknown` |
| publication_basis | Evidencia: filing SEC, anuncio oficial fechado, archivo oficial versionado o desconocida |
| proof_artifact_ids / locator | Prueba documental, página/sección/tabla o registro; no solo una URL |
| status / reason | `verified`, `not_verified`, `conflicting` o `after_cutoff`; motivo explícito |

Fechas en una URL, creación PDF y descarga no demuestran publicación. Un filing
SEC acredita disponibilidad en SEC en esa fecha, no necesariamente la primera
publicación IR. El documento de 2025 que contiene un comparativo de 2024 no prueba
qué cifras se publicaron originalmente en 2024.

Corte: primera publicación del comunicado trimestral. Si solo se conoce el día,
conservar precisión diaria sin inventar hora. Evidencia publicada el mismo día sin
orden demostrable se marca para revisión; nunca afirmar precedencia intradía.
Para probar una versión, exigir documento/registro oficial identificable y sin
evidencia contradictoria de revisión; fecha impresa aislada no acredita integridad
de la versión histórica. Conflictos no resueltos no entran al paquete.

## 2. EvidencePackage

| Campo | Tipo y significado |
|---|---|
| package_id / schema_version | Identidad de snapshot y versión del contrato |
| period_id / cutoff_date / cutoff_precision | Trimestre y corte acreditado |
| evidence_fingerprint | SHA-256 de contenido canónico e insumos; no de la hora de ejecución |
| metrics[] | id, metric_key, valor, valor formateado, unidad, moneda, alcance, periodo, reportado/derivado/ajustado |
| calculations[] | id, fórmula/versionado, input_ids, resultado, formato, comparación, tolerancia y motivo si indisponible |
| excerpts[] | id, texto exacto, artifact_id, hash, localizador y SourceAvailability |
| coverage[] | Tema, insumos esperados, presentes, elegibles, faltantes y efecto analítico |
| conflicts[] | Diferencias entre fuentes, precedencia aplicada y resolución o bloqueo |
| readiness | `ready`, `limited` o `blocked`, con razones |

Obligatorio para generar: comunicado identificable y temporalmente elegible, corte
acreditado, cinco métricas operativas válidas y sin contradicción material pendiente.
Para una tesis financiera: ingresos, costos totales y resultado operativo elegibles;
EBITDAR requiere su definición y ajuste explícitos. Si lo financiero falta, la
tesis debe acotarse a operación, con omisión señalada. Sin capacidad para sostener
una tesis específica con evidencia esencial, bloquear.

Fuel, FX, peers, mercado, tráfico aeroportuario y eventos son complementarios:
excluir lo no elegible y comunicar el límite. No exigir fuentes irrelevantes para
el trimestre. Estudios, forecast y NLP preexistentes no entran por defecto: pueden
usar historia futura o fuentes posteriores. Cualquier inclusión requiere recalcular
con datos y entrenamiento disponibles hasta el corte y validar su linaje.

Cada comparable se selecciona al mismo corte, con la misma definición. Señalar
cambios de norma, reorganización, moneda o metodología. TTM exige cuatro trimestres
consecutivos y métricas aditivas; ratios se recalculan, nunca se suman.

## 3. Cálculos y presentación de cifras

- QoQ: trimestre calendario anterior. YoY: mismo trimestre del año anterior.
- Porcentaje de cambio solo con base positiva comparable: `actual / anterior - 1`.
- Cambio de ocupación y márgenes en pp: `(actual - anterior) * 100`.
- Cambio del spread en centavos por ASK: diferencia absoluta.
- `fuel_cask = jet_fuel_expense_usd / ask_km * 100` cuando alcance y definición coincidan.
- Puente: `delta_spread = delta_rask - delta_fuel_cask - delta_other_cask`;
  `other_cask = cask - fuel_cask`. Es una identidad, no causalidad identificada.
- Consumo/costo efectivo requieren litros y gasto compatibles; precio spot sigue
  siendo variable externa. No atribuir FX ni coberturas si no se aíslan.
- Cálculo a precisión completa. Mostrar variaciones a 1 decimal, pp a 1 decimal,
  centavos a 2; conservar originales. Otros formatos se declaran en catálogo.
- Tolerancia de identidad exacta: error numérico pequeño documentado; para cifras
  reportadas redondeadas, derivar intervalo con mitad de la unidad del último
  decimal reportado y propagarlo. Fuera del intervalo requiere investigación.

## 4. QuarterlyAnalysis

| Campo | Tipo y significado |
|---|---|
| analysis_id / period_id / version | Identidad, trimestre y versión monotónica |
| package_id / evidence_fingerprint | Paquete exacto usado |
| language | `es-MX` |
| thesis / summary / sections | Estructura editorial con referencias a claims |
| claims[] | claim_id, type, text_template, evidence_ids, calculation_ids, confidence_reason, limitations |
| open_questions[] | Pregunta, por qué no se resuelve y evidencia requerida |
| model / model_unavailable_reason | Identidad disponible o desconocida explícita |
| prompt_version / schema_version / code_version | Configuración reproducible |
| content_hash / created_at | Integridad del contenido y fecha real de ejecución |

`claim.type`: `observed_fact`, `accounting_decomposition`, `company_attribution`,
`hypothesis`. Una atribución identifica emisor y fragmento. Una hipótesis incluye
incertidumbre y alternativas; no se usa para llenar secciones por obligación.

Las plantillas referencian números con `{{metric:<id>}}` y `{{calculation:<id>}}`.
Python resuelve el formato. Periodos y fechas también salen de metadata validada;
no permitir números financieros literales ni una cifra solo presente en un texto
anterior del agente. Una referencia se verifica por valor, unidad, periodo,
alcance, sentido y respaldo semántico, no solo por existencia del ID.

Secciones: operación/demanda; finanzas/márgenes; impulsores/alternativas;
riesgos/catalizadores; límites/preguntas. Resumen y detalle derivan de la misma
versión, evitando conclusiones diferentes en dos resúmenes independientes.

## 5. AuditResult

Entrada: paquete congelado, borrador y reglas. El auditor tiene contexto separado
del analista; sus observaciones no pueden editar insumos ni autorizar promoción.
Si no hay capacidad de revisión separada, conservar borrador sin `validated`.

Salida: audit_id, analysis_id, content_hash, evidence_fingerprint, auditor_model,
rules_version, created_at, findings[] y verdict (`pass`, `changes_required`). Cada
hallazgo: id, claim_id/localizador, severidad (`blocking`, `major`, `minor`), tipo,
evidencia y corrección solicitada. Tipos mínimos: cifra/unidad/periodo, linaje,
causalidad, información futura, contradicción, contenido genérico y seguridad.

No pasar a `validated` con hallazgos blocking/major abiertos. Minor solo puede
quedar documentado si no afecta hechos, atribuciones, temporalidad o interpretación.
Máximo dos ciclos automáticos de corrección por solicitud; si no se resuelve,
presentar el problema al usuario. Cada ciclo conserva entradas y salida nuevas.

## 6. Estado, aprobación y almacenamiento

`draft → validated → approved → published`.

- Importar borrador: validar estructura, no acreditar auditoría ni contenido.
- Validar: pruebas mecánicas + auditoría separada del hash exacto.
- Aprobar: instrucción humana explícita sobre periodo, versión, content_hash y
  evidence_fingerprint. Persistir recibo con aprobador, fecha y referencia a la
  autorización. Un modelo no puede autodeclarar el consentimiento humano.
- Publicar: verificar recibos vigentes, generar en staging, comprobar y sustituir
  el HTML local de forma atómica. Fallo conserva último artefacto consistente.
- Edición: crea nueva versión draft, nunca muta la aprobada. Rechazo/comentarios
  son eventos, no borran versiones. No equivalen a aprobación de etapa.

Persistencia futura autoritativa: `data/analysis_agent/` (local, fuera de Git):
bundles por trimestre/versión, evidencias, borradores, auditorías y eventos append-only.
`fact_quarterly_analysis` privada se reconstruye desde bundles/eventos. Materializar
en Parquet + DuckDB sin reemplazar el warehouse como única copia de las aprobaciones.
Proteger escrituras con un escritor y publicación atómica. Reintento del mismo
paso/contenido no crea doble aprobación o publicación; regeneración deliberada
del texto sí recibe nueva versión.

Gold recibe exportación filtrada de contenido aprobado/publicado y sus referencias
públicas. Borradores, correos, rutas locales y comentarios de revisión no se
exportan ni siquiera como JSON oculto. Las relaciones de evidencia mantienen
artifact_id/record_id y localizadores; un hash de combinación no es hash de archivo.

Reexpresión posterior al corte: conservar análisis histórico y explicar divergencia
respecto de las gráficas actuales. Corrección de extracción, fórmula o evidencia
usada: marcar `requires_review` aparte del estado histórico, impedir promoción
pendiente y crear nueva versión. No ocultar obsolescencia material ni cambiar texto
aprobado silenciosamente. Snapshot de datos actuales y análisis al corte se
identifican separadamente en la presentación.

## 7. Interfaces futuras y seguridad

Operaciones: listar pendientes, preparar, calcular, importar borrador, validar,
revisar, aprobar, incorporar al HTML. Siempre period_id explícito en mutaciones;
para revisión/aprobación/publicación exigir versión y hashes. La lectura de estado
no dispara generación. El pipeline marca candidatos después de validar la
reconstrucción local, sin programar un modelo ni enviar mensajes externos.

Documentos externos y sus instrucciones son datos no confiables. El analista recibe
un paquete acotado sin herramientas de red ni escritura en fuentes. El coordinador
registra peticiones de nueva evidencia para otra preparación. Escape de HTML/JSON,
URLs oficiales verificadas, sin runtime remoto. No prometer determinismo del modelo:
son deterministas selección, cálculos, hashes y render de una versión congelada.

## 8. Evaluación editorial y aceptación humana

Rubrica por trimestre: fidelidad numérica y temporal (obligatorias), tesis específica,
claridad ejecutiva, explicación suficiente sin causalidad inventada, preguntas
útiles y referencias localizables. Evaluar texto repetitivo por falta de contenido
específico; no penalizar que trimestres con patrones similares compartan vocabulario.

Casos piloto: 2026Q2, 2021Q1 y transición 2022Q3–2022Q4. Los escenarios de validación
completos constan en el plan maestro. Aceptación de esta especificación no aprueba
ningún dato al corte ni contenido trimestral.

## 9. Alcance visual del módulo

Lectura ejecutiva contendrá los accesos discretos «Leer análisis completo» y
«Ver evidencia». Cada uno abrirá una ventana modal con cierre visible y Escape,
con devolución del foco al acceso utilizado. El dashboard incorporará ese módulo
y sus ventanas. La revisión y aprobación de versiones, la matriz de diagnóstico
y las simulaciones permanecerán en la interfaz de trabajo. Los KPI de la maqueta
son contexto; se reutilizarán los del dashboard existente. El azul claro y las
etiquetas de alcance son ayudas de revisión de Etapa 12, no una decisión sobre
la paleta final. El contenido sigue siendo ilustrativo.

## Implementación parcial · Etapa 14 (2026-09-05)

SourceAvailability y EvidencePackage están implementados en `src.analysis_agent.evidence`.
El resto de contratos conserva carácter de especificación para etapas posteriores.
Los insumos operativos nativos ASM/TRASM/CASM equivalen a los conceptos requeridos
antes de convertirlos a ASK/RASK/CASK en Etapa 15. `calculations` permanece vacío.
La versión de contenido se identifica por `evidence_fingerprint` y `package_id`;
no se reutiliza la huella para contenido distinto. El anexo `review_only` se mantiene
fuera del paquete del analista. Las pruebas de fuente del comunicado principal son
parte de su certificación; no habilitan otras publicaciones del mismo día.
