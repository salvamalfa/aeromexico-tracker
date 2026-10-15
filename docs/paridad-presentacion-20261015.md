# Paridad de presentación: diagnóstico y decisión pendiente (15 octubre 2026)

Estado: **presentación no verificada; exportación/publicación bloqueadas**. Este diagnóstico no importa versiones, no escribe aprobaciones y no autoriza publicar.

## Control que falla y origen

Los dos controles `test_site_flights_and_executive_data_match_a_fresh_export` y `test_reading_tab_narrative_matches_the_approved_analysis` fallan con `Entity implementation changed: import and audit a new version`. Se reprodujeron los mismos dos fallos en las dos ramas y en un checkout limpio de master `40a63d1905afde97ae8e3f8671c8217aafacc4aa`, con los mismos insumos restaurados. Es una desalineación heredada de master, además de los cambios técnicos propios de cada pestaña.

El control `entity_adapter.code_version()` incluye entidades/configuración/lock, análisis, publicación, exportadores, contratos web y código de interfaz. `require_current_presentation()` exige igualdad exacta con la versión registrada antes de exportar. No se excluyen las pestañas de su huella. Ambas propuestas refuerzan el selector incluyendo los constructores nuevos `src/dashboard/market_demand.py`, `src/dashboard/news.py` y `src/conversational_analytics/news_projection.py` cuando existen en su rama: modificar cálculos, cuarentena o proyección invalida la aprobación técnica anterior. No se modifica la condición de igualdad ni se aprueba una versión.

Las tres entidades (industria, Viva y Volaris) guardan `8fc1d53128ae8a0cc795f29ae944e37787bb280f6025ec66b6a8b1cbc1f6382f`, que coincide exactamente con el árbol `6d8da2c4c0b96371c26521aedb5828610451d03a`. Master usa `29a4b6b87c52f29de1c450d23a335f82647af0b5285cba1f992bb9e2f99a693f`, también presente en el commit del manifiesto publicado. Entre esas versiones cambiaron doce componentes: `src/publish/frozen_data.py`, `src/publish/gate.py`, `web/index.html` y nueve módulos/estilos de Vuelos. El JSON adjunto enumera cada ruta y sus hashes, junto a los cambios de esta rama. No se toca la rama de Vuelos.

## Evidencia conservada

Se repitió la validación de fuentes y cálculos de las cuatro versiones seleccionadas por el manifiesto. Las tesis, resúmenes y **68 afirmaciones públicas** coinciden literalmente con el resultado recalculado (Aeroméxico 18, industria 16, Viva 18, Volaris 16). El prompt sigue igual. El registro histórico de Aeroméxico supera su control legado; las otras tres versiones quedan bloqueadas por su huella técnica. Los estados y eventos de aprobación existentes permanecen iguales.

En directorios temporales se compararon exclusivamente los payloads numéricos recién construidos de Lectura ejecutiva y Vuelos con los publicados: igualdad exacta en ambos. Esto aporta evidencia de datos sin cambios; no sustituye el control completo de presentación ni autoriza exportar. Las cuatro tablas Gold privadas suman 348215 bytes y se verifican por hash local; el reporte no contiene filas privadas. Gold, `site/`, los registros y tesis de análisis, la skill y el índice aprobado no cambian respecto de master. Cambia únicamente el selector técnico de dependencias de análisis para añadir los constructores/proyección nuevos; esa ampliación fortalece el control.

## Decisión mínima preparada

Para poder exportar tras revisar el código, hay que importar/auditar **tres versiones técnicas** vinculadas a la huella final elegida (industria, Viva, Volaris), conservando evidencia, cálculos y las tesis existentes, y obtener la aprobación explícita que exige el ciclo de vida. El diagnóstico calcula sus identificadores propuestos en memoria, marcados `unapproved_not_written`; no crea ni aprueba registros. Una integración posterior de ambas ramas produciría otra huella que debe revisarse en su conjunto.

No se solicita cambiar la conclusión económica ni se declara la presentación verificada. La decisión sobre las once noticias candidatas y las autorizaciones de integración/publicación son independientes. Las previews son candidatas y llevan ese aviso.

## Reproducción

```sh
uv run python -m scripts.audit.presentation_parity --out /tmp/presentation-parity.json
uv run pytest --require-local-data -q tests/test_site_parity.py::test_site_flights_and_executive_data_match_a_fresh_export tests/test_site_parity.py::test_reading_tab_narrative_matches_the_approved_analysis
```

La segunda orden conserva los dos fallos mientras no exista una nueva versión técnica aprobada. El diagnóstico de la primera compara los componentes con el selector de producción para evitar atribuir el fallo a una aproximación distinta.

Evidencia de la rama actual: [directorio de reportes JSON reproducibles](referencias/presentation-parity-20261015/). Los insumos privados solo se describen por conteo y tamaño agregados; se omiten nombres, tamaños individuales y hashes.

El reporte v2 registra `evaluated_commit`, su árbol y el SHA del propio generador; exige además que el código de presentación del worktree coincida con ese commit. Se regenera después de las correcciones de código. Guardar el JSON crea necesariamente un commit documental posterior: el artefacto no puede incluir su propio hash de commit. La huella de componentes y del generador permiten verificar que ese commit documental conserva exactamente el código evaluado.
