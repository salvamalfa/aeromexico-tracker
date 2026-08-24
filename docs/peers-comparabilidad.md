# Comparabilidad de Aeroméxico y peers

Fecha de corte: 2026-08-23

Esta matriz describe lo que publica cada compañía; no implica que las métricas sean
intercambiables sin normalización. La conversión de moneda, millas/kilómetros y periodos
fiscales corresponde a la Etapa 6.

## Matriz

| Aerolínea | Alcance | Norma | Moneda | Capacidad | FY end | Yield | CASM/CASK ex-fuel | Ancillary separado | Stage length |
|---|---|---|---|---|---:|---|---|---|---|
| Aeroméxico | Aerolínea/grupo | IFRS | USD en releases | ASM y ASK | Dic | Sí | Sí, CASK ex-fuel | Limitado | Sí |
| Volaris | Aerolínea | IFRS | USD | ASM | Dic | Sí | Sí | Sí | Sí |
| Viva Aerobus | Aerolínea | IFRS | USD | ASM | Dic | Sí | Sí | Limitado | Sí |
| Ryanair | Grupo | IFRS | EUR | ASM/ASK según fuente | Mar | No homogéneo | No homogéneo | Sí | Sí |
| Delta | Aerolínea + regionales CPA | US-GAAP | USD | ASM | Dic | Sí | Sí, CASM-Ex | No comparable | No en la tabla usada |
| IAG | Grupo multi-aerolínea | IFRS | EUR | ASK | Dic | Sí | Sí, por compañía | Incluye IAG Loyalty | No homogéneo |

`Limitado` significa que el dato puede aparecer en notas o aperturas de ingresos, pero
no existe una serie trimestral homogénea en el parser actual.

## Definiciones literales y perímetro

Las frases entre comillas son extractos breves de la fuente primaria. Las fórmulas que
siguen explican cómo se interpretan en este proyecto.

### Aeroméxico

- ASK: “number of seats available for passengers multiplied by the number of
  kilometers flown”.
- RPK: “number of transported passengers multiplied by the number of kilometers
  flown”.
- Load factor se define como RPK dividido por ASK y se expresa como porcentaje.
- CASK usa gastos operativos por ASK y excluye partidas no operativas especificadas en
  el filing; CASK ex-fuel excluye además combustible.
- Fuente primaria: 20-F de Aeroméxico preservado en bronze, accession
  `0001193125-24-137345`.

El release mensual usa ASM/RPM en parte de la historia y el 20-F define ASK/RPK. No se
debe comparar una serie métrica con otra imperial sin conversión explícita.

### Volaris

- El release etiqueta literalmente `Available seat miles (ASMs)`, `Revenue passenger
  miles (RPMs)` y `Load factor`.
- TRASM es `Total operating revenue per ASM`; CASM es `Operating expenses per ASM`.
- CASM ex fuel es la medida CASM después de retirar combustible, según la reconciliación
  del propio release.
- Fuente primaria: 6-K/Exhibit 99.1 de Volaris en EDGAR, por ejemplo accession
  `0001292814-25-002705`.

El parser toma la columna del trimestre actual, no YTD ni el comparativo, y conserva el
label original en `metric_label_raw`.

### Viva Aerobus

- ASM: “number of seats available for passengers multiplied by the number of miles”.
- TRASM: “total operating revenue divided by our total available seat miles”.
- RPM mide millas voladas por pasajeros y yield divide ingresos operativos entre RPM.
- Load factor se publica literalmente como `scheduled, RPM/ASM`.
- Fuente primaria: glosario de los reportes trimestrales oficiales de Viva Aerobus,
  preservados en `data/bronze/peers/viva_aerobus/`.

La moneda funcional y de reporte es USD desde 2020, según el mismo glosario.

### Ryanair

- ASM: “total seats available during the period multiplied by the average sector
  length”.
- La fuente mensual publica `Passengers` y `Load Factor`; los trimestres calendario se
  reconstruyen sumando pasajeros y ponderando ocupación por asientos implícitos.
- Fuente primaria: glosario del 20-F FY2026 y tabla oficial
  `https://corporate.ryanair.com/facts-figures/key-stats/`.

Ryanair cierra el 31 de marzo. `FY2026` cubre abril de 2025 a marzo de 2026; nunca se
etiqueta como año calendario 2026. Los financieros anuales no se reconstruyen a
trimestre calendario.

### Delta

- La tabla operativa usa literalmente `Revenue passenger miles (in millions) (RPM)` y
  `Available seat miles (in millions) (ASM)`.
- Passenger mile yield, PRASM y TRASM se expresan por RPM o ASM, respectivamente.
- CASM-Ex es una medida no GAAP que retira combustible e impuestos relacionados,
  ventas de refinería a terceros, MRO y profit sharing en la reconciliación seleccionada.
- Fuente primaria: 10-Q de Delta en EDGAR; los valores financieros se extraen del
  contexto inline XBRL consolidado y trimestral.

Las operaciones de regionales bajo capacity purchase agreements están incluidas en el
perímetro consolidado. IFRS 16 y ASC 842 no son equivalentes, por lo que deuda, renta de
aeronaves y EBITDAR requieren advertencia.

### IAG

- La fuente define passenger yield como passenger revenue por RPK.
- PRASK para la red total es total passenger revenue dividido entre ASK.
- Fuente primaria: `https://www.iairgroup.com/investors-and-shareholders/financial-reporting/`
  y Annual Report and Accounts 2025.

IAG es un grupo que combina British Airways, Iberia, Vueling, Aer Lingus, LEVEL e IAG
Loyalty. No se implementa en el MVP; ver `docs/decisiones/decision-006-acceso-iag.md`.

## Diferencias contables y de uso

- Aeroméxico, Volaris, Viva, Ryanair e IAG reportan bajo IFRS; Delta usa US-GAAP.
- IFRS 16 y ASC 842 producen presentaciones distintas de arrendamientos. Comparar deuda,
  EBITDA/EBITDAR o costos de renta sin puente contable puede inducir conclusiones falsas.
- Mantenimiento puede reconocerse como gasto, activo o provisión dependiendo del contrato
  y la política contable.
- Los programas de lealtad difieren en control, medición de obligaciones y apertura de
  ingresos; IAG Loyalty además aparece como negocio dentro del grupo.
- Ryanair tiene cierre fiscal en marzo; los demás cierran en diciembre.
- Para el dashboard se priorizarán RASM/CASM o RASK/CASK, su spread, load factor y margen.
  Los valores absolutos siempre deberán mostrar moneda, norma, perímetro y periodo fiscal.

## Estado de implementación

| Carrier | Trimestres calendario operativos | Rango | Estado |
|---|---:|---|---|
| Volaris | 15 | 2022Q4–2026Q2 | Implementado |
| Viva Aerobus | 14 | 2023Q1–2026Q2 | Implementado |
| Ryanair | 19 | 2021Q4–2026Q2 | Implementado desde meses |
| Delta | 11 | 2023Q1–2026Q2 | Implementado |
| IAG | 0 | — | Excluido del MVP por decisión documentada |
