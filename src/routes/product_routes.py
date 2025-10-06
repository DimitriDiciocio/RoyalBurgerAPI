from flask import Blueprint, request, jsonify  
from ..services import product_service  
from ..services.auth_service import require_role  

product_bp = Blueprint('products', __name__)  

@product_bp.route('/', methods=['GET'])  
def list_products_route():  
    name = request.args.get('name')  
    category_id = request.args.get('category_id', type=int)  
    page = request.args.get('page', type=int, default=1)  
    page_size = request.args.get('page_size', type=int, default=10)  
    result = product_service.list_products(name_filter=name, category_id=category_id, page=page, page_size=page_size)  
    return jsonify(result), 200  

@product_bp.route('/<int:product_id>', methods=['GET'])  
def get_product_by_id_route(product_id):  
    product = product_service.get_product_by_id(product_id)  
    if product:  
        return jsonify(product), 200  
    return jsonify({"msg": "Produto não encontrado"}), 404  

@product_bp.route('/', methods=['POST'])  
@require_role('admin', 'manager')  
def create_product_route():  
    data = request.get_json()  
    if not data:  
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400  
    new_product, error_code, error_message = product_service.create_product(data)  
    if new_product:  
        return jsonify(new_product), 201  
    if error_code in ["INVALID_NAME", "INVALID_PRICE", "INVALID_COST_PRICE", "INVALID_PREP_TIME", "INVALID_CATEGORY"]:  
        return jsonify({"error": error_message}), 400  
    if error_code == "CATEGORY_NOT_FOUND":  
        return jsonify({"error": error_message}), 404  
    if error_code == "PRODUCT_NAME_EXISTS":  
        return jsonify({"error": error_message}), 409  
    if error_code == "DATABASE_ERROR":  
        return jsonify({"error": error_message}), 500  
    return jsonify({"error": "Não foi possível criar o produto"}), 500  

@product_bp.route('/<int:product_id>', methods=['PUT'])  
@require_role('admin', 'manager')  
def update_product_route(product_id):  
    data = request.get_json()  
    if not data:  
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400  
    success, error_code, message = product_service.update_product(product_id, data)  
    if success:  
        return jsonify({"msg": message}), 200  
    if error_code == "PRODUCT_NOT_FOUND":  
        return jsonify({"error": message}), 404  
    if error_code == "PRODUCT_NAME_EXISTS":  
        return jsonify({"error": message}), 409  
    if error_code in ["INVALID_NAME", "INVALID_PRICE", "INVALID_COST_PRICE", "INVALID_PREP_TIME", "NO_VALID_FIELDS", "INVALID_CATEGORY"]:  
        return jsonify({"error": message}), 400  
    if error_code == "CATEGORY_NOT_FOUND":  
        return jsonify({"error": message}), 404  
    elif error_code == "DATABASE_ERROR":  
        return jsonify({"error": message}), 500  
    else:  
        return jsonify({"error": "Falha ao atualizar produto"}), 500  

@product_bp.route('/<int:product_id>', methods=['DELETE'])  
@require_role('admin', 'manager')  
def delete_product_route(product_id):  
    if product_service.deactivate_product(product_id):  
        return jsonify({"msg": "Produto inativado com sucesso"}), 200  
    return jsonify({"error": "Falha ao inativar produto ou produto não encontrado"}), 404  

@product_bp.route('/<int:product_id>/ingredients', methods=['GET'])  
def get_product_ingredients_route(product_id):  
    # redireciona para ingredient_service para incluir custo estimado
    from ..services import ingredient_service
    result = ingredient_service.get_ingredients_for_product(product_id)
    return jsonify(result), 200  

@product_bp.route('/<int:product_id>/ingredients', methods=['POST'])  
@require_role('admin', 'manager')  
def add_ingredient_to_product_route(product_id):  
    data = request.get_json()  
    ingredient_id = data.get('ingredient_id')  
    quantity = data.get('quantity')  
    unit = data.get('unit')  
    if not ingredient_id or quantity is None:  
        return jsonify({"error": "'ingredient_id' e 'quantity' são obrigatórios"}), 400  
    from ..services import ingredient_service
    if ingredient_service.add_ingredient_to_product(product_id, ingredient_id, quantity, unit):  
        return jsonify({"msg": "Ingrediente associado/atualizado com sucesso"}), 201  
    return jsonify({"error": "Falha ao associar ingrediente"}), 500  

@product_bp.route('/<int:product_id>/ingredients/<int:ingredient_id>', methods=['DELETE'])  
@require_role('admin', 'manager')  
def remove_ingredient_from_product_route(product_id, ingredient_id):  
    from ..services import ingredient_service
    if ingredient_service.remove_ingredient_from_product(product_id, ingredient_id):  
        return jsonify({"msg": "Ingrediente desassociado com sucesso"}), 200  
    return jsonify({"error": "Falha ao desassociar ingrediente ou associação não encontrada"}), 404  


@product_bp.route('/<int:product_id>/ingredients/<int:ingredient_id>', methods=['PUT'])
@require_role('admin', 'manager')
def update_product_ingredient_route(product_id, ingredient_id):
    data = request.get_json() or {}
    quantity = data.get('quantity')
    unit = data.get('unit')
    from ..services import ingredient_service
    success, error_code, message = ingredient_service.update_product_ingredient(product_id, ingredient_id, quantity=quantity, unit=unit)
    if success:
        return jsonify({"msg": message}), 200
    if error_code == "NO_VALID_FIELDS":
        return jsonify({"error": message}), 400
    if error_code == "LINK_NOT_FOUND":
        return jsonify({"error": message}), 404
    if error_code == "DATABASE_ERROR":
        return jsonify({"error": message}), 500
    return jsonify({"error": "Falha ao atualizar vínculo"}), 500


@product_bp.route('/search', methods=['GET'])  
def search_products_route():  
    name = request.args.get('name')  
    category_id = request.args.get('category_id', type=int)  
    page = request.args.get('page', type=int, default=1)  
    page_size = request.args.get('page_size', type=int, default=10)  
    result = product_service.search_products(name=name, category_id=category_id, page=page, page_size=page_size)  
    return jsonify(result), 200  
