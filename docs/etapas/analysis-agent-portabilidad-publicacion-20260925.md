# Portabilidad del Analysis Agent y publicación de Vuelos internacional

Fecha: 25 de septiembre de 2026.
Autorización: explícita del operador ("Publica, soluciona el problema del
Analysis Agent…").
Estado: **dashboard integrado publicado por el flujo normal de `stage18`**,
con el mismo expediente y el mismo evento de aprobación ya vigentes. Ninguna
aprobación se creó, cambió ni reinterpretó.

## La falla del Analysis Agent

Desde el 21 de septiembre, reconstruir el resumen ejecutivo fuera de la
máquina original fallaba con `Excerpt does not match its source locator`
(documentado como limitación en
[`vuelos-selector-trimestre-nacional-internacional-20260921.md`](vuelos-selector-trimestre-nacional-internacional-20260921.md)).

**Causa.** Los comunicados de resultados de la SEC escriben la viñeta como
referencia numérica `&#149;`, un punto de control C1. HTML5 la reinterpreta
como el glifo de Windows-1252 (U+2022, `•`); libxml2 lo hace desde la versión
2.14, que es la que traen las ruedas de `lxml` 6.1.2 para Linux, pero no la
compilación incluida en la rueda de Windows. El expediente aprobado se
construyó en Windows y guardó U+0095; al revalidarlo en Linux (nube, CI) el
texto extraído traía `•` y los cuatro extractos "comunicado completo" de cada
paquete dejaban de coincidir. El contenido de la SEC es idéntico; solo cambia
la decodificación por plataforma.

**Corrección.** `src/parse/sec/common.py::html_text` fija las referencias
`&#128;`–`&#159;` (decimales o hexadecimales) al punto de código literal,
como en el expediente aprobado, enrutándolas por caracteres de uso privado
que libxml2 no reinterpreta. Rechaza un documento que ya contenga ese rango
privado. Pruebas: `tests/test_sec_html_text_portability.py`.

**Efecto medido** (suite completa, mismo entorno, antes y después): se
corrigen 6 pruebas (4 cuantitativas de la etapa 15, la reproducción congelada
de la etapa 16 y la regeneración exacta del resumen ejecutivo) y no aparece
ninguna falla nueva. Tres de los cinco paquetes de evidencia de 2T26 validan,
incluido el del expediente aprobado (`808256…`); los otros dos, obsoletos,
fallan en la fecha de emisión igual con el código anterior y no se usan.

Nota de diagnóstico: la prueba de regeneración parecía colgarse; en realidad
pytest calculaba el diff de dos HTML de 7 MB al fallar la igualdad.

## Publicación

`python -m src.analysis_agent.stage18 --record analysis_runs/drafts/2026Q2/26bc9135….json --output prototypes/etapa-11/resumen_ejecutivo.html`
y copia idéntica a `static/aeromexico_tracker.html`. Antes de reemplazar se
comparó contra lo publicado: solo cambian la red internacional de 2T26 en los
datos de Vuelos (§9.13 del documento canónico), `flights.js` y el orden de
atributos HTML, que ahora sale del generador canónico y no del parche de texto
del 21 de septiembre.

Para reproducirlo en la nube hace falta restaurar el snapshot privado
(`restore_snapshot.py`) **y después** reconstruir el warehouse con las tablas
Gold nacionales e internacionales del repositorio privado: el snapshot trae un
warehouse del 19 de septiembre que no las tiene.

## Silver de la captura internacional

El barrido internacional escribe ahora en `data/silver/aerodatabox_international/`
en vez de la raíz de Silver, como las demás extensiones de rutas: la puerta de
catálogo de la etapa 9 solo gobierna la raíz y fallaba al encontrar las
capturas locales. Workflows privados actualizados.

## Disponibilidad de agosto de 2026

- **AFAC**: al 25 de septiembre el último mes publicado es julio (27 de agosto).
  Rezagos observados: 28 días (marzo de 2025), 36 días (diciembre de 2025, con
  vacaciones) y 27 días (julio de 2026). Agosto se espera entre el 28 de
  septiembre y el 2 de octubre de 2026.
- **AeroDataBox**: agosto ya es consultable. Con la ventana histórica de 210
  días (hipótesis no confirmada contra el panel), el 1 de agosto sale de la
  ventana hacia el 27 de febrero de 2027 y el 31 de agosto hacia el 29 de marzo
  de 2027. Costo esperado con el diseño actual: 1,612 unidades.
