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
            FROM conversaciones_pedidos
            WHERE codigo = %s AND estado = 'completado' AND DATE(actualizado_en) = %s
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
            FROM conversaciones_pedidos
            WHERE codigo = %s AND estado = 'completado' AND DATE(actualizado_en) >= %s
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
            FROM conversaciones_pedidos
            WHERE codigo = %s AND estado = 'completado' AND DATE(actualizado_en) = %s
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
