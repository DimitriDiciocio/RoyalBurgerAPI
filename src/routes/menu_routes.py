from flask import Blueprint, request, jsonify  
from ..services import product_service  
from ..services.auth_service import require_role  

menu_bp = Blueprint('menu', __name__)

@menu_bp.route('/summary', methods=['GET'])  
@require_role('admin', 'manager')  
def get_menu_summary_route():  
    summary = product_service.get_menu_summary()  
    return jsonify(summary), 200

@menu_bp.route('/products/<int:product_id>', methods=['GET'])
def get_menu_product_route(product_id):
    """
    Obtém um produto específico do menu.
    Usa a mesma função get_product_by_id que calcula max_quantity corretamente.
    """
    # Aceita parâmetro quantity opcional para calcular max_available corretamente
    quantity = request.args.get('quantity', type=int, default=1)
    product = product_service.get_product_by_id(product_id, quantity=quantity)
    if product:
        return jsonify(product), 200
    return jsonify({"msg": "Produto não encontrado"}), 404

@menu_bp.route('/products/<int:product_id>/ingredients', methods=['GET'])
def get_menu_product_ingredients_route(product_id):
    """
    Obtém ingredientes de um produto do menu.
    Redireciona para ingredient_service para incluir custo estimado.
    """
    from ..services import ingredient_service
    result = ingredient_service.get_ingredients_for_product(product_id)
    return jsonify(result), 200
