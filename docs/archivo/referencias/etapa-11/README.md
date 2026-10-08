# Referencias visuales de la Etapa 11

Estos archivos son insumos de diseño proporcionados por el usuario para construir el
prototipo del resumen ejecutivo. Se conservan como referencias versionadas; no son
fuentes de datos, no alimentan el pipeline y sus cifras no deben copiarse al modelo
analítico.

| Archivo | Uso | SHA-256 |
|---|---|---|
| `design_system_aeromexico.md` | Tokens, jerarquía y lineamientos visuales | `780680865dabd8b3f5db2d3a936634d7e0eade580d2e906a152b2df80f027ddc` |
| `reporte_precios_aeromexico.html` | Dashboard HTML de referencia | `fd2022fab8a86ef091bb59ccbd4231a05b10ec8570fdb539ce2f51b9ac2b9a6c` |
| `aeromexico_precios.jsx` | Implementación JSX asociada a la referencia | `fd75ebe2c45e7e3c13c84c56c99eac017074439e475a19711b40ee9c28dc062d` |

Los 22 comunicados trimestrales PDF de Aeroméxico, desde 1T21 hasta 2T26, están
preservados en la capa Bronze bajo `data/bronze/aeromexico_ir/`. Sus metadatos,
URLs públicas y hashes están registrados en `data/bronze/_manifest.jsonl`. Bronze es
local e inmutable y permanece excluido de Git por diseño.

