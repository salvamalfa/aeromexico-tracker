# Etapa 13 — Cobertura financiera histórica

Autorizada por el usuario el 2026-09-05 tras aceptar Etapa 12.

1. Congelar la cobertura previa para hacer una comparación reproducible.
2. Verificar hashes de los 18 PDF de 2021Q1–2025Q2 preservados en Bronze.
3. Extraer tablas trimestrales, excluyendo columnas acumuladas y comparativos.
4. Conservar moneda original, escala, página, fila, precisión y definición.
5. Separar UAFIDAR reportada de ajustada y resultados excluyendo PLM.
6. Conservar gastos agrupados sin repartirlos entre componentes no publicados.
7. Guardar la extracción financiera en Silver con contrato y reconstrucción local.
8. Calcular conversiones explícitas para revisión, fuera de Silver; distinguir USD
   de conveniencia de USD como moneda funcional de presentación.
9. Conciliar resultados y márgenes con tolerancias según redondeo publicado.
10. Comparar 2024Q3–2025Q2 con sus cifras SEC vigentes y explicar diferencias.
11. Entregar HTML local con matriz antes/después y fichas cifra–reporte.
12. Ejecutar pruebas, documentar límites y detenerse para revisión humana.

La tabla histórica conserva versiones y definiciones por fuente; no sustituye la
vista vigente del dashboard. Su selección temporal y consumo se implementarán en
Etapa 14. La recuperación de cifras no certifica la disponibilidad al corte.

Aceptación: cada campo objetivo extraído o ausencia documentada; cero diferencias
materiales sin explicar; hashes intactos, grano único, signos y unidades correctos,
reconstrucción idempotente y resultado visible. Etapa 14 requiere otro permiso.
