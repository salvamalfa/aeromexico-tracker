# Actualización por lotes: entrega documental de fase 1

Corte de investigación: 13 octubre 2026. Alcance: catálogo y calendario,
dependencias de datos y propuesta de continuidad sin capturas AeroDataBox
recurrentes. Sin implementación del coordinador, cambios de datos/dashboard,
compras, cancelación, secretos, workflows nuevos ni despliegue.

## Problema y entregables

Las ingestas y contratos existentes no enlazan descubrimiento de publicaciones
con actualización del sitio. Hay límites temporales en parsers y catálogos
cacheados; una fuente más reciente no implica periodo incorporado al dashboard.
La fase documenta esa distancia antes de implementar autonomía.

- [Catálogo y calendario](../catalogo-fuentes-calendario.md): productos, grano,
  cobertura, adquisición, dependencias y fechas oficiales frente a ventanas.
- [Anexos verificables](../referencias/actualizacion-fase1-20261013/): las 29
  claves de fuente, 99 métricas (34 seleccionadas), 93 presentes en hechos de
  aerolínea y 43 tablas Gold públicas.
- [Propuesta de salida](../plan-salida-aerodatabox.md): preservar agregados
  reportados por aerolínea y rutas BTS observadas; futura retirada por
  procedencia de pasajeros/vuelos/asientos/ocupación estimados.
- README, REPO_MAP y ROADMAP enlazan los entregables activos. El expediente
  privado conserva evidencia de periodos y presupuesto; sus procedimientos
  y pendientes vigentes pertenecen al README privado, no al informe fechado.

La propuesta agrupa una ronda mensual desde el primer hábil en/después del 15
y una trimestral según publicaciones centrales reales, con reprogramaciones
acotadas y periodos independientes. No se creó ningún schedule.

## Procedencia y verificación

Inventario leído del código/Gold público `ea88008` y respaldo privado `701eaf1`.
Los CSV contienen metadatos ya públicos, sin cubos privados ni observaciones
nuevas; `inventario.json` conserva conteos, alcance y SHA-256 de sus bytes Git.

Controles completados: claves únicas y correspondencia exacta CSV↔YAML/Gold,
43 conteos de tabla, enlaces locales, JSON, tres checksums de archivos
comprometidos, `git diff --check` y revisión independiente de fuentes,
calendario, cobertura y privacidad. Se corrigieron la frontera para conservar
ANAC observado y la referencia al producto CAA Flight Punctuality.

En el head documental `0b494c0`, la [CI](https://github.com/salvamalfa/aeromexico-tracker/actions/runs/38486573505)
terminó SUCCESS: jobs `test` y `web`. La integración usa los checks del head
final y revisiones sin hilos pendientes. No se repitió la suite completa local
con insumos privados, porque no cambia código ni datos. La inspección privada
verificó 89 archivos de once manifiestos y cobertura de cuatro combinados;
no se recalculó el snapshot ni se consultó una API pagada.

Precisiones de revisión: costes 360/720/2.176 condicionados a tarifa efectiva de
dos unidades por ventana de doce horas, con control de requests/bandwidth y
créditos; excepción de caché de derivados no prueba derecho de publicación
tras cancelar. No se borró contenido ni se cambió exposición del sitio.

## Límites y siguiente paso

AFAC PDF agosto disponible no demuestra fecha de primera publicación ni edición
compatible de ambos XLSX de marginales. BTS anuncia meses nuevos en historial,
pero falta comprobar el máximo mes efectivamente descargable MX-US. Un 403 o
desafío de navegador es un fallo de acceso, no ausencia de datos.

No existe semilla septiembre: agosto se capturó en septiembre. Saldo absoluto,
tarifa, término efectivo y condiciones de cuenta/licencia permanecen sin
verificar en el expediente privado; ningún presupuesto es autorización de compra.
El alcance de UI y la derivación compartida siguen como propuesta, no implementación.

La integración autorizada es exclusivamente documental. Antes de una fase
funcional, definir aceptación del lote y frontera de aprobación/publicación;
antes de una captura, satisfacer el procedimiento privado y aprobar paquete/topes.
