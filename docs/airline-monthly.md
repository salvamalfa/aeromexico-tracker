# Airline Monthly

M11 es una publicación mensual original de aviación mexicana dentro de
Aerolíneas MX Tracker. La edición piloto corresponde a septiembre de 2026 y
cubre Aeroméxico, Viva y Volaris. Tiene índice, señales, análisis propio,
rutas y capacidad cuando la evidencia lo permite, resultados, agenda y archivo
mensual. El [acuerdo y calendario activos](airline-monthly-plan-20261019.md)
conservan el alcance solicitado por Salva.

## Estado de revisión

Es un borrador editorial. Preparar el código y el HTML no aprueba sus cifras,
no activa tesis ni autoriza publicarlo. El build habitual excluye la página,
sus datos y el enlace de producto. Noticias y las herramientas de actualización
ya están integradas en la base de revisión; M11 conserva su propio PR.

La rama se actualizó con `master` en `194ff92c`. Solo hubo conflictos en la
bitácora de cambios y el README; se conservaron las entradas de ambos trabajos.
La interfaz, el JSON editorial y el HTML mantienen los mismos bytes entregados
en `63433c3`, al igual que las capturas. No se reemplazan los archivos de Library.

La estructura pública de [Airline Weekly](https://airlineweekly.skift.com/)
y su [archivo](https://airlineweekly.skift.com/issues/) sirven de referencia
para organizar una edición y navegar meses. La identidad, textos y análisis
son propios. No se usa contenido de pago, marca ajena ni muro de pago.

## Autoría y procedencia

- `config/monthly/issues/2026-09.json`: texto editorial, cifras reportadas y
  referencias públicas con fecha, localizador y SHA-256 del documento consultado.
- `contracts/editorial/airline-monthly.schema.json`: contrato del candidato;
  no forma parte del manifiesto de análisis aprobado ni de `data/v1/`.
- `scripts/monthly/validate.py`: valida estructura, periodos, fuentes,
  referencias y una fila por compañía, sin red ni cambios de aprobación.
- `web/monthly.html` y `web/src/monthly/`: única interfaz de edición y archivo,
  con enlaces `#edicion/AAAA-MM`, `#edicion/AAAA-MM/seccion` y `#archivo`.
- `scripts/monthly/build_preview.py`: usa esa misma interfaz y los mismos
  insumos para generar un solo HTML sin dependencias de red al leerlo.

Cada afirmación distingue hecho, inferencia, evento programado o límite de
evidencia. Las cifras son declaraciones públicas atribuidas, no una auditoría
de las compañías. El piloto no contiene estimaciones. Los faltantes conservan
`null` y se muestran como «No disponible»; no se calculan porcentajes de
cobertura ni cuotas con definiciones incompatibles.

El corte de consulta y el mes analizado son distintos: los reportes de
septiembre se publicaron en octubre. La metodología aclara diferencias de
pasajeros, ocupación y millas. No se suman pasajeros entre compañías ni se
deriva rentabilidad de tráfico. No se usan datos de Amex o tarjetahabientes.

Los PDF se consultan en los portales públicos de inversionistas de las tres
compañías; Volaris distribuye su reporte mediante el CDN enlazado por su portal.
Los crudos no se incluyen en el PR. Las huellas permiten contrastar una nueva
descarga con el documento revisado; no acreditan por sí mismas veracidad.

## Revisar localmente

Con el entorno del repo y las dependencias de `web/` instalados:

```bash
uv run python -m scripts.monthly.validate
uv run python -m scripts.monthly.build_preview
```

El segundo comando genera
[`prototypes/airline-monthly/septiembre-2026.html`](../prototypes/airline-monthly/septiembre-2026.html).
Puede abrirse directamente o servirse con un servidor local. Los enlaces de
fuentes sí abren documentos externos cuando el lector los selecciona.

Para revisar el módulo junto al dashboard, habilitar explícitamente la opción
local de preview y abrir `monthly.html`:

```bash
cd web
VITE_AIRLINE_MONTHLY_PREVIEW=true npm run dev
```

En PowerShell: `$env:VITE_AIRLINE_MONTHLY_PREVIEW='true'` antes de `npm run dev`;
retirarla al terminar con `Remove-Item Env:VITE_AIRLINE_MONTHLY_PREVIEW`.
El dashboard necesita sus datos exportados para sus propias vistas; Monthly
no consulta el warehouse, el chat ni servicios pagados. La opción también
funciona con `npm run build` para una compilación local de revisión. Nunca se
ejecuta el gate ni se copia ese build a `site/` durante esta preparación.

Para añadir una edición, crear su JSON e importarlo en el catálogo de
`web/src/monthly/main.ts`; conservar meses previos y actualizar el enlace de
edición piloto en `web/monthly.html` cuando corresponda. Ejecutar validación,
pruebas y revisión editorial antes de preparar una nueva preview.

## Validación

```bash
uv run pytest -q tests/test_airline_monthly.py
cd web && npm run check && npm run test && npm run build
uv run pytest -m browser -q tests/test_web_monthly_smoke.py
```

El último comando se ejecuta desde la raíz del repositorio. Comprueba teclado,
edición, enlaces a secciones, archivo, historial, recarga y anchos de móvil y
escritorio; la preview no solicita recursos externos. CI además verifica que
el build habitual no incluya el borrador. No sustituye la comprobación humana
de las fuentes ni la autorización de publicación.

La incorporación futura a producción requiere aprobación editorial y revisión
de la huella técnica del dashboard. No se modifican firmas o recibos para
sortear esa revisión. El [límite conocido de presentación](etapas/mercado-candidato-20261015.md)
también aplica a cambios de interfaz del nuevo módulo.
