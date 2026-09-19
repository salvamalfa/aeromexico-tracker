# Etapa 15 · Motor cuantitativo

Estado: implementada, pendiente de revisión humana. Etapa 14 aceptada por el usuario;
Etapa 15 autorizada con «Continua». Fecha: 2026-09-05.

## Entrega

[Abrir cálculos y fuentes](../../prototypes/etapa-15/quantitative_review.html).
Cada cálculo permite abrir la fórmula, recorrer sus insumos y consultar el documento
original. Es una UI de comprobación; no se incorpora al dashboard.

El motor consume únicamente el paquete congelado de 2T26:
`2026Q2_808256bfb7420d221a3f2f2383c4b95d9889110ad1545fd85f24df8d442a9ff1`.
Produce 372 nodos de valores/cálculos con referencias, 40 controles y seis puentes.
No consulta las cifras actuales de Gold ni amplía silenciosamente el paquete.

## Cálculos implementados

- ASM a ASK y TRASM/CASM a RASK/CASK, con 1.609344 km por milla.
- QoQ contra 1T26 y YoY contra 2T25, sin saltar periodos ausentes.
- Cambios absolutos, porcentajes con base positiva y puntos porcentuales.
- Spread, combustible/ASK, resto del CASK, costo efectivo por litro e intensidad.
- Márgenes derivados, conciliación de resultado operativo e ingresos/costos por ASK.
- Puentes QoQ/YoY del spread: RASK, combustible/ASK y resto del costo unitario.
- Puentes simétricos de ingresos (capacidad/monetización) y combustible (litros/costo
  efectivo), mediante Δvolumen × tasa media + Δtasa × volumen medio.

El spread cambia −0.6835 centavos USD/ASK QoQ y −1.1806 YoY. Sus contribuciones
reconcilian con error numérico inferior a 10⁻¹⁰. Estas son identidades contables,
no explicaciones causales. La monetización por ASK no equivale a tarifa; el costo
efectivo de combustible no equivale al precio de mercado.

## Diferencias que permanecen abiertas

35 de los 40 contrastes coinciden dentro de los intervalos publicados. Los otros
cinco comparan CASK reportado con gasto operativo/ASK y no reconcilian:
3T24, 1T25, 3T25, 4T25 y 1T26. No se ha demostrado equivalencia de alcance ni la
causa de cada diferencia. No se amplían tolerancias para hacerlas desaparecer.

El motor las conserva como `not_reconciled` y emite la restricción explícita
`allow_spread_to_financial_margin_attribution: false`. El puente del spread sí cierra;
eso no demuestra que explique el margen operativo. Tampoco el residual prueba
eficiencia ni cambios estructurales. La aceptación de este límite queda para revisión.

La cifra de combustible utilizada proviene de las tablas financieras redondeadas
(por ejemplo, USD 494 millones en 2T26). No se sustituye automáticamente por la
cifra más precisa de la prosa sin crear otra versión del paquete de evidencia.

## Precisión y validación

Se propagan intervalos desde media unidad del último decimal conservado en el
valor original y su escala. Cuando Silver pierde ceros finales, la tolerancia es
conservadora y puede ser más amplia; no se inventa precisión adicional.
Una base no positiva, un denominador cuyo intervalo incluye cero, una unidad o
ajuste incompatible y un comparable ausente producen indisponibilidad explícita.

- 250 pruebas del proyecto pasan; 14 específicas del motor.
- Los seis puentes contables reconcilian. Los cinco contrastes de alcance siguen
  marcados aparte; no se cuentan como reconciliaciones aprobadas.
- Linaje acíclico, referencias resueltas, monedas/ajustes incompatibles, cero,
  negativos, faltantes, cambio de año y bloqueo histórico comprobados.
- Cuaderno ejecutado: resultado idéntico al repetir, evidencia y Gold intactos.
- HTML sin peticiones de red al abrirse; búsqueda, detalle, Escape y tres anchos
  (360, 736 y 1440 px) comprobados.

## Operación y siguiente paso

Los resultados inmutables se conservan en `analysis_runs/quantitative`, separados
de Gold y de las carpetas regeneradas. El JSON de revisión puede reconstruirse.
[Expediente y comandos](../referencias/etapa-15/README.md).

No hay redacción del agente, auditor ni aprobación de contenido. No se ha publicado
ni cambiado el dashboard. Etapa 16 requiere autorización humana posterior a esta revisión.
