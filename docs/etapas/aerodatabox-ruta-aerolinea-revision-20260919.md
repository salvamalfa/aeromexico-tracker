# Revisión del plan AeroDataBox + AFAC para pasajeros por ruta y aerolínea

Fecha: 2026-09-19  
Alcance: mercado nacional mexicano, 2T26 y posible ampliación a todas las
aerolíneas.  
Estado: evaluación; ningún dato del proveedor está activado en el dashboard ni
en Analysis Agent.

## Veredicto

El plan es técnicamente plausible para producir una **estimación reconciliada**
de pasajeros por ruta y aerolínea. No puede producir una observación de cuántos
pasajeros transportó cada aerolínea en cada ruta porque AeroDataBox no entrega
pasajeros y las dos marginales AFAC no identifican la celda conjunta.

La distinción cambia el criterio de éxito:

- sí puede completar el mapa con una distribución estimada, trazable y útil;
- no elimina `N/D` con cifras observadas;
- no debe etiquetar el resultado como dato de AFAC ni como pasajeros reportados
  por la aerolínea;
- debe acompañar cada celda con método, versión, cobertura de la semilla y una
  medida de incertidumbre o calidad.

Es escalable a todas las aerolíneas en cómputo y adquisición: un barrido por
aeropuerto y fecha captura a todos los operadores visibles, por lo que el costo
no crece linealmente con el número de aerolíneas. La dificultad que sí crece es
la normalización de operadores, codeshares, carga, charter, configuraciones de
flota y rutas ausentes de la semilla.

## Qué está demostrado y qué no

| Afirmación | Evaluación |
|---|---|
| AFAC publica marginal por ruta y marginal por aerolínea | Base válida si ambos archivos usan mes, dirección y universo compatibles |
| AeroDataBox puede aportar frecuencia ruta × operador | Plausible y comprobable con un piloto pagado |
| IPF reconcilia ambas marginales | Sí, si el soporte contiene todas las celdas necesarias y los totales son compatibles |
| La celda IPF representa pasajeros observados | No; es una solución modelada entre múltiples soluciones posibles |
| Error de 1.98 pp en T-100 | Reproducido después mediante el handoff; sigue siendo evidencia transfronteriza, no validación doméstica |
| Una ruta con un operador es exacta | Solo si la semilla tiene cobertura completa y AFAC usa exactamente el mismo universo |
| El enfoque se extiende a todas las aerolíneas | Sí, con un crosswalk exhaustivo y una puerta que rechace cobertura insuficiente |

El documento inicial afirmaba que los módulos se habían mergeado en otro clon.
La entrega posterior permitió recuperar el código, pruebas, fixtures y evidencia;
la verificación independiente se documenta al final de este reporte.

## Identificabilidad y límites del método

IPF encuentra una matriz que respeta totales por ruta y por aerolínea, partiendo
de una semilla de frecuencias. El ajuste cancela sesgos que sean constantes para
toda una fila o columna, pero no puede identificar interacciones propias de una
ruta: calibre de avión, ocupación, estacionalidad, mix de conexiones, política
comercial o concentración de una aerolínea en ciertos horarios.

Que los márgenes cierren exactamente es una propiedad del algoritmo, no una
validación de las celdas. Deben publicarse al menos dos niveles de prueba:

1. **Consistencia:** suma por ruta y aerolínea contra AFAC, convergencia y cero
   masa perdida.
2. **Validez:** backtest donde sí exista verdad conjunta, con error por
   aerolínea, densidad, competencia, mes y tipo de ruta; después, una prueba de
   sensibilidad con semillas perturbadas.

El backtest México–Estados Unidos de T-100 es útil, pero no demuestra el error
del mercado doméstico mexicano. La mezcla de flota y el comportamiento de
Volaris/Viva pueden ser distintos. El 1.98 pp debe presentarse como referencia
externa hasta conseguir una muestra doméstica independiente.

## Grano correcto

El estimador debe ejecutarse en el mismo grano de las marginales, idealmente:

`mes × origen × destino × operador`.

Después se suma a trimestre para el dashboard. Ejecutar IPF directamente en el
trimestre puede dar celdas distintas a sumar tres ajustes mensuales. También hay
que decidir si la vista muestra dirección o par bidireccional. No deben mezclarse
en un mismo total:

- vuelos realizados y programación;
- pasajeros por tramo y pasajeros de itinerario;
- operador y comercializador/codeshare;
- Aerovías de México y Aeroméxico Connect cuando AFAC o la semilla permitan
  distinguirlos;
- pasajeros de Aeroméxico y total de todas las aerolíneas.

## Factibilidad de AeroDataBox para 2T26

El tarifario vigente ofrece Starter por USD 19 al mes, 40,000 unidades, cinco
solicitudes por segundo, ventanas FIDS de 12 horas y hasta 180 días de histórico.
El endpoint Tier 2 consume dos unidades.

Con 58 aeropuertos, dos ventanas diarias y 92 días del trimestre, el máximo
teórico es:

`58 × 2 × 92 × 2 = 21,344 unidades`.

Cabe en Starter. El plan externo cita 6,960 unidades por mes, cifra consistente
con 58 aeropuertos, no con el piloto declarado de 40. Es necesario generar el
presupuesto desde el inventario real y deduplicar: consultar llegadas y salidas
en ambos extremos puede contar dos veces el mismo vuelo.

La ventana histórica es urgente. El 1 de abril de 2026 está a 171 días de la
fecha de esta revisión y rebasa 180 días el 28 de septiembre de 2026. Una
respuesta obtenida fuera del límite documentado no debe utilizarse para planear
el proyecto; se trata como comportamiento no garantizado.

## Restricción de licencia que cambia la arquitectura

Starter permite retener contenido crudo solo siete días. Los términos prohíben
redistribuir respuestas, selecciones de campos o tablas apenas reformateadas.
Definen una obra derivada como procesamiento no trivial de múltiples
observaciones o combinación con datos externos que no permita reconstruir un
registro individual; esa obra derivada queda fuera de la restricción de caché.

Por tanto:

- no se debe crear un Bronze permanente versionado con respuestas AeroDataBox;
- no se deben subir respuestas ni una tabla vuelo por vuelo a GitHub;
- un agregado mensual ruta × operador más el resultado IPF podría calificar
  como obra derivada, pero conviene confirmarlo con el proveedor antes de
  publicarlo como dataset descargable;
- el código, crosswalks creados por el proyecto, manifiestos sin contenido,
  diagnósticos y salidas AFAC pueden versionarse según sus propias licencias;
- la ingesta debe borrar el crudo al completar el propósito o al vencer siete
  días, lo que ocurra primero.

Los términos revisados fueron actualizados el mismo 2026-09-19. Deben congelarse
la URL, fecha y un hash o PDF de la versión aceptada al contratar.

## Diseño recomendado

### Puerta A: importar y reproducir el trabajo externo

Obtener del otro clon los commits o un patch de los módulos, pruebas, fixtures y
resultados de backtest. Ejecutar la suite local antes de aceptar las cifras de
error. No reescribirlos desde el documento si el código original puede
recuperarse.

### Puerta B: piloto mínimo antes de barrer el trimestre

1. Registrar el endpoint, términos, plan, costo y secreto.
2. Ejecutar `--dry-run` para 58 aeropuertos y 2T26.
3. Consultar dos días con perfiles distintos y solo una orientación que evite
   duplicados.
4. Separar vuelo operativo de codeshare, carga, charter y cancelación.
5. Medir rutas y aerolíneas no mapeadas por conteo y por pasajeros AFAC.
6. Rechazar la fuente si no representa al menos 99% de pasajeros y todos los
   operadores materiales, o si exige crear soporte no observado.

### Puerta C: estimación auditable

Crear hechos AFAC versionados para ambas marginales y una tabla nueva, sin
contaminar T-100:

`fact_route_carrier_domestic_estimate`

Campos mínimos:

- `period_id`, `origin_airport`, `destination_airport`;
- `operating_carrier`, `passengers_estimated`;
- `estimator_version`, `seed_source`, `seed_period_id`;
- `is_estimated`, `is_single_operator_supported`;
- `seed_coverage`, `unmapped_passenger_share`;
- `row_residual`, `column_residual`, `converged`;
- `uncertainty_band` o clase de confianza basada en sensibilidad.

Persistir también reconciliaciones por ruta y aerolínea. Si los márgenes no
coinciden o el soporte es inviable, no publicar un resultado parcial.

### Puerta D: integración separada

Mostrar primero una vista de revisión con tres capas distintas:

1. rutas y vuelos observados/programados;
2. pasajeros totales AFAC por ruta;
3. distribución estimada por aerolínea.

Solo después de revisión humana debe entrar al mapa principal. El dashboard
debe permitir diferenciar `observado`, `programado`, `inferido` y `estimado` sin
depender de un tooltip. La elegibilidad histórica al corte 2026-07-13 permanece
separada del uso retrospectivo posterior.

## Asientos, ocupación e internacional

Frecuencias por sí solas no producen asientos ni ocupación. Una fase posterior
puede mapear modelo de aeronave a configuración por operador, con rangos cuando
haya varias cabinas, y calcular capacidad estimada. Esa extensión agrega otra
fuente de error y no debe bloquear el primer cubo de pasajeros estimados.

El método puede ampliarse a mercados internacionales solo cuando existan las
dos marginales compatibles. Países con un cubo observado por ruta y aerolínea
deben usar la fuente observada, no IPF. Para todas las aerolíneas, el mismo
pipeline funciona si el universo AFAC, el seed y los filtros operativos se
reconcilian.

## Impacto de subir el proyecto a GitHub

Versionar el trabajo local elimina el principal punto ciego del plan externo:
un agente de nube podrá ver el generador integrado, ingestas internacionales,
contratos, Gold y pruebas. No cambia la validez estadística del estimador ni
autoriza publicar datos pagados. Tampoco reemplaza secretos, crudos locales o el
ledger privado de aprobaciones.

La nube mejora colaboración, revisión y continuidad. El costo es que la
frontera de licencia debe quedar automatizada: un agente con acceso al repo no
debe poder añadir accidentalmente una respuesta cruda. `.gitignore`, revisión
de secretos, rutas temporales y pruebas de clasificación de artefactos deben
formar parte de la implementación.

## Preparación para continuar

El repositorio local ya permite implementar la arquitectura y el piloto. Antes
de consumir unidades o publicar resultados hacen falta:

1. recuperar los commits/patch del código que el plan afirma haber construido;
2. una clave de AeroDataBox guardada como secreto, después de elegir el plan;
3. confirmación del proveedor sobre publicación del agregado mensual ruta ×
   operador, si se pretende versionarlo;
4. aceptar explícitamente que el producto será una estimación y no pasajeros
   observados por celda.

No hace falta mantener abierta la sesión externa: sus commits, 89 pruebas,
fixtures y resultados reproducibles ya fueron recuperados y verificados.

## Verificación de la entrega externa

La entrega se recibió en la rama
`claude/route-carrier-handoff-20260919`, commit
`762664bac1fb969ec46a8144c25ca1588596b2a3`. Los cinco PRs de implementación ya
forman parte de `origin/master` mediante `dc55d07`.

Comprobaciones independientes realizadas:

- los 19 parches aplican desde `26d3617` y generan exactamente el árbol de
  `dc55d07`;
- las 89 pruebas focalizadas pasan en el entorno local;
- el módulo reproduce 1.40 pp con asientos y 1.98 pp con vuelos;
- el `--dry-run` calcula 7,192 unidades para 58 aeropuertos y julio completo;
- la entrega no contiene una llave de API.

La entrega está preservada y la sesión externa ya no es necesaria. Antes de
usar una cuota pagada hay cuatro reparaciones locales:

1. La caché guarda respuestas crudas sin vencimiento en `data/cache/`, ruta que
   tampoco está ignorada. Debe excluirse de Git y aplicar borrado máximo a siete
   días para Starter.
2. La consulta pide `withCancelled=true` y el normalizador no identifica ni
   excluye cancelaciones. Debe conservar la distinción entre operación realizada
   y programación.
3. El adaptador no reconoce todavía los códigos propios `5D`/`SLI` de
   Aeroméxico Connect, aunque el crosswalk general del proyecto sí los conoce;
   tampoco puede tratar silenciosamente un modelo de aeronave faltante como
   Aerovías de México.
4. `is_exact` no debe derivarse solo de que la semilla muestre un operador. Esa
   condición depende también de cobertura completa y del mismo universo AFAC;
   hasta demostrarlo, todas las celdas del IPF permanecen estimadas.

El manifiesto SHA-256 del handoff tiene dos discrepancias en las copias de los
crosswalks por normalización LF/CRLF. Los contenidos coinciden con los archivos
del árbol y los parches son reproducibles, pero el manifiesto debe regenerarse
antes de considerarlo portable. La salida de la suite y los propios parches
también contienen espacios finales; es higiene documental, no un fallo del
estimador.

## Fuentes del proveedor revisadas

- [API Pricing](https://aerodatabox.com/pricing/)
- [Terms of Use](https://aerodatabox.com/terms)
- [Direct API access](https://aerodatabox.com/direct-subscriptions)
- [API Specification](https://aerodatabox.com/api-spec/)
