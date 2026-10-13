# Continuidad de Airline Tracker sin capturas AeroDataBox recurrentes

Revisión: 13 de octubre de 2026. **Propuesta de alcance y migración; no aplicada
al dashboard, datos, suscripción ni workflows.** Complementa el
[catálogo y calendario de fase 1](catalogo-fuentes-calendario.md).
Los detalles de cuenta, saldo y eventual autorización de compra permanecen en
el expediente privado; no se trasladan a este repositorio público.

## Alcance recomendado

Mantener pasajeros mensuales/trimestrales reportados por aerolínea y mezcla
nacional/internacional de AFAC/IR/SEC, además de finanzas, ASK/ASM, RPK/RPM,
ocupación y flota reportadas. Retirar de la vista activa los pasajeros estimados
por ruta×aerolínea y los vuelos, asientos y ocupación dependientes de AeroDataBox.
Para ese alcance no hace falta contratar un proveedor sustituto.

La vista principal de rutas puede centrarse en **México–Estados Unidos · datos
observados**, con BTS T-100: pasajeros, salidas realizadas, asientos y
capacidad/tráfico por operador/reportante. Ocupación es un cociente calculado
de medidas observadas. El dato no representa la red mundial, comercializadores,
destino final del boleto o rentabilidad.

Conservar evidencia adicional por fuente en una capa separada si ayuda:
Brasil ANAC aporta pasajeros pagados/asientos/despegues; los adaptadores
Colombia Aerocivil y Reino Unido CAA aportan vuelos. Aena mantiene dos granos
distintos (aerolínea×aeropuerto y par de aeropuertos), no la celda conjunta.
Slots AICM y anuncios OMA son programación/presencia. Sus métricas ausentes
deben quedar N/D; no enriquecerse con una semilla histórica.

Un mapa nacional de mercado con totales AFAC por ruta y **todas las aerolíneas**
es una opción posterior, sin atribución por compañía. AFAC publica marginales
de ruta y empresa, no su cruce; no se puede repartir el agregado entre
operadores como si se observara. La lista de destinos puede ser presencia
documentada, sin prometer volumen ni vuelos exactos universales.

## Periodos reales y significado de la semilla

Los históricos documentados tienen semillas nacionales marzo–agosto de 2026 e
internacionales abril–agosto; **no septiembre**. Agosto fue capturado el
25 de septiembre: periodo de operación y fecha de captura son distintos.
Los pasajeros ajustados llegan a julio y la capacidad a agosto. La captura
de agosto quedó esperando marginales AFAC en aquel momento; ese motivo histórico
no prueba la disponibilidad actual y no obliga a continuar el ajuste IPF.

La [captura de agosto](etapas/aerodatabox-agosto-captura-20260925.md) y el
[método canónico](estimacion-pasajeros-ruta-aerolinea.md) conservan la historia.
La [guía vigente de Vuelos](etapas/vuelos-pasajeros-traspaso-20260913.md)
describe lo que efectivamente se muestra hoy; encabezados históricos de algunos
documentos anteriores aún dicen pendiente de integración y no deben sustituir
la comprobación del `site/` actual.

AeroDataBox aporta oferta y estructura operacional; **no publica pasajeros**.
Los pesos de una muestra mensual se expanden y ajustan a AFAC. La reconciliación
exacta de marginales no convierte esas celdas en observaciones.

## Impactos de datos e interfaz

| Salida actual | Dependencia | Tratamiento propuesto |
|---|---|---|
| Tarjetas por grupo, pasajeros mensuales/trimestrales, mezcla y finanzas | AFAC/IR/SEC/BMV | Conservar; actualizar por las rondas propuestas y definiciones reportadas |
| Pasajeros estimados por ruta nacional/internacional | IPF sobre AFAC + semilla | Retirar de vista activa y chat; no proyectar semilla sobre nuevos meses |
| Vuelos nacionales estimados | Muestreo AeroDataBox + ponderación temporal | Retirar o conservar únicamente como histórico estimado separado, nunca como realizados exhaustivos |
| Asientos/ocupación Aeroméxico/Connect | Frecuencias AeroDataBox + modelos/configuración + IPF | Retirar en rutas afectadas; el inventario de flota por sí solo no reemplaza vuelos |
| Asientos/ocupación Volaris/Viva/Industria fuera de BTS | Frecuencias AeroDataBox + promedio de asientos por salida BTS de doce meses | También retirar: usar un promedio BTS no elimina la dependencia de la semilla |
| Rutas MX-US | T-100 del operador/reportante | Conservar pasajeros, salidas realizadas, asientos, ASM/RPM, ocupación calculada y comparación con mismos meses |
| ANAC Brasil | Medidas observadas acotadas | Conservar fuente/definición y periodo propio; no sumar automáticamente a una red global comparable |
| Aerocivil / CAA | Vuelos observados enriquecidos después con IPF | Conservar los vuelos originales; quitar pasajeros/asientos/ocupación estimados |
| AICM / OMA / presencia AIFA | Programación/presencia enriquecida con IPF | Conservar solo evidencia propia en capa explícita; no sumar programación y realizado |

**La retirada debe ser por métrica y procedencia.** Filtrar únicamente rutas
etiquetadas AeroDataBox dejaría estimaciones añadidas a otras fuentes. En el
payload público Aeroméxico 2T26, 23 rutas AICM, cuatro Aerocivil, una CAA y dos
OMA llevan enriquecimiento IPF, además de cuatro rutas exclusivamente estimadas.
No borrar vuelos observados CAA/Aerocivil al quitar ese enriquecimiento.

En el artefacto 2T26 vigente permanecen 40 rutas BTS de Aeroméxico, 69 Volaris,
38 Viva y 120 Industria. **Su cobertura BTS local es abril–mayo; falta junio**.
No prometer trimestre completo a partir de esos conteos; comprobar el ZIP más
reciente antes de actualizar. El mapa doméstico de Aeroméxico julio tiene
55 rutas, todas estimadas: después de retirar IPF no queda un mapa de volumen
propio nacional equivalente. Los totales de aerolínea sí permanecen.

## Dependencias de implementación a revisar después

- `src/dashboard/{domestic_routes,international_routes,entity_routes}.py`:
  selección, enriquecimiento, totales y comparativos de red.
- `route_capacity.py`, `route_entities.py`, `src/analytics/fleet_capacity.py`:
  frecuencias estimadas, asientos promedio, agrupación Aerovías/Connect.
- `flights.py` / `flights_html.py`, contratos y `web/src/views/flights/`:
  mapas/tablas/leyendas, estados vacíos y campos que llegan al frontend.
- `config/web_inputs.yaml`: hoy exige cuatro Gold privados de estimación para
  exportar Vuelos. Borrarlos primero bloquearía la publicación; cambiar la
  frontera de insumos cuando el nuevo alcance esté implementado y validado.
- `src/web_export/`, `src/publish/` y herramientas de rutas del chat:
  retirar campos estimados también del snapshot consultado por Railway,
  referencias, sumas, filtros y variaciones. No basta ocultar una columna.
- `src/analysis_agent/flight_evidence.py`: conservar su condición candidata,
  sin activación/backfill ni modificación de aprobaciones de tesis.

## Uso eventual de una captura acotada: valor antes que volumen

Un corte histórico de septiembre de 2026 puede aportar oferta y cobertura de
estado/codeshare en aeropuertos seleccionados, si se define antes su producto
y derecho de conservación. No requiere reanudar estimaciones de pasajeros.
Evitar recomprar marzo–agosto conservados, horarios futuros o octubre incompleto.
El remanente de una cuota no obliga a consumirla.

El endpoint vigente de aeropuerto cuesta dos unidades por ventana de doce
horas. Septiembre completo son 120 unidades/aeropuerto; siete días son 28.
**MEX/GDL/MTY completos: 360 unidades; seis aeropuertos del núcleo: 720**.
Filtrar Aeroméxico después de recibir datos no reduce solicitudes ni coste.
Mantener diagnóstico de estatus: un registro del feed no certifica por sí solo
un vuelo realizado. Un conteo de días muestreados es observado en esos días;
su expansión mensual sigue siendo estimación.

La unión de 58 aeropuertos nacionales contiene los seis del núcleo y los
31 secundarios internacionales. Una captura `Both` compartida de seis
completos + 52 con siete días costaría 2.176 unidades, frente a 3.212 del diseño
separado. **Es una optimización propuesta, no implementada**: el normalizador
internacional descarta domésticos y la CLI doméstica puede lanzar IPF.
Primero revisar derivación offline compatible y deduplicación entre extremos,
sin comprar ni despachar comandos esperando reutilización automática.

## Históricos y licencia

Conservar los derivados privados y su linaje para trazabilidad; no borrar
históricos ni ampliar su exposición durante esta fase. Los [términos actuales](https://aerodatabox.com/terms)
distinguen contenido crudo/extractos de derivados no reconstruibles; una
agregación mensual no basta por sí sola. La práctica del repositorio es
retención cruda de siete días y derivados privados. El [anuncio de septiembre](https://aerodatabox.com/2026-09-terms-update)
incluye transiciones para suscripciones existentes: comprobar las condiciones
efectivas del plan antes de cualquier compra, retención o redistribución.
No acumular contenido especulativamente ni tratar una cancelación como permiso
de publicar respuestas. El expediente contractual permanece privado.

## Migración propuesta y aceptación

1. Acordar alcance de UI/datos y separar hecho observado, dato reportado,
   programación e histórico estimado; conservar los archivos originales.
2. Retirar dependencia activa de semilla/IPF y campos enriquecidos por
   procedencia, sin borrar las medidas oficiales. Adaptar el requisito de cuatro
   Gold privados al alcance nuevo, no ocultar ausencias con ceros.
3. Comparar antes/después los agregados AFAC/IR y métricas BTS/autoridades que
   permanecen; comprobar meses/comparativos. Modelos y forecasts conservan corte
   y no se reentrenan por esta migración automáticamente.
4. Verificar las cuatro entidades, mapa/tabla/chat, estados vacíos,
   desktop/móvil y selección rápida; actualizar regresiones justificadas.
5. Preparar PR y artefacto mediante el gate, con auditoría y autorización de
   publicación correspondientes. La fase documental no publica la migración.

Criterios concretos: futuras rondas sin llamadas ni credenciales AeroDataBox;
cero pasajeros estimados por ruta en vista activa/chat; cero vuelos/asientos/
ocupación dependientes de semilla allí; métricas retenidas con fuente, grano,
periodo y cobertura; originales/históricos intactos; faltantes N/D; ningún
cambio de suscripción, secretos o aprobaciones implícito en la retirada.
