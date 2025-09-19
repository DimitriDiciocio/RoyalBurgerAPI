# src/routes/stock_routes.py

from flask import Blueprint, request, jsonify
from ..services import ingredient_service
from ..services.auth_service import require_role

stock_bp = Blueprint('stock', __name__)


# GET /stock/summary -> KPIs de estoque
@stock_bp.route('/summary', methods=['GET'])
@require_role('admin', 'manager')
def get_stock_summary_route():
    summary = ingredient_service.get_stock_summary()
    return jsonify(summary), 200


# POST /stock/purchase-order -> Gerar pedido de compra
@stock_bp.route('/purchase-order', methods=['POST'])
@require_role('admin', 'manager')
def generate_purchase_order_route():
    purchase_order = ingredient_service.generate_purchase_order()
    return jsonify(purchase_order), 200
