-- =============================================================
-- Proyecto Final: Sismicidad en México (SSN 1966–2026)
-- Script 01 — Creación del schema dimensional
-- Ejecutar desde DBeaver conectado a tu cluster Aurora
-- =============================================================

-- Crear schema separado del OLTP
CREATE SCHEMA IF NOT EXISTS sismo_dwh;

-- =============================================================
-- DIMENSIONES
-- =============================================================

-- Dimensión Fecha
-- Grano: un día calendario
DROP TABLE IF EXISTS sismo_dwh.dim_fecha CASCADE;
CREATE TABLE sismo_dwh.dim_fecha (
    date_key     INT          PRIMARY KEY,   -- surrogate: YYYYMMDD
    fecha        DATE         NOT NULL,
    anio         SMALLINT     NOT NULL,
    mes          SMALLINT     NOT NULL,
    nombre_mes   VARCHAR(20)  NOT NULL,
    trimestre    SMALLINT     NOT NULL,
    decada       SMALLINT     NOT NULL,      -- ej. 1970, 1980 ... 2020
    dia_semana   VARCHAR(15)  NOT NULL,
    es_fin_semana BOOLEAN     NOT NULL
);

-- Dimensión Hora
-- Grano: una hora del día (0–23)
DROP TABLE IF EXISTS sismo_dwh.dim_hora CASCADE;
CREATE TABLE sismo_dwh.dim_hora (
    hour_key   SMALLINT    PRIMARY KEY,
    hora       SMALLINT    NOT NULL,
    banda_dia  VARCHAR(15) NOT NULL    -- madrugada / mañana / tarde / noche
);

-- Dimensión Ubicación
-- Grano: estado de la república donde se localizó el sismo
DROP TABLE IF EXISTS sismo_dwh.dim_ubicacion CASCADE;
CREATE TABLE sismo_dwh.dim_ubicacion (
    ubicacion_key  SERIAL       PRIMARY KEY,
    abreviatura    VARCHAR(10)  NOT NULL UNIQUE,   -- natural key: GRO, OAX...
    estado         VARCHAR(50)  NOT NULL,
    region         VARCHAR(30)  NOT NULL            -- Norte/Centro/Sur/Pacifico/Golfo/Noroeste
);

-- Dimensión Magnitud
-- Grano: rango de magnitud (clasificación estándar sismológica)
DROP TABLE IF EXISTS sismo_dwh.dim_magnitud CASCADE;
CREATE TABLE sismo_dwh.dim_magnitud (
    magnitud_key  SMALLINT     PRIMARY KEY,
    rango         VARCHAR(20)  NOT NULL,    -- Leve / Moderado / Fuerte / Severo
    m_min         NUMERIC(3,1) NOT NULL,
    m_max         NUMERIC(3,1) NOT NULL
);

-- =============================================================
-- TABLA DE HECHOS
-- Grano: un evento sísmico registrado por el SSN
-- Medidas: magnitud, profundidad, latitud, longitud
-- =============================================================

DROP TABLE IF EXISTS sismo_dwh.fact_sismo CASCADE;
CREATE TABLE sismo_dwh.fact_sismo (
    sismo_key      SERIAL       PRIMARY KEY,
    date_key       INT          NOT NULL REFERENCES sismo_dwh.dim_fecha(date_key),
    hour_key       SMALLINT     NOT NULL REFERENCES sismo_dwh.dim_hora(hour_key),
    ubicacion_key  INT          NOT NULL REFERENCES sismo_dwh.dim_ubicacion(ubicacion_key),
    magnitud_key   SMALLINT     NOT NULL REFERENCES sismo_dwh.dim_magnitud(magnitud_key),
    -- Medidas degeneradas (no FK, valores directos)
    magnitud       NUMERIC(3,1) NOT NULL,
    latitud        NUMERIC(7,4) NOT NULL,
    longitud       NUMERIC(7,4) NOT NULL,
    profundidad_km INT          NOT NULL,
    estatus        VARCHAR(15)  NOT NULL    -- revisado / verificado
);

-- Índices para acelerar las queries analíticas frecuentes
CREATE INDEX idx_fact_date      ON sismo_dwh.fact_sismo(date_key);
CREATE INDEX idx_fact_ubicacion ON sismo_dwh.fact_sismo(ubicacion_key);
CREATE INDEX idx_fact_magnitud  ON sismo_dwh.fact_sismo(magnitud_key);
CREATE INDEX idx_fact_mag_val   ON sismo_dwh.fact_sismo(magnitud);

-- =============================================================
-- Verificación rápida de estructura
-- =============================================================
SELECT
    table_name,
    pg_size_pretty(pg_total_relation_size('sismo_dwh.' || table_name)) AS tamaño
FROM information_schema.tables
WHERE table_schema = 'sismo_dwh'
ORDER BY table_name;
