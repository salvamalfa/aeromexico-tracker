# Publicación coordinada de Mercado y Noticias

## Resumen

La publicación final usa una sola combinación de Noticias y las herramientas
aprobadas de actualización. El expediente privado identifica los tres pares
exactos de Industria, Viva y Volaris para 2T26. Los tres pares tienen auditoría
independiente favorable y consentimiento expreso del dueño para su propia huella
de código. Aeroméxico conserva su registro histórico. La publicación utiliza el
gate normal, CI del artefacto final y comprobaciones reales de Pages y Railway.

## Qué cambia para ti

Mercado reúne participación, tamaño, crecimiento, contribución y cambios de
participación con universos comparables y cortes explícitos. El detalle
aeroportuario se conserva en datos y exportación.

Noticias presenta las tres fichas del índice aprobado, con filtros por mes,
tema y aerolínea y navegación citada desde el chat. Las once candidatas siguen
inactivas y la cobertura es parcial. La consulta de RSS/GDELT incluye Aeroméxico,
Viva y Volaris; no recupera necesariamente todas las noticias de un mes.

Las herramientas de actualización se integran como código. Esa integración no
activa calendarios, datos, modelos, noticias candidatas ni tesis. Este trabajo
no refresca los datos M11 ni modifica Gold. La primera observación de GDELT y la
primera captura permanecen separadas de la publicación. Los metadatos sin
publicación conocida se conservan para revisión, fuera de las ediciones fechadas.

## Qué necesitas hacer

El consentimiento específico de esta combinación ya fue recibido. Revisa el
[dashboard público](https://salvamalfa.github.io/aeromexico-tracker/) con sus
cinco vistas. Un cambio posterior de contenido o huella requiere la decisión
que le corresponda; no se reutiliza este mensaje para otras identidades.

## Apéndice técnico

### Combinación y comprobaciones

Vuelos #134, empaquetado #138 y Mercado #135 ya se integraron con el sitio
anterior conservado. La propuesta final de Noticias reúne su corrección #139
con las herramientas #137 y #141. Los merges reales de estas últimas
son `3b7771e` y `dfa207c`; la combinación aprobada parte de `76c750a`
y de la huella global `f54fb9f2…`. Los tres pares canónicos y sus hashes
están en la [decisión inmutable](https://github.com/salvamalfa/aeromexico-tracker-data/blob/dfc8d88632e492191d0e1ccb4129862186d6a6f8/review/operacion/20261019/market-news-final/decision.md). No
integrar de nuevo sus PR ni pedir al dueño elegir un orden técnico.

La preparación conservó `site/` igual al master aceptado. Tras el consentimiento
del 19 de octubre de 2026 a las 14:58:36 UTC, se registran los tres eventos de
aprobación y se genera un manifiesto propio con las identidades verificadas.
No reutilizar un manifiesto firmado para otra huella. La preparación de código,
la auditoría, la aprobación y la publicación son pasos distintos.

Cerrar CI y revisión del commit exacto, probar la integración sin red y revisar
la interfaz a 1440 y 390 píxeles. El smoke del proveedor mock no acredita una
llamada real al proveedor. Las pruebas del sitio anterior conservan su propio
corte; no acreditan un sitio nuevo firmado o desplegado. Después de la aprobación,
usar `src.publish` y `src.publish.verify`, cerrar la suite del sitio firmado y
seguir CI, Pages y Railway. Verificar sus commits, hashes, salud y vista pública.

La huella conservadora incluye todo `src/**/*.py`, además de los componentes
web y contratos definidos en `src/analysis_agent/entity_adapter.py`. Por ello
los cambios de las herramientas también exigen una renovación técnica aunque
las cifras permanezcan iguales. No omitir componentes para conservar una huella
anterior. Consultar los registros y eventos originales, nunca inferir aprobación
desde un HTML o desde la proyección SQL.

### Historia que se conserva

La aprobación auténtica del 18 de octubre a las 21:16:59 UTC corresponde a los
eventos 88–90 y a la huella `6534f876…`. El [plan de aquel corte](https://github.com/salvamalfa/aeromexico-tracker/blob/2e23b0fd03fa4b5339dc776ecc01127aabb0ee7e/docs/publicacion-mercado-noticias.md)
conserva sus pares, pruebas y gate local. La renovación aislada `a77a7243…`
también conserva sus tres auditorías como historia. Ninguna de esas aprobaciones
o auditorías se traslada a la combinación final.

Las cuatro tesis, sus resúmenes y las 68 afirmaciones financieras conservan los
textos originales y los insumos congelados. Cada renovación técnica debe
comprobarlo de nuevo. Los registros privados, fuentes, auditorías y mensajes
humanos permanecen en su respaldo. El snapshot histórico no se sobrepone con
una continuación divergente del ledger.

### Metadatos de noticias sin fecha

`src/source_updates/news.py` conserva los metadatos sin publicación conocida en
`data/quality/news_metadata_selection.json`, campo
`publication_unknown_metadata`. No los mezcla con una edición RSS fechada aunque
compartan URL. Si no existe ninguna publicación fechada, `parse.news` se detiene
sin sobrescribir Silver ni el recibo aceptados. El intento bloqueado se guarda
en `data/quality/news_metadata_selection_attempt.json`; las capturas originales
permanecen para revisión. Ambos recibos usan JSON estricto y conservan nulos
para los valores numéricos no finitos. Las consultas directa y mensual reutilizan
`GDELT_QUERY_PARAMS`; no realizan capturas por importar o probar el módulo.

## Pendientes

- Para futuras modificaciones, conservar la aprobación ligada a sus pares y
  comprobar la huella, el gate, la CI y el despliegue real antes de publicar.
- Skills por fuente y coordinador mensual/trimestral como herramientas, con sus
  comprobaciones y activaciones coordinadas aparte. No habilitar calendarios aquí.
- Noticias mensual y aprobación independiente de las once candidatas.
- Limpieza futura con revisión de dependencias. La [auditoría Gold](gold-exposure.md)
  conserva el denominador y las candidatas; este trabajo no borra datos.
