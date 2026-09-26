# 12 — Playbook de Computer Use

Varias fuentes de este proyecto tienen protección anti-bot o formularios dinámicos que
bloquean el acceso programático. Este documento define **cuándo** escalar a controlar
el navegador o la computadora del usuario, **cómo** hacerlo de forma segura, y el
**procedimiento concreto** para cada fuente problemática.

---

## 1. Principio rector

> Computer use existe para acceder a **información pública que un humano vería en su
> navegador**. No para evadir autenticación, saltar paywalls, ni burlar límites que la
> fuente impone deliberadamente por razones distintas al filtrado de bots.

El agente **siempre** avisa antes de tomar control y explica qué va a hacer.

## 2. Escalada obligatoria (nunca saltarse pasos)

```
Nivel 1: httpx con headers realistas
  ↓ (falla: 403, 429 persistente, challenge JS, contenido vacío)
Nivel 2: Playwright headless
  ↓ (falla: detección de headless, CAPTCHA, timeout)
Nivel 3: Playwright con headless=False (navegador visible)
  ↓ (falla)
Nivel 4: Computer use — controlar el navegador del usuario
  ↓ (falla)
Nivel 5: Pedirle al usuario que descargue manualmente,
         con instrucciones precisas
```

**En cada nivel, documentar qué falló y por qué.** El nivel que finalmente funciona
determina si esa fuente puede automatizarse en GitHub Actions o requiere intervención
periódica — y eso debe quedar registrado en `docs/decisiones/`.

## 3. Reglas de seguridad para computer use

1. **Avisar antes.** Formato:
   > "Voy a abrir tu navegador en {URL} para descargar {archivo}. Esto implica que veré
   > tu pantalla durante el proceso. Serán aproximadamente {N} clics. ¿Adelante?"
2. **No tocar nada fuera del alcance.** Solo la pestaña del navegador en la URL objetivo.
   Nunca abrir otras aplicaciones, archivos personales, correo, mensajería.
3. **No interactuar con sesiones autenticadas.** Si el navegador tiene sesiones abiertas
   de correo, banca o redes sociales, no entrar ahí. Si el sitio objetivo pide login,
   **detenerse y preguntar**.
4. **Nada de datos personales.** No leer ni transcribir información que no sea el dato
   objetivo.
5. **Reportar cada acción.** Al terminar, listar qué se hizo: "Abrí X, hice clic en Y,
   descargué Z a ~/Downloads, lo moví a data/bronze/afac/".
6. **Timeout.** Si después de ~10 minutos de intentos no se logra, detenerse y pasar
   al Nivel 5.
7. **Nunca resolver CAPTCHAs automáticamente.** Si aparece uno, pedirle al usuario que
   lo resuelva y luego continuar.

## 4. Procedimiento: AFAC / gob.mx

**Confirmado en la investigación previa: gob.mx bloquea peticiones automatizadas.**
Esta es la fuente donde computer use es más probable que sea necesario.

### Antes de escalar, probar:
1. **DATATUR como espejo**: `https://datatur.sectur.gob.mx/Documentoscompartidos/afac/AFAC_{AÑO}_{MES}.pdf`
   Sectur republica las tablas de AFAC y suele ser más accesible. **Probar esto primero,
   puede resolver todo.**
2. httpx con `User-Agent` de navegador real + `Referer: https://www.gob.mx/afac`
3. Playwright headless
4. Playwright visible

### Procedimiento de computer use
```
1. Avisar al usuario.
2. Abrir el navegador en:
   https://www.gob.mx/afac/acciones-y-programas/estadistica-mensual-por-aerolinea-monthly-airline-statistics
3. Esperar carga completa (la página tiene JS).
4. Localizar visualmente la sección de descargas. Los enlaces suelen estar agrupados
   por año y mes.
5. Para cada archivo objetivo:
   a. Clic en el enlace
   b. Esperar a que la descarga termine (verificar en ~/Downloads)
   c. Confirmar que el archivo no es un HTML de error (verificar tamaño y magic bytes)
6. Al terminar todas las descargas, salir del navegador.
7. Mover archivos:
   mv ~/Downloads/{archivo} data/bronze/afac/{año}/{mes}/
8. Generar el .meta.json con download_method = "computer_use"
9. Reportar: cuántos archivos, qué periodos, cuáles fallaron.
```

### Eficiencia
No descargar de uno en uno con una sesión de computer use por archivo. **Hacer una sola
sesión que descargue todo el lote**, porque cada arranque de sesión es costoso en tiempo.

### Si la serie histórica completa (1992-presente) es demasiado
Priorizar: **2015 a la fecha** cubre pre-COVID, COVID, Categoría 2 y recuperación.
Es suficiente para todo el análisis. La historia de los 90 es un extra, no un requisito.

## 5. Procedimiento: BMV (portal XBRL)

El portal `https://www.bmv.com.mx/es/emisoras/archivos-estadar-xbrl` tiene una tabla
filtrable que probablemente se alimente por AJAX.

### Antes de escalar
1. **Inspeccionar la petición de red real** con Playwright: abrir la página, filtrar por
   "AERO", y capturar el request que dispara el filtro (`page.on("request")`).
   Si es un POST/GET reproducible → implementarlo con httpx y olvidarse del navegador.
   **Esta es la mejor salida y hay que intentarla en serio.**
2. Si la descarga del zip requiere una sesión o un token, capturarlo con Playwright y
   reusarlo.

### Procedimiento de computer use
```
1. Avisar.
2. Abrir https://www.bmv.com.mx/es/emisoras/archivos-estadar-xbrl
3. En el filtro de clave de emisora, escribir "AERO" (luego "VOLAR")
4. Seleccionar periodicidad y año
5. Aplicar filtro
6. Para cada fila de la tabla, clic en el enlace de descarga
7. Verificar que el .zip descargó completo
8. Mover a data/bronze/bmv/xbrl/{ticker}/{periodo}/
```

### Fallback: CNBV STIV-2
`https://stivconsultasexternas.cnbv.gob.mx/` tiene el "Visor de Información Financiera
XBRL" con la misma información (los emisores presentan a ambos). Si BMV resiste,
probar aquí.

## 6. Procedimiento: BTS TranStats (T-100)

El formulario de TranStats requiere seleccionar columnas con checkboxes y luego
descargar.

### Antes de escalar
1. Inspeccionar el POST del formulario con Playwright. **Casi siempre es reproducible**
   con httpx: es un form clásico, no una SPA moderna.
2. Buscar si hay endpoints de descarga directa por año/banco.

### Procedimiento con Playwright (probablemente suficiente, sin computer use)
```
1. page.goto(URL del banco 28IS)
2. Seleccionar el año y mes en los dropdowns
3. Marcar los checkboxes de las columnas necesarias
   (o usar el botón "Select All Fields" si existe)
4. Clic en Download
5. Capturar el evento de descarga con page.expect_download()
6. Guardar a bronze
```

### Advertencia de volumen
Los archivos son grandes. **Verificar espacio en disco antes** y descargar año por año,
no todo de golpe. Filtrar a México lo antes posible en el procesamiento.

## 7. Procedimiento: Sitios de IR de aerolíneas

Para Aeroméxico (`ir.aeromexico.com`), Volaris, Viva (`ri.vivaaerobus.com`),
Ryanair (`investor.ryanair.com`), IAG (`iairgroup.com`).

**Nota:** el CDN de Viva (`cdn.investorcloud.net`) tiene URLs de patrón predecible
(`{año}-{trimestre}-{idioma}.pdf`) y suele ser accesible con httpx directo. Probar eso
primero.

**Preferencia general:** para Aeroméxico, Volaris, Ryanair y Delta, **usar EDGAR en vez
del sitio de IR**. Los documentos son los mismos, EDGAR tiene formato estable, URLs
predecibles y una API real. El sitio de IR es el fallback, no la primera opción.

## 8. Registro de decisiones de acceso

Al terminar cada etapa que involucre estas fuentes, escribir
`docs/decisiones/decision-00X-acceso-{fuente}.md`:

```markdown
# Acceso a {fuente}

## Niveles probados
- Nivel 1 (httpx): FALLÓ — 403 con challenge de Incapsula
- Nivel 2 (Playwright headless): FALLÓ — detectado, redirige a página de verificación
- Nivel 3 (Playwright visible): FUNCIONÓ

## Método adoptado
Playwright con headless=False, {N} segundos de espera tras la carga.

## ¿Automatizable en CI?
NO — requiere navegador con display. Opciones:
  - xvfb en GitHub Actions (probar)
  - Ejecución manual trimestral

## Frecuencia de actualización requerida
Mensual (los datos de AFAC salen ~2 meses después del cierre)

## Instrucciones para actualización manual
1. ...
```

**Este documento es lo que evita que dentro de seis meses nadie recuerde cómo se
actualizaba la fuente.**

## 9. Instalaciones que puede requerir esta escalada

El agente debe pedir autorización (Etapa 0) para:
- `playwright` + `playwright install chromium` (~150 MB)
- Posiblemente `playwright install-deps` en Linux (requiere sudo — **preguntar
  explícitamente**)
- `xvfb` si se intenta correr navegador visible en CI

---

## 10. Cuándo NO usar computer use

- Cuando existe una API. La SEC tiene API: usarla.
- Cuando el sitio requiere login del usuario y el dato no es realmente público.
- Cuando hay un CAPTCHA que exige resolución humana — pedirle al usuario, no intentar
  resolverlo.
- Cuando el volumen de interacciones es enorme (cientos de clics). Ahí conviene el
  Nivel 5: pedirle al usuario una descarga manual en lote, o replantear si esa fuente
  vale el esfuerzo.
- Para scraping de reseñas de usuarios o redes sociales. **Prohibido por este plan**,
  independientemente de la viabilidad técnica.
