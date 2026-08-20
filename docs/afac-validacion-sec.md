# Validación cruzada AFAC vs SEC — pasajeros de Aeroméxico

Fecha de cálculo: 2026-08-20

## Resultado

La serie mensual AFAC de **Aeroméxico + Aeroméxico Connect** correlaciona **0.999303**
con los pasajeros totales mensuales publicados por Grupo Aeroméxico ante la SEC. Hay
14 meses de solape entre 2024M10 y 2026M06; el umbral de aceptación era >0.95.

AFAC queda, en promedio, **28,895 pasajeros por mes por debajo** de SEC, equivalente a
**-1.4497%**. La mediana es **-1.5487%**. La diferencia es estable: en los 14 cruces
se mantiene entre -1.08% y -1.68%, sin cambios de signo ni outliers materiales.

## Comparación mensual

| Periodo | AFAC: AM + Connect | SEC grupo | Diferencia | Diferencia % |
|---|---:|---:|---:|---:|
| 2024M10 | 2,017,164 | 2,041,000 | -23,836 | -1.1679% |
| 2025M01 | 2,065,355 | 2,090,000 | -24,645 | -1.1792% |
| 2025M02 | 1,744,746 | 1,764,000 | -19,254 | -1.0915% |
| 2025M03 | 2,001,068 | 2,023,000 | -21,932 | -1.0841% |
| 2025M04 | 2,054,990 | 2,088,000 | -33,010 | -1.5809% |
| 2025M05 | 2,026,965 | 2,059,000 | -32,035 | -1.5559% |
| 2025M06 | 2,004,087 | 2,033,000 | -28,913 | -1.4222% |
| 2025M10 | 1,962,660 | 1,994,000 | -31,340 | -1.5717% |
| 2026M01 | 2,022,461 | 2,053,000 | -30,539 | -1.4875% |
| 2026M02 | 1,715,135 | 1,744,000 | -28,865 | -1.6551% |
| 2026M03 | 1,960,822 | 1,994,000 | -33,178 | -1.6639% |
| 2026M04 | 2,029,229 | 2,061,000 | -31,771 | -1.5415% |
| 2026M05 | 2,066,587 | 2,102,000 | -35,413 | -1.6847% |
| 2026M06 | 1,821,195 | 1,851,000 | -29,805 | -1.6102% |

## Interpretación

La comparación usa la vista consolidada elegida para negocio, pero los perímetros no
son idénticos. AFAC suma observaciones regulatorias por aerolínea, mercado y tipo de
servicio; SEC informa el total consolidado del grupo y redondea a miles. La diferencia
negativa, pequeña y muy estable es consistente con un componente de perímetro y
redondeo, no con un error de escala o desplazamiento temporal del parser.

No se ajustó ninguna cifra para mejorar el cruce. El Parquet reproducible está en
`data/quality/afac_sec_reconciliation.parquet`.
