# Etapa 3 — AFAC: Estadística Mensual por Aerolínea (México)

**Objetivo:** obtener la serie histórica mensual de estadística operacional por aerolínea
del gobierno mexicano, que es la **única fuente pública que permite calcular participación
de mercado nacional** y comparar a Aeroméxico contra Volaris, Viva y el resto del mercado
mexicano con criterio homogéneo.

**Esta es la etapa más sucia del proyecto.** Los datos son valiosos y el parseo es un
dolor de cabeza. Presupuestar tiempo en consecuencia.

---

## 1. La fuente

La **AFAC** (Agencia Federal de Aviación Civil, sustituyó a la DGAC en octubre de 2019)
publica en gob.mx:

| Dataset | URL | Formato | Frecuencia |
|---|---|---|---|
| Estadística Mensual por Aerolínea / Monthly Airline Statistics (1992–presente) | `gob.mx/afac/acciones-y-programas/estadistica-mensual-por-aerolinea-monthly-airline-statistics` | Excel (`.xls`/`.xlsx`) | Mensual |
| Estadística Operacional de Aerolíneas | `gob.mx/afac/acciones-y-programas/estadistica-operacional-de-aerolineas-traffic-statistics-by-airline-253114` | Excel | Mensual |
| Boletín de Estadística Operacional | `gob.mx/cms/uploads/attachment/file/{id}/boletin-es-{mes}-{año}-{fecha}.pdf` | PDF | Mensual |
| La Aviación Mexicana en Cifras | Portal AFAC | PDF | Anual |
| Datos Abiertos AFAC | `gob.mx/afac/acciones-y-programas/datos-abiertos-306832` | Varios | Variable |

### Espejo útil: DATATUR
Sectur republica tablas de la AFAC en:
`https://datatur.sectur.gob.mx/Documentoscompartidos/afac/AFAC_{AÑO}_{MES}.pdf`
(ej. `AFAC_2026_03.pdf`)

**Este espejo puede ser más accesible que gob.mx** (menos anti-bot). Probarlo primero.
Contiene "Pasajeros transportados en vuelos nacionales por aerolínea" con participación
y variación.

### Contenido de los datos
- Pasajeros por aerolínea: nacional vs internacional, regular vs fletamento,
  aerolíneas nacionales vs extranjeras
- ASK por aerolínea
- Factor de ocupación (PLF/FOC) por aerolínea
- Carga transportada
- Operaciones (movimientos)
- Horas voladas
- Participación de mercado y variación interanual

Fuente citada en las tablas: *"SICT, AFAC, DREE/DDE — Información proporcionada por
las aerolíneas"*.

> **Nota importante:** el RPK por aerolínea **no siempre se desglosa** en el boletín
> gratuito. Es más confiable derivarlo de los filings de cada aerolínea. Si AFAC da
> ASK y load factor, se puede derivar RPK = ASK × LF y marcarlo `is_derived = true`.

## 2. Sub-etapa 3A — Acceso (aquí entra computer use)

**La investigación previa confirmó que gob.mx tiene protección anti-bot que bloquea
peticiones automatizadas.** Escalada obligatoria:

### Nivel 1 — httpx con headers realistas
```python
headers = {
    "User-Agent": "Mozilla/5.0 (...)",   # UA de navegador real
    "Accept": "text/html,application/xhtml+xml,...",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    "Referer": "https://www.gob.mx/afac",
}
```
Rate: 1 request cada 3 segundos.

### Nivel 2 — Playwright headless
Navegador real, resuelve JS challenges básicos. Interceptar la respuesta de descarga.

### Nivel 3 — Playwright con `headless=False`
Algunos sistemas anti-bot detectan headless. Correr con navegador visible.

### Nivel 4 — Computer use
**Avisar al usuario antes.** Procedimiento detallado en `12-computer-use-playbook.md`,
sección AFAC. Resumen:
1. Abrir el navegador del usuario en la URL de la AFAC
2. Localizar visualmente el enlace de descarga del archivo del periodo objetivo
3. Hacer clic, esperar la descarga
4. Mover el archivo desde `~/Downloads` a `data/bronze/afac/` con su `.meta.json`
   (registrando `download_method = "computer_use"`)
5. Repetir por periodo

### Nivel 5 — Intervención manual del usuario
Si nada funciona: generar una **lista precisa de URLs y nombres de archivo** y pedirle
al usuario que los descargue manualmente a una carpeta, indicando exactamente dónde
dejarlos. El agente sigue desde ahí. **Esto es una salida legítima, no un fracaso.**

> Documentar en `docs/decisiones/` qué nivel funcionó, porque determina si la
> actualización puede automatizarse en GitHub Actions o requiere un paso manual
> trimestral. Si requiere manual, el dashboard debe mostrar la fecha del último
> refresh de AFAC de forma visible.

## 3. Sub-etapa 3B — Inventario de archivos

Antes de parsear, hacer un **inventario completo**:

1. Listar todos los archivos disponibles (por año, por mes)
2. Descargar **todos** los que se pueda (la serie va de 1992 a la fecha)
3. Producir `docs/afac-inventario.md`:
   ```
   | Periodo | Archivo | Formato | Tamaño | Hojas | ¿Descargado? | Método |
   ```
4. Identificar **generaciones de formato**: el formato de 1995 no es el de 2025.
   Agrupar los archivos por "familia de formato" y documentar cada familia.

**Este inventario es el que hace que el parseo sea manejable.** Sin él, el parser se
convierte en un nido de casos especiales.

## 4. Sub-etapa 3C — Parseo

**Módulo:** `src/parse/afac/monthly_stats.py`

### Retos conocidos (documentados en la investigación)
1. **Encabezados multinivel y celdas combinadas.** Los Excel tienen bloques apilados:
   doméstico/internacional × regular/charter × nacionales/extranjeras.
2. **Cambios de formato entre años.**
3. **Encoding y acentos** inconsistentes.
4. **Nombres de aerolínea inconsistentes entre periodos:**
   - Interjet (dejó de operar)
   - Mexicana histórica (1921–2010) **vs** la nueva Mexicana / Aerolínea del Estado
     Mexicano (desde 2024) — **son entidades distintas, no confundirlas**
   - Viva / VivaAerobus / Viva Aerobus
   - AM Connect / Aeroméxico Connect / Aerolitoral
   - Aeroméxico / Grupo Aeroméxico
5. **Notas al pie con datos preliminares o estimados** (ej. TAR operando para Mexicana,
   Magnicharters estimado). **Hay que leerlas y capturarlas**, porque cambian la
   interpretación del dato.
6. **Cifras sujetas a revisión** — retroalimenta el mecanismo SCD2.

### Estrategia de parseo

```
Por cada archivo:
  1. Abrir todas las hojas, listar sus nombres
  2. Para cada hoja, detectar la fila de encabezado buscando keywords
     ('AEROLÍNEA', 'PASAJEROS', 'NACIONAL', 'INTERNACIONAL')
  3. Aplanar encabezados multinivel a nombres compuestos:
     'pax_nacional_regular', 'pax_internacional_fletamento', ...
  4. Detectar el bloque de datos (desde el encabezado hasta la primera fila totalmente
     vacía o hasta la fila 'TOTAL')
  5. Extraer las filas de aerolínea
  6. Extraer las filas de TOTAL por separado -> sirven para validar que la suma cuadra
  7. Extraer las notas al pie como texto y asociarlas a las filas que marcan
  8. Emitir formato largo
```

### Crosswalk de aerolíneas (entregable crítico)

Crear `data/reference/carrier_crosswalk.csv`, versionado en git:
```csv
source_system,source_carrier_name,carrier_key,iata,icao,valid_from,valid_to,notes
afac,AEROMEXICO,AEROMEXICO,AM,AMX,1992-01,,
afac,AEROMÉXICO,AEROMEXICO,AM,AMX,1992-01,,
afac,AEROMEXICO CONNECT,AEROMEXICO_CONNECT,5D,SLI,2008-01,,
afac,AEROLITORAL,AEROMEXICO_CONNECT,5D,SLI,1992-01,2007-12,rebranding a Connect
afac,MEXICANA,MEXICANA_LEGACY,MX,MXA,1992-01,2010-08,aerolínea histórica
afac,MEXICANA DE AVIACION,MEXICANA_NUEVA,,,2024-01,,Aerolínea del Estado Mexicano
afac,VIVAAEROBUS,VIVA_AEROBUS,VB,VIV,2006-01,,
afac,VIVA AEROBUS,VIVA_AEROBUS,VB,VIV,2006-01,,
...
```

**Reglas:**
- El crosswalk se construye **iterativamente**: correr el parser, ver qué nombres
  quedaron sin mapear, agregarlos, repetir.
- Todo nombre sin mapear genera `log_issue(issue_type="unmapped_entity")` y **no se
  descarta la fila** — se guarda con `carrier_key = NULL` para no perder información.
- **Presentar la lista de nombres sin mapear al usuario** al cerrar la etapa; algunas
  decisiones (¿Aeroméxico Connect se consolida con Aeroméxico o se reporta aparte?)
  son de negocio, no técnicas.

> **Decisión de negocio a consultar:** ¿el "Aeroméxico" del dashboard incluye Connect?
> Los filings de la SEC reportan el **grupo consolidado**; la AFAC los reporta
> **separados**. Para que la participación de mercado sea comparable con los financieros,
> probablemente haya que sumar Aeroméxico + Aeroméxico Connect. Presentar ambas vistas
> y dejar que el usuario elija la predeterminada.

### Esquema de salida: `silver/afac_monthly_stats.parquet`
```
period_id, period_type, period_start_date, period_end_date,
carrier_key, source_carrier_name, iata_code,
is_domestic_carrier,          -- nacional vs extranjera según AFAC
service_type,                 -- 'scheduled' | 'charter'
market,                       -- 'domestic' | 'international'
metric_key,                   -- 'passengers', 'ask_km', 'load_factor', 'cargo_tons', 'operations'
value, unit,
is_preliminary, is_estimated, footnote_text,
source_system, source_file, source_hash, ingested_at, parser_version
```

## 5. Sub-etapa 3D — Validación

### Validaciones internas
- Suma de aerolíneas = fila TOTAL del propio archivo (±0.1%)
- No hay periodos duplicados
- `load_factor` entre 0 y 1
- Continuidad de la serie: identificar y reportar todos los meses faltantes

### Validación cruzada con otras fuentes
1. **AFAC vs SEC**: los pasajeros mensuales de Aeroméxico según AFAC vs los del reporte
   de tráfico mensual de la SEC (Etapa 1). No van a coincidir exactamente (perímetro de
   consolidación, definiciones), pero deben estar en el mismo orden de magnitud y
   **correlacionar >0.95**. Cuantificar y explicar la diferencia sistemática.
2. **flyapm.mx** republica tablas mensuales de factor de ocupación por aerolínea. Útil
   como tercera opinión para validar el parser. Consulta puntual, no fuente de ingesta.
3. **Grupos aeroportuarios** (Etapa 4): el total de pasajeros del sistema debería
   guardar relación estable con la suma AFAC.

## 6. Fuentes alternativas si AFAC resulta impracticable

Si después de agotar la escalada el acceso a AFAC no es viable de forma sostenible:

| Alternativa | Qué da | Qué pierde |
|---|---|---|
| **DATATUR (Sectur)** espejo PDF | Mismas tablas de AFAC | Mismo problema de parseo, pero mejor acceso |
| **Grupos aeroportuarios (ASUR/GAP/OMA)** | Pasajeros mensuales por aeropuerto, limpio y oportuno | **No desglosa por aerolínea** → sin participación de mercado |
| **BTS T-100 (Etapa 5)** | Aeroméxico y peers en rutas México-EE.UU., por aerolínea | Solo el mercado transfronterizo, no el doméstico mexicano |

**Recomendación:** si AFAC solo se puede obtener con computer use semi-manual, aceptarlo.
Es una carga trimestral de 15 minutos y el dato no tiene sustituto.

---

## Entregables de la Etapa 3

1. `src/ingest/afac/download.py` (con la escalada implementada)
2. `src/parse/afac/monthly_stats.py`
3. Archivos AFAC en bronze con su meta
4. `docs/afac-inventario.md` — inventario completo con familias de formato
5. `data/reference/carrier_crosswalk.csv` versionado
6. `silver/afac_monthly_stats.parquet`
7. Reporte de validación cruzada AFAC vs SEC (correlación, diferencia sistemática)
8. Lista de nombres de aerolínea sin mapear, presentada al usuario para decisión
9. `docs/decisiones/decision-00X-acceso-afac.md` — qué nivel de escalada funcionó y si
   la actualización puede automatizarse
10. Tests con al menos **dos** familias de formato distintas en fixtures
11. `docs/etapas/etapa-3-reporte.md`

**Detenerse y esperar "go".**
