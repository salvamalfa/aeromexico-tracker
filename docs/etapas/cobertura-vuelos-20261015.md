# Vuelos: cobertura publicada y ampliación de prueba

15 de octubre de 2026. Son dos entregas distintas:

- **Publicado:** [PR #133](https://github.com/salvamalfa/aeromexico-tracker/pull/133),
  aprobado por el dueño e integrado como `40a63d1905afde97ae8e3f8671c8217aafacc4aa`.
  [Pages](https://salvamalfa.github.io/aeromexico-tracker/) y Railway terminaron
  correctamente; se verificaron los 134 archivos del manifiesto, los 117 datos
  conservados, las cuatro tesis y el snapshot del chat. Volaris y Viva tienen
  rutas presentes y totales contrastados en navegador, escritorio y móvil.
- **Ampliación:** código y preview privada, pendientes de revisión y aprobación.
  No se ha integrado, desplegado, ajustado un modelo ni activado un mes nuevo.

## Qué significa el porcentaje

La [matriz publicada](../assets/flight-coverage/quarterly-flight-coverage-published.csv)
tiene 1.128 filas: tres entidades, nacional/internacional, trimestre y tipo de
cifra. Incluye los periodos sin datos del mapa como **no calculables**.
[Fuentes y hashes](../assets/flight-coverage/sources-published.json) permiten
reproducirla sin descargar fuentes. Los denominadores se releyeron de `VLOSREG`
de los Excel AFAC conservados de 2015–2026; no del CSV de pasajeros. Las 76
celdas domésticas de los operadores objetivo presentes en el CSV vigente
coinciden exactamente con esa relectura. No se modificaron las marginales.

Se comparan vuelos regulares del mismo operador, periodo y ámbito. Grupo
Aeroméxico incluye Aerovías y Connect en AFAC, aunque BTS solo observa Aerovías.
Volaris es **Y4/VOI México**: excluye Costa Rica Q6 y El Salvador N3. Viva es
Aeroenlaces. Se cuentan ambos sentidos una sola vez, sin volver a sumar el
total de mercado sobre sus direcciones. BTS clases `F/G` entran en el numerador
regular (pasajeros/carga y solo carga); `L/P` son no regulares y quedan fuera.
La clasificación procede de la [guía T-100 de BTS](https://www.bts.gov/sites/bts.dot.gov/files/docs/explore-topics-and-geography/topics/airlines-and-airports/219466/t100-guide-april-2007.pdf).
Aerocivil declara operaciones regulares. ANAC/CAA cuyos
registros no acreditan esa misma clasificación quedan fuera del numerador
comparable, aunque sus vuelos observados permanezcan en el mapa.

El porcentaje es una **proporción mínima de operaciones oficiales regulares
representadas por observaciones comparables**, no una medición de coincidencia
vuelo a vuelo ni una prueba de que la red internacional está completa.

| Internacional 2T26 publicado | Observaciones regulares comparables | Total AFAC regular del trimestre | Proporción mínima |
|---|---:|---:|---:|
| Grupo Aeroméxico | 5.474 | 14.522 | 37,69 % |
| Volaris México | 7.216 | 11.803 | 61,14 % |
| Viva | 2.302 | 4.878 | 47,19 % |

Volaris y Viva tienen BTS solo de abril–mayo: junio está pendiente. Sobre esos
dos meses, las proporciones son 93,33 % y 75,23 %, respectivamente; **no** se
extrapolan a junio. La matriz separa denominador completo, meses representados
y pendientes. Si AFAC solo llega a julio, 3T26 completo es no calculable.

Nacional contiene frecuencias **estimadas**, no un inventario de vuelos
realizados: su cobertura de vuelos reales es no calculable. Tampoco se divide
programación o atribución de mercado por vuelos realizados para llamarlo
cobertura. No se suman las cuatro clases. Que un IPF reconcilie pasajeros no
mide cobertura de vuelos. No se usa el número de rutas como porcentaje de vuelos.

**Discrepancia conservada:** Volaris internacional 2T25 tiene 13.323 salidas
BTS frente a 10.919 vuelos regulares AFAC. Operador y año del workbook fueron
comprobados; Gold no duplica sus claves ruta/mes/aeronave/clase. El porcentaje
queda vacío, con `source totals inconsistent`; no se recorta al 100 % ni se
corrige Gold sin una investigación separada.

## Datos almacenados frente a selección visible

En la versión publicada, Nacional tiene archivos marzo–julio de 2026 para las
tres aerolíneas. El trimestre general termina en 2T26, por lo que **julio está
almacenado pero no seleccionable**. Internacional ofrece 1T21–2T26; antes de
2T26 es México–EE. UU. observado por BTS. En 2T26 se añaden estimaciones de
otros países. Volaris/Viva no heredan capas AM de AICM, AIFA, OMA o autoridades.

La ampliación prepara:

1. Un periodo propio del mapa: meses y trimestres, incluido julio parcial,
   manteniendo las tarjetas financieras y cuatro tesis en su trimestre general.
   BTS retenido desde enero de 2015 hasta mayo de 2026 se vuelve accesible;
   las observaciones oficiales posteriores conservan su fecha específica.
2. Julio internacional ya ajustado en Gold, sin exigir agosto y septiembre ni
   completar esos faltantes. Agosto solo tiene capturas/capacidad: no se activa.
3. Frecuencias de su mismo mes independientes de asientos/modelo de avión.
   El soporte prestado de otro mes no se convierte en vuelos. Una suma solo
   de frecuencias conocidas se marca parcial; lo desconocido sigue N/D.
4. Una capa nacional separada de programación AICM y atribuciones AFAC para
   Aeroméxico; permite sus meses retenidos sin sumarla a frecuencias estimadas.
   No propaga esas fuentes de marca AM a otras aerolíneas.
5. Observaciones de un solo sentido, con flecha y cobertura parcial; no se
   fabrica el regreso ni se presume que sean una ruta comercial completa.
   Diez movimientos históricos MEX–PBI carecen de coordenadas en Gold y
   permanecen fuera del dibujo, declarados como falta de geografía.

**Propuesta adicional explícita en la preview máxima:**
`--include-existing-us-estimates` permite visualizar frecuencias históricas
estimadas de EE. UU. cuando no gana una ruta observada. Está desactivada por
defecto. No combina un trimestre BTS parcial con estimaciones de sus meses
faltantes; esos meses se consultan por separado. Cambia una prioridad de fuente
del mapa y requiere aprobación antes de producción; no constituye un modelo nuevo.

La preview no lleva `publication_manifest.json` ni recibo de publicación. Sus
datos ampliados y su matriz permanecen privados; el PR público contiene código,
pruebas y la matriz de la versión ya publicada. Finanzas, mezcla y los cuatro
JSON de análisis se exigen idénticos a la publicación aprobada.

## Reproducir y revisar

```bash
# Matriz de producción aprobada; solo lectura:
python -m scripts.research.flight_coverage --private-root /ruta/al/respaldo \
  --site site --out analysis_runs/research/coverage-published
# Después de confirmar en Git las entradas de compilación:
python -m scripts.research.build_flight_coverage_preview \
  --out analysis_runs/research/coverage-preview --include-existing-us-estimates
python -m scripts.research.flight_coverage --private-root /ruta/al/respaldo \
  --site analysis_runs/research/coverage-preview \
  --independent-map-periods --out analysis_runs/research/coverage-candidate
```

El constructor usa los pins externos ya aprobados del proyecto para verificar
la publicación base. No los deriva de archivos nuevos. Requiere Gold restaurado,
Python y dependencias web; no llama APIs ni escribe aprobaciones. La evidencia
de pruebas, navegador y revisión del commit exacto queda en el PR de la ampliación.
