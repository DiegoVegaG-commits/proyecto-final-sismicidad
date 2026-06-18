"""
mapa_sismos_mexico.py — Genera un mapa de México con el sismo más fuerte
registrado en cada estado, guardado como HTML interactivo y PNG estático.

Uso:
    python scripts/mapa_sismos_mexico.py \
        --host sismicidad-proyecto-instance-1.cnokess0ahhv.us-east-1.rds.amazonaws.com \
        --db northwind \
        --user postgres \
        --password TU_PASSWORD

Dependencias (ya instaladas):
    pip install pandas sqlalchemy psycopg2-binary plotly kaleido
"""

import argparse
import logging
import os
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine, text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def query(engine, sql):
    with engine.connect() as con:
        return pd.read_sql(text(sql), con)


def generar_mapa(engine, out_dir):
    log.info("Consultando sismo más fuerte por estado...")

    df = query(engine, """
        WITH ranked AS (
            SELECT
                du.estado,
                du.region,
                df.fecha,
                df.anio,
                fs.magnitud,
                fs.latitud,
                fs.longitud,
                fs.profundidad_km,
                ROW_NUMBER() OVER (
                    PARTITION BY du.estado
                    ORDER BY fs.magnitud DESC, df.fecha
                ) AS rn
            FROM sismo_dwh.fact_sismo fs
            JOIN sismo_dwh.dim_fecha     df USING (date_key)
            JOIN sismo_dwh.dim_ubicacion du USING (ubicacion_key)
        )
        SELECT * FROM ranked WHERE rn = 1
        ORDER BY magnitud DESC
    """)

    log.info("  Estados encontrados: %d", len(df))

    # ── Categoría para color ──────────────────────────────────────────────────
    def categoria(m):
        if m >= 7:   return "Severo (M≥7)"
        elif m >= 6: return "Fuerte (M 6–6.9)"
        else:        return "Moderado (M 5–5.9)"

    df["categoria"] = df["magnitud"].apply(categoria)

    COLORES_CAT = {
        "Severo (M≥7)":      "#dc2626",
        "Fuerte (M 6–6.9)":  "#f59e0b",
        "Moderado (M 5–5.9)":"#3b82f6",
    }

    # ── Texto hover ───────────────────────────────────────────────────────────
    df["texto"] = df.apply(lambda r: (
        f"<b>{r['estado']}</b><br>"
        f"Magnitud: <b>M {r['magnitud']}</b><br>"
        f"Fecha: {r['fecha']}<br>"
        f"Región: {r['region']}<br>"
        f"Profundidad: {r['profundidad_km']} km"
    ), axis=1)

    # ── Tamaño de burbuja proporcional a magnitud ──────────────────────────
    df["tamaño"] = (df["magnitud"] ** 3) / 5

    # ── Construir figura ──────────────────────────────────────────────────────
    fig = go.Figure()

    for cat, color in COLORES_CAT.items():
        mask = df["categoria"] == cat
        sub = df[mask]
        if sub.empty:
            continue
        fig.add_trace(go.Scattergeo(
            lat=sub["latitud"],
            lon=sub["longitud"],
            text=sub["texto"],
            hoverinfo="text",
            mode="markers",
            name=cat,
            marker=dict(
                size=sub["tamaño"],
                color=color,
                opacity=0.85,
                line=dict(width=1, color="white"),
                sizemode="area",
            )
        ))

    # ── Etiquetas de magnitud sobre cada punto ────────────────────────────────
    fig.add_trace(go.Scattergeo(
        lat=df["latitud"],
        lon=df["longitud"],
        text=df["magnitud"].apply(lambda m: f"M{m}"),
        mode="text",
        textfont=dict(size=8, color="#1e293b", family="Arial Black"),
        showlegend=False,
        hoverinfo="skip",
    ))

    fig.update_layout(
        title=dict(
            text="<b>Sismo más intenso registrado por estado — México (SSN 1966–2026)</b><br>"
                 "<sup>Tamaño del círculo proporcional a la magnitud · "
                 "Datos: Servicio Sismológico Nacional · UNAM</sup>",
            x=0.5,
            xanchor="center",
            font=dict(size=16),
        ),
        geo=dict(
            scope="north america",
            resolution=50,
            showland=True,
            landcolor="#f1f5f9",
            showocean=True,
            oceancolor="#dbeafe",
            showcountries=True,
            countrycolor="#94a3b8",
            showcoastlines=True,
            coastlinecolor="#64748b",
            showlakes=True,
            lakecolor="#dbeafe",
            showrivers=True,
            rivercolor="#93c5fd",
            center=dict(lat=23.6, lon=-102.5),
            projection_scale=3.2,
            lataxis=dict(range=[14, 33]),
            lonaxis=dict(range=[-118, -86]),
        ),
        legend=dict(
            title="<b>Categoría</b>",
            x=0.01, y=0.99,
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor="#cbd5e1",
            borderwidth=1,
        ),
        margin=dict(l=0, r=0, t=80, b=0),
        height=650,
        paper_bgcolor="white",
    )

    # ── Guardar HTML interactivo ──────────────────────────────────────────────
    os.makedirs(out_dir, exist_ok=True)
    ruta_html = os.path.join(out_dir, "mapa_sismos_por_estado.html")
    fig.write_html(ruta_html, include_plotlyjs="cdn")
    log.info("  Mapa HTML guardado: %s", ruta_html)

    # ── Intentar guardar PNG estático ─────────────────────────────────────────
    ruta_png = os.path.join(out_dir, "mapa_sismos_por_estado.png")
    try:
        fig.write_image(ruta_png, width=1400, height=750, scale=2)
        log.info("  Mapa PNG  guardado: %s", ruta_png)
    except Exception:
        log.warning("  No se pudo generar PNG (instala kaleido: pip install kaleido)")
        log.warning("  Pero el HTML interactivo sí quedó guardado.")

    # ── Tabla resumen en consola ──────────────────────────────────────────────
    log.info("\n%s", "=" * 55)
    log.info("  RANKING — Sismos más intensos por estado")
    log.info("%s", "=" * 55)
    for _, r in df.sort_values("magnitud", ascending=False).iterrows():
        log.info("  %-25s  M%-4s  %s", r["estado"], r["magnitud"], str(r["fecha"]))


def main():
    parser = argparse.ArgumentParser(description="Mapa de sismos más fuertes por estado")
    parser.add_argument("--host",     required=True)
    parser.add_argument("--db",       default="northwind")
    parser.add_argument("--user",     default="postgres")
    parser.add_argument("--password", required=True)
    parser.add_argument("--port",     default=5432, type=int)
    parser.add_argument("--out",      default="docs/graficas")
    args = parser.parse_args()

    db_url = (
        f"postgresql+psycopg2://{args.user}:{args.password}"
        f"@{args.host}:{args.port}/{args.db}"
    )
    engine = create_engine(db_url, pool_pre_ping=True)

    log.info("=== Mapa de sismicidad por estado ===")
    generar_mapa(engine, args.out)
    log.info("=== Listo ===")


if __name__ == "__main__":
    main()
