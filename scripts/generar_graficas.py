"""
generar_graficas.py — Genera visualizaciones del proyecto de Sismicidad México
y las guarda como imágenes PNG en docs/graficas/

Uso:
    python scripts/generar_graficas.py \
        --host sismicidad-proyecto-instance-1.cnokess0ahhv.us-east-1.rds.amazonaws.com \
        --db northwind \
        --user postgres \
        --password TU_PASSWORD

Dependencias:
    pip install pandas sqlalchemy psycopg2-binary matplotlib seaborn kaleido plotly
"""

import argparse
import logging
import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
from sqlalchemy import create_engine, text

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Estilo general ───────────────────────────────────────────────────────────
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor":   "white",
    "axes.grid":        True,
    "grid.alpha":       0.3,
    "font.family":      "DejaVu Sans",
    "font.size":        11,
})
COLORES = ["#ef4444", "#f59e0b", "#3b82f6", "#10b981", "#8b5cf6", "#ec4899"]


def query(engine, sql):
    with engine.connect() as con:
        return pd.read_sql(text(sql), con)


# ═══════════════════════════════════════════════════════════════════════════════
# GRÁFICA 1 — Serie temporal anual de sismos fuertes y severos
# ═══════════════════════════════════════════════════════════════════════════════
def grafica_serie_anual(engine, out_dir):
    log.info("Generando gráfica 1 — Serie anual...")
    df = query(engine, """
        SELECT
            df.anio,
            COUNT(*) FILTER (WHERE fs.magnitud BETWEEN 6 AND 6.9) AS fuertes,
            COUNT(*) FILTER (WHERE fs.magnitud >= 7)              AS severos
        FROM sismo_dwh.fact_sismo fs
        JOIN sismo_dwh.dim_fecha df USING (date_key)
        WHERE fs.magnitud >= 6
        GROUP BY df.anio
        ORDER BY df.anio
    """)

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.bar(df["anio"], df["fuertes"], label="Fuertes (M 6–6.9)", color="#f59e0b", alpha=0.9)
    ax.bar(df["anio"], df["severos"], bottom=df["fuertes"],
           label="Severos (M ≥ 7)", color="#ef4444", alpha=0.9)

    ax.set_title("Frecuencia anual de sismos fuertes y severos en México (1966–2026)",
                 fontsize=14, fontweight="bold", pad=15)
    ax.set_xlabel("Año")
    ax.set_ylabel("Número de sismos")
    ax.legend(loc="upper left")
    ax.xaxis.set_major_locator(mticker.MultipleLocator(5))
    plt.xticks(rotation=45)

    # Anotar eventos históricos clave
    eventos = {1985: "1985\nCDMX", 2017: "2017\nPuebla", 2010: "2010\nBC"}
    for anio, label in eventos.items():
        if anio in df["anio"].values:
            y = df.loc[df["anio"] == anio, ["fuertes","severos"]].sum(axis=1).values[0]
            ax.annotate(label, xy=(anio, y), xytext=(anio, y+1.5),
                       fontsize=8, ha="center", color="#1e293b",
                       arrowprops=dict(arrowstyle="->", color="#64748b", lw=0.8))

    plt.tight_layout()
    ruta = os.path.join(out_dir, "01_serie_anual.png")
    plt.savefig(ruta, dpi=150, bbox_inches="tight")
    plt.close()
    log.info("  Guardada: %s", ruta)


# ═══════════════════════════════════════════════════════════════════════════════
# GRÁFICA 2 — Top 10 estados con más sismos M≥6
# ═══════════════════════════════════════════════════════════════════════════════
def grafica_top_estados(engine, out_dir):
    log.info("Generando gráfica 2 — Top estados...")
    df = query(engine, """
        SELECT
            du.estado,
            du.region,
            COUNT(*)                   AS total,
            ROUND(AVG(fs.magnitud), 2) AS mag_media,
            MAX(fs.magnitud)           AS mag_max
        FROM sismo_dwh.fact_sismo fs
        JOIN sismo_dwh.dim_ubicacion du USING (ubicacion_key)
        WHERE fs.magnitud >= 6
        GROUP BY du.estado, du.region
        ORDER BY total DESC
        LIMIT 10
    """)

    fig, ax = plt.subplots(figsize=(10, 6))
    colores_barra = [COLORES[i % len(COLORES)] for i in range(len(df))]
    bars = ax.barh(df["estado"], df["total"], color=colores_barra, alpha=0.85)

    # Etiquetas de valor
    for bar, val, mag in zip(bars, df["total"], df["mag_media"]):
        ax.text(bar.get_width() + 5, bar.get_y() + bar.get_height()/2,
                f"{val:,}  (M̄={mag})", va="center", fontsize=9)

    ax.set_title("Top 10 estados con más sismos M ≥ 6.0 (1966–2026)",
                 fontsize=14, fontweight="bold", pad=15)
    ax.set_xlabel("Número de sismos")
    ax.invert_yaxis()
    ax.set_xlim(0, df["total"].max() * 1.25)

    plt.tight_layout()
    ruta = os.path.join(out_dir, "02_top_estados.png")
    plt.savefig(ruta, dpi=150, bbox_inches="tight")
    plt.close()
    log.info("  Guardada: %s", ruta)


# ═══════════════════════════════════════════════════════════════════════════════
# GRÁFICA 3 — Heatmap hora × mes
# ═══════════════════════════════════════════════════════════════════════════════
def grafica_heatmap_temporal(engine, out_dir):
    log.info("Generando gráfica 3 — Heatmap hora × mes...")
    df = query(engine, """
        SELECT
            df.mes,
            df.nombre_mes,
            dh.hora,
            COUNT(*) AS total
        FROM sismo_dwh.fact_sismo fs
        JOIN sismo_dwh.dim_fecha df USING (date_key)
        JOIN sismo_dwh.dim_hora  dh USING (hour_key)
        GROUP BY df.mes, df.nombre_mes, dh.hora
        ORDER BY df.mes, dh.hora
    """)

    orden_meses = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
                   "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
    pivot = df.pivot(index="hora", columns="nombre_mes", values="total")
    pivot = pivot.reindex(columns=[m for m in orden_meses if m in pivot.columns])

    fig, ax = plt.subplots(figsize=(14, 7))
    sns.heatmap(pivot, ax=ax, cmap="YlOrRd", linewidths=0.3,
                cbar_kws={"label": "Número de sismos"},
                annot=False)

    ax.set_title("Distribución de sismos por hora del día y mes del año",
                 fontsize=14, fontweight="bold", pad=15)
    ax.set_xlabel("Mes")
    ax.set_ylabel("Hora del día (UTC−6)")
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0)

    plt.tight_layout()
    ruta = os.path.join(out_dir, "03_heatmap_hora_mes.png")
    plt.savefig(ruta, dpi=150, bbox_inches="tight")
    plt.close()
    log.info("  Guardada: %s", ruta)


# ═══════════════════════════════════════════════════════════════════════════════
# GRÁFICA 4 — Magnitud promedio por región (ranking)
# ═══════════════════════════════════════════════════════════════════════════════
def grafica_regiones(engine, out_dir):
    log.info("Generando gráfica 4 — Comparación por región...")
    df = query(engine, """
        SELECT
            du.region,
            COUNT(*)                                                     AS total,
            ROUND(AVG(fs.magnitud), 2)                                   AS mag_media,
            COUNT(*) FILTER (WHERE fs.magnitud >= 6)                     AS fuertes,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY fs.magnitud)    AS mag_p95
        FROM sismo_dwh.fact_sismo fs
        JOIN sismo_dwh.dim_ubicacion du USING (ubicacion_key)
        GROUP BY du.region
        ORDER BY mag_media DESC
    """)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Subplot 1 — Magnitud media por región
    colores = [COLORES[i % len(COLORES)] for i in range(len(df))]
    axes[0].barh(df["region"], df["mag_media"], color=colores, alpha=0.85)
    axes[0].set_title("Magnitud promedio por región", fontweight="bold")
    axes[0].set_xlabel("Magnitud promedio")
    axes[0].invert_yaxis()
    axes[0].set_xlim(4.0, df["mag_media"].max() + 0.2)
    for i, (val, p95) in enumerate(zip(df["mag_media"], df["mag_p95"])):
        axes[0].text(val + 0.01, i, f"{val}  (P95={p95:.1f})", va="center", fontsize=9)

    # Subplot 2 — Total de sismos por región
    axes[1].barh(df["region"], df["total"], color=colores, alpha=0.85)
    axes[1].set_title("Total de sismos registrados por región", fontweight="bold")
    axes[1].set_xlabel("Número de sismos")
    axes[1].invert_yaxis()
    for i, val in enumerate(df["total"]):
        axes[1].text(val + 50, i, f"{val:,}", va="center", fontsize=9)

    fig.suptitle("Actividad sísmica por región geográfica (M ≥ 4.0)",
                 fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    ruta = os.path.join(out_dir, "04_comparacion_regiones.png")
    plt.savefig(ruta, dpi=150, bbox_inches="tight")
    plt.close()
    log.info("  Guardada: %s", ruta)


# ═══════════════════════════════════════════════════════════════════════════════
# GRÁFICA 5 — Evolución por década
# ═══════════════════════════════════════════════════════════════════════════════
def grafica_decadas(engine, out_dir):
    log.info("Generando gráfica 5 — Evolución por década...")
    df = query(engine, """
        SELECT
            df.decada,
            dm.rango,
            COUNT(*) AS total
        FROM sismo_dwh.fact_sismo fs
        JOIN sismo_dwh.dim_fecha    df USING (date_key)
        JOIN sismo_dwh.dim_magnitud dm USING (magnitud_key)
        GROUP BY df.decada, dm.rango
        ORDER BY df.decada, dm.rango
    """)

    pivot = df.pivot(index="decada", columns="rango", values="total").fillna(0)
    orden = [c for c in ["Leve","Moderado","Fuerte","Severo"] if c in pivot.columns]
    pivot = pivot[orden]

    fig, ax = plt.subplots(figsize=(12, 5))
    colores_dec = ["#93c5fd", "#f59e0b", "#ef4444", "#7f1d1d"]
    pivot.plot(kind="bar", ax=ax, color=colores_dec[:len(orden)],
               alpha=0.85, width=0.7, edgecolor="white")

    ax.set_title("Sismos registrados por década y categoría de magnitud",
                 fontsize=14, fontweight="bold", pad=15)
    ax.set_xlabel("Década")
    ax.set_ylabel("Número de sismos")
    ax.legend(title="Categoría", bbox_to_anchor=(1.01, 1), loc="upper left")
    plt.xticks(rotation=0)
    plt.tight_layout()

    ruta = os.path.join(out_dir, "05_evolucion_decadas.png")
    plt.savefig(ruta, dpi=150, bbox_inches="tight")
    plt.close()
    log.info("  Guardada: %s", ruta)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Genera gráficas del proyecto de sismicidad")
    parser.add_argument("--host",     required=True)
    parser.add_argument("--db",       default="northwind")
    parser.add_argument("--user",     default="postgres")
    parser.add_argument("--password", required=True)
    parser.add_argument("--port",     default=5432, type=int)
    parser.add_argument("--out",      default="docs/graficas",
                        help="Carpeta donde guardar las imágenes")
    args = parser.parse_args()

    # Crear carpeta de salida
    os.makedirs(args.out, exist_ok=True)
    log.info("Guardando gráficas en: %s", os.path.abspath(args.out))

    db_url = (
        f"postgresql+psycopg2://{args.user}:{args.password}"
        f"@{args.host}:{args.port}/{args.db}"
    )
    engine = create_engine(db_url, pool_pre_ping=True)

    log.info("=== Generando visualizaciones ===")
    grafica_serie_anual(engine, args.out)
    grafica_top_estados(engine, args.out)
    grafica_heatmap_temporal(engine, args.out)
    grafica_regiones(engine, args.out)
    grafica_decadas(engine, args.out)
    log.info("=== Listo — 5 gráficas generadas en %s ===", args.out)


if __name__ == "__main__":
    main()
