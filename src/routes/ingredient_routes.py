from flask import Blueprint, request, jsonify  
from ..services import ingredient_service  
from ..services.auth_service import require_role  

ingredient_bp = Blueprint('ingredients', __name__)  

@ingredient_bp.route('/', methods=['GET'])
def list_ingredients_route():  
    """Lista ingredientes - ROTA PÚBLICA para permitir visualização no cardápio"""
    status_filter = request.args.get('status')  
    name = request.args.get('name')
    category_filter = request.args.get('category')
    page = request.args.get('page', type=int, default=1)  
    page_size = request.args.get('page_size', type=int, default=10)  
    result = ingredient_service.list_ingredients(name_filter=name, status_filter=status_filter, category_filter=category_filter, page=page, page_size=page_size)
    return jsonify(result), 200

@ingredient_bp.route('/', methods=['POST'])  
@require_role('admin', 'manager')  
def create_ingredient_route():  
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception as e:
        return jsonify({"error": "Erro ao processar JSON"}), 400  
    ingredient, error_code, message = ingredient_service.create_ingredient(data)  
    if ingredient:  
        return jsonify(ingredient), 201  
    if error_code in ["INVALID_NAME", "INVALID_UNIT", "INVALID_COST", "INVALID_STOCK", "INVALID_MIN_STOCK", "INVALID_MAX_STOCK", "INVALID_BASE_PORTION_QUANTITY", "INVALID_BASE_PORTION_UNIT"]:  
        return jsonify({"error": message}), 400  
    if error_code == "INGREDIENT_NAME_EXISTS":  
        return jsonify({"error": message}), 409  
    if error_code == "DATABASE_ERROR":  
        return jsonify({"error": message}), 500  
    return jsonify({"error": "Não foi possível criar o ingrediente"}), 500  

@ingredient_bp.route('/<int:ingredient_id>', methods=['PUT'])  
@require_role('admin', 'manager')  
def update_ingredient_route(ingredient_id):  
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception as e:
        return jsonify({"error": "Erro ao processar JSON"}), 400  
    success, error_code, message = ingredient_service.update_ingredient(ingredient_id, data)  
    if success:  
        return jsonify({"msg": message}), 200  
    if error_code == "NO_VALID_FIELDS":  
        return jsonify({"error": message}), 400  
    if error_code in ["INVALID_NAME", "INVALID_UNIT", "INVALID_COST", "INVALID_STOCK", "INVALID_MIN_STOCK", "INVALID_MAX_STOCK", "INVALID_BASE_PORTION_QUANTITY", "INVALID_BASE_PORTION_UNIT"]:  
        return jsonify({"error": message}), 400  
    if error_code == "INGREDIENT_NOT_FOUND":  
        return jsonify({"error": message}), 404  
    if error_code == "INGREDIENT_NAME_EXISTS":  
        return jsonify({"error": message}), 409  
    if error_code == "DATABASE_ERROR":  
        return jsonify({"error": message}), 500  
    return jsonify({"error": "Falha ao atualizar ingrediente"}), 500  

@ingredient_bp.route('/<int:ingredient_id>', methods=['DELETE'])  
@require_role('admin', 'manager')  
def delete_ingredient_route(ingredient_id):  
    success, error_code, message = ingredient_service.delete_ingredient(ingredient_id)  
    if success:  
        return jsonify({"msg": message}), 200  
    if error_code == "INGREDIENT_NOT_FOUND":  
        return jsonify({"error": message}), 404  
    if error_code == "INGREDIENT_IN_USE":  
        return jsonify({"error": message}), 409  
    if error_code == "DATABASE_ERROR":  
        return jsonify({"error": message}), 500  
    return jsonify({"error": "Falha ao excluir ingrediente"}), 500  

@ingredient_bp.route('/<int:ingredient_id>/availability', methods=['PATCH'])  
@require_role('admin', 'manager')  
def update_availability_route(ingredient_id):  
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception as e:
        return jsonify({"error": "Erro ao processar JSON"}), 400
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
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception as e:
        return jsonify({"error": "Erro ao processar JSON"}), 400
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


@ingredient_bp.route('/<int:ingredient_id>/add-quantity', methods=['POST'])  
@require_role('admin', 'manager')  
def add_quantity_route(ingredient_id):  
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception as e:
        return jsonify({"error": "Erro ao processar JSON"}), 400
    quantity_to_add = data.get('quantity')  
    if quantity_to_add is None:  
        return jsonify({"error": "O campo 'quantity' é obrigatório"}), 400  
    try:  
        quantity_to_add = float(quantity_to_add)  
    except (ValueError, TypeError):  
        return jsonify({"error": "O campo 'quantity' deve ser um número válido"}), 400  
    success, error_code, message = ingredient_service.add_ingredient_quantity(ingredient_id, quantity_to_add)  
    if success:  
        return jsonify({"msg": message}), 200  
    elif error_code == "INGREDIENT_NOT_FOUND":  
        return jsonify({"error": message}), 404  
    elif error_code == "INVALID_QUANTITY":  
        return jsonify({"error": message}), 400  
    else:  
        return jsonify({"error": "Erro interno do servidor"}), 500

@ingredient_bp.route('/check-name', methods=['POST'])  
def check_name_route():  
    """Verifica se um nome de ingrediente já existe"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception as e:
        return jsonify({"error": "Erro ao processar JSON"}), 400
    
    name = data.get('name')
    if not name or not name.strip():
        return jsonify({"error": "Nome é obrigatório"}), 400
    
    exists, existing_ingredient = ingredient_service.check_ingredient_name_exists(name.strip())
    
    return jsonify({
        "exists": exists,
        "existing_ingredient": existing_ingredient
    }), 200  
