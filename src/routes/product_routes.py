# src/routes/product_routes.py

from flask import Blueprint, request, jsonify
from ..services import product_service
from ..services.auth_service import require_role

product_bp = Blueprint('products', __name__)


# --- Rotas de CRUD para Produtos ---
# ... (as rotas GET, POST, PUT, DELETE para /src/products que já fizemos continuam aqui) ...
@product_bp.route('/', methods=['GET'])
def get_all_products_route():
    products = product_service.get_all_products()
    return jsonify(products), 200


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
    if not data or not data.get('name') or not data.get('price'):
        return jsonify({"error": "Nome e preço são obrigatórios"}), 400
    new_product, error_code, error_message = product_service.create_product(data)
    if new_product:
        return jsonify(new_product), 201
    
    # Retorna códigos de status HTTP específicos baseados no erro
    if error_code == "PRODUCT_NAME_EXISTS":
        return jsonify({"error": error_message}), 409
    elif error_code in ["INVALID_NAME", "INVALID_PRICE"]:
        return jsonify({"error": error_message}), 400
    elif error_code == "DATABASE_ERROR":
        return jsonify({"error": error_message}), 500
    else:
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
    
    # Retorna códigos de status HTTP específicos baseados no erro
    if error_code == "PRODUCT_NOT_FOUND":
        return jsonify({"error": message}), 404
    elif error_code == "PRODUCT_NAME_EXISTS":
        return jsonify({"error": message}), 409
    elif error_code in ["INVALID_NAME", "INVALID_PRICE", "NO_VALID_FIELDS"]:
        return jsonify({"error": message}), 400
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


# --- Rotas de Associação (Produto <-> Ingrediente) ---

# GET /src/products/<id>/ingredients -> Lista os ingredientes de um produto
@product_bp.route('/<int:product_id>/ingredients', methods=['GET'])
def get_product_ingredients_route(product_id):
    ingredients = product_service.get_ingredients_for_product(product_id)
    return jsonify(ingredients), 200


# POST /src/products/<id>/ingredients -> Adiciona um ingrediente a um produto
@product_bp.route('/<int:product_id>/ingredients', methods=['POST'])
@require_role('admin', 'manager')
def add_ingredient_to_product_route(product_id):
    data = request.get_json()
    ingredient_id = data.get('ingredient_id')
    quantity = data.get('quantity')
    if not ingredient_id or not quantity:
        return jsonify({"error": "'ingredient_id' e 'quantity' são obrigatórios"}), 400

    if product_service.add_ingredient_to_product(product_id, ingredient_id, quantity):
        return jsonify({"msg": "Ingrediente associado/atualizado com sucesso"}), 201
    return jsonify({"error": "Falha ao associar ingrediente"}), 500


# DELETE /src/products/<id>/ingredients/<id> -> Remove um ingrediente de um produto
@product_bp.route('/<int:product_id>/ingredients/<int:ingredient_id>', methods=['DELETE'])
@require_role('admin', 'manager')
def remove_ingredient_from_product_route(product_id, ingredient_id):
    if product_service.remove_ingredient_from_product(product_id, ingredient_id):
        return jsonify({"msg": "Ingrediente desassociado com sucesso"}), 200
    return jsonify({"error": "Falha ao desassociar ingrediente ou associação não encontrada"}), 404