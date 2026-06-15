"""
Analytics PRO para pedidos (BÁSICO)
Versión 1: Solo conteos y datos simples sin JSONB complexity
"""

from flask import Blueprint, jsonify, request
from db import execute
from datetime import datetime, timedelta

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api/pro/analytics')


@analytics_bp.route('/pedidos-hoy', methods=['GET'])
def pedidos_hoy():
    """Pedidos completados hoy"""
    try:
        codigo = request.args.get('codigo')
        if not codigo:
            return jsonify({'error': 'codigo requerido'}), 400

        hoy = datetime.now().date()

        resultado = execute("""
            SELECT COUNT(*) as pedidos
            FROM pedidos
            WHERE codigo = %s AND estado = 'despachado' AND DATE(creado_en) = %s
        """, (codigo, hoy), fetch='one')

        return jsonify({
            'fecha': str(hoy),
            'pedidos_completados': resultado['pedidos'] if resultado else 0
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@analytics_bp.route('/clientes-activos', methods=['GET'])
def clientes_activos():
    """Clientes que han comprado (últimos 30 días)"""
    try:
        codigo = request.args.get('codigo')
        if not codigo:
            return jsonify({'error': 'codigo requerido'}), 400

        hace_30 = datetime.now().date() - timedelta(days=30)

        resultado = execute("""
            SELECT COUNT(DISTINCT numero_cliente) as clientes_unicos
            FROM pedidos
            WHERE codigo = %s AND estado = 'despachado' AND DATE(creado_en) >= %s
        """, (codigo, hace_30), fetch='one')

        return jsonify({
            'periodo': 'últimos 30 días',
            'clientes_unicos': resultado['clientes_unicos'] if resultado else 0
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@analytics_bp.route('/estado-conversaciones', methods=['GET'])
def estado_conversaciones():
    """Resumen de estados de conversaciones"""
    try:
        codigo = request.args.get('codigo')
        if not codigo:
            return jsonify({'error': 'codigo requerido'}), 400

        resultado = execute("""
            SELECT
                estado,
                COUNT(*) as cantidad
            FROM conversaciones_pedidos
            WHERE codigo = %s
            GROUP BY estado
        """, (codigo,), fetch='all')

        resumen = {}
        for row in (resultado or []):
            resumen[row['estado']] = row['cantidad']

        return jsonify({
            'codigo': codigo,
            'resumen_por_estado': resumen,
            'total': sum(resumen.values())
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@analytics_bp.route('/actividad', methods=['GET'])
def actividad():
    """Actividad general: fecha actual"""
    try:
        codigo = request.args.get('codigo')
        if not codigo:
            return jsonify({'error': 'codigo requerido'}), 400

        hoy = datetime.now().date()

        completados = execute("""
            SELECT COUNT(*) as total
            FROM pedidos
            WHERE codigo = %s AND estado = 'despachado' AND DATE(creado_en) = %s
        """, (codigo, hoy), fetch='one')

        en_progreso = execute("""
            SELECT COUNT(*) as total
            FROM conversaciones_pedidos
            WHERE codigo = %s AND estado IN ('pidiendo', 'esperando_confirmacion') AND DATE(actualizado_en) = %s
        """, (codigo, hoy), fetch='one')

        return jsonify({
            'fecha': str(hoy),
            'pedidos_completados': completados['total'] if completados else 0,
            'conversaciones_activas': en_progreso['total'] if en_progreso else 0
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Analytics de CITAS ────────────────────────────────────────────────────────

@analytics_bp.route('/citas-resumen', methods=['GET'])
def citas_resumen():
    """Resumen para negocios de citas: hoy, semana, no-shows, ingresos, clientes."""
    try:
        codigo = request.args.get('codigo')
        if not codigo:
            return jsonify({'error': 'codigo requerido'}), 400

        hoy = datetime.now().date()
        fin_semana = hoy + timedelta(days=6)
        hace_30 = hoy - timedelta(days=30)

        hoy_n = execute(
            "SELECT COUNT(*) c FROM citas WHERE codigo=%s AND estado='confirmada' AND fecha=%s",
            (codigo, hoy), fetch='one')
        semana_n = execute(
            "SELECT COUNT(*) c FROM citas WHERE codigo=%s AND estado='confirmada' AND fecha BETWEEN %s AND %s",
            (codigo, hoy, fin_semana), fetch='one')
        clientes = execute(
            "SELECT COUNT(DISTINCT numero_cliente) c FROM citas WHERE codigo=%s AND agendado_en >= %s",
            (codigo, hace_30), fetch='one')
        no_shows = execute(
            "SELECT COUNT(*) c FROM citas WHERE codigo=%s AND (COALESCE(no_show_negocio,0) > 0 OR no_show_cliente = TRUE)",
            (codigo,), fetch='one')
        canceladas = execute(
            "SELECT COUNT(*) c FROM citas WHERE codigo=%s AND estado='cancelada'",
            (codigo,), fetch='one')
        # Ingresos estimados del mes (precio del servicio, con fallback al costo del negocio por tipo)
        ingresos = execute("""
            SELECT COALESCE(SUM(
                CASE
                    WHEN c.tipo='online'     THEN COALESCE(NULLIF(s.precio,0), n.costo_online, 0)
                    WHEN c.tipo='presencial' THEN COALESCE(NULLIF(s.precio,0), n.costo_presencial, 0)
                    ELSE COALESCE(s.precio, 0)
                END
            ), 0) AS total
            FROM citas c
            LEFT JOIN servicios s ON s.codigo = c.codigo AND s.clave = c.servicio
            LEFT JOIN negocios  n ON n.codigo = c.codigo
            WHERE c.codigo=%s AND c.estado='confirmada'
              AND date_trunc('month', c.fecha) = date_trunc('month', %s::date)
        """, (codigo, hoy), fetch='one')

        return jsonify({
            'confirmadas_hoy': hoy_n['c'] if hoy_n else 0,
            'confirmadas_semana': semana_n['c'] if semana_n else 0,
            'clientes_30d': clientes['c'] if clientes else 0,
            'no_shows': no_shows['c'] if no_shows else 0,
            'canceladas': canceladas['c'] if canceladas else 0,
            'ingresos_mes_estimado': float(ingresos['total']) if ingresos else 0,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@analytics_bp.route('/citas-estado', methods=['GET'])
def citas_estado():
    """Distribución de citas por estado."""
    try:
        codigo = request.args.get('codigo')
        if not codigo:
            return jsonify({'error': 'codigo requerido'}), 400
        rows = execute(
            "SELECT estado, COUNT(*) c FROM citas WHERE codigo=%s GROUP BY estado",
            (codigo,), fetch='all') or []
        resumen = {r['estado']: r['c'] for r in rows}
        return jsonify({'resumen_por_estado': resumen, 'total': sum(resumen.values())})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@analytics_bp.route('/citas-servicios', methods=['GET'])
def citas_servicios():
    """Servicios más solicitados (citas confirmadas)."""
    try:
        codigo = request.args.get('codigo')
        if not codigo:
            return jsonify({'error': 'codigo requerido'}), 400
        rows = execute("""
            SELECT nombre_servicio, COUNT(*) c
            FROM citas
            WHERE codigo=%s AND estado='confirmada' AND nombre_servicio IS NOT NULL
            GROUP BY nombre_servicio ORDER BY c DESC LIMIT 6
        """, (codigo,), fetch='all') or []
        return jsonify({'servicios': [{'nombre': r['nombre_servicio'], 'cantidad': r['c']} for r in rows]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@analytics_bp.route('/citas-horas', methods=['GET'])
def citas_horas():
    """Horas pico: citas confirmadas agrupadas por hora del día."""
    try:
        codigo = request.args.get('codigo')
        if not codigo:
            return jsonify({'error': 'codigo requerido'}), 400
        rows = execute("""
            SELECT substring(hora from 1 for 2) AS h, COUNT(*) c
            FROM citas
            WHERE codigo=%s AND estado='confirmada' AND hora IS NOT NULL
            GROUP BY 1 ORDER BY 1
        """, (codigo,), fetch='all') or []
        return jsonify({'horas': [{'hora': f"{r['h']}:00", 'cantidad': r['c']} for r in rows]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
