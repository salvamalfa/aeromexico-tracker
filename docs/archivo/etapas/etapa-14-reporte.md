# Etapa 14 · Paquete de evidencia temporal

Estado: implementada localmente; pendiente de aceptación humana. Fecha: 2026-09-05.

La aceptación de Etapa 13 autorizó esta etapa. El usuario priorizó lecturas recientes,
aceptó faltantes anteriores a 2024 y delegó la elección documental de 3T24. La política
conserva el reporte original para su lectura histórica y mantiene revisiones posteriores
por separado; no dispensa la comprobación temporal.

## Entrega visible

[Abrir dossier navegable](../../prototypes/etapa-14/evidence_dossier.html).
Selector 2T26/1T21, estado, corte, cobertura, búsqueda de cifras, fuentes y pruebas
en ventanas cerrables. Es una UI de comprobación: ninguna sección se publica en el dashboard.

| Expediente | Resultado | Alcance |
|---|---|---|
| 2T26 | `limited` | Corte 2026-07-13; 35 cifras del trimestre, 299 con historia/comparables, cuatro comunicados y 157 fragmentos |
| 1T21 | `blocked` | Fecha impresa 2021-04-20; versión histórica no certificada. Cero cifras o fragmentos enviados al analista |

En 2T26 están los insumos operativos y financieros esenciales. Los 299 registros
incluyen ocho periodos: no significan 299 métricas distintas del trimestre actual.
Las métricas ASM/TRASM/CASM conservan sus unidades originales; las conversiones
a ASK/RASK/CASK y las comparaciones corresponden a Etapa 15.

## Prueba temporal y selección

El comunicado de 2T26 está en el anexo 99.1 del envío SEC
`0001193125-26-302103`. El 6-K identifica el comunicado y su fecha de emisión.
El encabezado del envío completo acredita la fecha de filing. Se coteja el contenido
íntegro del anexo con su bloque en el envío archivado, normalizando solo finales de línea.
No se utiliza la descarga de agosto como prueba de publicación de julio.

Los otros comunicados elegibles dentro de este corte son 3T25, 4T25 y 1T26.
Se distingue su publicación IR de su posterior disponibilidad acreditada en SEC.
Un 6-K puede contener anuncios de tráfico y resultados en días distintos: la fecha
se vincula al título del comunicado correcto, no al primer anuncio del documento.

La precisión del corte es diaria. El propio comunicado define el evento; otras fuentes
del mismo día, sin orden demostrable, se excluyen. Este tratamiento no acredita una hora.
Tampoco certifica automáticamente el corte original de todos los trimestres recientes:
cuando el filing llegó después del comunicado, hará falta otra prueba para ese corte.

Los 22 PDF IR conservan estado temporal no certificado, aunque su integridad local
está verificada. El PDF en español de 2T26 no se equipara automáticamente a los bytes
del anexo inglés: el paquete utiliza directamente la versión SEC identificada.

## Implementación y almacenamiento

`src.analysis_agent.evidence` registra disponibilidad, selecciona por corte, conserva
versiones, resuelve fragmentos y valida integridad. No usa la vista de valores vigentes
de Gold: solo reutiliza su catálogo de identificadores de artefactos.

Cada paquete vive en `analysis_runs/evidence`, fuera de las carpetas regeneradas por
el pipeline. La huella incorpora contenido, fuentes, política y versión del código,
sin hora de ejecución. La escritura es atómica y no reemplaza un paquete existente.
Repetir los mismos insumos reutiliza la misma versión; un cambio crea otra huella.

La información excluida queda en un anexo de revisión separado. El paquete entregable
al analista contiene únicamente fuentes elegibles, sus pruebas y cifras. Los fragmentos
se tratan como evidencia no confiable para instrucciones; no se ejecuta su contenido.

## Validación

- Suite completa: 236 pruebas aprobadas; 19 pruebas específicas repetidas y aprobadas
  después del ajuste final de persistencia atómica.
- Controles adversariales: fuente posterior, mismo día ambiguo, fecha desconocida,
  primera fecha incorrecta en un 6-K, cambio de versión, alteración de anexo, hash,
  valor, escala o referencia, contenido inyectado y escape de metadatos en HTML.
- Los localizadores se vuelven a comprobar contra Bronze; las cifras más precisas
  de la prosa enlazan su párrafo, no una fila redondeada con otro valor.
- Navegación, búsqueda, estados vacíos, ventanas, cierre con Escape y sin peticiones
  de red al abrir el HTML: comprobados a 360, 736 y 1440 px.
- Cuaderno ejecutado: reconstrucción idéntica, misma versión y tablas Gold intactas.

## Límites y siguiente paso

El contexto externo de combustible, FX, aeropuertos, AFAC, competidores y eventos
no tiene versiones temporales certificadas en estos paquetes. Hay cero meses elegibles
en esos dominios: no se los representa como trimestres completos. Se permite una
lectura acotada al comunicado; no una atribución causal externa independiente.

Los valores ausentes permanecen ausentes. Las afirmaciones de la compañía en el
comunicado pueden citarse como atribuciones; no se convierten en causalidad demostrada.
Las diferencias de precisión entre prosa y tablas se conservan para las tolerancias
del motor cuantitativo, sin forzar identidades con redondeos distintos.

No hay agente redactor, aprobación de análisis, cálculos QoQ/YoY, despliegue ni servicio
de generación instalado. La Etapa 15 requiere aceptación humana de esta entrega.

[Expediente reproducible](../referencias/etapa-14/README.md).

## Aceptación humana

Tras la entrega y explicación de lo realizado, el usuario indicó «Continua». Se registra la aceptación de Etapa 14 y autorización de Etapa 15.
