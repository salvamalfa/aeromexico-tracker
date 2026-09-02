# Etapa 10 — Página interactiva “Estructura de datos”

Fecha de entrega local: 2026-09-01
Estado: IMPLEMENTACIÓN LOCAL COMPLETA — PENDIENTE DE APROBACIÓN VISUAL Y PUBLICACIÓN

## Resumen ejecutivo

Se añadió una undécima página de Streamlit que explica, de arriba abajo, cómo una
fuente pública se convierte en evidencia comparable, análisis y producto. La primera
lectura usa lenguaje de negocio; los nombres de archivos, tablas, campos, contratos y
granos aparecen solo cuando la persona pide detalle.

La página no mantiene un diagrama paralelo al backend. Sus fuentes, conteos, relaciones,
tablas, vistas y consumidores se generan desde el catálogo validado, los contratos
Silver/Gold, el registro central, el SQL semántico y la navegación real. Si esa metadata
no coincide con el recibo validado de Etapa 9, la página falla cerrada y no muestra una
arquitectura parcial.

No se instalaron dependencias, no se descargaron datos, no se modificaron cifras de
negocio y no se publicó nada. La versión pública anterior permanece intacta hasta la
aprobación visual del usuario.

## Qué se construyó

- Registro único de navegación para once páginas, con `Estructura de datos` entre
  `Salud de datos` y `Glosario` y enlace profundo `/estructura-datos`.
- Embudo interactivo de cinco niveles con cuatro conectores permanentes:
  fuentes públicas; captura y preservación; limpieza y estandarización; modelo y
  análisis; producto.
- Veintitrés tarjetas con lectura de negocio inicial, resumen adicional por hover,
  foco o toque y detalle persistente mediante HTML semántico `details/summary`.
- Catálogo visible de 19 fuentes públicas activas agrupadas por función de negocio.
  Cada fuente ofrece página oficial segura y solo seis ofrecen enlace directo a un
  archivo cuando el catálogo demuestra que la URL es pública y estable.
- Ejemplos reales antes → después para porcentaje (`84.4 %` → `0.844`), moneda
  (`US$1,479 million` → `1,479,000,000 USD`) y periodo (`1Q26` → `2026Q1`).
- Esquema estrella interactivo derivado de contratos: dimensiones por quién, cuándo,
  qué y dónde; hecho seleccionable; vistas, resultados y páginas consumidoras.
- Explorador de las 31 tablas Gold con propósito, entradas, salidas, campos
  principales, grano, contrato y páginas consumidoras.
- Toggle que mantiene ocultos los nombres técnicos hasta que la persona los solicita.
- HTML, CSS y JavaScript locales mediante `st.html`; no hay CDN, scripts externos,
  recursos remotos ni llamadas de red en runtime.
- Recibo público compacto `data/gold/_stage9_public_validation.json`, necesario para
  verificar en un checkout limpio el corte de metadata que respalda la página.
- Validador ejecutable de Etapa 10, pruebas de seguridad y regresión, y actualización
  del workflow y del comando `dashboard-validate`.

## Metadata y cobertura mostrada

| Elemento | Resultado |
|---|---:|
| Definiciones de fuente catalogadas | 23 |
| Fuentes públicas activas visibles | 19 |
| Artefactos Bronze catalogados | 752 |
| Pasos del registro central | 32 |
| Datasets Silver | 28 |
| Tablas Gold | 31 |
| Vistas semánticas descubiertas | 21 |
| Relaciones foráneas Gold | 23 |
| Registros con linaje esperado/declarado | 277,805 / 277,805 |
| Relaciones del bridge de linaje | 412,139 |
| Cobertura de linaje | 100% |

Los 752 artefactos siguen en Bronze y no se copiaron al despliegue. La interfaz solo
expone URLs públicas autorizadas y rutas relativas dentro de los paneles técnicos;
nunca muestra rutas absolutas, correo SEC, credenciales o secretos.

## Validaciones automatizadas

| Check | Resultado | Evidencia |
|---|---|---|
| Suite completa | PASS | 186/186 pruebas |
| Suite enfocada Etapa 10 + dashboard | PASS | 51/51 pruebas |
| Aceptación Etapa 10 | PASS | 15/15 controles |
| Regresión Etapa 8 | PASS | 18/18 controles |
| Páginas locales | PASS | 11/11 sin excepciones |
| Navegación | PASS | orden y ruta exactos desde un único registro |
| Metadata | PASS | determinista en dos construcciones |
| Relaciones Gold | PASS | 31/31 tablas y 23/23 relaciones coinciden con contratos |
| Enlaces | PASS | 19 enlaces HTTPS; cero hosts o protocolos no autorizados |
| Seguridad HTML | PASS | metadata adversarial escapada; cero sinks inseguros o recursos remotos |
| Linaje en runtime | PASS | conteos y SHA-256 del bridge, artefactos y ledger coinciden con el recibo |
| Contraste oscuro | PASS | mínimo 7.87:1 en las combinaciones evaluadas |
| Corte del tracker | PASS | usa el último artefacto preservado: 24 ago 2026; no el fin futuro del trimestre |

El validador de regresión midió cargas iniciales de 0.20–0.48 s y reruns de
0.008–0.085 s. La nueva página cargó en 0.36 s y su rerun en 0.008 s en esta corrida.

## QA visual y funcional en navegador local

| Escenario | Resultado observado |
|---|---|
| Escritorio claro, 1280 × 900 | Cinco niveles, cuatro conectores, cinco flechas Gold iniciales, cero overflow y cero excepciones |
| Tablet, 736 × 900 | Introducción y esquema Gold pasan a una columna; ancho raíz 694 px; cero overflow |
| Móvil, 360 × 800 | Tarjetas y detalle en una columna, dimensiones en dos; resumen táctil visible; cero overflow |
| Escritorio oscuro, 1280 × 900 | Tema detectado, título/contexto/sidebar legibles, cinco flechas y cero excepciones |
| Movimiento reducido | Regla local `prefers-reduced-motion` elimina desplazamiento y reduce transiciones a 0.001 ms |
| Apertura y cierre | `aria-expanded` cambia correctamente; botón Cerrar y Escape devuelven foco al control |
| Toque móvil | Abre el mismo detalle persistente sin depender del hover |
| Hecho de grupos aeroportuarios | Ilumina solo periodo y grupo; dibuja dos relaciones, una vista y una página |
| Nombres técnicos | Aparecen únicamente al activar el toggle y las flechas se recalculan |

La prueba oscura detectó inicialmente que el encabezado compartido conservaba colores
claros de la Etapa 8. Se corrigió vinculando el tema calculado del componente con el
chrome de esta ruta; las relaciones de contraste resultantes superan 4.5:1.

## Auditoría independiente y correcciones

Dos revisiones parciales durante la implementación y una auditoría final independiente
se usaron como control de sesgo. La auditoría final no encontró P0 y señaló cinco P1,
todos resueltos antes de este reporte:

1. Un conteo Gold se insertaba sin pasar por el escapador HTML; ahora se escapa y tiene
   prueba adversarial específica.
2. El placeholder del explorador no declaraba sus etiquetas de presentación; se
   corrigió y la suite enfocada pasó de un fallo a 51/51.
3. El recibo público requerido estaba fuera del conjunto de cambios; ahora forma parte
   explícita de la candidata local.
4. Runtime verificaba filas pero no el hash completo del bridge; ahora compara el
   SHA-256 de sus 61.7 MB antes de aceptar el 100% de cobertura.
5. Faltaban reporte y evidencia responsive; se materializaron en este documento y en
   los controles ejecutables de tema, breakpoints y movimiento reducido.

## Qué no funcionó y por qué

1. Streamlit elimina SVG inline dentro de `st.html`. Las relaciones Gold no aparecieron
   en la primera versión; ahora el JavaScript local crea el SVG con APIs DOM seguras y
   solo usa metadata previamente escapada.
2. La primera lectura del tema oscuro dejó el título global con paleta clara. El
   componente ahora propaga únicamente la señal `light/dark` al host de esta página.
3. El pie heredado decía `Datos al 30 Sep 2026` el 1 de septiembre porque confundía el
   fin calendario de un periodo parcial con una fecha de observación. Ahora dice
   `Corte actualizado al 24 ago 2026`, derivado del último artefacto preservado.
4. El hover no existe en pantallas táctiles. A 520 px o menos, y en dispositivos con
   `hover: none`, el resumen adicional permanece visible y el toque abre el detalle.
5. AFAC alcanzó 63 días desde su último periodo (`2026-06-30`) frente al umbral de 62.
   El validador lo reporta como `age_exceeded`; no se interpreta como cero ni se hizo
   una descarga manual dentro de esta etapa sin ingesta.

## Decisiones y supuestos

- Se conservó Streamlit, DuckDB, Parquet y Bronze/Silver/Gold; no se añadió HTML
  separado, framework frontend ni dependencia nueva.
- Las etiquetas amistosas viven en un registro exclusivamente de presentación. Ese
  registro no puede declarar relaciones; contratos, SQL y catálogo siguen siendo la
  autoridad.
- El contenido dinámico se escapa en el servidor y las URLs se aceptan solo si son
  HTTPS, no llevan credenciales ni puerto alterno y pertenecen a hosts autorizados.
- Una fuente sin archivo público estable enlaza a su página oficial y explica la
  limitación. No se fabrican URLs ni se expone Bronze.
- La carga de 61.7 MB del bridge no se hace como DataFrame en cada rerun. Se calcula su
  SHA-256 una vez por fingerprint cacheado, suficiente para detectar cambios con el
  mismo número de filas.
- La página explica el corte materializado; no descarga datos ni entrena modelos al
  abrirse.

## Pendientes y gate humano

- La candidata local está disponible en `http://localhost:8502/estructura-datos` para
  anotaciones.
- La aplicación pública y `docs/deploy-streamlit.md` permanecen deliberadamente en el
  estado de diez páginas de Etapa 8.
- No se hará push, despliegue ni verificación del enlace público
  `/estructura-datos` hasta recibir aprobación visual explícita.
- Después de esa aprobación se actualizará la guía de despliegue, se publicará el mismo
  repositorio, se comprobarán las once páginas y se cerrará definitivamente la etapa.
- La Etapa 11 de rediseño general no se ha iniciado.

## Comandos para reproducir

```powershell
uv run pytest -q
uv run pytest -q tests/test_stage10_structure.py tests/test_dashboard.py
uv run python -m src.dashboard.validate_stage10
uv run python -m src.dashboard.validate_stage8
uv run streamlit run streamlit_app.py
```

## Gate actual

La implementación, seguridad, exactitud de metadata, accesibilidad, responsive, tema,
regresión y documentación de la entrega local cumplen los criterios técnicos. El único
gate abierto es humano: revisar la página con anotaciones y decidir si se aprueba su
publicación. El trabajo se detiene aquí y no avanza al rediseño general.
