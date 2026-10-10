# F2.9 · Admisión presupuestal de finalización

- La reserva de esta finalización usa 30 turnos completos fijados por hash: 14 Luna medium, 15 Luna max y una respuesta Sol low recuperada por GET; excluye el fallo original de uso desconocido y no inventa filas para el progreso agregado perdido.
- El promedio descriptivo es 50,792 tokens de entrada y 1,535 de salida; el margen operativo de 35% fija 68,570/2,073 por solicitud. La muestra mezcla candidatos y no es un límite estadístico.
- Se valora la entrada a US$2.50/M (cache-write, sin descuento de cache) y la salida a US$10/M, con multiplicadores de contexto largo del catálogo fijado SHA-256 `9744c985f051c898a8af6e8d3c8766c6885e77d8a13d55b72e30427b15468d4c`.
- Las 29 solicitudes planificadas (14 Sol low reemplazo/nunca intentado y 15 Sol medium, sin selección por calidad) reservan US$5.572495; con arrastre estimado de US$2.274144375 suman US$7.846639375 de los US$8 autorizados.
- El presupuesto aprobado estima US$4.254293–US$5.284293 para ese lote (JSON SHA-256 `0f94efcae33177cde6e1cfc71415a3caa724757b0f053cca82b1e63d18f27803`); la estimación y el margen son operativos, no tope de factura ni garantía de gasto.
- El control empírico se limita a esta finalización; la reserva genérica de producción conserva el cálculo actual. Simulaciones offline del scheduler completaron las 29 ranuras bajo ambos extremos aprobados; no se llamó al proveedor.
