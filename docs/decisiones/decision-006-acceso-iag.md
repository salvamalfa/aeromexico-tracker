# Decisión 006 — Acceso y alcance de IAG

Fecha: 2026-08-23
Estado: Aceptada para Etapa 5

## Contexto

IAG no presenta reportes ante EDGAR. Su fuente primaria es `iairgroup.com`, protegida
por Cloudflare, y el comparable disponible es el grupo consolidado (British Airways,
Iberia, Vueling, Aer Lingus y LEVEL), no una aerolínea homogénea con Aeroméxico.

## Evidencia de acceso

Se siguió la escalada definida en el playbook:

1. `httpx` contra la página oficial de financial reporting: HTTP 403.
2. Playwright headless: HTTP 403 y pantalla `Just a moment...` de Cloudflare.
3. Playwright visible: la prueba fue interrumpida al cerrarse la ventana; no se usó
   como evidencia sobre la disponibilidad de la fuente.
4. Control de Chrome: se detuvo automáticamente antes de navegar porque no pudo
   confirmar con suficiente seguridad la URL activa.
5. Navegador integrado aislado: la verificación automática de Cloudflare terminó en
   ocho segundos. Se confirmó la página oficial `Financial reporting | IAG` y el PDF
   `English - Annual Report - FY25`, con URL publicada por IAG.

La vista del PDF en el navegador no produjo un archivo local exportable. Por ello no
se contabiliza como descarga del pipeline ni se añadió un artefacto incompleto a
bronze. La pestaña aislada se cerró al terminar.

## Decisión

IAG queda **fuera del MVP analítico de Etapa 5**. La razón principal es de
comparabilidad: el grupo consolidado mezcla cinco aerolíneas y un negocio de lealtad.
La fragilidad de acceso incrementa el costo, pero no es el motivo único ni se interpreta
como ausencia de datos.

Se conserva IAG en la matriz de comparabilidad y en la serie de mercado de la Etapa 4.
Una extensión futura deberá:

- ingerir al menos ocho trimestres desde la página oficial de quarterly reporting;
- etiquetar todos los hechos como `IAG_GROUP`, sin presentarlos como Iberia;
- separar, cuando el reporte lo permita, los indicadores por compañía operadora;
- preservar cada PDF en bronze con hash y registrar `computer_use` o `browser` como
  método de descarga.

## Consecuencias

- La Etapa 5 cierra con cuatro peers operativos implementados: Volaris, Viva Aerobus,
  Ryanair y Delta.
- No se fabrican ocho trimestres de IAG ni se mezclan cifras de grupo con una sola
  aerolínea.
- Etapa 6 podrá normalizar el panel implementado sin una excepción conceptual de IAG.

