# Mercado: ajustes de revisión visual del 18 de octubre de 2026

PR #135, rama `codex/market-tab-20261015`, base original master
`40a63d1905afde97ae8e3f8671c8217aafacc4aa`. Se revisaron los píxeles de las
capturas anotadas del dueño antes de editar. Esta etapa conserva el PR en
borrador; no integra ni publica, ni modifica la rama de Vuelos del otro encargo.

## Cambios y decisiones

- El trimestre superior es el único selector de fecha de Mercado. Indicadores,
  tabla y comparación interanual usan ese trimestre completo; la historia mensual
  se corta al final de ese trimestre y lo destaca. Cambiar segmento o aerolínea
  conserva el trimestre global, también para el contexto del chat.
- Se retiran Grano, Corte AFAC, Demanda por aeropuerto, Universo y cálculo y
  los párrafos explicativos bajo el título y al pie. El botón de información
  conserva fuente, universo mexicano, Connect, pasajeros por tramo, fórmula,
  corte y captura en una ventana que se puede abrir desde móvil y teclado.
- Se mantienen Gold, fuentes, históricos, cálculos, exportaciones aeroportuarias
  y sus controles. Ningún faltante se convierte en cero. La exposición actual
  de Gold se aclara en `docs/gold-exposure.md`; el inventario fechado al 15 de
  octubre conserva su escenario histórico de 9/23, frente al actual 7/23.

## Verificación

La regresión incluye aritmética con bases comparables y ausentes; cambio global
entre 1T26 y 2T26; truncamiento de las series; indicadores; segmento; contexto
del chat; entrada a Mercado durante la carga inicial; navegación entre pestañas
y ausencia de peticiones al payload aeroportuario desde esta pestaña.
Los resultados exactos de CI, revisión Codex y capturas desktop/móvil se
adjuntan al PR y al traspaso de esta etapa, identificando el commit completo.
Las previews se generan desde el código y conservan su identidad de Library.

## Pendientes

La aprobación visual condicionada a estos cambios no aprueba datos nuevos,
corpus de Noticias, integración ni publicación. La presentación técnica final
se debe vincular a los nuevos commits por separado. Skills por fuente,
coordinador mensual/trimestral, Noticias mensual, aprobaciones y limpieza futura
siguen pendientes. No se habilitó cron ni se borró o archivó ningún dato.
