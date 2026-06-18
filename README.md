# Análisis del comportamiento de la sismicidad en México (1966–2026)

> Proyecto final del módulo. Analiza el catálogo histórico de sismos del Servicio Sismológico Nacional (SSN · UNAM) para caracterizar patrones temporales, geográficos y de severidad en la actividad sísmica de México.

## 📋 Resumen ejecutivo

| Campo | Valor |
|---|---|
| **Pregunta analítica** | ¿Qué patrones temporales, geográficos y de severidad caracterizan la sismicidad en México entre 1966 y 2026, y cómo ha evolucionado la frecuencia de sismos severos (M≥6) por estado y región a lo largo del tiempo? |
| **Dataset** | Catálogo de sismos del Servicio Sismológico Nacional (SSN · UNAM), eventos M≥4.0, periodo 1966–2026 — pública, 50,056 registros |
| **Fuente** | `www2.ssn.unam.mx:8080/catalogo` — Catálogo de sismos |
| **Modelo** | Estrella con 1 fact + 4 dimensiones (fecha, hora, ubicación, magnitud) |
| **Infraestructura** | Aurora PostgreSQL en AWS (cluster `sismicidad-proyecto`, schema `sismo_dwh`) |
| **ETL** | `etl_pipeline.py` end-to-end con pandas + SQLAlchemy + validaciones post-carga |
| **SQL avanzado** | Window functions (RANK, LAG, promedio móvil), CTE, PERCENTILE_CONT, COUNT FILTER |
| **Dashboard** | Streamlit + Plotly: serie anual, ranking de estados, mapa geográfico, heatmap temporal |

---

## 🎯 Problema y motivación

México se ubica sobre la convergencia de cinco placas tectónicas, lo que lo convierte en una de las regiones con mayor actividad sísmica del planeta. Entender **dónde**, **cuándo** y con qué **intensidad** ocurren los sismos tiene valor directo para:

- Priorizar zonas para inversión en infraestructura sismorresistente y protección civil.
- Informar a la población sobre el riesgo sísmico real de su región.
- Evaluar si la frecuencia de sismos severos ha cambiado a lo largo de seis décadas.

Este proyecto responde tres preguntas concretas:

1. ¿Qué estados y regiones concentran los sismos más intensos?
2. ¿Existen patrones temporales por hora del día o mes del año?
3. ¿Cómo ha evolucionado la frecuencia de sismos fuertes/severos por década?

---

## 📦 Origen de los datos

Los datos provienen del catálogo público del **Servicio Sismológico Nacional (SSN · UNAM)**, descargado como un único archivo CSV con 50,056 eventos de magnitud ≥4.0 registrados entre el 1 de enero de 1966 y el 7 de junio de 2026. A diferencia de fuentes que requieren descarga vía API por rangos de fecha, el catálogo del SSN se distribuye como un export consolidado, por lo que el ETL lo toma como insumo directo — sin una etapa de scraping o requests HTTP por periodo.

### Flujo end-to-end

```
        ┌──────────────────────────────────────┐
        │  SSN · UNAM (catálogo público)        │
        │  www2.ssn.unam.mx:8080/catalogo       │
        │                                       │
        │  • CSV plano: una fila por evento     │
        │  • Columnas: Fecha, Hora, Magnitud,   │
        │    Latitud, Longitud, Profundidad,    │
        │    Referencia de localización, Estatus│
        │  • Periodo: 1966–2026, M≥4.0          │
        │  • 50,056 registros                   │
        └──────────────────┬────────────────────┘
                            │  Descarga manual (export del portal)
                            ▼
        ┌──────────────────────────────────────┐
        │  PASO 1 — DBeaver                     │
        │  01_schema_ddl.sql                    │
        │                                       │
        │  • Crea el schema sismo_dwh           │
        │  • Crea las 5 tablas vacías           │
        │    (4 dims + 1 fact) con sus FKs      │
        │  • Crea los índices de la fact        │
        └──────────────────┬────────────────────┘
                            │  Tablas vacías ya existentes
                            ▼
        ┌──────────────────────────────────────┐
        │  PASO 2 — VS Code (terminal)          │
        │  etl_pipeline.py                      │
        │                                       │
        │  Extract:   pd.read_csv(...)          │
        │  Transform: parseo de fecha/hora,     │
        │             extracción de estado por  │
        │             regex sobre la referencia,│
        │             clasificación de magnitud,│
        │             construcción de las 4 dims│
        │             y resolución de surrogate │
        │             keys en fact_sismo        │
        │  Load:      to_sql(method='multi',    │
        │             chunksize=1000) + tqdm    │
        │             + validación post-carga   │
        └──────────────────┬────────────────────┘
                            │  INSERT sobre las tablas ya creadas
                            ▼
        ┌──────────────────────────────────────┐
        │  Aurora PostgreSQL                    │
        │  sismicidad-proyecto-instance-1...    │
        │  .rds.amazonaws.com / northwind        │
        │  Schema: sismo_dwh                    │
        │                                       │
        │  • 4 dims + 1 fact, ya pobladas       │
        │  • Índices en date_key, ubicacion_key,│
        │    magnitud_key                       │
        └──────────────────┬────────────────────┘
                            │  SELECT
                            ▼
        ┌──────────────────────────────────────┐
        │  PASO 3 — DBeaver + VS Code            │
        │  Capa analítica                       │
        │  • queries_analiticas.sql (DBeaver)   │
        │  • generar_graficas.py (VS Code)      │
        │  • mapa_sismos_mexico.py (VS Code)     │
        │  • dashboard/app.py (VS Code)          │
        └────────────────────────────────────────┘
```

Nota la diferencia con flujos donde el propio ETL crea las tablas: aquí el schema y las relaciones (`REFERENCES`) se definen primero y a mano en DBeaver, de modo que cualquier error de integridad referencial se detecta antes de cargar datos. El ETL solo hace `INSERT` (`if_exists="append"`), nunca `DROP`/`CREATE`, para no perder las llaves foráneas ya definidas.

### Por qué no se sube el CSV pesado al repo

El archivo `SSNMX_catalogo_19660101_20260607_m40_99.csv` pesa varios MB con 50,056 filas. Subirlo al repositorio:

- Infla el tamaño del clone sin agregar valor — el catálogo del SSN es público y se puede volver a exportar en cualquier momento.
- Cualquier actualización del periodo (por ejemplo, extender a 2027) requeriría reemplazar el archivo completo en el repo.
- Va contra la recomendación de la rúbrica de no subir datasets pesados al repositorio.

Por eso el repositorio solo incluye el código que transforma y carga los datos. El dataset se coloca una sola vez en `datasets/` (no versionado) y a partir de ahí todo el trabajo analítico se hace desde Aurora.

---

## 📁 Estructura del repositorio

```
proyecto-final/
├── README.md                       ← este archivo
├── datasets/
│   └── SSNMX_catalogo_19660101_20260607_m40_99.csv   ← no versionado, se coloca manualmente
├── scripts/
│   ├── 01_schema_ddl.sql           ← esquema estrella (4 dims + 1 fact) + índices
│   ├── etl_pipeline.py             ← ETL Python end-to-end (Extract → Transform → Load)
│   ├── generar_graficas.py         ← 5 visualizaciones estáticas (matplotlib/seaborn)
│   └── mapa_sismos_mexico.py       ← mapa geográfico interactivo (Plotly) + PNG
├── analisis/
│   └── queries_analiticas.sql      ← 6 queries con SQL avanzado
├── dashboard/
│   └── app.py                      ← dashboard interactivo Streamlit + Plotly
└── docs/
    └── graficas/                   ← imágenes generadas (PNG + HTML), no versionadas
        ├── 01_serie_anual.png
        ├── 02_top_estados.png
        ├── 03_heatmap_hora_mes.png
        ├── 04_comparacion_regiones.png
        ├── 05_evolucion_decadas.png
        └── mapa_sismos_por_estado.png / .html
```

---

## 🔧 Cómo ejecutar

El proyecto sigue un flujo de dos herramientas: **DBeaver** para todo lo que es SQL puro (crear el schema, correr las queries analíticas) y **VS Code** para todo lo que es Python (ETL, gráficas, dashboard).

### 1. Setup del schema en Aurora (DBeaver)

Con el cluster Aurora PostgreSQL ya creado (`sismicidad-proyecto`) y conectado en DBeaver, abre `scripts/01_schema_ddl.sql` y ejecútalo completo:

```sql
-- Desde DBeaver, conectado al cluster Aurora
-- Abrir scripts/01_schema_ddl.sql y ejecutar todo (Ctrl+A, Ctrl+Enter)
```

O bien desde `psql` si lo prefieres:

```bash
psql "postgresql://postgres:TU_PASSWORD@sismicidad-proyecto-instance-1.cnokess0ahhv.us-east-1.rds.amazonaws.com:5432/northwind" \
     -f scripts/01_schema_ddl.sql
```

Esto crea el schema `sismo_dwh` con las cinco tablas **vacías** (`dim_fecha`, `dim_hora`, `dim_ubicacion`, `dim_magnitud`, `fact_sismo`), sus llaves foráneas y sus índices. En este punto las tablas existen pero no tienen ningún dato — eso lo hace el ETL en el siguiente paso.

### 2. Colocar el dataset

Descarga el catálogo del SSN y colócalo en `datasets/`:

```
datasets/SSNMX_catalogo_19660101_20260607_m40_99.csv
```

### 3. Instalar dependencias y correr el ETL (VS Code)

Con las tablas ya creadas en el paso 1, ahora en la terminal integrada de VS Code:

```bash
pip install pandas sqlalchemy psycopg2-binary tqdm

python scripts/etl_pipeline.py \
    --host sismicidad-proyecto-instance-1.cnokess0ahhv.us-east-1.rds.amazonaws.com \
    --db northwind \
    --user postgres \
    --password TU_PASSWORD \
    --csv datasets/SSNMX_catalogo_19660101_20260607_m40_99.csv
```

El script crea las cinco tablas en una sola pasada (dimensiones y luego la fact en chunks de 1,000 filas con barra de progreso) y al final valida `COUNT(*)` por tabla contra el origen, además de verificar que no haya registros huérfanos en la fact.

### 4. Verificar la carga (DBeaver)

```sql
SELECT 'fact_sismo'    AS tabla, COUNT(*) FROM sismo_dwh.fact_sismo    UNION ALL
SELECT 'dim_fecha',              COUNT(*) FROM sismo_dwh.dim_fecha      UNION ALL
SELECT 'dim_hora',               COUNT(*) FROM sismo_dwh.dim_hora       UNION ALL
SELECT 'dim_ubicacion',          COUNT(*) FROM sismo_dwh.dim_ubicacion  UNION ALL
SELECT 'dim_magnitud',           COUNT(*) FROM sismo_dwh.dim_magnitud;
```

### 5. Generar las visualizaciones estáticas

```bash
pip install matplotlib seaborn kaleido plotly

python scripts/generar_graficas.py \
    --host sismicidad-proyecto-instance-1.cnokess0ahhv.us-east-1.rds.amazonaws.com \
    --db northwind --user postgres --password TU_PASSWORD

python scripts/mapa_sismos_mexico.py \
    --host sismicidad-proyecto-instance-1.cnokess0ahhv.us-east-1.rds.amazonaws.com \
    --db northwind --user postgres --password TU_PASSWORD
```

Ambos scripts consultan Aurora directamente y guardan las imágenes en `docs/graficas/`.

### 6. Levantar el dashboard interactivo

```bash
pip install streamlit

$env:AURORA_HOST="sismicidad-proyecto-instance-1.cnokess0ahhv.us-east-1.rds.amazonaws.com"
$env:AURORA_PASSWORD="TU_PASSWORD"
python -m streamlit run dashboard/app.py
```

---

## 🏗️ Modelo dimensional

### Esquema estrella

```
                        ┌──────────────────┐
                        │     dim_fecha     │
                        │                   │
                        │ date_key      PK  │
                        │ fecha             │
                        │ anio              │
                        │ mes               │
                        │ nombre_mes        │
                        │ trimestre         │
                        │ decada            │
                        │ dia_semana        │
                        │ es_fin_semana     │
                        └─────────┬─────────┘
                                  ▲
                                  │
┌──────────────┐         ┌───────┴───────────────┐         ┌──────────────────┐
│   dim_hora   │◄────────│      fact_sismo        │────────►│   dim_ubicacion  │
│              │         │                        │         │                  │
│ hour_key PK  │         │ sismo_key         PK   │         │ ubicacion_key PK │
│ hora (0-23)  │         │ date_key          FK   │         │ abreviatura      │
│ banda_dia    │         │ hour_key          FK   │         │ estado           │
│  (madrugada/ │         │ ubicacion_key     FK   │         │ region           │
│   mañana/... │         │ magnitud_key      FK   │         └──────────────────┘
└──────────────┘         │ magnitud  NUMERIC(3,1) │
                          │ latitud   NUMERIC(7,4) │
                          │ longitud  NUMERIC(7,4) │
                          │ profundidad_km   INT   │
                          │ estatus      VARCHAR   │
                          └───────────┬────────────┘
                                      ▼
                            ┌───────────────────┐
                            │   dim_magnitud     │
                            │                    │
                            │ magnitud_key   PK  │
                            │ rango              │
                            │  (Leve/Moderado/   │
                            │   Fuerte/Severo)   │
                            │ m_min              │
                            │ m_max              │
                            └────────────────────┘
```

### Decisiones de diseño

**Grano de la fact:** una fila por evento sísmico registrado por el SSN. Es el grano más fino que el origen provee — cada sismo es un átomo único, sin descomposición adicional posible (a diferencia, por ejemplo, de mediciones repetidas por sensor a través del tiempo).

**Por qué `dim_hora` separada de `dim_fecha`:** el origen viene con fecha y hora en columnas distintas, y analíticamente el patrón horario (¿hay horas con más sismos percibidos?) y el patrón calendario (estacionalidad, década) son ortogonales. Separarlas permite `GROUP BY dh.banda_dia` sin tener que extraer la hora de un timestamp combinado, igual que se hizo con `dim_hour` en el ejemplo de calidad del aire.

**Categorización pre-calculada en `dim_magnitud`:** los umbrales de severidad (Leve, Moderado, Fuerte, Severo) viven en la dimensión y no se recalculan en cada query. Si la clasificación sismológica cambiara, el ajuste se hace en una sola tabla de 4 filas y se propaga a todo el análisis.

**`region` aplanada en `dim_ubicacion`, sin dimensión propia:** las 6 regiones geográficas (Pacífico Sur, Centro, Norte, etc.) son un atributo agregador del estado, no una entidad analizada de forma independiente. Se aplanó en `dim_ubicacion` siguiendo el mismo criterio que `alcaldia` en el ejemplo de calidad del aire — no amerita una tabla separada porque no tiene atributos propios más allá de agrupar estados.

**`date_key` como entero `YYYYMMDD` en lugar de `DATE`:** permite ordenamiento y filtros por rango de año directamente sobre la llave (`WHERE date_key BETWEEN 19850101 AND 19851231`) sin tener que castear tipos, y es ligeramente más eficiente para los índices que usa la fact.

**Latitud, longitud y profundidad como medidas degeneradas en la fact:** no justifican una dimensión propia porque son continuas y específicas de cada evento — no se repiten entre sismos como sí lo haría una estación de monitoreo fija (a diferencia del ejemplo de calidad del aire, donde la estación sí es una entidad recurrente con sus propios atributos).
