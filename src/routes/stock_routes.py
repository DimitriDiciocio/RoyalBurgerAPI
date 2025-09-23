from flask import Blueprint, request, jsonify  # importa Blueprint, request e jsonify do Flask
from ..services import ingredient_service  # importa serviço de ingredientes (estoque)
from ..services.auth_service import require_role  # importa decorator de autorização por papel

stock_bp = Blueprint('stock', __name__)  # cria o blueprint de estoque

@stock_bp.route('/summary', methods=['GET'])  # KPIs de estoque
@require_role('admin', 'manager')  # restringe a admin/manager
def get_stock_summary_route():  # função handler dos KPIs
    summary = ingredient_service.get_stock_summary()  # busca resumo de estoque
    return jsonify(summary), 200  # retorna resumo com status 200

@stock_bp.route('/purchase-order', methods=['POST'])  # gera pedido de compra
@require_role('admin', 'manager')  # restringe a admin/manager
def generate_purchase_order_route():  # função handler para gerar pedido de compra
    purchase_order = ingredient_service.generate_purchase_order()  # gera pedido via serviço
    return jsonify(purchase_order), 200  # retorna pedido com status 200
