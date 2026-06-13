"""
Analytics PRO para pedidos
- Ventas hoy vs ayer
- Top 5 productos
- Clientes frecuentes
- Ingresos acumulados
"""

from flask import Blueprint, jsonify, request
from db import execute
from datetime import datetime, timedelta

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api/pro/analytics')


@analytics_bp.route('/ventas-comparativa', methods=['GET'])
def ventas_comparativa():
    """Ventas hoy vs ayer"""
    try:
        codigo = request.args.get('codigo')
        if not codigo:
            return jsonify({'error': 'codigo requerido'}), 400

        hoy = datetime.now().date()
        ayer = hoy - timedelta(days=1)

        hoy_total = execute("""
            SELECT COALESCE(SUM(total), 0) as total
            FROM conversaciones_pedidos
            WHERE codigo = %s AND DATE(actualizado_en) = %s AND estado = 'completado'
        """, (codigo, hoy), fetch='one')

        ayer_total = execute("""
            SELECT COALESCE(SUM(total), 0) as total
            FROM conversaciones_pedidos
            WHERE codigo = %s AND DATE(actualizado_en) = %s AND estado = 'completado'
        """, (codigo, ayer), fetch='one')

        hoy_val = hoy_total['total'] if hoy_total else 0
        ayer_val = ayer_total['total'] if ayer_total else 0

        cambio = ((hoy_val - ayer_val) / ayer_val * 100) if ayer_val > 0 else 0

        return jsonify({
            'hoy': float(hoy_val),
            'ayer': float(ayer_val),
            'cambio_pct': round(cambio, 2)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@analytics_bp.route('/top-productos', methods=['GET'])
def top_productos():
    """Top 5 productos vendidos (últimos 30 días)"""
    try:
        codigo = request.args.get('codigo')
        if not codigo:
            return jsonify({'error': 'codigo requerido'}), 400

        hace_30 = datetime.now().date() - timedelta(days=30)

        productos = execute("""
            SELECT
                nombre as nombre,
                COUNT(*) as cantidad_vendida,
                SUM(precio) as ingresos
            FROM items_pedidos
            WHERE codigo = %s AND DATE(actualizado_en) >= %s
            GROUP BY nombre
            ORDER BY cantidad_vendida DESC
            LIMIT 5
        """, (codigo, hace_30), fetch='all')

        return jsonify({
            'top_productos': [
                {
                    'nombre': p['nombre'],
                    'cantidad': p['cantidad_vendida'],
                    'ingresos': float(p['ingresos']) if p['ingresos'] else 0
                }
                for p in (productos or [])
            ]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@analytics_bp.route('/clientes-frecuentes', methods=['GET'])
def clientes_frecuentes():
    """Clientes que más compran"""
    try:
        codigo = request.args.get('codigo')
        if not codigo:
            return jsonify({'error': 'codigo requerido'}), 400

        clientes = execute("""
            SELECT
                numero_cliente,
                COUNT(*) as compras,
                COALESCE(SUM(total), 0) as gasto_total
            FROM conversaciones_pedidos
            WHERE codigo = %s AND estado = 'completado'
            GROUP BY numero_cliente
            ORDER BY compras DESC
            LIMIT 10
        """, (codigo,), fetch='all')

        return jsonify({
            'clientes_frecuentes': [
                {
                    'numero': c['numero_cliente'],
                    'compras': c['compras'],
                    'gasto_total': float(c['gasto_total']) if c['gasto_total'] else 0
                }
                for c in (clientes or [])
            ]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@analytics_bp.route('/ingresos-acumulados', methods=['GET'])
def ingresos_acumulados():
    """Ingresos acumulados (mes/año actual)"""
    try:
        codigo = request.args.get('codigo')
        periodo = request.args.get('periodo', 'mes')  # 'mes' o 'ano'

        if not codigo:
            return jsonify({'error': 'codigo requerido'}), 400

        hoy = datetime.now().date()

        if periodo == 'ano':
            desde = hoy.replace(month=1, day=1)
        else:  # mes
            desde = hoy.replace(day=1)

        resultado = execute("""
            SELECT
                COALESCE(SUM(total), 0) as total,
                COUNT(*) as pedidos
            FROM conversaciones_pedidos
            WHERE codigo = %s AND estado = 'completado' AND DATE(actualizado_en) >= %s
        """, (codigo, desde), fetch='one')

        return jsonify({
            'periodo': periodo,
            'desde': str(desde),
            'hasta': str(hoy),
            'ingresos_totales': float(resultado['total']) if resultado else 0,
            'pedidos_completados': resultado['pedidos'] if resultado else 0
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
