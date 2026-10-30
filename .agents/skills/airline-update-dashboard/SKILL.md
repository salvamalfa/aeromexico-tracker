---
name: airline-update-dashboard
description: Incorporar un producto validado y una tesis aprobada al dashboard, generar el sitio, integrar y comprobar la publicación servida con recuperación idempotente.
---

# Agente de actualización del dashboard

Leer `AGENTS.md`, `REPO_MAP.md`, `src/publish/README.md`, `web/README.md` y
el recibo del handoff antes de escribir. La unidad es fuente/producto/periodo y
versión real de contenido. Una tesis de una aerolínea no espera a las demás.
Una fuente común actualiza solo sus consumidores afectados. Una revisión cruzada
material necesita evidencia y motivo; no desencadena una reescritura universal.

## Entrada y alcance

1. Recibir `job_id`, `data_version`, entidad, periodo, `release_kind` y recibo físico
   de fuente validada. Para datos basta el paquete técnico validado; no esperar una
   tesis ni pedir un registro de aprobación editorial. Para edición editorial,
   recibir además el registro de análisis aprobado con ruta/hash exactos. Cotejar
   esos identificadores contra el ledger privado del handoff. Un nombre de archivo,
   un directorio Gold o un acuse de subagente no acreditan validación/publicación.
2. Leer el manifiesto servido y el de `site/`, cotejar Git remoto, periodo, entidad,
   versión y hashes. Si la misma salida ya está publicada, registrar el resultado
   observado sin volver a adquirir, analizar, compilar ni publicar. Si hay un envío
   incierto, consultar su PR/deploy/URL original antes de repetir.
3. Verificar autorización vigente y específica para datos y análisis. La autorización
   del 30/oct/2026 cubre Aeroméxico, Viva y Volaris tras validación; no Industria,
   Airline Monthly, `flight_evidence_v1`, cuotas, secretos ni permisos. Conservar
   los límites originales de cada fuente y aprobación.
4. Ejecutar los comprobadores dedicados con el corte congelado del candidato.
   No usar la fecha de hoy para invalidar o rejuvenecer un replay histórico.
   Un periodo o revisión realmente nuevo requiere evidencia propia.

## Datos, tesis y gráficas

Los adaptadores de fuentes producen Bronze/Silver/Gold candidatos y linaje. El
agente de análisis verifica esos insumos y construye evidencia/cálculos congelados,
redacta y pasa auditoría/aprobación. Este agente incorpora únicamente resultados
admisibles: nunca concatena una tabla de observaciones de fuente con
`fact_carrier_metrics`, cuyos grano y unidades son diferentes.

Para Viva y Volaris 3T26, `src.publish.issuer_projection` reproduce el paquete
`issuer_quarter_v1` y proyecta la entidad en `executive.json`: tarjetas, gráficas de
pasajeros con boleto, capacidad, ocupación y economía unitaria usan esa misma serie.
Los datos públicos nuevos nacen en esa proyección verificada, sin cambiar Gold
histórico ni el warehouse. El candidato aislado conserva todo su linaje privado.
Los comparativos anuales del reporte alimentan la nueva vista; no sustituyen puntos
históricos de otra edición. Separar trimestre, acumulado, saldos, servicios regulares
y chárter, pasajeros con boleto y efectivamente transportados. La conversión
milla–kilómetro usa 1,609344 y no inventa un costo/ingreso comparable.

`release_kind=data` ejecuta el tramo de datos y gráficas con auditoría de fuente
y autorización de exposición específicas, sin introducir una tesis ni modificar
el ledger editorial. El paquete técnico se genera/reproduce con
`src.analysis_agent.issuer_quarter prepare` desde el candidato retenido: esa
operación no redacta, audita ni aprueba una tesis. `release_kind=editorial` añade
la lectura exacta aprobada después, conservando los indicadores ya publicados.
Los dos trabajos tienen versiones e intenciones distintas; ninguno espera a
otras aerolíneas. La modalidad combinada se conserva para una entrega cuyo
análisis y datos ya estén listos y aprobados.

Revisar los bloques afectados mediante su grafo de impacto. No reconstruir vuelos,
modelos, noticias, Industria o mercado por una actualización financiera de una sola
entidad. Si cambia una entrada de esas vistas, usar su generador documentado y sus
propios controles; no copiar directorios enteros de candidatos al dataset activo.

El nombre de una fuente no determina una gráfica: `src/dashboard/market.py`
consulta pasajeros AFAC y genera participación, no cotizaciones. Banxico, EIA y
Yahoo no alimentan directamente las gráficas publicadas actuales. Ante una de esas
llegadas, inspeccionar consumidores reales y registrar `no_visual_change` con
evidencia de dependencia y comparación, si no cambió un payload visible. No inventar
una actualización ni crear un panel nuevo para justificar un build. Un futuro
consumidor explícito modifica ese mapa con sus pruebas. Para Aeroméxico 3T26 ya
servido, comparar valores/versiones; una captura nueva con iguales cifras no
justifica otra tesis por estilo ni una recompilación idéntica.

## Generación reproducible

### Aerocivil: movimientos provisionales en Vuelos

El handoff `product=aerocivil`, `period=2026Q3`, `source_period=2026M07` y
`release_kind=movements` va directamente a este agente; no pide una tesis ni
espera un financiero. Su `data_version` conserva el periodo de trabajo y los
hechos nativos de julio. El binding de publicación utiliza `period=2026M07`.
No presentar ese mes como trimestre completo. Los 347 movimientos de las ocho
observaciones originales se mantienen separados de salidas, pasajeros y asientos;
no dividirlos entre dos ni convertir un faltante en cero.

1. Reproducir el candidato dedicado con su propio corte y confirmar la política
   operacional provisional ligada físicamente a sus recibos/filas/hashes. El
   verificador no permite cambiar la confirmación oficial a verdadera ni omitir
   la disponibilidad. Si el cambio de normalizador invalida el fingerprint del
   certificado anterior, conservarlo y certificar offline en otro workspace a
   partir de los mismos originales y metadatos. No renovar captura, copiar el
   Gold mal tipado ni modificar el recibo histórico para eludir ese control.
2. Usar exclusivamente el gate `src.publish.movements_scope`, con proof
   `aerocivil-movements-publication.json`, contra el baseline financiero final
   de siete tesis y su productor liberado. UI-only y flights-only de 2T26 no
   autorizan este cambio de datos. No activar `flight_evidence_v1`.
3. Confirmar en el anchor `product=aerocivil`, `stage=movements`, periodo 3T26 y
   `source_binding` exacto del candidato mensual. El outbox verifica ese gate,
   distinto del financiero; una falla no permite fallback a otro verificador.
4. Retener el recibo `site_built_verified`, seguir la integración y Pages, y
   registrar `served` sólo tras HTTP200 y hashes exactos de las rutas afectadas.
   El escritor sigue reservado hasta esa QA. La recepción del envelope no es
   ejecución: el coordinador registra intención y llama al worker nativo real.

### Generación común

1. Trabajar en rama/worktree aislado desde `origin/master` vigente. Conservar cambios
   ajenos. Registrar intención del handoff antes de efectos externos; un integrador
   serializa cambios de `site/` para evitar que dos aerolíneas se sobrescriban.
2. Guardar y confirmar primero los inputs de compilación (`src/`, `web/`, contratos,
   configuración). El manifiesto identifica ese commit; no publicar código sucio.
3. Para el tramo de datos, ejecutar primero:

   ```bash
   python -m src.publish.issuer_update --inspect-data <paquete-tecnico.json>
   ```

   La salida contiene el `binding` exacto de paquete/fuente, baseline, productor
   y ejecutivo. El auditor independiente lo revisa y retiene el dictamen
   `issuer_data_audit_v1` con `status=passed`, ese `binding`,
   `unresolved_findings=[]` y `reviewer_reference`. La autoridad
   `issuer_data_authorization_v1` conserva `state=authorized`, el mismo `binding`,
   `source_audit_sha256`, el consentimiento auténtico en `owner_consent`
   (`source_reference`, `instruction`, `received_at`) y los límites
   `constraints={theses:false,other_entities:false,industry:false}`. No inventar
   una firma o aprobación; registrar la autorización vigente recibida. Ambos
   JSON se guardan por hash bajo `analysis_runs/dashboard_updates/audits/` y
   `authorizations/`. El dictamen general de la ronda no sustituye esta revisión
   de significado y de la proyección exacta.

   ```bash
   python -m src.publish.issuer_update --prepare-data <paquete.json> --data-authorization <autorizacion-por-hash.json>
   # Revisar y confirmar issuer-release.json. No añadir cohorte ni tesis.
   python -m src.publish.issuer_update --record <cada-registro-anterior> --package <paquete.json> --out site/
   python -m src.publish.issuer_scope site/
   ```

   Se revalida autoridad, auditoría y replay físico antes/después del build.
   Una autoridad revocada o de otra fuente/salida bloquea. El manifiesto editorial
   permanece idéntico. Para una salida ya idéntica, llamar
   `issuer_update.verify_no_visual_change(paquete, source_binding)` y retener
   su resultado verificado; no dar por válida la etiqueta del worker.
4. Para el tramo editorial sobre datos ya servidos, ejecutar
   `python -m src.publish.issuer_update --prepare-record <registro-nuevo-aprobado> --editorial-only`.
   Solo pasa si la proyección financiera es idéntica al sitio anterior. Para
   una entrega combinada ya aprobada, omitir `--editorial-only` y ejecutar
   `python -m src.publish.issuer_update --prepare-record <registro-nuevo-aprobado>`.
   Prepara los dos JSON públicos, sin aprobar ni publicar. Revisar y confirmar el ancla
   `config/publish/issuer-release.json`: baseline Git/manifiesto exactos, identidad
   de análisis, SHA/tamaño de tesis y ejecutivo, huella del productor revisado.
   Añadir el único pin de la nueva cohorte en `approval-cohorts.json`. El pin
   no concede aprobación: el gate reproduce el ledger, fuentes y payloads reales.
5. Invocar el gate editorial/combinado con todos los registros exactos del manifiesto anterior y el
   registro nuevo, sin descubrimiento ambiguo:

   ```bash
   python -m src.publish.issuer_update --record <registro-exacto-anterior> --record <registro-nuevo> --out site/
   python -m src.publish.issuer_scope site/
   ```

   Repetir `--record` para cada registro anterior. El gate verifica el baseline
   con su propio verificador liberado, comprueba Git/Pages/HTTPS, revalida fuentes
   y aprobaciones antes/después del build y sustituye `site/` atómicamente. No
   admitir un baseline que falle su verificador original. Una actualización ya
   presente e idéntica termina sin build. Para una revisión material del mismo
   trimestre, seleccionar explícitamente la versión servida con
   `--replace-version <version-anterior-exacta>` al preparar el registro nuevo.
   El ancla conserva `previous_entry` y `previous_file` completos. La nueva tesis
   debe tener auditoría y aprobación propias; el dato cambiado usa su autoridad
   independiente o una entrega combinada autorizada. En la invocación del gate,
   seleccionar los registros anteriores excepto el slot que se reemplaza, más
   el registro nuevo. El registro anterior debe seguir en su ruta canónica del
   ledger privado: el gate lo reproduce con su implementación y fuente originales
   antes de sustituir el único slot. No revoca ni borra su aprobación. La historia
   de Git conserva su archivo público; un cambio de otra entidad/cohorte, una
   versión anterior incorrecta o una aprobación no vigente bloquean la revisión.
6. El gate ejecuta `npm ci && npm run build`. En modo issuer, el frontend debe
   permanecer idéntico; todos los demás archivos de datos se conservan byte a byte.
   Para una modificación real de interfaz, usar el modo aplicable de `src.publish`
   y revisar el diff; no editar HTML compilado manualmente ni borrar recibos.
7. Para una actualización general que sí requiere fuentes/warehouse completos,
   restaurar solo insumos privados verificados conforme a `docs/cloud-development.md`.
   Tras cambios de Vuelos, ejecutar primero `python -m src.dashboard.build_flights`;
   exportar `python -m src.web_export --out web/public/data/v1 --analysis-manifest <manifest-exacto>`.
   Publicación general: `python -m src.publish --record <cada-registro> --out site/`
   y `python -m src.publish.verify site/`. `--allow-missing-analysis` es solo de
   desarrollo y no publica un expediente incompleto. Nunca usar `--ui-only` para
   introducir datos nuevos.

## Publicar la corrección de movimientos Aerocivil

Para un handoff `release_kind=movements`, usar exclusivamente
`src.publish.movements_update`. Preparar una solicitud privada
`aerocivil_movements_request_v1`: perfil de fuente con ruta/SHA físicos, siete
registros publicados exactos y autorización con ruta/SHA. El perfil reproduce
originales, metadatos y certificación nativa de julio. Mantener `period=2026Q3`
del job y `period=2026M07` del binding; no sustituirlos ni mover la captura.

1. Ejecutar `python -m src.publish.movements_update --inspect <solicitud>` con
   `authorization: null` si falta retener el consentimiento. Revisar la proyección
   y `authority_scope`. Retener únicamente consentimiento auténtico del dueño,
   con ese scope exacto, en la ruta canónica privada por SHA descrita en
   `src/publish/README.md`; completar su referencia en la solicitud.
2. Ejecutar `--prepare <solicitud>`, revisar y confirmar el ancla
   `config/publish/aerocivil-movements-release.json`. No crear eventos de aprobación
   de tesis ni cambiar cohortes históricas. Los pins no autorizan por sí solos.
3. Con código y ancla confirmados, ejecutar
   `python -m src.publish.movements_update --request <solicitud> --out site/`
   y `python -m src.publish.movements_scope site/`. El gate verifica el baseline
   liberado completo, todas las cohortes y el replay físico antes/después del
   build, preserva finanzas y siete tesis y realiza el intercambio atómico.
4. Verificar la red internacional por periodos y entidades afectados: movimientos
   provisionales, fuente/captura, cobertura mensual real, salidas N/D cuando
   corresponda. No dividir movimientos entre dos ni llamarlos vuelos regulares.
   Conservar todas las cifras ajenas al alcance y recursos históricos. Un fallo
   del perfil específico bloquea; no usar UI-only ni otro verificador como salida.
5. Continuar integración y QA servido del siguiente apartado. Un build no acredita
   despliegue; conservar job, data_version, source_binding y hashes exactos para
   cerrar el mismo handoff sin una tesis financiera o un monitor adicional.

## Integración, despliegue y resultado real

1. Validar esquema/privacidad, identidades, hashes, cobertura y diferencias respecto
   al baseline. Revisar en preview local periodo, entidad, título, cifras/citas,
   selectores y todas las gráficas afectadas. Conservar captura/recibo privado.
2. Entregar recibo `site_built_verified` con `job_id`, `data_version`, `entity`,
   `period`, `site_path` y `manifest: {path, sha256}`. Ese estado acredita el build,
   no un despliegue. El ledger usa el verificador explícito del recibo presente;
   un fallo no permite caer al verificador genérico para eludirlo.
3. Después de cada cambio financiero o de datos en `site/`, regenerar la matriz
   documental F2.9 con `python -m scripts.chat.render_f29_coverage_matrix` y ejecutar
   `python -m pytest tests/test_chat_f29_final_campaign_preflight.py -q` antes de CI.
   La matriz incluye bytes de los payloads conversacionales actuales; cambiar una
   tesis o dato puede cambiar esos bytes. Conservar el fixture, Gold y pins
   congelados: regenerar su documentación, sin campañas ni llamadas pagadas.
   Incluir `site/` y la matriz generada en el segundo commit del mismo PR inicialmente draft.
   Completar lifecycle. Esperar `test`/`web` del head final, dictamen Codex favorable
   e hilos resueltos; integrar con merge commit conforme a `AGENTS.md`.
4. Seguir `.github/workflows/pages.yml` hasta que verificación, CI y deploy del
   commit exacto terminen. El workflow despliega `site/` ya construido; no analiza
   ni reconstruye datos. Preservar preview privado/roadmap y permisos existentes.
5. Descargar por HTTPS el manifiesto y payloads afectados del sitio servido,
   comprobar HTTP 200, entidad/periodo/versión y SHA idéntico al build integrado.
   Abrir el dashboard real y revisar las gráficas, selección y citas nuevas.
   Registrar `served_verified` solo después de esta comprobación, con commit/run,
   URL, hashes y hora observada. Un merge, un workflow verde o la ruta local no
   demuestran por sí solos la versión servida.
6. Si falla un tramo, preservar evidencia y último sitio válido. Reanudar desde
   el resultado validado anterior; no repetir adquisición o análisis ya cerrados.
   Un envío incierto mantiene su intención hasta comprobarlo. No crear calendarios,
   monitores, reintentos diarios, aprobaciones ni revisiones históricas para pasarlo.


## Fuentes mensuales independientes

Para `release_kind=source_data`, seguir la receta de
`src/publish/README.md` (Llegadas mensuales). Ejecutar
`src.publish.source_data_update --inspect`, cotejar el alcance exacto y el
consentimiento real de exposición, preparar/confirmar los pins y ejecutar su gate.
No añadir aprobación ni tesis por una llegada operativa. El manifiesto editorial
anterior completo debe conservarse, con verificación de sus cohortes congeladas.

El adaptador AM `am_monthly_projection` reproduce la fuente original y las siete
salidas del candidato con disponibilidad en su corte retenido. Su gráfica usa un
selector explícito entre AFAC y el reporte corporativo no auditado, que incluye
fletamento. Mantener fecha documental, captura y enlace; distinguir total reportado
de suma de componentes redondeados. Los comparativos de la edición no reescriben
AFAC ni otra edición. Un mes aislado no forma trimestre. Las llegadas de aeropuertos
usan el adaptador aeroportuario y sus controles de grano/universo propios.


Las series mensuales corporativas de Viva y Volaris usan
`peer_monthly_projection` y `corporate_peer_monthly_passengers`, separadas de
AFAC y de las cifras financieras trimestrales. Son reservaciones de tramos,
no pasajeros observados transportados. Conservar estado preliminar, captura,
fecha del documento, original y atribución de entidad: el reporte Viva identifica
la marca sin establecer un operador legal. El selector corporativo está disponible
solo para una aerolínea; las comparaciones de varias aerolíneas conservan AFAC.
Septiembre 2025 es el comparativo de la edición septiembre 2026, no una fuente
histórica capturada en 2025. No sumar acumulados ni construir 3T desde ese mes.
