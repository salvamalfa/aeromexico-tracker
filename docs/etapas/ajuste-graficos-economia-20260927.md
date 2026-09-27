# Ajuste de gráficos de Economía unitaria

Fecha: 2026-09-27

## Diagnóstico

Los tres gráficos de Economía unitaria se dibujan al cargar la página, mientras
su panel está oculto. Al abrirlo, `shell/tabs.ts` intentaba recalcular su tamaño
con `window.Plotly`, pero la aplicación importa Plotly como módulo local y nunca
define esa variable global. Por eso el SVG conservaba dimensiones incorrectas:
el gráfico ancho quedaba comprimido y los dos gráficos inferiores podían
desbordar sus tarjetas.

## Cambio

El manejador de pestañas ahora importa la instancia local de Plotly y llama a
`Plots.resize` para cada gráfico del panel visible antes de anunciar el cambio
de pestaña. Se añadió una verificación al smoke test del dashboard para esperar
y comprobar que los SVG de los tres gráficos coincidan con el ancho de sus
contenedores.

## Validación y límites

- `pytest tests/test_web_page_smoke.py -q`: 4 pruebas aprobadas; el smoke test
  comprueba que los tres SVG ocupen el ancho de sus contenedores al mostrar la
  pestaña.
- `npm run check` y `npm run build`: aprobados.
- `git diff --check`: aprobado.

La corrección modifica el código fuente y no publica una nueva versión de
GitHub Pages; la publicación sigue sujeta a instrucción explícita del dueño.
