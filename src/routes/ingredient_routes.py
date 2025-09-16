# src/routes/ingredient_routes.py

from flask import Blueprint, request, jsonify
from ..services import ingredient_service # CORREÇÃO: Importa o serviço correto
from ..services.auth_service import require_role

ingredient_bp = Blueprint('ingredients', __name__)

# GET /src/ingredients/ -> Lista todos os ingredientes
@ingredient_bp.route('/', methods=['GET'])
@require_role('admin', 'manager') # Alterado para admin, pois a versão pública pode vir dos produtos
def get_all_ingredients_route():
    ingredients = ingredient_service.get_all_ingredients()
    return jsonify(ingredients), 200

# POST /src/ingredients/ -> Cria um novo ingrediente
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

# PUT /src/ingredients/<ingredient_id> -> Atualiza um ingrediente
@ingredient_bp.route('/<int:ingredient_id>', methods=['PUT'])
@require_role('admin', 'manager')
def update_ingredient_route(ingredient_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400

    if ingredient_service.update_ingredient(ingredient_id, data):
        return jsonify({"msg": "Ingrediente atualizado com sucesso"}), 200
    return jsonify({"error": "Falha ao atualizar ingrediente ou ingrediente não encontrado"}), 404

# DELETE /src/ingredients/<ingredient_id> -> Inativa um ingrediente
@ingredient_bp.route('/<int:ingredient_id>', methods=['DELETE'])
@require_role('admin', 'manager')
def delete_ingredient_route(ingredient_id):
    # A lógica de inativar agora simplesmente marca como indisponível
    if ingredient_service.deactivate_ingredient(ingredient_id):
        return jsonify({"msg": "Ingrediente marcado como indisponível com sucesso"}), 200
    return jsonify({"error": "Falha ao inativar ingrediente ou ingrediente não encontrado"}), 404

# PATCH /src/ingredients/<id>/availability -> Atualiza o status de disponibilidade
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