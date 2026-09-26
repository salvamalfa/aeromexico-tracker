# 15 — Etapa 10: Página interactiva “Estructura de datos”

## Objetivo

Explicar de forma visual, interactiva y comprensible cómo la información pública se
convierte en datos confiables, análisis y decisiones dentro del tracker. La página debe
servir tanto a una persona de negocio como a un perfil técnico, sin convertir rutas y
nombres internos en el primer impacto visual.

## Navegación y tecnología

- Añadir la undécima página de Streamlit con título `Estructura de datos`, ruta
  `/estructura-datos` y posición entre `Salud de datos` y `Glosario`.
- Implementar la experiencia con `st.html(..., unsafe_allow_javascript=True)`.
- Mantener HTML, CSS y JavaScript locales, sin CDN, paquetes nuevos ni descargas en
  runtime.
- Generar todo contenido dinámico desde metadata validada y escapar cada valor antes de
  insertarlo en HTML o atributos.

## Embudo principal

La vista inicial debe mostrar cinco niveles conectados permanentemente con flechas:

1. **Fuentes públicas:** SEC/EDGAR, BMV, AFAC, BTS, Banxico, EIA, aeropuertos,
   mercado, peers y fuentes regulatorias.
2. **Captura y preservación:** descarga, conservación del original y detección de
   nuevas versiones.
3. **Limpieza y estandarización:** parsing, tipado, periodos, monedas, unidades y
   nombres consistentes.
4. **Modelo de negocio y análisis:** dimensiones, hechos, vistas, forecast, anomalías y
   estudios.
5. **Producto:** DuckDB, páginas de Streamlit, gráficas y narrativa.

Las tarjetas muestran primero una explicación corta de negocio. Rutas relativas,
tablas, campos, grano, controles y linaje aparecen únicamente en el detalle.

## Interacciones

- Hover o foco muestra explicación, cobertura, actualización y responsable.
- `Ver detalle` mantiene la tarjeta expandida o volteada hasta cerrarla.
- Toque móvil ofrece la misma información sin depender del hover.
- Las fuentes incluyen `Ir a la fuente oficial` y, cuando exista una URL pública
  estable, `Abrir archivo fuente`.
- Si no existe enlace estable al archivo, se muestra la página de origen y se explica
  la limitación; nunca se presenta una ruta local como enlace útil.
- Los ejemplos de parsing muestran transformaciones reales, como porcentaje publicado
  a fracción normalizada, moneda reportada a valor tipado y trimestre textual a
  `period_id`.
- No se muestran correos, secretos, rutas absolutas ni metadata no pública.

## Relaciones Gold

Mostrar un esquema estrella ordenado por significado, no el ERD completo amontonado:

- **Quién:** aerolínea o grupo.
- **Cuándo:** periodo.
- **Qué:** métrica.
- **Dónde:** ruta, aeropuerto o grupo aeroportuario.
- **Qué ocurrió:** hechos.
- **Qué consume el negocio:** vistas y resultados analíticos.

Las relaciones y nombres técnicos se generan desde contratos y catálogo. La vista
inicial usa nombres comprensibles; `Ver nombres técnicos` revela tabla, claves y grano.
Seleccionar una tabla muestra propósito, entradas, salidas, campos principales y páginas
del dashboard que la consumen.

## Seguridad, accesibilidad y rendimiento

- No usar `fetch`, XHR, WebSocket, scripts externos, imports remotos ni recursos CDN.
- Escapar metadata y validar URLs contra el catálogo permitido.
- Mantener acceso equivalente por mouse, teclado y toque; usar HTML semántico, foco
  visible, estados ARIA y regiones anunciables.
- Respetar temas claro/oscuro y `prefers-reduced-motion`.
- Funcionar sin solapamientos en escritorio, 736 px y 360 px.
- Mantener la página autocontenida y sin consultas pesadas durante cada rerun.

## Entregables

- Página `Estructura de datos` y adaptador de metadata.
- Pruebas de navegación, seguridad, contenido, relaciones e interacciones.
- Validación de las once páginas y QA visual responsive.
- Documentación del recorrido del dashboard.
- `docs/etapas/etapa-10-reporte.md`.

## Gate

Primero se presenta una versión local para anotaciones. Solo después de aprobación visual
explícita se publica en el repositorio remoto y se verifica el enlace profundo público.
La publicación no forma parte de la primera entrega local de esta etapa.
