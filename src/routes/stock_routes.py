from flask import Blueprint, request, jsonify
from ..services import stock_service
from ..services.auth_service import require_role

stock_bp = Blueprint('stock', __name__)


@stock_bp.route('/alerts', methods=['GET'])
@require_role('admin', 'manager')
def get_stock_alerts_route():
    """
    Retorna lista de ingredientes com estoque baixo.
    """
    alerts, error_code, message = stock_service.get_stock_alerts()
    if alerts is not None:
        return jsonify({"alerts": alerts}), 200
    
    if error_code == "DATABASE_ERROR":
        return jsonify({"error": message}), 500
    
    return jsonify({"error": "Falha ao buscar alertas de estoque"}), 500


@stock_bp.route('/confirm-out-of-stock', methods=['POST'])
@require_role('admin', 'manager')
def confirm_out_of_stock_route():
    """
    Confirma que um ingrediente está fora de estoque e desativa produtos dependentes.
    Body: {"ingredient_id": 123}
    """
    data = request.get_json() or {}
    ingredient_id = data.get('ingredient_id')
    
    if not ingredient_id:
        return jsonify({"error": "ingredient_id é obrigatório"}), 400
    
    success, deactivated_products, error_code, message = stock_service.confirm_out_of_stock(ingredient_id)
    if success:
        response_data = {"msg": message}
        if deactivated_products:
            response_data["deactivated_products"] = deactivated_products
        return jsonify(response_data), 200
    
    if error_code == "INGREDIENT_NOT_FOUND":
        return jsonify({"error": message}), 404
    if error_code == "DATABASE_ERROR":
        return jsonify({"error": message}), 500
    
    return jsonify({"error": "Falha ao confirmar estoque zerado"}), 500


@stock_bp.route('/ingredients/<int:ingredient_id>/stock', methods=['POST'])
@require_role('admin', 'manager')
def adjust_ingredient_stock_route(ingredient_id):
    """
    Ajusta manualmente o estoque de um ingrediente.
    Body: {"adjustment": 10} ou {"adjustment": -5}
    """
    data = request.get_json() or {}
    adjustment = data.get('adjustment')
    
    if adjustment is None:
        return jsonify({"error": "adjustment é obrigatório"}), 400
    
    if not isinstance(adjustment, (int, float)):
        return jsonify({"error": "adjustment deve ser um número"}), 400
    
    success, reactivated_products, error_code, message = stock_service.adjust_stock(ingredient_id, adjustment)
    if success:
        response_data = {"msg": message}
        if reactivated_products:
            response_data["reactivated_products"] = reactivated_products
        return jsonify(response_data), 200
    
    if error_code == "INGREDIENT_NOT_FOUND":
        return jsonify({"error": message}), 404
    if error_code == "DATABASE_ERROR":
        return jsonify({"error": message}), 500
    
    return jsonify({"error": "Falha ao ajustar estoque"}), 500