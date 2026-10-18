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
2. Calcular mensual en o después del 15. Noticias van con esa ronda, nunca con
   un barrido diario/semanal. Trimestral: dos hábiles estrictamente posteriores
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
   solo con alcance autorizado. Un escritor por lote, sin escrituras activas.
6. Inspeccionar recibos, faltantes, hashes, cambios de filas y cobertura; el
   coordinador no inventa periodos ni mide disponibilidad desde nombres Gold.
7. Proponer reintentos con `retry`, máximo dos reprogramaciones por lote.
   Ningún comando instala tareas, cron o automatizaciones. Mantener cuenta de
   reprogramaciones en el expediente del lote; no reiniciarla para eludir límite.
8. Entregar resumen y pendientes en español claro. Adjuntar evidencia técnica.
   Aprobación de calendario no aprueba contenido ni concede activación.

```bash
python -m src.source_updates calendar --start 2026-10 --months 3 --quarter 2026Q3 --as-of 2026-10-18T12:00:00-06:00
python -m src.source_updates plan --round combined --quarter 2026Q3 --as-of 2026-10-18T12:00:00-06:00
python -m src.source_updates round --recipe config/source_update_round.example.json --workspace tmp/source-updates/prueba --dry-run
```

