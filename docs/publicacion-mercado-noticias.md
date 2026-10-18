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
`6534f8760546e9649996ffbd75fc5cbe73ecbcd3d96c58de3c4b9b14782e9aee`,
con Vuelos `8b5dd73a3c827b6e6cdee12addc4e4bbd73eede6` y los ajustes visuales
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

El dueño aprobó los tres pares técnicos exactos después de sus auditorías,
el 18 de octubre a las 21:16:59 UTC. El expediente conserva el mensaje real;
la aprobación se registró mediante el ciclo oficial como eventos 88–90.
Industria `e2906ca73927d3f57d74df264446841f4da23967730532fb478cfe126477a84a`,
Viva `afb0f464133f5a01fc6d42ebbd0a2fcdac79e2180f3e7481ad3fa6406b78041c`
y Volaris `1c96fa4d8fdd1238cd8b4dfe64ad245a0723227efdf093657efc2e4e6dd6fbcb`
conservan el contenido financiero auditado. Las auditorías 85–87 y aprobaciones
históricas permanecen intactas. La autorización no cubre otra huella.

El gate normal produjo 795 archivos desde `e69cfe0` y el verificador pasó.
La UI firmada pasa a 1440/390 con API/worker y proveedor mock. La suite completa
del sitio firmado está en ejecución. Una prueba histórica que descartaba
programación en celdas observadas se corrigió para comprobar la retención
independiente y reconciliar los 897 movimientos programados LAX–MEX con Gold;
el código de producto, las identidades aprobadas y los datos permanecen iguales.
Integración y comprobación productiva esperan el cierre de esta validación.
Las propuestas de huellas fd41, abbcf12 y a1de751 quedaron superadas antes de importar
auditorías; el ledger permanece en 84. La huella indicada arriba incorpora la
corrección final de períodos de Vuelos y el cierre reforzado de dependencias:
todo `src/**/*.py` participa en la identidad de aprobación, incluidas
dependencias transitivas de evidencia y capacidad. El alcance conservador también
exige nueva revisión ante cambios Python ajenos a la presentación. Se prueban
mutaciones, altas y bajas de módulos para invalidar identidades obsoletas. El cierre de CI contempla los perfiles
firmados histórico y candidato, con expectativas exactas y sin omitir pruebas.
Pendientes: suite del sitio firmado, CI/revisión del artefacto exacto,
publicación/verificación, skills por fuente, coordinador mensual/trimestral,
Noticias mensual y limpieza futura con dependencias.
