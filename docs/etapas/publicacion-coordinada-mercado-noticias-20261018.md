# Preparación de la publicación conjunta · 18 de octubre de 2026

Corte de validación local: 22:27 UTC. Este informe registra la preparación;
los resultados del despliegue real se conservarán en el expediente final y en
el PR #136. No sustituye los informes históricos cerrados de Vuelos ni las
previews visuales aprobadas.

## Resultado y autorización

Mercado usa un trimestre global, participación nacional/internacional ampliada,
tamaño, crecimiento y contribución comparable por aerolínea. La revisión visual
aprobada retiró la sección aeroportuaria; los Gold y sus exportaciones se
conservan. Noticias incorpora filtros de mes, tema, aerolínea y búsqueda desde
el chat, con tres fichas previamente aprobadas. Once candidatas verificadas
permanecen fuera del índice publicado; tres fichas no representan cobertura
mensual completa. Publicación, fecha del hecho y primera captura son campos
distintos. Los resúmenes son breves y originales, sin artículos completos ni
imágenes sin licencia.

El dueño autorizó las tres renovaciones técnicas exactas el 18 de octubre a
las 21:16:59 UTC, después de auditorías independientes 85–87. El ciclo oficial
registró las aprobaciones 88–90. La huella aprobada sigue siendo
`6534f8760546e9649996ffbd75fc5cbe73ecbcd3d96c58de3c4b9b14782e9aee`.
Industria, Viva y Volaris conservan sus textos y cifras; Aeroméxico conserva
su registro histórico. Las cuatro tesis, resúmenes, 68 afirmaciones y el par
financiero firmado reproducen el baseline sin cambios.

El gate normal exportó 795 archivos desde
`e69cfe06ad3414336de7c85872844fc284265a4d`. El verificador pasó. SHA256 de
los bytes del manifiesto:
`b33d97eb52e0dc744ee7d029eddb5c0b3edfa43f67a0484f9ca0466cc7ab2a84`.
Snapshot esperado del backend conjunto:
`d2d6ab679214a686b3d8bab744ce028b317637c6e28b84d3b779d6bef6eb4699`.
Los merges documentales, de pruebas y empaquetado conservan esa identidad.

## Validación y correcciones de las pruebas

La suite completa con `--require-local-data` terminó con **2478 pruebas y
29 subpruebas aprobadas, una omisión prevista, 1429.72 s**. Comenzó en
`c1bfc9455789ded7561b282c0a0e0f01a21ee07b`; las adiciones posteriores de
empaquetado se validaron separadamente sobre el sitio final firmado: tres
pruebas aprobadas en 33.86 s y dos de watchPatterns en 0.05 s. La CI del HEAD
final debe comprobar también esas adiciones antes de integrar #136.

La primera ejecución detectó expectativas históricas desactualizadas, no un
cambio autorizado de cifras: la programación AICM se conserva incluso cuando
coincide con celdas observadas y se reconcilian 897 movimientos LAX–MEX;
el manifiesto compara el conjunto y hashes exactos de contratos opcionales;
y el documento generado de cobertura del chat se actualizó con el renderizador
oficial usando los pins existentes. Una entrada BTS local ausente se restauró
byte a byte desde el respaldo privado verificado, sin descargar datos nuevos
ni modificar Gold. Todos esos casos se volvieron a ejecutar y la suite limpia
completa pasó después.

La UI local firmada pasa a 1440 y 390 px, sin errores JavaScript ni
desbordamiento. Incluye navegación por las cinco pestañas, filtros de Mercado
y Noticias, resultados vacíos correctos y fallback al periodo oficial de
Vuelos. El recorrido del chat usa API/worker reales con proveedor mock y
evidencia citada; no genera turnos pagados en producción.

## Integración, respaldo y límites

Respaldos privados #33 y #34 integrados en ese orden. El último snapshot
verifica 2322 archivos y 1298922535 bytes, once manifiestos derivados sin
diferencias y 48 registros válidos en la proyección; un wrapper histórico
inválido se conserva sin incorporarlo a la proyección. El #33 aclara la
atribución del resultado antiguo de 1733 pruebas a su commit real, sin
reescribir los logs originales.

El código de Vuelos #134 se integró conservando `site/` y el pin de Pages.
Su imagen intermedia falló salud por recursos omitidos del contenedor;
Railway mantuvo el backend anterior saludable. El #138 corrige únicamente
COPY, contexto deny-all y watchPatterns, con regresión de snapshot aislado.
Se debe comprobar la imagen exacta saludable antes de avanzar a #135 y #136.
El [informe de empaquetado](chat-empaquetado-contrato-retenido-20261018.md)
documenta la causa y la validación sin cambiar código de producto.

La [auditoría Gold](../gold-exposure.md) verifica 43 tablas públicas y cuatro
privadas; denominador público analítico de 23, exposición directa 7/23
(~30 %) y amplia 11/23 (~48 %). Conserva inventario, dependencias, tamaños y
tres estudios candidatos a archivo futuro; no se borró ni archivó nada.

La aceptación productiva exige CI y Codex del HEAD exacto, todos los hilos
resueltos, Pages desplegado desde el merge y Railway SUCCESS del mismo commit
con snapshot esperado, más navegador desktop/móvil en la URL pública.
Los recibos de esas comprobaciones se incorporarán al expediente de cierre.

## Pendientes

Skills por fuente (#137 permanece independiente), coordinador mensual y
trimestral, Noticias mensual y aprobación de contenido candidato nuevo,
aprobaciones de futuras publicaciones y limpieza con dependencias. No se
activan cron, candidatos de noticias ni estimaciones adicionales de EE. UU.
