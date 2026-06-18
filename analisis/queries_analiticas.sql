-- =============================================================
-- Proyecto Final: Sismicidad en México (SSN 1966–2026)
-- Queries analíticas con SQL avanzado
-- Ejecutar desde DBeaver contra Aurora (schema sismo_dwh)
-- =============================================================


-- ─────────────────────────────────────────────────────────────
-- Q1. Top 10 estados con más sismos severos (M≥6)
--     Técnica: CTE simple
-- ─────────────────────────────────────────────────────────────
WITH severos AS (
    SELECT
        du.estado,
        du.region,
        dm.rango,
        COUNT(*)                     AS total_sismos,
        ROUND(AVG(fs.magnitud), 2)   AS mag_promedio,
        MAX(fs.magnitud)             AS mag_maxima
    FROM      sismo_dwh.fact_sismo fs
    JOIN      sismo_dwh.dim_ubicacion du USING (ubicacion_key)
    JOIN      sismo_dwh.dim_magnitud  dm USING (magnitud_key)
    WHERE     dm.rango IN ('Fuerte', 'Severo')
    GROUP BY  du.estado, du.region, dm.rango
)
SELECT
    estado,
    region,
    rango,
    total_sismos,
    mag_promedio,
    mag_maxima,
    RANK() OVER (ORDER BY total_sismos DESC) AS ranking
FROM  severos
ORDER BY total_sismos DESC
LIMIT 10;


-- ─────────────────────────────────────────────────────────────
-- Q2. Evolución anual de sismos fuertes/severos con variación
--     Técnicas: CTE + window function LAG
-- ─────────────────────────────────────────────────────────────
WITH anuales AS (
    SELECT
        df.anio,
        COUNT(*)                                          AS total,
        COUNT(*) FILTER (WHERE dm.rango = 'Fuerte')      AS fuertes,
        COUNT(*) FILTER (WHERE dm.rango = 'Severo')      AS severos,
        ROUND(AVG(fs.magnitud), 2)                       AS mag_promedio
    FROM      sismo_dwh.fact_sismo fs
    JOIN      sismo_dwh.dim_fecha    df USING (date_key)
    JOIN      sismo_dwh.dim_magnitud dm USING (magnitud_key)
    WHERE     dm.rango IN ('Fuerte', 'Severo')
    GROUP BY  df.anio
)
SELECT
    anio,
    total,
    fuertes,
    severos,
    mag_promedio,
    LAG(total)  OVER (ORDER BY anio)              AS total_anio_anterior,
    total - LAG(total) OVER (ORDER BY anio)       AS delta_absoluto,
    ROUND(
        100.0 * (total - LAG(total) OVER (ORDER BY anio))
        / NULLIF(LAG(total) OVER (ORDER BY anio), 0),
    1)                                            AS delta_pct
FROM  anuales
ORDER BY anio;


-- ─────────────────────────────────────────────────────────────
-- Q3. Ranking de estados por magnitud promedio dentro de cada
--     década — permite ver si los mismos estados siempre lideran
--     Técnicas: CTE + window function RANK() con PARTITION
-- ─────────────────────────────────────────────────────────────
WITH por_decada AS (
    SELECT
        du.estado,
        du.region,
        df.decada,
        COUNT(*)                   AS total_sismos,
        ROUND(AVG(fs.magnitud), 2) AS mag_promedio,
        MAX(fs.magnitud)           AS mag_maxima
    FROM      sismo_dwh.fact_sismo fs
    JOIN      sismo_dwh.dim_fecha     df USING (date_key)
    JOIN      sismo_dwh.dim_ubicacion du USING (ubicacion_key)
    GROUP BY  du.estado, du.region, df.decada
    HAVING    COUNT(*) >= 10    -- filtrar estados con poca muestra en esa década
),
ranking_decada AS (
    SELECT
        *,
        RANK() OVER (PARTITION BY decada ORDER BY mag_promedio DESC) AS rk_mag,
        RANK() OVER (PARTITION BY decada ORDER BY total_sismos DESC) AS rk_frec
    FROM por_decada
)
SELECT *
FROM   ranking_decada
WHERE  rk_mag <= 5
ORDER  BY decada, rk_mag;


-- ─────────────────────────────────────────────────────────────
-- Q4. Profundidad y magnitud por región: percentiles y conteo
--     Técnicas: PERCENTILE_CONT (función de orden de conjuntos)
--              + COUNT FILTER
-- ─────────────────────────────────────────────────────────────
SELECT
    du.region,
    COUNT(*)                                                              AS total,
    ROUND(AVG(fs.magnitud),    2)                                        AS mag_media,
    ROUND(AVG(fs.profundidad_km), 1)                                     AS prof_media_km,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY fs.profundidad_km)::INT AS prof_p50,
    PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY fs.profundidad_km)::INT AS prof_p90,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY fs.magnitud)            AS mag_mediana,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY fs.magnitud)            AS mag_p95,
    COUNT(*) FILTER (WHERE fs.magnitud >= 6)                             AS mag_6_mas,
    COUNT(*) FILTER (WHERE fs.magnitud >= 7)                             AS mag_7_mas,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE fs.magnitud >= 6) / COUNT(*), 1
    )                                                                    AS pct_fuerte_o_mas
FROM      sismo_dwh.fact_sismo fs
JOIN      sismo_dwh.dim_ubicacion du USING (ubicacion_key)
GROUP BY  du.region
ORDER BY  mag_media DESC;


-- ─────────────────────────────────────────────────────────────
-- Q5. Heatmap: magnitud promedio por hora × mes
--     (para alimentar el dashboard con el patrón temporal)
--     Técnicas: window function con promedio móvil acumulado
-- ─────────────────────────────────────────────────────────────
SELECT
    df.mes,
    df.nombre_mes,
    dh.hora,
    dh.banda_dia,
    COUNT(*)                   AS total_sismos,
    ROUND(AVG(fs.magnitud), 2) AS mag_promedio,
    MAX(fs.magnitud)           AS mag_maxima,
    -- Promedio móvil acumulado por hora a lo largo de los meses
    ROUND(
        AVG(AVG(fs.magnitud)) OVER (
            PARTITION BY dh.hora
            ORDER BY df.mes
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ), 2
    )                          AS mag_movil_3meses
FROM      sismo_dwh.fact_sismo fs
JOIN      sismo_dwh.dim_fecha df USING (date_key)
JOIN      sismo_dwh.dim_hora  dh USING (hour_key)
GROUP BY  df.mes, df.nombre_mes, dh.hora, dh.banda_dia
ORDER BY  df.mes, dh.hora;


-- ─────────────────────────────────────────────────────────────
-- Q6. Sismos históricos más intensos (top 20 de toda la serie)
--     Técnica: CTE + ROW_NUMBER()
-- ─────────────────────────────────────────────────────────────
WITH ordenados AS (
    SELECT
        df.fecha,
        dh.hora,
        du.estado,
        du.region,
        fs.magnitud,
        fs.profundidad_km,
        fs.latitud,
        fs.longitud,
        fs.estatus,
        ROW_NUMBER() OVER (ORDER BY fs.magnitud DESC, df.fecha) AS rn
    FROM      sismo_dwh.fact_sismo fs
    JOIN      sismo_dwh.dim_fecha     df USING (date_key)
    JOIN      sismo_dwh.dim_hora      dh USING (hour_key)
    JOIN      sismo_dwh.dim_ubicacion du USING (ubicacion_key)
)
SELECT *
FROM   ordenados
WHERE  rn <= 20
ORDER  BY magnitud DESC;
