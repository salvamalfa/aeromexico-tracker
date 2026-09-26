# GOAL — pegar esto en `/goal` de Claude Code

---

## Objetivo

Construir, por etapas y con aprobación humana entre cada una, un sistema completo de
ingesta, consolidación, análisis y visualización de toda la información pública
disponible sobre **Grupo Aeroméxico S.A.B. de C.V.** (ticker AERO, NYSE + BMV,
CIK EDGAR 1561861), culminando en un dashboard analítico trimestral orientado a negocio.

El plan completo está en `docs/plan/`. **Léelo antes de escribir una sola línea de código.**

## Orden de lectura obligatorio

1. `docs/plan/README.md`
2. `docs/plan/00-contexto-y-principios.md`
3. `docs/plan/01-arquitectura-y-convenciones.md`
4. El archivo de la etapa que toca ejecutar
5. `docs/plan/13-criterios-de-aceptacion.md` (sección de esa etapa) antes de cerrar

## Reglas de ejecución no negociables

1. **Trabajo por etapas.** Ejecuta UNA etapa a la vez. Al terminar, presenta resultados
   y **detente**. No continúes a la siguiente etapa sin un "go" explícito del usuario.
2. **La calidad manda sobre la velocidad.** Es preferible una etapa que tarda tres
   sesiones y queda impecable, que cinco etapas a medias. La Etapa 0 y la Etapa 1
   deben quedar perfectas.
3. **Pide autorización antes de instalar.** Si necesitas DuckDB, Playwright, un
   paquete de Python, Node, o cualquier cosa que no esté en la máquina, **pregunta
   primero**, explica para qué la necesitas y espera el sí.
4. **Usa computer use cuando el acceso programático falle.** Varias fuentes (AFAC en
   gob.mx, algunos portales de IR, BMV) tienen protección anti-bot que bloquea `requests`
   y `curl`. Ver `docs/plan/12-computer-use-playbook.md`. Antes de usar el navegador o
   controlar la pantalla, avisa al usuario qué vas a hacer.
5. **Nunca inventes datos.** Si no puedes obtener una cifra, la marcas como faltante y
   lo reportas. Jamás rellenes con estimaciones sin etiquetarlas explícitamente como tales.
6. **Toda descarga se preserva cruda.** Nada se sobrescribe. La capa bronze es inmutable
   y con hash. Ver `01-arquitectura-y-convenciones.md`.
7. **Valida contra cifras ancla.** Cada etapa tiene cifras conocidas contra las cuales
   comprobar el pipeline. Si no cuadran, investiga y reporta; no ajustes el código para
   que cuadre artificialmente.
8. **Documenta mientras trabajas.** Al cerrar cada etapa escribe
   `docs/etapas/etapa-N-reporte.md` con el formato del README.
9. **Pregunta cuando haya ambigüedad real.** El usuario prefiere una pregunta a un
   supuesto silencioso que se descubre tres etapas después.

## Contexto del usuario

Analista de datos (Python, SQL, BigQuery). Sabe de datos, no necesita explicaciones
básicas de programación, pero sí quiere entender las decisiones de arquitectura.
El dashboard es un proyecto de portafolio personal (no comercial). Solo se usan
fuentes de datos gratuitas y abiertas.

## Primer paso

Lee la documentación indicada, luego ejecuta la **Etapa 0** descrita en
`docs/plan/02-etapa-0-setup.md`. Antes de empezar a implementar, muéstrame tu plan
de ataque para esa etapa y la lista de cosas que necesitas instalar.
