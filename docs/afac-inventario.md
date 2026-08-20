# Inventario de fuentes AFAC

Inventario generado a partir de la capa bronze. La serie anual oficial de gob.mx
está completa para 1992–2025; DATATUR aporta boletines mensuales 2024M01–2026M06
y una base larga 2016M01–2026M06. Todos los archivos tienen SHA-256 y metadatos
inmutables en `data/bronze/_manifest.jsonl`.

## Familias de formato

| Familia | Periodos | Rasgos | Uso en silver |
|---|---|---|---|
| `legacy_biff_wide` | 1992–2008 | `.xls`, hojas PAX/PAS por servicio, bloques apilados y meses en columnas | Fixture y archivo histórico; no entra al corte analítico 2015+ |
| `biff_wide_plus_hours` | 2009 | Agrega hojas de horas | Inventariada |
| `biff_wide_plus_operational` | 2010–2011 | Agrega OPREG/OPFLET en formato largo | Inventariada |
| `ooxml_wide_plus_operational` | 2012–2016 | Migración a `.xlsx`; PAX ancho y operación larga | Pasajeros desde 2015 |
| `ooxml_summary_plus_operational` | 2017–2019 | Incorpora hoja Resumen | Pasajeros |
| `ooxml_with_revision_history` | 2020–2024 | Incorpora historial explícito de revisiones | Pasajeros |
| `ooxml_modern` | 2025 | Misma topología moderna; sin hoja de revisiones en la descarga actual | Pasajeros preliminares |
| `datatur_monthly_bulletin_pdf` | 2024M01–2026M06 | Tablas mensuales, participación y notas de estimación | Canónico para vuelos regulares 2026 |
| `datatur_long_database` | 2016M01–2026M06 | Una fila por mes/mercado/servicio/región/aerolínea | Canónico para fletamento 2026; solape usado para QA |

## Archivos

| Periodo | Archivo bronze | Formato | Tamaño (bytes) | Hojas/páginas | Descargado | Método | Familia |
|---|---|---|---:|---|---|---|---|
| 1992 | `afac/1992/afac_afac_annual_workbook_1992_20260820T224830Z.xls` | xls | 125,952 | VLOSREG, PAXREG, CARREG, VLOSFLET, PAXFLET, CARFLET | Sí | httpx | `legacy_biff_wide` |
| 1993 | `afac/1993/afac_afac_annual_workbook_1993_20260820T224833Z.xls` | xls | 164,864 | VLOSREG, PAXREG, CARREG, VLOSFLET, PAXFLET, CARFLET, RESUMEN | Sí | httpx | `legacy_biff_wide` |
| 1994 | `afac/1994/afac_afac_annual_workbook_1994_20260820T224836Z.xls` | xls | 160,256 | VLOSREG, PAXREG, CARREG, VLOSFLET, PAXFLET, CARFLET, RESUMEN | Sí | httpx | `legacy_biff_wide` |
| 1995 | `afac/1995/afac_afac_annual_workbook_1995_20260820T224839Z.xls` | xls | 182,272 | VLOSREG, PAXREG, CARREG, VLOSFLET, PAXFLET, CARGAFLET | Sí | httpx | `legacy_biff_wide` |
| 1996 | `afac/1996/afac_afac_annual_workbook_1996_20260820T224842Z.xls` | xls | 145,408 | VLOSREG, PASREG, CARREG, VLOSFLET, PASFLET, CARFLET | Sí | httpx | `legacy_biff_wide` |
| 1997 | `afac/1997/afac_afac_annual_workbook_1997_20260820T224845Z.xls` | xls | 127,488 | VLOSREG, PASREG, CARGREG, VLOSFLET, PASFLET, CARFLET | Sí | httpx | `legacy_biff_wide` |
| 1998 | `afac/1998/afac_afac_annual_workbook_1998_20260820T224848Z.xls` | xls | 134,656 | VLOSREG, PASREG, CARGREG, VLOSFLET, PASFLET, CARFLET | Sí | httpx | `legacy_biff_wide` |
| 1999 | `afac/1999/afac_afac_annual_workbook_1999_20260820T224851Z.xls` | xls | 133,632 | VLOSREG, PASREG, CARGREG, VLOSFLET, PASFLET, CARFLET | Sí | httpx | `legacy_biff_wide` |
| 2000 | `afac/2000/afac_afac_annual_workbook_2000_20260820T224854Z.xls` | xls | 157,184 | VLOSREG, PAXREG, CARREG, VLOSFLET, PAXFLET, CARFLET | Sí | httpx | `legacy_biff_wide` |
| 2001 | `afac/2001/afac_afac_annual_workbook_2001_20260820T224857Z.xls` | xls | 154,112 | VLOSREG, PAXREG, CARGREG, VLOSFLET, PAXFLET, CARGFLET, RESUMEN | Sí | httpx | `legacy_biff_wide` |
| 2002 | `afac/2002/afac_afac_annual_workbook_2002_20260820T224900Z.xls` | xls | 154,624 | VLOSREG, PAXREG, CARGREG, VLOSFLET, PAXFLET, CARGFLET, RESUMEN | Sí | httpx | `legacy_biff_wide` |
| 2003 | `afac/2003/afac_afac_annual_workbook_2003_20260820T224903Z.xls` | xls | 155,648 | VLOSREG, PAXREG, CARREG, VLOSFLET, PAXFLET, CARFLET, RESUMEN | Sí | httpx | `legacy_biff_wide` |
| 2004 | `afac/2004/afac_afac_annual_workbook_2004_20260820T224906Z.xls` | xls | 169,472 | VLOSREG, PAXREG, CARREG, VLOSFLET, PAXFLET, CARFLET, RESUMEN-01 | Sí | httpx | `legacy_biff_wide` |
| 2005 | `afac/2005/afac_afac_annual_workbook_2005_20260820T224909Z.xls` | xls | 199,680 | VLOSREG, PAXREG, CARREG, VLOSFLET, PAXFLET, CARFLET, RESUMEN | Sí | httpx | `legacy_biff_wide` |
| 2006 | `afac/2006/afac_afac_annual_workbook_2006_20260820T224912Z.xls` | xls | 162,816 | VLOSREG, PAXREG, CARREG, VLOSFLET, PAXFLET, CARFLET, RESUMEN | Sí | httpx | `legacy_biff_wide` |
| 2007 | `afac/2007/afac_afac_annual_workbook_2007_20260820T224915Z.xls` | xls | 183,296 | VLOSREG, PAXREG, CARREG, VLOSFLET, PAXFLET, CARFLET | Sí | httpx | `legacy_biff_wide` |
| 2008 | `afac/2008/afac_afac_annual_workbook_2008_20260820T224918Z.xls` | xls | 208,896 | VLOSREG, PAXREG, CARREG, VLOSFLET, PAXFLET, CARFLET, RESUMEN | Sí | httpx | `legacy_biff_wide` |
| 2009 | `afac/2009/afac_afac_annual_workbook_2009_20260820T224921Z.xls` | xls | 156,672 | VLOSREG, PAXREG, CARGREG, HRSREG, VLOSFLET, PAXFLET, CARGFLET, HRSFLET | Sí | httpx | `biff_wide_plus_hours` |
| 2010 | `afac/2010/afac_afac_annual_workbook_2010_20260820T224924Z.xls` | xls | 325,120 | VLOSREG, PAXREG, CARGREG, OPREG, VLOSFLET, PAXFLET, CARGFLET, OPFLET | Sí | httpx | `biff_wide_plus_operational` |
| 2011 | `afac/2011/afac_afac_annual_workbook_2011_20260820T224927Z.xls` | xls | 337,408 | VLOSREG, PAXREG, CARGREG, OPREG, VLOSFLET, PAXFLET, CARGFLET, OPFLET | Sí | httpx | `biff_wide_plus_operational` |
| 2012 | `afac/2012/afac_afac_annual_workbook_2012_20260820T225955Z.xlsx` | xlsx | 206,430 | VLOSREG, PAXREG, CARGREG, OPREG, VLOSFLET, PAXFLET, CARGFLET, OPFLET | Sí | computer_use | `ooxml_wide_plus_operational` |
| 2013 | `afac/2013/afac_afac_annual_workbook_2013_20260820T225955Z.xlsx` | xlsx | 210,246 | VLOSREG, PAXREG, CARGREG, OPREG, VLOSFLET, PAXFLET, CARGFLET, OPFLET | Sí | computer_use | `ooxml_wide_plus_operational` |
| 2014 | `afac/2014/afac_afac_annual_workbook_2014_20260820T225955Z.xlsx` | xlsx | 203,798 | VLOSREG, PAXREG, CARGREG, OPREG, VLOSFLET, PAXFLET, CARGFLET, OPFLET | Sí | computer_use | `ooxml_wide_plus_operational` |
| 2015 | `afac/2015/afac_afac_annual_workbook_2015_20260820T225955Z.xlsx` | xlsx | 201,145 | VLOSREG, PAXREG, CARGREG, OPREG, VLOSFLET, PAXFLET, CARGFLET, OPFLET | Sí | computer_use | `ooxml_wide_plus_operational` |
| 2016 | `afac/2016/afac_afac_annual_workbook_2016_20260820T225955Z.xlsx` | xlsx | 192,166 | VLOSREG, PAXREG, CARGREG, OPREG, VLOSFLET, PAXFLET, CARGFLET, OPFLET | Sí | computer_use | `ooxml_wide_plus_operational` |
| 2017 | `afac/2017/afac_afac_annual_workbook_2017_20260820T225955Z.xlsx` | xlsx | 220,338 | Resumen, VLOSREG, PAXREG, CARGREG, OPREG, VLOSFLET, PAXFLET, CARGFLET, OPFLET | Sí | computer_use | `ooxml_summary_plus_operational` |
| 2018 | `afac/2018/afac_afac_annual_workbook_2018_20260820T225955Z.xlsx` | xlsx | 269,841 | Resumen, VLOSREG, PAXREG, CARGREG, OPREG, Boletín, VLOSFLET, PAXFLET, CARGFLET, OPFLET | Sí | computer_use | `ooxml_summary_plus_operational` |
| 2019 | `afac/2019/afac_afac_annual_workbook_2019_20260820T225955Z.xlsx` | xlsx | 265,321 | Resumen, VLOSREG, PAXREG, CARGREG, OPREG, VLOSFLET, PAXFLET, CARGFLET, OPFLET | Sí | computer_use | `ooxml_summary_plus_operational` |
| 2020 | `afac/2020/afac_afac_annual_workbook_2020_20260820T225955Z.xlsx` | xlsx | 240,452 | Resumen, VLOSREG, PAXREG, CARGREG, OPREG, VLOSFLET, PAXFLET, CARGFLET, OPFLET, Historial de revisiones | Sí | computer_use | `ooxml_with_revision_history` |
| 2021 | `afac/2021/afac_afac_annual_workbook_2021_20260820T225955Z.xlsx` | xlsx | 304,376 | Resumen, VLOSREG, PAXREG, CARGREG, OPREG, VLOSFLET, PAXFLET, CARGFLET, OPFLET, Historial de revisiones | Sí | computer_use | `ooxml_with_revision_history` |
| 2022 | `afac/2022/afac_afac_annual_workbook_2022_20260820T225955Z.xlsx` | xlsx | 248,788 | Resumen, VLOSREG, PAXREG, CARGREG, OPREG, VLOSFLET, PAXFLET, CARGFLET, OPFLET, Historial de revisiones | Sí | computer_use | `ooxml_with_revision_history` |
| 2023 | `afac/2023/afac_afac_annual_workbook_2023_20260820T225955Z.xlsx` | xlsx | 244,599 | Resumen, VLOSREG, PAXREG, CARGREG, OPREG, VLOSFLET, PAXFLET, CARGFLET, OPFLET, Historial de revisiones | Sí | computer_use | `ooxml_with_revision_history` |
| 2024 | `afac/2024/afac_afac_annual_workbook_2024_20260820T225955Z.xlsx` | xlsx | 245,200 | Resumen, VLOSREG, PAXREG, CARGREG, OPREG, VLOSFLET, PAXFLET, CARGFLET, OPFLET, Historial de revisiones | Sí | computer_use | `ooxml_with_revision_history` |
| 2025 | `afac/2025/afac_afac_annual_workbook_2025_20260820T225955Z.xlsx` | xlsx | 281,498 | Resumen, VLOSREG, PAXREG, CARGREG, OPREG, VLOSFLET, PAXFLET, CARGFLET, OPFLET | Sí | computer_use | `ooxml_modern` |
| 2024M01 | `afac/2024/01/afac_datatur_monthly_bulletin_2024M01_20260820T225230Z.pdf` | pdf | 239,950 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2024M02 | `afac/2024/02/afac_datatur_monthly_bulletin_2024M02_20260820T225233Z.pdf` | pdf | 241,126 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2024M03 | `afac/2024/03/afac_datatur_monthly_bulletin_2024M03_20260820T225236Z.pdf` | pdf | 241,141 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2024M04 | `afac/2024/04/afac_datatur_monthly_bulletin_2024M04_20260820T225239Z.pdf` | pdf | 241,252 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2024M05 | `afac/2024/05/afac_datatur_monthly_bulletin_2024M05_20260820T225242Z.pdf` | pdf | 241,226 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2024M06 | `afac/2024/06/afac_datatur_monthly_bulletin_2024M06_20260820T225245Z.pdf` | pdf | 241,312 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2024M07 | `afac/2024/07/afac_datatur_monthly_bulletin_2024M07_20260820T225248Z.pdf` | pdf | 241,332 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2024M08 | `afac/2024/08/afac_datatur_monthly_bulletin_2024M08_20260820T225251Z.pdf` | pdf | 241,345 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2024M09 | `afac/2024/09/afac_datatur_monthly_bulletin_2024M09_20260820T225254Z.pdf` | pdf | 241,369 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2024M10 | `afac/2024/10/afac_datatur_monthly_bulletin_2024M10_20260820T225257Z.pdf` | pdf | 241,362 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2024M11 | `afac/2024/11/afac_datatur_monthly_bulletin_2024M11_20260820T225300Z.pdf` | pdf | 241,328 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2024M12 | `afac/2024/12/afac_datatur_monthly_bulletin_2024M12_20260820T225303Z.pdf` | pdf | 240,899 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2025M01 | `afac/2025/01/afac_datatur_monthly_bulletin_2025M01_20260820T225306Z.pdf` | pdf | 305,545 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2025M02 | `afac/2025/02/afac_datatur_monthly_bulletin_2025M02_20260820T225309Z.pdf` | pdf | 307,208 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2025M03 | `afac/2025/03/afac_datatur_monthly_bulletin_2025M03_20260820T225312Z.pdf` | pdf | 307,037 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2025M04 | `afac/2025/04/afac_datatur_monthly_bulletin_2025M04_20260820T225315Z.pdf` | pdf | 307,096 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2025M05 | `afac/2025/05/afac_datatur_monthly_bulletin_2025M05_20260820T225318Z.pdf` | pdf | 306,918 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2025M06 | `afac/2025/06/afac_datatur_monthly_bulletin_2025M06_20260820T225321Z.pdf` | pdf | 306,945 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2025M07 | `afac/2025/07/afac_datatur_monthly_bulletin_2025M07_20260820T225324Z.pdf` | pdf | 306,867 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2025M08 | `afac/2025/08/afac_datatur_monthly_bulletin_2025M08_20260820T225327Z.pdf` | pdf | 307,065 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2025M09 | `afac/2025/09/afac_datatur_monthly_bulletin_2025M09_20260820T225330Z.pdf` | pdf | 307,090 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2025M10 | `afac/2025/10/afac_datatur_monthly_bulletin_2025M10_20260820T225333Z.pdf` | pdf | 307,048 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2025M11 | `afac/2025/11/afac_datatur_monthly_bulletin_2025M11_20260820T225336Z.pdf` | pdf | 307,058 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2025M12 | `afac/2025/12/afac_datatur_monthly_bulletin_2025M12_20260820T225339Z.pdf` | pdf | 306,597 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2026M01 | `afac/2026/01/afac_datatur_monthly_bulletin_2026M01_20260820T225342Z.pdf` | pdf | 251,437 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2026M02 | `afac/2026/02/afac_datatur_monthly_bulletin_2026M02_20260820T225345Z.pdf` | pdf | 256,207 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2026M03 | `afac/2026/03/afac_datatur_monthly_bulletin_2026M03_20260820T225348Z.pdf` | pdf | 256,710 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2026M04 | `afac/2026/04/afac_datatur_monthly_bulletin_2026M04_20260820T225351Z.pdf` | pdf | 256,882 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2026M05 | `afac/2026/05/afac_datatur_monthly_bulletin_2026M05_20260820T225354Z.pdf` | pdf | 257,079 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2026M06 | `afac/2026/06/afac_datatur_monthly_bulletin_2026M06_20260820T225357Z.pdf` | pdf | 257,130 | 2 páginas | Sí | httpx | `datatur_monthly_bulletin_pdf` |
| 2016M01–2026M06 | `afac/database/extracted/afac_datatur_database_member_current_20260820T224211Z.xlsx` | xlsx | 790,171 | AFAC | Sí | httpx | `datatur_long_database` |

## Precedencia de fuentes

- 2015–2025: libros anuales oficiales AFAC, porque conservan bloques y filas TOTAL.
- 2026 vuelos regulares: boletín mensual DATATUR/AFAC del mismo periodo.
- 2026 fletamento: base larga DATATUR, ya que el boletín no publica ese desglose.
- Los solapes no se concatenan: se usan para detectar revisiones y diferencias de versión.
