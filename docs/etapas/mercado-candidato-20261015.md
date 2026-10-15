# Mercado: candidato independiente del 15 de octubre de 2026

Base: `40a63d1905afde97ae8e3f8671c8217aafacc4aa` de master. Rama:
`codex/market-tab-20261015`. Alcance autorizado: implementación y PR en borrador;
integración y publicación requieren decisiones independientes.

Se mueve la participación AFAC desde Lectura ejecutiva a Mercado, con gráfica
de 480 px y selección mensual/trimestral, segmento y aerolíneas. Tamaño,
crecimiento interanual, cambio absoluto, participación, cambio en puntos y
contribución usan el mismo periodo/segmento de las aerolíneas mexicanas.
Se incluye el resto para reconciliar la contribución con el crecimiento total.
Corte AFAC: junio 2026; último trimestre completo: 2T26; captura: 13 sep 2026.

`market-demand.json` se genera desde Gold público con claves únicas,
faltantes nulos y bases por el mismo aeropuerto/grupo un año antes. Tiene
cortes hasta julio 2026; ASUR no tiene todos esos meses. Se muestran todas las
compañías en cada aeropuerto y México en los grupos. No representa viajeros
únicos ni todo el mercado nacional; no se suman aeropuerto y grupo ni se
atribuyen sus pasajeros a Aeroméxico. El detalle OMA se retiene por la
reconciliación documentada en `docs/gold-exposure.md`.

No se modifican Gold, `site/`, tesis, manifests de aprobación, permisos,
credenciales ni cron. Se restauraron 2,261 archivos privados verificados y los
cuatro combinados actuales cotejados por SHA-256 contra Git; el warehouse local
se reconstruyó con Gold actual. El payload de Mercado conserva su contrato.
Se añade una exportación de demanda independiente y enlaces de procedencia.

El contrato de contexto acepta las pestañas Mercado y Noticias sin ampliar
herramientas ni acceso a evidencia. La base de compatibilidad de contexto y
pruebas es idéntica entre las dos propuestas; cada UI se implementa en su rama.

Validación: cálculos sintéticos de reconciliación, faltantes/bases cero,
claves duplicadas y cuarentena; TypeScript, Vitest, build, comandos exactos de
CI y smoke desktop/móvil. Las vistas previas autocontenidas embeben datos
públicos y el mismo bundle compilado; el chat real no está conectado en ellas.
Las capturas y el registro de navegador se entregan en Library. Los resultados
finales de CI y la prueba combinada quedan en el PR, sin merge ni deploy.

Pendientes: revisión independiente, aprobación para integrar/publicar, corregir
el parser OMA en un cambio revisable, y decidir las skills por fuente y el
coordinador mensual/trimestral. No se habilita automatización en esta etapa.


## Límite de aprobación comprobado en la validación final

El guard `src/analysis_agent/entity_adapter.py::require_current_presentation`
conserva una huella amplia que incluye `web/src`, los contratos y el código de
exportación/publicación. Las tesis publicadas no cambian, pero una interfaz
nueva no coincide con su versión técnica aprobada. La suite con datos privados
lo detecta en dos pruebas de paridad de `tests/test_site_parity.py`; no se
modificaron recibos, firmas ni aprobaciones para hacerlas pasar. El despliegue
requiere resolver esa revisión técnica con el dueño, además de aprobar el PR.
Las previews reutilizan los payloads ya publicados y se marcan candidatas;
no equivalen a una regeneración aprobada del sitio.

La demanda aeroportuaria nueva no habilita herramientas del chat. Se omite su
atajo contextual y no se envía un identificador de tarjeta que el backend
rechazaría. El chat de participación conserva mes y segmento AFAC seleccionados.
