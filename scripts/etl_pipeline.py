"""
etl_pipeline.py — ETL completo para el proyecto de Sismicidad México (SSN 1966–2026)

Uso:
    python etl_pipeline.py \
        --host TU_HOST.rds.amazonaws.com \
        --db  northwind \
        --user postgres \
        --password Sismicidad1966#2026 \
        --csv datasets/SSNMX_catalogo_19660101_20260607_m40_99.csv

Dependencias:
    pip install pandas sqlalchemy psycopg2-binary tqdm
"""

import argparse
import logging
import sys
import pandas as pd
from sqlalchemy import create_engine, text
from tqdm import tqdm

# ─── Configuración de logging ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Mapas de referencia ─────────────────────────────────────────────────────

NOMBRES_ESTADO = {
    "OAX":  "Oaxaca",           "CHIS": "Chiapas",
    "GRO":  "Guerrero",         "MICH": "Michoacán",
    "VER":  "Veracruz",         "BCS":  "Baja California Sur",
    "JAL":  "Jalisco",          "BC":   "Baja California",
    "SIN":  "Sinaloa",          "SON":  "Sonora",
    "COL":  "Colima",           "CHIH": "Chihuahua",
    "TAB":  "Tabasco",          "NAY":  "Nayarit",
    "SLP":  "San Luis Potosí",  "PUE":  "Puebla",
    "COAH": "Coahuila",         "NL":   "Nuevo León",
    "QR":   "Quintana Roo",     "HGO":  "Hidalgo",
    "TAMS": "Tamaulipas",       "DGO":  "Durango",
    "GTO":  "Guanajuato",       "MEX":  "Estado de México",
    "ZAC":  "Zacatecas",        "CAMP": "Campeche",
    "TLAX": "Tlaxcala",         "YUC":  "Yucatán",
    "MOR":  "Morelos",          "QRO":  "Querétaro",
    "CDMX": "Ciudad de México", "AGS":  "Aguascalientes",
}

REGIONES = {
    "OAX":  "Pacífico Sur",   "CHIS": "Sur",
    "GRO":  "Pacífico Sur",   "MICH": "Pacífico Centro",
    "JAL":  "Pacífico Centro","COL":  "Pacífico Centro",
    "NAY":  "Pacífico Norte", "SIN":  "Noroeste",
    "SON":  "Noroeste",       "BC":   "Noroeste",
    "BCS":  "Noroeste",       "VER":  "Golfo",
    "TAB":  "Sur",            "CAMP": "Golfo",
    "QR":   "Sureste",        "YUC":  "Sureste",
    "PUE":  "Centro",         "HGO":  "Centro",
    "MEX":  "Centro",         "CDMX": "Centro",
    "MOR":  "Centro",         "TLAX": "Centro",
    "QRO":  "Centro",         "GTO":  "Centro",
    "AGS":  "Norte",          "ZAC":  "Norte",
    "DGO":  "Norte",          "CHIH": "Norte",
    "COAH": "Norte",          "NL":   "Norte",
    "TAMS": "Norte",          "SLP":  "Norte",
}

BANDAS_DIA = {
    range(0, 6):   "madrugada",
    range(6, 12):  "mañana",
    range(12, 19): "tarde",
    range(19, 24): "noche",
}

RANGOS_MAGNITUD = [
    (1, "Leve",     4.0, 4.9),
    (2, "Moderado", 5.0, 5.9),
    (3, "Fuerte",   6.0, 6.9),
    (4, "Severo",   7.0, 9.9),
]

NOMBRES_MES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}


# ═══════════════════════════════════════════════════════════════════════════════
# EXTRACT
# ═══════════════════════════════════════════════════════════════════════════════

def extract(csv_path: str) -> pd.DataFrame:
    """Carga el CSV crudo del SSN y hace validaciones básicas."""
    log.info("EXTRACT — leyendo %s", csv_path)
    df = pd.read_csv(csv_path)
    log.info("  Filas cargadas : %d", len(df))
    log.info("  Columnas       : %s", list(df.columns))

    # Verificar columnas esperadas
    expected = {"Fecha", "Hora", "Magnitud", "Latitud", "Longitud",
                "Profundidad", "Referencia de localizacion", "Estatus"}
    missing = expected - set(df.columns)
    if missing:
        raise ValueError(f"Columnas faltantes en el CSV: {missing}")

    return df


# ═══════════════════════════════════════════════════════════════════════════════
# TRANSFORM
# ═══════════════════════════════════════════════════════════════════════════════

def _banda_dia(hora: int) -> str:
    for rng, banda in BANDAS_DIA.items():
        if hora in rng:
            return banda
    return "noche"


def _magnitud_key(mag: float) -> int:
    for key, _, m_min, m_max in RANGOS_MAGNITUD:
        if m_min <= mag <= m_max:
            return key
    return 4  # Severo si está fuera de rango alto


def transform(df: pd.DataFrame):
    """
    Transforma el DataFrame crudo en las cinco tablas del modelo dimensional.
    Devuelve: (dim_fecha, dim_hora, dim_ubicacion, dim_magnitud, fact_sismo)
    """
    log.info("TRANSFORM — iniciando transformaciones...")

    # ── Parsear fechas y horas ──────────────────────────────────────────────
    df = df.copy()
    df["fecha_dt"] = pd.to_datetime(df["Fecha"], format="%d/%m/%Y", errors="coerce")
    df["hora_int"] = (
        pd.to_datetime(df["Hora"], format="%H:%M:%S", errors="coerce").dt.hour
    )

    filas_antes = len(df)
    df = df.dropna(subset=["fecha_dt", "hora_int", "Magnitud", "Latitud", "Longitud"])
    log.info("  Filas válidas  : %d (descartadas: %d)", len(df), filas_antes - len(df))

    df["hora_int"] = df["hora_int"].astype(int)

    # ── Extraer abreviatura de estado ───────────────────────────────────────
    df["abreviatura"] = (
        df["Referencia de localizacion"]
        .str.extract(r",\s*([A-Z]+)$")[0]
        .fillna("OTRO")
    )

    # ── dim_fecha ───────────────────────────────────────────────────────────
    log.info("  Construyendo dim_fecha...")
    fechas_unicas = df["fecha_dt"].drop_duplicates().sort_values()
    dim_fecha = pd.DataFrame({
        "date_key":     fechas_unicas.dt.strftime("%Y%m%d").astype(int),
        "fecha":        fechas_unicas.dt.date,
        "anio":         fechas_unicas.dt.year.astype("int16"),
        "mes":          fechas_unicas.dt.month.astype("int16"),
        "nombre_mes":   fechas_unicas.dt.month.map(NOMBRES_MES),
        "trimestre":    fechas_unicas.dt.quarter.astype("int16"),
        "decada":       ((fechas_unicas.dt.year // 10) * 10).astype("int16"),
        "dia_semana":   fechas_unicas.dt.day_name(),
        "es_fin_semana": fechas_unicas.dt.dayofweek >= 5,
    }).drop_duplicates("date_key").reset_index(drop=True)

    # ── dim_hora ────────────────────────────────────────────────────────────
    log.info("  Construyendo dim_hora...")
    dim_hora = pd.DataFrame({
        "hour_key": range(24),
        "hora":     range(24),
        "banda_dia": [_banda_dia(h) for h in range(24)],
    })

    # ── dim_ubicacion ───────────────────────────────────────────────────────
    log.info("  Construyendo dim_ubicacion...")
    abrevs = sorted(df["abreviatura"].unique())
    dim_ubicacion = pd.DataFrame({
        "abreviatura": abrevs,
        "estado":  [NOMBRES_ESTADO.get(a, a) for a in abrevs],
        "region":  [REGIONES.get(a, "Otro") for a in abrevs],
    }).reset_index(drop=True)
    dim_ubicacion.insert(0, "ubicacion_key", dim_ubicacion.index + 1)

    # ── dim_magnitud ────────────────────────────────────────────────────────
    log.info("  Construyendo dim_magnitud...")
    dim_magnitud = pd.DataFrame(
        RANGOS_MAGNITUD, columns=["magnitud_key", "rango", "m_min", "m_max"]
    )

    # ── fact_sismo ──────────────────────────────────────────────────────────
    log.info("  Construyendo fact_sismo...")
    ubi_map = dict(zip(dim_ubicacion["abreviatura"], dim_ubicacion["ubicacion_key"]))

    df["date_key"]      = df["fecha_dt"].dt.strftime("%Y%m%d").astype(int)
    df["hour_key"]      = df["hora_int"].astype("int16")
    df["ubicacion_key"] = df["abreviatura"].map(ubi_map)
    df["magnitud_key"]  = df["Magnitud"].apply(_magnitud_key).astype("int16")

    fact_sismo = df[[
        "date_key", "hour_key", "ubicacion_key", "magnitud_key",
        "Magnitud", "Latitud", "Longitud", "Profundidad", "Estatus",
    ]].copy()
    fact_sismo.columns = [
        "date_key", "hour_key", "ubicacion_key", "magnitud_key",
        "magnitud", "latitud", "longitud", "profundidad_km", "estatus",
    ]
    fact_sismo = fact_sismo.dropna(subset=["ubicacion_key"])

    log.info("  dim_fecha      : %d filas", len(dim_fecha))
    log.info("  dim_hora       : %d filas", len(dim_hora))
    log.info("  dim_ubicacion  : %d filas", len(dim_ubicacion))
    log.info("  dim_magnitud   : %d filas", len(dim_magnitud))
    log.info("  fact_sismo     : %d filas", len(fact_sismo))

    return dim_fecha, dim_hora, dim_ubicacion, dim_magnitud, fact_sismo


# ═══════════════════════════════════════════════════════════════════════════════
# Cargar
# ═══════════════════════════════════════════════════════════════════════════════

def _load_table(df: pd.DataFrame, table: str, engine, schema: str = "sismo_dwh"):
    """Carga una tabla usando replace (idempotente: re-correr no duplica)."""
    log.info("  Cargando %s (%d filas)...", table, len(df))
    df.to_sql(
        table, engine,
        schema=schema,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=500,
    )


def load(engine, dim_fecha, dim_hora, dim_ubicacion, dim_magnitud, fact_sismo):
    """Carga las cinco tablas en Aurora y verifica conteos post-carga."""
    log.info("LOAD — cargando a Aurora (schema sismo_dwh)...")

    # Cargar dimensiones primero (integridad referencial)
    _load_table(dim_magnitud,  "dim_magnitud",  engine)
    _load_table(dim_hora,      "dim_hora",       engine)
    _load_table(dim_fecha,     "dim_fecha",      engine)
    _load_table(dim_ubicacion, "dim_ubicacion",  engine)

    # Cargar fact (más grande, con tqdm para progreso)
    log.info("  Cargando fact_sismo (%d filas) en chunks de 1000...", len(fact_sismo))
    chunks = [fact_sismo[i:i+1000] for i in range(0, len(fact_sismo), 1000)]
    first_chunk = True
    for chunk in tqdm(chunks, desc="fact_sismo"):
        chunk.to_sql(
            "fact_sismo", engine,
            schema="sismo_dwh",
            if_exists="append",
            index=False,
            method="multi",
        )
        first_chunk = False

    # ── Validaciones post-carga ─────────────────────────────────────────────
    log.info("VALIDACIÓN — verificando integridad post-carga...")
    with engine.connect() as con:
        checks = {
            "dim_fecha":     len(dim_fecha),
            "dim_hora":      len(dim_hora),
            "dim_ubicacion": len(dim_ubicacion),
            "dim_magnitud":  len(dim_magnitud),
            "fact_sismo":    len(fact_sismo),
        }
        all_ok = True
        for tabla, esperado in checks.items():
            real = con.execute(
                text(f"SELECT COUNT(*) FROM sismo_dwh.{tabla}")
            ).scalar()
            status = "✓" if real == esperado else "✗ ERROR"
            log.info("  %-18s esperado=%d  en_db=%d  %s", tabla, esperado, real, status)
            if real != esperado:
                all_ok = False

        # Verificar integridad referencial (no debe haber huérfanos)
        huerfanos = con.execute(text("""
            SELECT COUNT(*) FROM sismo_dwh.fact_sismo fs
            LEFT JOIN sismo_dwh.dim_fecha df ON fs.date_key = df.date_key
            WHERE df.date_key IS NULL
        """)).scalar()
        log.info("  Huérfanos en fact (dim_fecha): %d", huerfanos)

    if all_ok:
        log.info("Carga completada exitosamente ✓")
    else:
        log.error("Hay discrepancias — revisar los logs anteriores")
        sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="ETL Sismicidad México → Aurora")
    parser.add_argument("--host",     required=True, help="Host del cluster Aurora")
    parser.add_argument("--db",       default="northwind", help="Nombre de la base de datos")
    parser.add_argument("--user",     default="postgres")
    parser.add_argument("--password", required=True)
    parser.add_argument("--port",     default=5432, type=int)
    parser.add_argument("--csv",      required=True, help="Ruta al CSV del SSN")
    args = parser.parse_args()

    db_url = (
        f"postgresql+psycopg2://{args.user}:{args.password}"
        f"@{args.host}:{args.port}/{args.db}"
    )
    engine = create_engine(db_url, pool_pre_ping=True)

    log.info("=== ETL Sismicidad México — inicio ===")
    try:
        raw = extract(args.csv)
        dim_fecha, dim_hora, dim_ubicacion, dim_magnitud, fact = transform(raw)
        load(engine, dim_fecha, dim_hora, dim_ubicacion, dim_magnitud, fact)
        log.info("=== ETL finalizado ===")
    except Exception as e:
        log.error("Error fatal: %s", e)
        raise


if __name__ == "__main__":
    main()
