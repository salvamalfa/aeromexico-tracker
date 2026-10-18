# Publicación coordinada de Mercado y Noticias

Plan activo del 18 de octubre de 2026. El dueño autorizó publicar las dos
pestañas revisadas mediante el mensaje de las 19:38:06 UTC en el hilo
`01a13089-a03a-73db-950b-ca38154ae004`. Ese mensaje aprueba la publicación de
la interfaz revisada; no concede aprobación a pares técnicos todavía no auditados.

## Orden y alcance

1. Cerrar las comprobaciones y coordinación de Vuelos #134 y su respaldo #33.
   Conservar el sitio publicado de master hasta la entrega conjunta; los
   artefactos firmados intermedios quedan como evidencia histórica.
2. Integrar el código de Vuelos #134 y después Mercado #135, con `site/`
   idéntico al baseline publicado. Esos pasos no disparan Pages por sí solos.
3. Noticias #136 incorpora la resolución de contexto y ambas pestañas. Congelar
   el código conjunto, auditar una única cohorte técnica Industria/Viva/Volaris,
   obtener aprobación específica posterior y generar el sitio con el gate normal.
4. Cerrar CI y Codex del HEAD exacto, integrar #136, seguir Pages y el backend,
   y verificar commits, manifiestos y UI desktop/móvil desplegados.

La huella de presentación candidata final es
`fd41a49463d985c4c6668a54be66b090cab32e6588181c1f1c794ebaf4a81571`,
con Vuelos `c3aec696228434e32a4290233f313d1e38deee38` y los ajustes visuales
v6 de ambas pestañas. Los merges documentales, pruebas excluidas de la huella
y `site/` generado conservan esa identidad; cualquier cambio a componentes
incluidos exige detenerse y revisar la cohorte exacta antes de exportar.

## Conservación y aceptación

Se verificó el snapshot privado de referencia por 2303 archivos y los once
manifiestos derivados sin diferencias, más los cuatro Gold combinados contra
Git antes de restaurarlos en un checkout aislado. No se altera el expediente
histórico para resolver aprobaciones. Las cuatro tesis, resúmenes y 68
afirmaciones se reproducen literalmente desde sus insumos congelados.

El smoke CI del chat usa un snapshot público sintético firmado y datos de UI
sintéticos acotados: la expansión del mapa productivo no forma parte de esa
prueba de búsqueda de noticias. La comprobación del backend completo es
independiente y se conserva en la evidencia de publicación.

Publicación de Noticias: exclusivamente tres fichas ya aprobadas, sin las once
candidatas. El índice, recibos y pins permanecen intactos. No se habilitan cron,
skills ni calendarios. Las nuevas propuestas técnicas no trasladan la aprobación
82–84 de Vuelos a una huella distinta. Aeroméxico conserva su registro histórico.

Estado: preparación y auditoría; sin merge a master ni despliegue de las pestañas.
Pendientes: cierre de la cohorte y aprobación específica, CI/revisión exactos,
publicación/verificación, skills por fuente, coordinador mensual/trimestral,
Noticias mensual y limpieza futura con dependencias.
