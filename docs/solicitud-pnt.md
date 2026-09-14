# Solicitud de acceso a la información — paquete listo para la PNT

Todo lo necesario para presentar la solicitud a AFAC en la Plataforma Nacional de
Transparencia. El texto está redactado para pegarse tal cual.

## Estado

| Vía | Estado |
|---|---|
| Correo a `transparencia@afac.gob.mx` | **Rebotado.** `550 5.4.1 Recipient address rejected: Access denied` desde `namprd05.prod.outlook.com`. Rechazo a nivel de destinatario, no de contenido |
| Copia a `maria.bello@sict.gob.mx` | **Entregada.** Titular de la Unidad de Transparencia de SICT, que funge como la de AFAC. Recibió la solicitud original y su corrección de fundamentos |
| Plataforma Nacional de Transparencia | **Pendiente.** Es la vía recomendada |

El rebote es `5.4.1`, no `5.7.x`: el servidor rechazó a quién iba dirigido, no lo
que decía. Las causas posibles son que la dirección ya no exista en el directorio
del tenant, que el buzón solo acepte remitentes internos, o que una regla bloquee
dominios de correo personal. Exchange Online devuelve el mismo código en los tres
casos a propósito, para no revelar qué direcciones existen.

## Datos del formulario

| Campo | Valor |
|---|---|
| Sujeto obligado | Agencia Federal de Aviación Civil |
| Ámbito | Federal |
| Medio para recibir notificaciones | Correo electrónico registrado en la cuenta |
| Modalidad de entrega | Entrega por Internet en la Plataforma Nacional |
| Formato | Archivo electrónico (XLSX o CSV) |
| Tipo de solicitud | Información pública |

## Texto para pegar en el campo de descripción

```
Solicito, en formato abierto y procesable por medios electrónicos (XLSX o CSV),
la estadística operacional de servicio regular nacional desagregada
SIMULTÁNEAMENTE por: 1) par de ciudades origen-destino, 2) permisionaria o
concesionaria, y 3) mes. Para cada combinación de esas tres variables solicito
vuelos realizados, asientos ofrecidos y pasajeros transportados. Periodo: de
enero de 2024 al mes más reciente disponible.

No se solicita procesamiento ni generación de información nueva, sino el
registro tal como esa Agencia lo recibe y lo conserva, por lo que no resulta
aplicable el artículo 131 de la Ley General de Transparencia y Acceso a la
Información Pública.

Esa Agencia publica dos productos derivados de esa misma base: la "Estadística
operacional origen-destino / Traffic Statistics by City Pairs", que reporta
pasajeros por par de ciudades y mes sin desagregar por aerolínea; y el "Resumen
operacional por aerolínea / Airline Statistics Summary", que reporta pasajeros
por empresa y mes sin desagregar por ruta. Ambos son agregados marginales de un
mismo universo. Para el primer trimestre de 2025, la suma de todos los pares de
ciudades del primer producto asciende a 14,799,004 pasajeros y la suma de todas
las empresas del segundo a 14,799,050 pasajeros: una diferencia de 46 pasajeros,
equivalente a 0.0003%. Dos publicaciones independientes solo coinciden en ese
grado si ambas se construyen a partir de un mismo registro que ya contiene, de
forma conjunta, la ruta y la empresa. Ese registro es el que se solicita.

Lo anterior es congruente con el artículo 84 de la Ley de Aviación Civil, que
obliga a las concesionarias, asignatarias, operadoras aéreas y permisionarias
del servicio de transporte aéreo comercial a entregar mensualmente a esa Agencia
informes, bitácoras, estadísticas y reportes, y dispone que la Agencia dará
seguimiento a la información presentada y la publicará trimestralmente.

En caso de que se considere que la información reviste carácter confidencial por
corresponder a empresas determinadas, solicito subsidiariamente y en este orden
de preferencia: 1) versión pública en términos del artículo 120 de la Ley
General de Transparencia y Acceso a la Información Pública; 2) la misma
desagregación con las empresas agrupadas por grupo aeronáutico; 3) la misma
desagregación limitada a las rutas en las que operen tres o más permisionarias,
supuesto en el que no resulta identificable la posición individual de una
empresa determinada.
```

## Fundamentos vigentes

Aplica la Ley General de Transparencia y Acceso a la Información Pública
**publicada en el DOF el 20 de marzo de 2025**, que abrogó la anterior. Las
citas de la ley de 2015 que circulan en plantillas viejas ya no corresponden.

| Artículo | Contenido |
|---|---|
| 124 | Vías de presentación de la solicitud, incluida la Plataforma Nacional |
| 125 | Folio automático en la Plataforma; si se presenta por otra vía, la Unidad de Transparencia debe registrarla en la Plataforma en cinco días y enviar acuse |
| 126 | Requisitos máximos exigibles: medio para notificaciones, descripción y modalidad |
| 131 | Entrega de documentos existentes, sin obligación de elaborar documentos nuevos |
| 134 | Plazo de respuesta: veinte días, ampliable excepcionalmente diez más |
| 135 | El acceso se da en la modalidad de entrega elegida |
| 120 | Versión pública cuando el documento contiene partes clasificadas |
| 3, fr. XII | Definición de Formatos Abiertos |

## Qué esperar y qué hacer después

1. **Acuse con folio**, inmediato si se presenta por la Plataforma.
2. **Respuesta en veinte días hábiles**, prorrogables diez.
3. Si responden remitiendo a las publicaciones ya existentes, **no es una
   respuesta completa**: esos son los agregados marginales, no el registro
   solicitado. Procede recurso de revisión señalando ese punto.
4. Si clasifican la información, revisar que apliquen prueba de daño y pedir la
   versión pública del artículo 120.
5. Si no hay respuesta en plazo, procede recurso de revisión por falta de
   respuesta.

Si llega el acuse, conviene mencionar en el seguimiento que existe una gestión
previa por correo ante la Unidad de Transparencia de SICT, para que no se abran
dos expedientes por el mismo asunto.

## Para qué sirve la respuesta

Un trimestre de datos reales convierte en **medición** lo que hoy es un supuesto:
la exactitud del estimador está medida contra rutas México–Estados Unidos
(1.98 pp de error en participación con semilla de vuelos), pero el mercado
doméstico tiene una estructura competitiva distinta. Con la respuesta se calibra
el residuo real y se puede publicar una banda de error doméstica en vez de una
extrapolada. Ver [`estimador-ruta-aerolinea.md`](estimador-ruta-aerolinea.md).
