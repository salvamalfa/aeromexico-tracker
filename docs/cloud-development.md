# Desarrollo seguro desde GitHub y agentes de nube

Fecha de revisión: 2026-09-19.

## Decisión

Sí es correcto usar GitHub como fuente común para que un agente de nube pueda
inspeccionar y modificar el proyecto cuando la PC local esté apagada. El
repositorio ya tiene un remoto público; el problema actual es que una parte
importante del trabajo de Vuelos y Analysis Agent sigue sin commit en la rama
local.

GitHub debe contener código, contratos, documentación, Gold públicos y
artefactos generados aprobados. No debe convertirse en copia de secretos,
respuestas crudas con licencia, estados privados de revisión o archivos
regenerables demasiado grandes.

## Qué debe quedar versionado

| Clase | GitHub | Motivo |
|---|---|---|
| `src/`, `tests/`, `config/`, `sql/` | Sí | Código y contratos necesarios para revisar y cambiar el sistema |
| `docs/`, `AGENTS.md`, `CLAUDE.md` | Sí | Contexto, reglas y decisiones para humanos y agentes |
| `data/gold/*.parquet` | Sí, si son públicos y licenciables | Son los extractos compactos que consume el dashboard |
| manifiestos de Bronze | Sí | Conservan URL, hash y procedencia sin redistribuir el crudo |
| prototipos HTML de revisión | Sí, si están aprobados o claramente marcados | Permiten inspección sin ejecutar toda la tubería |
| `.env`, claves y secretos | No | Deben vivir en secretos del entorno |
| `data/bronze/*` y `data/silver/` | No por defecto | Crudos e intermedios locales; pueden estar sujetos a licencia |
| `data/warehouse.duckdb` | No | Es regenerable y no es la interfaz pública |
| `analysis_runs/` | No | Es el expediente autoritativo local de aprobación y publicación |
| caché/respuestas crudas de APIs pagadas | No | La licencia puede limitar retención y redistribución |

## Estado actual que hay que resolver antes de subir

La rama local `stage-11-executive-prototype` parte de una historia anterior y,
después de actualizar `origin/master` el 2026-09-19, está ocho commits por
delante y 33 por detrás. El remoto ya contiene los cinco PRs del estimador de
Claude y cuatro PRs posteriores que modifican únicamente el HTML estático de
Vuelos. El checkout local conserva además un conjunto grande de archivos
modificados y no rastreados que abarca los generadores de Vuelos y las etapas
12–18.

No conviene hacer push directo de este árbol a `master`. La secuencia segura es:

1. Guardar el estado actual en uno o más commits temáticos sin mezclar secretos
   ni temporales.
2. Actualizar la referencia remota y crear una rama de integración desde el
   `origin/master` vigente.
3. Integrar los commits locales, resolver los archivos generados desde su
   generador y ejecutar toda la suite.
4. Abrir un PR que muestre por separado código/pipeline, Gold públicos,
   documentación y el artefacto estático.
5. Publicar únicamente después de revisión humana.

El repositorio contiene aproximadamente 148 MiB de objetos sueltos en este
checkout. `data/gold/bridge_record_lineage.parquet` ronda 59 MiB: queda debajo
del límite duro de 100 MiB por archivo de GitHub, pero supera el umbral donde
GitHub suele advertir. Antes del PR conviene compactar la historia local y
evaluar si ese puente puede particionarse o reducirse sin perder trazabilidad.

## Qué podrá hacer un agente de nube

Con el estado pendiente ya versionado, podrá:

- entender la arquitectura y ejecutar la suite sobre Gold públicos;
- modificar ingestas, transformaciones, contratos y generadores;
- revisar la pestaña Vuelos y producir prototipos;
- preparar un adaptador y un `--dry-run` para una API;
- trabajar mediante PRs comparables y auditables.

No podrá, por diseño:

- reconstruir Bronze o Silver de fuentes manuales que no estén disponibles;
- usar una API pagada sin una clave configurada como secreto del entorno;
- reproducir una respuesta cruda que la licencia obliga a borrar;
- aprobar o republicar Analysis Agent sin el expediente autorizado de
  `analysis_runs/`.

Esta última frontera no deja al agente ciego respecto al código o al dashboard;
impide que una copia pública suplante una aprobación privada. Si se necesita
regeneración completa en nube, debe diseñarse un paquete público y sanitizado de
entradas de publicación, separado del ledger autoritativo. No debe resolverse
subiendo `analysis_runs/` completo.

## Proveedores pagados y GitHub

Los términos vigentes de AeroDataBox distinguen `Contents` de `Derived Works`.
Una respuesta de API, una selección de campos o una tabla ligeramente
reformateada sigue siendo contenido del proveedor y no puede republicarse como
dataset. En Starter, la retención estándar es de siete días. Una obra derivada
debe combinar múltiples observaciones o datos externos mediante un proceso no
trivial y no permitir reconstruir registros individuales; las obras derivadas
están exceptuadas de la restricción de caché, aunque siguen sujetas al resto de
los términos.

Para este proyecto, la implementación conservadora es:

1. Guardar respuestas crudas cifradas o locales solo durante la ventana
   permitida y nunca incluirlas en Git.
2. Derivar conteos mensuales de vuelos por ruta y operador, agregados a un nivel
   que no permita reconstruir un vuelo individual.
3. Combinar esos conteos con marginales AFAC mediante un estimador versionado.
4. Versionar solo diagnósticos, metadatos y resultados que cumplan la definición
   contractual de obra derivada.
5. Registrar la versión de términos y del plan aplicable en cada captura.

La clasificación contractual final debe confirmarse con AeroDataBox si se desea
publicar en GitHub el cubo de conteos de vuelos. El hecho de agregar por mes no
garantiza por sí solo que sea obra derivada.

Fuentes vigentes revisadas:

- [AeroDataBox API Pricing](https://aerodatabox.com/pricing/)
- [AeroDataBox Terms of Use](https://aerodatabox.com/terms)
- [Direct API access announcement](https://aerodatabox.com/direct-subscriptions)

## Configuración mínima de un entorno de nube

1. Clonar la rama de trabajo o el PR.
2. Instalar Python 3.13, `uv` y Chromium con `just setup`.
3. Crear secretos desde `.env.example`; nunca escribir valores en archivos
   versionados.
4. Ejecutar `just test` antes de editar y anotar cualquier diferencia de línea
   base.
5. Para tareas sin Bronze/Silver, trabajar contra `data/gold/` y declarar esa
   limitación en el PR.
6. Para una ingesta, usar un secreto del proveedor y un destino temporal
   ignorado; correr primero `--dry-run`.
