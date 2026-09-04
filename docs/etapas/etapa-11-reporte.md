# Etapa 11 — Prototipo HTML del resumen ejecutivo

Fecha de entrega: 2026-09-04

Estado: COMPLETA — PROTOTIPO LOCAL PENDIENTE DE APROBACIÓN VISUAL

## Resumen ejecutivo

Se construyó una sola Vista ejecutiva, autocontenida y conectada al modelo curado del
tracker. El prototipo no copia las cifras del HTML de referencia: consulta la vista
canónica `v_aeromexico_quarterly`, valida el grano trimestral y genera desde ese mismo
payload las tarjetas, conclusiones, narrativa, gráficas y tabla de detalle.

La cobertura comparable disponible es `2024Q3–2026Q2`, ocho trimestres completos con
RASK, CASK, ASK, factor de ocupación y pasajeros. No se rellenó el histórico
`2021–2024Q2`; cuando no existe un trimestre comparable, la interfaz muestra
`No disponible`.

El resultado permanece en la rama local `stage-11-executive-prototype`. No se cambió
la navegación de Streamlit, no se publicó el prototipo y no se hizo push.

## Qué se construyó

- Modelo de presentación reutilizable en `src/dashboard/executive_summary.py`.
- Generador de HTML autocontenido en `src/dashboard/executive_summary_html.py` y
  comando reproducible en `src/dashboard/build_stage11.py`.
- Hoja visual y comportamiento interactivo locales, sin CDN ni llamadas de red.
- Selector para recorrer los ocho trimestres; actualiza tarjetas, conclusiones,
  narrativa y énfasis de las gráficas.
- Cinco tarjetas: RASK, CASK, ASK, factor de ocupación y pasajeros, cada una con QoQ y
  YoY. El factor de ocupación se compara en puntos porcentuales.
- Gráfica principal RASK/CASK con margen unitario; gráfica de volumen y monetización;
  y mapa de ocupación/RASK con ASK representado por tamaño.
- Historial narrativo y tabla trimestral dentro de desplegables.
- Doce pruebas enfocadas y un validador de doce controles de aceptación.
- Comandos `stage11-prototype` y `stage11-validate` en el `justfile`.

## Datos utilizados

No se descargaron datos ni se modificaron Bronze, Silver, Gold o el warehouse. El
prototipo lee el warehouse existente y usa exclusivamente la vista semántica
`v_aeromexico_quarterly`.

| Elemento | Resultado |
|---|---:|
| Trimestres comparables | 8 |
| Cobertura | 2024Q3–2026Q2 |
| Último artefacto preservado | 24 ago 2026 |
| KPIs por trimestre | 5 |
| Gráficas | 3 |
| Vistas/pestañas generadas | 1 |

## Cifras ancla visibles en 2026Q2

| Métrica | Valor backend | Presentación |
|---|---:|---:|
| Pasajeros | 6,014,000 | 6.01 M |
| ASK | 14,896,088,064 ASK-km | 14.90 mil M |
| Factor de ocupación | 0.849 | 84.9% |
| RASK | 9.9419390758 centavos/ASK-km | 9.94 ¢ |
| CASK | 9.5069792412 centavos/ASK-km | 9.51 ¢ |
| Margen unitario | 0.4349598346 centavos/ASK-km | 0.43 ¢ |

El margen reconcilia con `RASK - CASK`. Para 2026Q2, las tarjetas muestran RASK
`+2.6% QoQ / +10.3% YoY`, CASK `+10.9% / +28.6%`, ASK `+7.7% / +1.9%`, factor de
ocupación `+0.5 pp / -0.8 pp` y pasajeros `+3.9% / -2.7%`.

## Validaciones automatizadas

| Check | Resultado | Evidencia |
|---|---|---|
| Suite completa | PASS | 198/198 pruebas |
| Suite enfocada Etapa 11 | PASS | 12/12 pruebas |
| Aceptación Etapa 11 | PASS | 12/12 controles |
| Fuente única | PASS | `v_aeromexico_quarterly` |
| Cobertura | PASS | ocho periodos únicos, 2024Q3–2026Q2 |
| Reconciliación | PASS | margen y cifras visibles coinciden con el warehouse |
| Seguridad | PASS | sin red, CDN, rutas absolutas, credenciales ni correo SEC |
| Determinismo | PASS | el artefacto regenerado coincide byte por byte |

## QA visual y funcional

| Escenario | Resultado observado |
|---|---|
| Escritorio | Jerarquía compacta, cinco tarjetas y tres gráficas legibles |
| Tablet, 736 × 900 | Tarjetas 3+2, gráficas sin colisiones ni overflow |
| Móvil, 360 × 800 | Tarjetas en dos columnas, gráficas de 297 px y cero overflow horizontal |
| Selector trimestral | Actualiza toda la lectura y vuelve al estado inicial al recargar |
| Primeros periodos | Las diez comparaciones ausentes aparecen como `No disponible` |
| Desplegables | Tabla visible con ocho filas; historial cerrado por defecto |
| Consola del navegador | Cero errores |

## Qué no funcionó y por qué

1. La precisión esperada inicial del ASK no coincidía con el valor completo del
   warehouse. Se corrigió el ancla de prueba; no se alteró el dato.
2. Un control de correo encontró la dirección del autor incluida en la licencia de
   Plotly. La validación ahora distingue el código de terceros del contenido del
   proyecto, mientras continúa prohibiendo correos y credenciales en el payload.
3. Un patrón de secretos demasiado amplio confundió `ASK-km` con un token `sk-`.
   Se reemplazó por patrones de credenciales reales.
4. La primera narrativa conjugaba en singular la métrica plural `pasajeros` y mostraba
   un signo negativo después de `disminuyó`. La revisión visual detectó ambos casos y
   se corrigieron antes del cierre.

## Decisiones y supuestos

- RASK se presenta como monetización por ASK-km; ASK permanece como capacidad. No se
  usa ASK como sustituto de precio.
- La referencia visual guía densidad, tarjetas y jerarquía, pero no aporta datos ni
  conclusiones al prototipo.
- Plotly se incrusta desde la dependencia existente para que el archivo funcione sin
  internet. El peso cercano a 4.9 MB es deliberado en esta versión local.
- Las conclusiones describen movimientos observados y no atribuyen causalidad.
- La cobertura comienza en 2024Q3 porque es el primer trimestre en Gold con las cinco
  métricas comparables. El backfill 2021–2024Q2 queda fuera de esta etapa.
- La traducción a componentes Streamlit se hará solo después de recibir anotaciones y
  aprobación explícita de esta composición.

## Riesgos abiertos para la siguiente etapa

- Confirmar que la densidad, orden de lectura, colores y lenguaje ejecutivo cumplen
  la expectativa antes de trasladarlos a Streamlit.
- Mantener paridad visual y funcional al convertir el prototipo sin duplicar la lógica
  de métricas ni introducir una segunda fuente de datos.
- Decidir después si el histórico anterior a 2024Q3 merece una etapa de backfill con
  nuevas fuentes comparables.

## Comandos para reproducir

```powershell
just stage11-prototype
just stage11-validate
uv run pytest -q tests/test_stage11_executive_prototype.py
uv run pytest -q
```

## Cierre de etapa

El prototipo cumple los criterios de datos, contenido, seguridad, interactividad y
respuesta visual de la Etapa 11. Se presenta localmente para anotaciones y el trabajo
se detiene aquí. No se iniciará la integración en Streamlit ni otra página sin un
`go` explícito del usuario.
