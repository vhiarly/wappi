"""
Agente ATLAS — Calcula estadísticas de negocios y las cachea en dashboard_stats.
Corre cada 60 minutos como daemon thread.
"""

import threading
import time
import json
from datetime import datetime, timedelta
from db import execute

INTERVALO_SEGUNDOS = 3600  # 60 minutos

def calcular_stats_negocio(codigo):
    """
    Calcula stats para UN negocio:
    - Ingresos hoy/mes
    - Clientes nuevos vs repetidos
    - Pedidos/citas del día
    - Ticket promedio
    - Producto/servicio top
    """
    hoy = datetime.now().date()
    primer_dia_mes = hoy.replace(day=1)

    stats = {
        "codigo": codigo,
        "actualizado": datetime.now().isoformat(),
        "ingresos_hoy": 0,
        "ingresos_mes": 0,
        "pedidos_hoy": 0,
        "citas_hoy": 0,
        "clientes_nuevos": 0,
        "clientes_repetidos": 0,
        "ticket_promedio": 0,
        "producto_top": None,
        "servicio_top": None,
    }

    result = execute("""
        SELECT
            COUNT(*) as pedidos_hoy,
            SUM(total) as ingresos_hoy,
            AVG(total) as ticket_promedio
        FROM pedidos
        WHERE codigo = %s AND DATE(creado_en) = %s AND estado != 'cancelado'
    """, (codigo, hoy), fetch='one')

    if result and result.get('pedidos_hoy'):
        stats["pedidos_hoy"] = result.get('pedidos_hoy') or 0
        stats["ingresos_hoy"] = float(result.get('ingresos_hoy')) if result.get('ingresos_hoy') else 0
        stats["ticket_promedio"] = float(result.get('ticket_promedio')) if result.get('ticket_promedio') else 0

    result = execute("""
        SELECT SUM(total) as ingresos_mes
        FROM pedidos
        WHERE codigo = %s AND DATE(creado_en) >= %s AND estado != 'cancelado'
    """, (codigo, primer_dia_mes), fetch='one')

    if result and result.get('ingresos_mes'):
        stats["ingresos_mes"] = float(result.get('ingresos_mes')) if result.get('ingresos_mes') else 0

    result = execute("""
        SELECT COUNT(*) as citas_hoy
        FROM citas
        WHERE codigo = %s AND fecha = %s AND estado IN ('confirmada', 'completada')
    """, (codigo, hoy), fetch='one')

    if result:
        stats["citas_hoy"] = result.get('citas_hoy') or 0

    hace_30 = hoy - timedelta(days=30)

    result = execute("""
        SELECT
            COUNT(DISTINCT CASE WHEN MIN(DATE(creado_en)) >= %s THEN numero_cliente END) as nuevos,
            COUNT(DISTINCT CASE WHEN MIN(DATE(creado_en)) < %s THEN numero_cliente END) as repetidos
        FROM pedidos
        WHERE codigo = %s GROUP BY codigo
    """, (hace_30, hace_30, codigo), fetch='one')

    if result:
        stats["clientes_nuevos"] = result.get('nuevos') or 0
        stats["clientes_repetidos"] = result.get('repetidos') or 0

    result = execute("""
        SELECT clave, nombre
        FROM catalogo
        WHERE codigo = %s
        ORDER BY cantidad DESC
        LIMIT 1
    """, (codigo,), fetch='one')

    if result:
        stats["producto_top"] = {"clave": result.get('clave'), "nombre": result.get('nombre')}

    result = execute("""
        SELECT clave, nombre
        FROM servicios
        WHERE codigo = %s
        ORDER BY precio DESC
        LIMIT 1
    """, (codigo,), fetch='one')

    if result:
        stats["servicio_top"] = {"clave": result.get('clave'), "nombre": result.get('nombre')}

    return stats


def calcular_stats_global():
    """
    Calcula stats globales para el admin:
    - Ingresos totales hoy/mes
    - Negocios activos
    - Conversaciones totales
    - Alertas abiertas
    """
    hoy = datetime.now().date()
    primer_dia_mes = hoy.replace(day=1)

    stats = {
        "codigo": "GLOBAL",
        "actualizado": datetime.now().isoformat(),
        "ingresos_hoy": 0,
        "ingresos_mes": 0,
        "negocios_activos": 0,
        "conversaciones_totales": 0,
        "alertas_abiertas": 0,
        "pedidos_activos": 0,
        "citas_activas": 0,
    }

    result = execute("""
        SELECT SUM(total) as ingresos_hoy
        FROM pedidos
        WHERE DATE(creado_en) = %s AND estado != 'cancelado'
    """, (hoy,), fetch='one')

    if result and result.get('ingresos_hoy'):
        stats["ingresos_hoy"] = float(result.get('ingresos_hoy')) if result.get('ingresos_hoy') else 0

    result = execute("""
        SELECT SUM(total) as ingresos_mes
        FROM pedidos
        WHERE DATE(creado_en) >= %s AND estado != 'cancelado'
    """, (primer_dia_mes,), fetch='one')

    if result and result.get('ingresos_mes'):
        stats["ingresos_mes"] = float(result.get('ingresos_mes')) if result.get('ingresos_mes') else 0

    result = execute("""
        SELECT COUNT(*) as negocios_activos FROM negocios WHERE activo = TRUE
    """, fetch='one')

    if result:
        stats["negocios_activos"] = result.get('negocios_activos') or 0

    result = execute("""
        SELECT
            (SELECT COUNT(*) FROM conversaciones_pedidos) +
            (SELECT COUNT(*) FROM conversaciones_citas) as total
    """, fetch='one')

    if result:
        stats["conversaciones_totales"] = result.get('total') or 0

    result = execute("""
        SELECT COUNT(*) as alertas_abiertas FROM imprevistos WHERE estado = 'abierto'
    """, fetch='one')

    if result:
        stats["alertas_abiertas"] = result.get('alertas_abiertas') or 0

    result = execute("""
        SELECT COUNT(*) as pedidos_activos FROM conversaciones_pedidos
    """, fetch='one')

    if result:
        stats["pedidos_activos"] = result.get('pedidos_activos') or 0

    result = execute("""
        SELECT COUNT(*) as citas_activas FROM conversaciones_citas
    """, fetch='one')

    if result:
        stats["citas_activas"] = result.get('citas_activas') or 0

    return stats


def guardar_stats(stats):
    """Guarda stats en tabla dashboard_stats (upsert)"""
    execute("""
        INSERT INTO dashboard_stats (codigo, stats, actualizado)
        VALUES (%s, %s, NOW())
        ON CONFLICT (codigo) DO UPDATE SET
            stats = EXCLUDED.stats,
            actualizado = NOW()
    """, (stats["codigo"], json.dumps(stats)))


def ejecutar_atlas():
    """Calcula y cachea todas las estadísticas"""
    try:
        print(f"[ATLAS] Calculando estadísticas... ({datetime.now().isoformat()})")

        stats_global = calcular_stats_global()
        guardar_stats(stats_global)

        result = execute("SELECT codigo FROM negocios WHERE activo = TRUE", fetch='all')
        if result:
            for row in result:
                codigo = row.get('codigo')
                stats = calcular_stats_negocio(codigo)
                guardar_stats(stats)

        print(f"[ATLAS] ✓ Estadísticas actualizadas")
    except Exception as e:
        print(f"[ATLAS] ✗ Error: {e}")


def daemon_atlas():
    """Daemon que corre ATLAS cada INTERVALO_SEGUNDOS"""
    print(f"[ATLAS] Iniciando daemon (intervalo: {INTERVALO_SEGUNDOS}s)")
    ejecutar_atlas()

    while True:
        time.sleep(INTERVALO_SEGUNDOS)
        ejecutar_atlas()


def iniciar_atlas():
    """Inicia el daemon en background"""
    thread = threading.Thread(target=daemon_atlas, daemon=True)
    thread.start()
    print("[ATLAS] Daemon iniciado en background")
