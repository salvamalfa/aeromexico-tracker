# Preparación de evidencia F2.5–F2.7 · 11 oct 2026

Se añadieron un índice JSON de evidencia aprobado por compuerta, búsqueda
determinística limitada, contratos/dispatch para dos herramientas, manifests
candidatos de fuentes, colector semanal manual dry-run e idempotente, y una
regla F2.7 versionada como propuesta independiente. No se conectó el registry,
no se modificó el prompt F2.1 aprobado y no se publicó ni aprobó contenido.

## Procedencia y límites

- `config/chat/evidence/candidates/reports-candidate.json` señala el exhibit
  99.1 del reporte de Aeroméxico 2T26 presentado en SEC EDGAR. El enlace ya se
  encuentra citado por el catálogo actual del chat. El manifest no almacena
  cuerpo, extracto, página ni hash porque todavía no se fijaron bytes ni se
  verificó la paginación para publicación.
- `config/chat/evidence/candidates/news-sources.json` registra como fuentes de
  descubrimiento Google News RSS en español y RSS de Empresas de El Economista,
  siguiendo el inventario ya existente en `src/ingest/news/rss_gdelt.py`. No
  se descargaron titulares en esta entrega; ambas fuentes quedan pendientes de
  revisar términos y registros concretos.
- `config/chat/evidence/approved-index.json` permanece vacío. Nunca se acepta
  un candidate manifest como índice publicado.

El índice comprueba un recibo de aprobación explícito, campos fuente, host
permitido, SHA-256, grano y límites de extracto al consultar. La búsqueda es
por tokens normalizados y score entero, con desempate estable. Cada resultado
lleva periodo/fecha y URL junto con el hash del artefacto citado. La salida de
noticias contiene título y ficha breve, no el texto completo.

## Revisión breve para el dueño

1. Revisar los dos enlaces/fuentes candidatos, sus términos de uso y si se
   deben incluir; la procedencia está indicada arriba y en los manifests.
2. Para habilitar un pasaje de reporte: fijar bytes exactos de SEC, hash,
   sección y página verificada, extraer texto breve, y dejar el recibo real de
   aprobación. No usar el manifest candidate como evidencia.
3. Para habilitar cada noticia semanal: revisar la ficha individual y escribir
   un resumen propio; confirmar liga/fecha/entidades, recibir decisión humana
   explícita y guardar el recibo emitido por el flujo del dueño.
4. Revisar la regla F2.7 independiente y agregar casos «por qué» con cita de
   cada capa antes de conectarla al servicio.

Comando sin red para planear una captura semanal:

```bash
python scripts/chat/collect_news_candidates.py \
  --week-start 2026-10-05 --input /ruta/privada/headline-metadata.json
```

El comando es dry-run por omisión y muestra destino/conteo. Añade
`--write-candidate` para guardar el manifest cerrado; no activa publicación ni
agenda futuras ejecuciones. No hubo aprobación humana ni despliegue.

## Validación

Las pruebas offline usan solamente el fixture sintético
`tests/fixtures/chat_evidence/index.json`. Verifican filtros empresa/periodo,
cita con página y hash, rechazo efectivo de registros no aprobados, ventana
de fecha de noticias, salida sin texto completo y rechazo de hosts externos.
