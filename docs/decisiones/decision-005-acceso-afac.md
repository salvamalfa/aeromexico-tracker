# Decisión 005 — Acceso, actualización y precedencia de fuentes AFAC

Fecha: 2026-08-20

## Contexto

La Etapa 3 requiere conservar los libros anuales de Estadística Mensual por Aerolínea
publicados en gob.mx. La página visible enumera 1992–2025, pero el CDN de adjuntos
activa de forma intermitente una validación Akamai ante clientes automatizados.
DATATUR, de Sectur, replica boletines AFAC recientes y publica una base larga más
accesible.

## Escalada ejecutada

1. **HTTP con cabeceras de navegador:** DATATUR funcionó; el catálogo y el ZIP de la
   base se descargaron correctamente. gob.mx devolvió HTTP 200 con HTML de
   `Challenge Validation` en lugar del Excel solicitado. La respuesta inesperada se
   preservó antes de rechazarla por magic bytes.
2. **Playwright headless:** gob.mx permaneció en la misma validación y no expuso
   enlaces utilizables. El HTML recibido también quedó preservado.
3. **Navegador integrado visible / computer use:** con autorización del usuario se
   abrió la página oficial, se localizaron los enlaces publicados y se descargaron
   2012–2025 mediante clic normal. No apareció ni se resolvió un CAPTCHA y no se
   eludió ningún interstitial de seguridad.
4. **Descubrimiento histórico:** una captura pública de Internet Archive permitió
   enumerar de forma auditable los enlaces oficiales 1992–2023. HTTP directo alcanzó
   a descargar 1992–2011 antes de que el CDN activara el challenge.

El nivel que completó la cobertura fue **navegador integrado / computer use**. Los
archivos obtenidos así se registraron con `download_method = computer_use`, URL
oficial, SHA-256, timestamp y metadatos inmutables.

## Decisión de precedencia

- **2015–2025:** libro anual oficial AFAC. Es la versión más completa y conserva las
  filas TOTAL de cada bloque.
- **2026 regular:** boletín mensual DATATUR/AFAC del mismo mes. Esto mantiene cada
  cifra junto con su TOTAL y sus notas preliminares/estimadas.
- **2026 fletamento:** base larga DATATUR, porque el boletín no publica ese desglose.
- Los solapes 2016–2025 se usan como QA y para detectar revisiones; nunca se
  concatenan como si fueran observaciones distintas.

Esta precedencia es necesaria porque la base DATATUR vigente ya incorpora revisiones
que no estaban en algunos PDF mensuales. Mezclar ambas versiones habría creado
diferencias artificiales contra los TOTAL contemporáneos.

## Actualización operativa

1. Ejecutar la ingesta normal. DATATUR debe refrescar catálogo, ZIP y boletines por
   HTTP con la tasa AFAC de una solicitud cada tres segundos.
2. Si gob.mx vuelve a entregar un Excel válido por HTTP, el archivo entra directamente
   a bronze. Si entrega HTML de challenge, conservarlo y detener ese tramo.
3. Abrir en navegador la página oficial
   `https://www.gob.mx/afac/acciones-y-programas/estadistica-mensual-por-aerolinea-monthly-airline-statistics`.
4. Descargar únicamente el nuevo año o la revisión publicada. Verificar nombre,
   periodo, extensión y que el libro abre antes de incorporarlo.
5. Añadir el nombre y URL observados a `CURRENT_ANNUAL_DOWNLOADS` y ejecutar
   `import_browser_downloads(Path.home() / "Downloads")`. La función valida magic
   bytes y conserva los bytes mediante `save_bronze`; nunca sobrescribe una versión.
6. Reconstruir silver sin red y ejecutar `python -m src.parse.afac.validate`.

## Consecuencias

- La actualización de DATATUR es automatizable en CI; la incorporación de un nuevo
  libro anual de gob.mx puede requerir intervención humana breve.
- El dashboard deberá mostrar el periodo máximo AFAC y la marca preliminar de los
  meses recientes.
- Los libros descargados permanecen también en Descargas del usuario; bronze guarda
  una copia exacta y auditada, sin borrar ni mover archivos personales.
