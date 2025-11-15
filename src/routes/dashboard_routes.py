from flask import Blueprint, request, jsonify  
from ..services import dashboard_service, ingredient_service  
from ..services.auth_service import require_role  
import logging

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint('dashboard', __name__)  

@dashboard_bp.route('/metrics', methods=['GET'])  
@require_role('admin', 'manager')  
def get_dashboard_metrics_route():  
    """Métricas gerais do dashboard (pedidos)"""
    metrics = dashboard_service.get_dashboard_metrics()  
    return jsonify(metrics), 200


@dashboard_bp.route('/menu', methods=['GET'])  
@require_role('admin', 'manager')  
def get_menu_dashboard_route():  
    """Métricas do dashboard de cardápio (produtos)"""
    metrics = dashboard_service.get_menu_dashboard_metrics()  
    return jsonify(metrics), 200


@dashboard_bp.route('/stock', methods=['GET'])  
@require_role('admin', 'manager')  
def get_stock_dashboard_route():  
    """Métricas do dashboard de estoque (ingredientes)"""
    summary = ingredient_service.get_stock_summary()
    
    # Calcular total de itens (todos os ingredientes ativos)
    from ..database import get_db_connection
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM INGREDIENTS WHERE IS_AVAILABLE = TRUE")
        total_items = cur.fetchone()[0] or 0
    except Exception as e:
        logger.error(f"Erro ao buscar total de itens de estoque: {e}", exc_info=True)
        total_items = 0
    finally:
        if conn:
            conn.close()
    
    # ALTERAÇÃO: Adicionar total_items ao resultado
    summary['total_items'] = total_items
    return jsonify(summary), 200


@dashboard_bp.route('/promotions', methods=['GET'])  
@require_role('admin', 'manager')  
def get_promotions_dashboard_route():  
    """Métricas do dashboard de promoções"""
    metrics = dashboard_service.get_promotions_dashboard_metrics()  
    return jsonify(metrics), 200
