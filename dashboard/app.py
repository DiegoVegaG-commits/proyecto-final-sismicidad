"""
dashboard/app.py — Dashboard interactivo de Sismicidad México (SSN 1966–2026)

Uso:
    pip install streamlit pandas sqlalchemy psycopg2-binary plotly
    streamlit run dashboard/app.py

    Variables de entorno (o editar la sección CONFIG):
        AURORA_HOST, AURORA_DB, AURORA_USER, AURORA_PASSWORD
"""

import os
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine, text

# ─── CONFIG ──────────────────────────────────────────────────────────────────
AURORA_HOST = os.getenv("AURORA_HOST", "TU_HOST.rds.amazonaws.com")
AURORA_DB   = os.getenv("AURORA_DB",   "northwind")
AURORA_USER = os.getenv("AURORA_USER", "postgres")
AURORA_PASS = os.getenv("AURORA_PASSWORD", "TU_PASSWORD")
AURORA_PORT = int(os.getenv("AURORA_PORT", "5432"))

DB_URL = (
    f"postgresql+psycopg2://{AURORA_USER}:{AURORA_PASS}"
    f"@{AURORA_HOST}:{AURORA_PORT}/{AURORA_DB}"
)

# ─── Conexión (cacheada) ──────────────────────────────────────────────────────
@st.cache_resource
def get_engine():
    return create_engine(DB_URL, pool_pre_ping=True)


@st.cache_data(ttl=300)
def query(sql: str, params: dict = None) -> pd.DataFrame:
    with get_engine().connect() as con:
        return pd.read_sql(text(sql), con, params=params)


# ─── Carga de datos ───────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_all():
    # Anios disponibles
    anios = query("SELECT MIN(anio) AS min, MAX(anio) AS max FROM sismo_dwh.dim_fecha")

    # Tabla principal para filtros
    estados = query("""
        SELECT DISTINCT du.estado, du.region
        FROM sismo_dwh.dim_ubicacion du
        JOIN sismo_dwh.fact_sismo fs USING (ubicacion_key)
        ORDER BY du.estado
    """)
    return anios, estados


# ─── Layout ───────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Sismicidad México",
    page_icon="🌎",
    layout="wide",
)

st.title("🌎 Sismicidad en México — SSN 1966–2026")
st.caption("Catálogo del Servicio Sismológico Nacional · Magnitudes ≥ 4.0")

# ── Sidebar filtros ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Filtros")

    anios_df, estados_df = load_all()
    anio_min = int(anios_df["min"].iloc[0])
    anio_max = int(anios_df["max"].iloc[0])

    rango_anio = st.slider(
        "Rango de años", min_value=anio_min, max_value=anio_max,
        value=(1990, anio_max)
    )

    regiones = ["Todas"] + sorted(estados_df["region"].unique().tolist())
    region_sel = st.selectbox("Región", regiones)

    mag_min = st.selectbox(
        "Magnitud mínima",
        options=[4.0, 5.0, 6.0, 7.0],
        index=1,
        format_func=lambda x: f"M ≥ {x}"
    )

    st.markdown("---")
    st.markdown("**Dataset:** SSN · UNAM")
    st.markdown("**Registros totales:** ~50,000")


# ── Métricas resumen ──────────────────────────────────────────────────────────
filtro_region = (
    "AND du.region = :region" if region_sel != "Todas" else ""
)

metricas = query(f"""
    SELECT
        COUNT(*)                                      AS total,
        COUNT(*) FILTER (WHERE fs.magnitud >= 6)      AS fuertes,
        COUNT(*) FILTER (WHERE fs.magnitud >= 7)      AS severos,
        ROUND(AVG(fs.magnitud), 2)                    AS mag_media,
        MAX(fs.magnitud)                              AS mag_max
    FROM      sismo_dwh.fact_sismo fs
    JOIN      sismo_dwh.dim_fecha     df USING (date_key)
    JOIN      sismo_dwh.dim_ubicacion du USING (ubicacion_key)
    WHERE     df.anio BETWEEN :anio_min AND :anio_max
      AND     fs.magnitud >= :mag_min
      {filtro_region}
""", {
    "anio_min": rango_anio[0],
    "anio_max": rango_anio[1],
    "mag_min": mag_min,
    "region": region_sel if region_sel != "Todas" else None,
})

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total sismos",     f"{int(metricas['total'].iloc[0]):,}")
col2.metric("M ≥ 6 (Fuertes)",  f"{int(metricas['fuertes'].iloc[0]):,}")
col3.metric("M ≥ 7 (Severos)",  f"{int(metricas['severos'].iloc[0]):,}")
col4.metric("Magnitud promedio",f"{metricas['mag_media'].iloc[0]}")
col5.metric("Magnitud máxima",  f"{metricas['mag_max'].iloc[0]}")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# VIZ 1 — Serie temporal anual
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("📈 Frecuencia anual de sismos fuertes y severos")

serie = query(f"""
    SELECT
        df.anio,
        COUNT(*) FILTER (WHERE fs.magnitud BETWEEN 6 AND 6.9)  AS fuertes,
        COUNT(*) FILTER (WHERE fs.magnitud >= 7)                AS severos,
        COUNT(*)                                                AS total
    FROM      sismo_dwh.fact_sismo fs
    JOIN      sismo_dwh.dim_fecha     df USING (date_key)
    JOIN      sismo_dwh.dim_ubicacion du USING (ubicacion_key)
    WHERE     df.anio BETWEEN :anio_min AND :anio_max
      AND     fs.magnitud >= 6
      {filtro_region}
    GROUP BY  df.anio
    ORDER BY  df.anio
""", {"anio_min": rango_anio[0], "anio_max": rango_anio[1],
      "region": region_sel if region_sel != "Todas" else None})

fig_serie = go.Figure()
fig_serie.add_bar(x=serie["anio"], y=serie["fuertes"],
                  name="Fuertes (M 6–6.9)", marker_color="#f59e0b")
fig_serie.add_bar(x=serie["anio"], y=serie["severos"],
                  name="Severos (M ≥ 7)",   marker_color="#ef4444")
fig_serie.update_layout(
    barmode="stack",
    xaxis_title="Año", yaxis_title="Número de sismos",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    height=380,
)
st.plotly_chart(fig_serie, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# VIZ 2 — Top estados + Mapa de puntos
# ══════════════════════════════════════════════════════════════════════════════
col_bar, col_map = st.columns([1, 1.5])

with col_bar:
    st.subheader("🏆 Top 10 estados — sismos M ≥ 6")
    top_estados = query(f"""
        WITH ranking AS (
            SELECT
                du.estado,
                du.region,
                COUNT(*)                   AS total,
                ROUND(AVG(fs.magnitud), 2) AS mag_media,
                MAX(fs.magnitud)           AS mag_max,
                RANK() OVER (ORDER BY COUNT(*) DESC) AS rk
            FROM      sismo_dwh.fact_sismo fs
            JOIN      sismo_dwh.dim_fecha     df USING (date_key)
            JOIN      sismo_dwh.dim_ubicacion du USING (ubicacion_key)
            WHERE     df.anio BETWEEN :anio_min AND :anio_max
              AND     fs.magnitud >= 6
              {filtro_region}
            GROUP BY  du.estado, du.region
        )
        SELECT * FROM ranking WHERE rk <= 10 ORDER BY total DESC
    """, {"anio_min": rango_anio[0], "anio_max": rango_anio[1],
          "region": region_sel if region_sel != "Todas" else None})

    fig_bar = px.bar(
        top_estados, x="total", y="estado",
        orientation="h",
        color="mag_media",
        color_continuous_scale="Reds",
        labels={"total": "Sismos M≥6", "estado": "", "mag_media": "Mag. media"},
        hover_data=["region", "mag_max"],
    )
    fig_bar.update_layout(height=400, yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig_bar, use_container_width=True)

with col_map:
    st.subheader("🗺️ Distribución geográfica de sismos")
    puntos = query(f"""
        SELECT
            fs.latitud, fs.longitud, fs.magnitud,
            du.estado, df.anio
        FROM      sismo_dwh.fact_sismo fs
        JOIN      sismo_dwh.dim_fecha     df USING (date_key)
        JOIN      sismo_dwh.dim_ubicacion du USING (ubicacion_key)
        WHERE     df.anio BETWEEN :anio_min AND :anio_max
          AND     fs.magnitud >= :mag_min
          {filtro_region}
        -- Muestra máximo 5000 puntos para no saturar el mapa
        ORDER BY  fs.magnitud DESC
        LIMIT 5000
    """, {"anio_min": rango_anio[0], "anio_max": rango_anio[1],
          "mag_min": mag_min,
          "region": region_sel if region_sel != "Todas" else None})

    fig_mapa = px.scatter_mapbox(
        puntos, lat="latitud", lon="longitud",
        size="magnitud", size_max=15,
        color="magnitud",
        color_continuous_scale="Reds",
        hover_name="estado",
        hover_data={"anio": True, "magnitud": True,
                    "latitud": False, "longitud": False},
        mapbox_style="carto-positron",
        zoom=4, center={"lat": 23.6, "lon": -102.5},
        labels={"magnitud": "Magnitud"},
        height=400,
    )
    fig_mapa.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})
    st.plotly_chart(fig_mapa, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# VIZ 3 — Heatmap hora × mes
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("🕐 Patrón temporal: frecuencia de sismos por hora y mes")

heatmap_data = query(f"""
    SELECT
        df.mes,
        df.nombre_mes,
        dh.hora,
        COUNT(*) AS total
    FROM      sismo_dwh.fact_sismo fs
    JOIN      sismo_dwh.dim_fecha     df USING (date_key)
    JOIN      sismo_dwh.dim_hora      dh USING (hour_key)
    JOIN      sismo_dwh.dim_ubicacion du USING (ubicacion_key)
    WHERE     df.anio BETWEEN :anio_min AND :anio_max
      AND     fs.magnitud >= :mag_min
      {filtro_region}
    GROUP BY  df.mes, df.nombre_mes, dh.hora
    ORDER BY  df.mes, dh.hora
""", {"anio_min": rango_anio[0], "anio_max": rango_anio[1],
      "mag_min": mag_min,
      "region": region_sel if region_sel != "Todas" else None})

pivot = heatmap_data.pivot(index="hora", columns="nombre_mes", values="total")
# Ordenar columnas por mes
orden_meses = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
               "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
pivot = pivot.reindex(columns=[m for m in orden_meses if m in pivot.columns])

fig_heat = px.imshow(
    pivot,
    color_continuous_scale="YlOrRd",
    labels=dict(x="Mes", y="Hora del día", color="Sismos"),
    aspect="auto",
    height=400,
)
fig_heat.update_layout(
    xaxis_title="Mes", yaxis_title="Hora del día (UTC local)",
    coloraxis_colorbar=dict(title="Núm. sismos"),
)
st.plotly_chart(fig_heat, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# VIZ 4 — Sismos históricos más intensos
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("💥 Los 20 sismos más intensos del período")

top20 = query(f"""
    WITH ordenados AS (
        SELECT
            df.fecha,
            dh.hora,
            du.estado,
            du.region,
            fs.magnitud,
            fs.profundidad_km,
            ROW_NUMBER() OVER (ORDER BY fs.magnitud DESC, df.fecha) AS rn
        FROM      sismo_dwh.fact_sismo fs
        JOIN      sismo_dwh.dim_fecha     df USING (date_key)
        JOIN      sismo_dwh.dim_hora      dh USING (hour_key)
        JOIN      sismo_dwh.dim_ubicacion du USING (ubicacion_key)
        WHERE     df.anio BETWEEN :anio_min AND :anio_max
          {filtro_region}
    )
    SELECT * FROM ordenados WHERE rn <= 20
""", {"anio_min": rango_anio[0], "anio_max": rango_anio[1],
      "region": region_sel if region_sel != "Todas" else None})

st.dataframe(
    top20.drop(columns="rn").rename(columns={
        "fecha": "Fecha", "hora": "Hora",
        "estado": "Estado", "region": "Región",
        "magnitud": "Magnitud", "profundidad_km": "Profundidad (km)",
    }),
    hide_index=True,
    use_container_width=True,
)

st.caption("Datos: Servicio Sismológico Nacional (SSN) · UNAM · 1966–2026")
