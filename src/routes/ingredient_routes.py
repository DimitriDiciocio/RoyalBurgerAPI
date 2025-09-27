from flask import Blueprint, request, jsonify  
from ..services import ingredient_service  
from ..services.auth_service import require_role  

ingredient_bp = Blueprint('ingredients', __name__)  

@ingredient_bp.route('/', methods=['GET'])  
@require_role('admin', 'manager')  
def get_all_ingredients_route():  
    status_filter = request.args.get('status')  
    ingredients = ingredient_service.get_all_ingredients(status_filter)  
    return jsonify(ingredients), 200  

@ingredient_bp.route('/', methods=['POST'])  
@require_role('admin', 'manager')  
def create_ingredient_route():  
    data = request.get_json()  
    if not data or not data.get('name'):  
        return jsonify({"error": "O campo 'name' é obrigatório"}), 400  
    new_ingredient = ingredient_service.create_ingredient(data)  
    if new_ingredient:  
        return jsonify(new_ingredient), 201  
    return jsonify({"error": "Não foi possível criar o ingrediente"}), 500  

@ingredient_bp.route('/<int:ingredient_id>', methods=['PUT'])  
@require_role('admin', 'manager')  
def update_ingredient_route(ingredient_id):  
    data = request.get_json()  
    if not data:  
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400  
    if ingredient_service.update_ingredient(ingredient_id, data):  
        return jsonify({"msg": "Ingrediente atualizado com sucesso"}), 200  
    return jsonify({"error": "Falha ao atualizar ingrediente ou ingrediente não encontrado"}), 404  

@ingredient_bp.route('/<int:ingredient_id>', methods=['DELETE'])  
@require_role('admin', 'manager')  
def delete_ingredient_route(ingredient_id):  
    if ingredient_service.deactivate_ingredient(ingredient_id):  
        return jsonify({"msg": "Ingrediente marcado como indisponível com sucesso"}), 200  
    return jsonify({"error": "Falha ao inativar ingrediente ou ingrediente não encontrado"}), 404  

@ingredient_bp.route('/<int:ingredient_id>/availability', methods=['PATCH'])  
@require_role('admin', 'manager')  
def update_availability_route(ingredient_id):  
    data = request.get_json()  
    is_available = data.get('is_available')  
    if is_available is None or not isinstance(is_available, bool):  
        return jsonify({"error": "O campo 'is_available' é obrigatório e deve ser true ou false"}), 400  
    if ingredient_service.update_ingredient_availability(ingredient_id, is_available):  
        status_text = "disponível" if is_available else "esgotado"  
        return jsonify({"msg": f"Ingrediente marcado como {status_text} com sucesso."}), 200  
    else:  
        return jsonify({"error": "Ingrediente não encontrado ou falha ao atualizar"}), 404  

@ingredient_bp.route('/<int:ingredient_id>/stock', methods=['POST'])  
@require_role('admin', 'manager')  
def adjust_ingredient_stock_route(ingredient_id):  
    data = request.get_json()  
    change = data.get('change')  
    if change is None:  
        return jsonify({"error": "O campo 'change' é obrigatório"}), 400  
    try:  
        change_amount = float(change)  
    except (ValueError, TypeError):  
        return jsonify({"error": "O campo 'change' deve ser um número válido"}), 400  
    success, error_code, message = ingredient_service.adjust_ingredient_stock(ingredient_id, change_amount)  
    if success:  
        return jsonify({"msg": message}), 200  
    elif error_code == "INGREDIENT_NOT_FOUND":  
        return jsonify({"error": message}), 404  
    elif error_code == "NEGATIVE_STOCK":  
        return jsonify({"error": message}), 400  
    else:  
        return jsonify({"error": "Erro interno do servidor"}), 500  
