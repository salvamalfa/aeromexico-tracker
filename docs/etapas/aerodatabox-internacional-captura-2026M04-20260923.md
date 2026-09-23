# Primera captura internacional: 2026M04

Fecha: 22–23 de septiembre de 2026.
Alcance: ejecutar la primera captura mensual pagada del plan de
[`aerodatabox-internacional-crosswalks-puerta-20260922.md`](aerodatabox-internacional-crosswalks-puerta-20260922.md),
pasarla por la puerta, ajustar el IPF internacional y medirlo contra T-100.
Autorización: explícita del operador para la llamada a la API y para fusionar
los PR #32 (público) y #12 (privado).
Estado: **captura hecha, ajuste convergido, sin publicar.** No se tocó el
dashboard, `flight_evidence_v1`, la elegibilidad histórica ni el Analysis
Agent.

El detalle técnico que debe durar está en el documento canónico
[`docs/estimacion-pasajeros-ruta-aerolinea.md`](../estimacion-pasajeros-ruta-aerolinea.md)
§9.11. Este reporte registra la sesión.

## Gasto

| Paso | Llamadas | Unidades |
|---|---:|---:|
| Canario: MEX, 1 de abril (confirma que abril sigue en la ventana histórica) | 2 | 4 |
| Núcleo: CUN, GDL, MEX, MTY, PVR, SJD, mes completo | 358 (2 en caché del canario) | 716 |
| Resto: 31 aeropuertos, 7 días ponderados | 434 | 868 |
| Reconstrucciones posteriores con `--offline` | 0 | 0 |
| **Total** | **794** | **1,588** |

Exactamente lo presupuestado. El sondeo de 8 unidades del 2026-09-10 no se
repitió.

## Resultado

- **Puerta** (`international_seed_acceptance_v1`): `review`, sin rechazos.
  Rutas 99.38 %, aerolíneas 98.74 %, `column_scale` 1.007, codeshare
  desconocido 1.09 %, vuelos semilla/AFAC 0.977.
- **Ajuste** (`fit_international`): convergió en 4,088 iteraciones,
  desviación máxima 4.8 pasajeros; 7,856 pasajeros topados (0.16 %, sobre
  todo TUI Airways) y 697 sin asignar (0.015 %).
- **Contraste contra T-100** (fuera del ajuste): 6.3 % de error ponderado,
  mediana 3.8 %, suma 0.997; Aerovías + Connect 6.9 %, mediana 5.4 %, suma
  1.023.
- **Grupo Aeroméxico**: 683,752 pasajeros estimados en 136 rutas dirigidas.

## Lo que la captura destapó

Cuatro problemas que un ensayo sin datos no podía ver, cada uno corregido con
prueba de regresión:

1. **Crosswalk de ciudad**: el "100 %" medía etiquetas con algún aeropuerto,
   no el correcto. PARIS apuntaba a Le Bourget, SAN SALVADOR a Ilopango, y
   faltaban CDG, IAD, EZE, NRT, SAL, ORY y DAL. Once reglas revisadas con
   códigos IATA de área metropolitana; nueva comprobación
   `aeropuertos_sin_ciudad`.
2. **Vuelos con escala en México** (MEX→MTY→NRT de Aeroméxico, Turkish
   vía CUN, China Southern vía SJD, Hainan vía PVR, Viva vía MTY): el
   adaptador los reconstruye en el aeropuerto de la escala y no los duplica
   cuando el primer tablero ya los muestra hasta el destino final.
3. **Regionales bajo la marca** (SkyWest, Envoy, Mesa, CommutAir; Lacsa,
   Taca; filiales de LATAM): familias revisadas que se ajustan como una
   columna. Sin esto el IPF no convergía (SkyWest pedía 789 pasajeros por
   vuelo visible).
4. **Crosswalk de aerolínea**: Breeze, Volaris El Salvador y Aerus
   confirmadas con la captura; una clave `unresolved` ya no puede entrar a la
   semilla; la comprobación de soporte estructural simula la matriz real
   (antes era tautológica y dejó pasar MONTERREY-BROWNSVILLE sin oferta
   ajustable).

## Retención

- Caché cruda del proveedor: solo en el contenedor, eliminada a los 7 días
  por `purge_expired_cache`; nunca en Git.
- Derivados sin contenido del proveedor (semilla ruta × operador, descartes
  agregados, estimación, diagnósticos, contraste, sensibilidad):
  `derived/aerodatabox_international/2026M04/` en el repositorio privado, con
  manifiesto SHA-256 y linaje. No incluye tablas vuelo por vuelo ni el
  detalle por modelo de aeronave.

## Workflow privado

`aerodatabox-international-sweep.yml` gana dos pasos que no gastan: la
reconstrucción `--offline` de ambas pasadas (para que la deduplicación de
vuelos con escala vea los dos tableros) y la puerta + ajuste + diagnósticos.
El artefacto sube solo agregados derivados.

## Validación

- Pruebas internacionales enfocadas: todas aprobadas (crosswalks, puerta,
  ajuste con familias y topes, vuelos con escala, modo offline).
- Suite completa: **477 aprobadas, 47 fallidas, 6 omitidas, 29 errores**.
  Las 47 fallas y los 29 errores son la línea base documentada del clon de
  nube (`data/silver/`, `data/bronze/`, `analysis_runs/` ausentes); las 15
  aprobadas adicionales son todas nuevas.

## Qué sigue

1. Revisión humana de la vista separada (rutas de un solo operador, rutas
   con un solo sentido, familias, topes) antes de cualquier cambio al
   dashboard.
2. Mayo–julio con el mismo workflow, ≈ 1,600 unidades por mes, para
   estabilidad y soporte temporal entre meses.
