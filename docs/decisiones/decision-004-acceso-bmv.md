# Decisión 004 — Acceso y representación de los paquetes XBRL de BMV

Fecha: 2026-08-20

## Contexto

La Etapa 2 requería descubrir y preservar todos los paquetes XBRL disponibles de
AERO y verificar la cobertura real de VOLAR. El plan anticipaba que el portal podía
requerir navegador y que cada ZIP contendría una instancia XML junto con taxonomías
y linkbases.

## Investigación

- La página pública de reportes XBRL de BMV se entrega completa como HTML generado
  en servidor. Las filas de AERO y VOLAR y sus enlaces al visor están presentes en
  la respuesta inicial; no fue necesario ejecutar JavaScript.
- El parámetro `docins` del visor identifica el paquete. Un enlace como
  `../ifrsxbrl/archivo.zip` se resuelve únicamente contra
  `https://www.bmv.com.mx/docs-pub/`, con validación estricta de host y ruta.
- Cada ZIP observado contiene exactamente un JSON grande. No contiene XML, XSD ni
  linkbases como archivos separados.
- Ese JSON no es una tabla reducida: conserva contextos, unidades, hechos,
  dimensiones, conceptos, etiquetas ES/EN y las relaciones de presentación,
  cálculo y definición de la taxonomía que usa el visor BMV.
- El repositorio de referencia
  [`emhlaos/bmv-scrapper`](https://github.com/emhlaos/bmv-scrapper) confirmó el antecedente del
  acceso por visor, pero su Selenium y su separación de texto JSON datan de 2018 y
  no son adecuados para el portal ni el contrato actuales.

## Decisión

1. Usar `httpx` mediante el cliente común del proyecto, a 0.5 solicitudes por
   segundo, para el catálogo y los paquetes.
2. Preservar sin modificación el HTML del catálogo, cada ZIP y su miembro JSON en
   bronze. Cada artefacto tiene URL, SHA-256, timestamp y clave lógica propios.
3. Rechazar hosts externos, rutas fuera de `/docs-pub/`, ZIPs con traversal,
   miembros no JSON y archivos que excedan los límites definidos.
4. Parsear el modelo JSON de BMV directamente y sin red. La tabla silver conserva
   concepto, contexto, unidad, dimensiones, etiquetas, orden/rol de presentación,
   namespace y linaje hasta el miembro JSON y el ZIP.
5. No instalar Arelle: no aporta valor para este formato de entrega y habría añadido
   una dependencia sin una instancia XML que validar.
6. Tratar la cobertura visible en el catálogo como la cobertura disponible, no
   fabricar periodos históricos ausentes.

## Cobertura observada

- AERO: 2025Q3, 2025Q4, anual 2025, 2026Q1 y 2026Q2.
- VOLAR: anual 2020; 2021Q3, 2021Q4 y anual 2021; todos los trimestres y anuales
  2022–2025; 2026Q1 y 2026Q2. Son 26 paquetes.

El portal actual no expone VOLAR desde 2016, como sugería la investigación previa
del plan. Esta diferencia se conserva como limitación de fuente.

## Fallback

Si BMV deja de entregar el catálogo o los ZIP por HTTP, se escalará según
`docs/plan/12-computer-use-playbook.md`: primero Playwright sin interfaz y después
computer use con aviso previo al usuario. Los archivos obtenidos por ese medio deben
entrar al mismo manifiesto bronze y cumplir los mismos hashes y contratos.

## Consecuencias

- La ingesta es más simple, auditable y reproducible que una automatización visual.
- El parser queda acoplado explícitamente al modelo JSON observado de BMV; el
  fixture congelado detectará cambios de contrato.
- La reconstrucción silver es completamente offline.
- Una futura publicación en XML requeriría un parser adicional, no reemplazaría ni
  reinterpretaría los paquetes históricos preservados.
