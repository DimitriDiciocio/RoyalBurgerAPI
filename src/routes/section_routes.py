# src/routes/section_routes.py

from flask import Blueprint, request, jsonify
from ..services import product_service
from ..services.auth_service import require_role
from flask_jwt_extended import get_jwt

section_bp = Blueprint('sections', __name__)

# --- Rotas de CRUD para Seções ---
# ... (as rotas GET, POST, PUT, DELETE para /src/sections que já fizemos continuam aqui) ...
@section_bp.route('/', methods=['GET'])
def get_all_sections_route():
    sections = product_service.get_all_sections()
    return jsonify(sections), 200

@section_bp.route('/', methods=['POST'])
@require_role('admin', 'manager')
def create_section_route():
    claims = get_jwt()
    user_id = claims.get('id')
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({"error": "O campo 'name' é obrigatório"}), 400
    new_section = product_service.create_section(data, user_id)
    if new_section:
        return jsonify(new_section), 201
    return jsonify({"error": "Não foi possível criar a seção"}), 500

@section_bp.route('/<int:section_id>', methods=['PUT'])
@require_role('admin', 'manager')
def update_section_route(section_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400
    if product_service.update_section(section_id, data):
        return jsonify({"msg": "Seção atualizada com sucesso"}), 200
    return jsonify({"error": "Falha ao atualizar seção ou seção não encontrada"}), 404

@section_bp.route('/<int:section_id>', methods=['DELETE'])
@require_role('admin', 'manager')
def delete_section_route(section_id):
    if product_service.delete_section(section_id):
        return jsonify({"msg": "Seção deletada com sucesso"}), 200
    return jsonify({"error": "Falha ao deletar seção ou seção não encontrada"}), 404


# --- Rotas de Associação (Seção <-> Produto) ---

# POST /src/sections/<id>/products/<id> -> Associa um produto a uma seção
@section_bp.route('/<int:section_id>/products/<int:product_id>', methods=['POST'])
@require_role('admin', 'manager')
def add_product_to_section_route(section_id, product_id):
    if product_service.add_product_to_section(product_id, section_id):
        return jsonify({"msg": f"Produto {product_id} associado à seção {section_id} com sucesso"}), 201
    return jsonify({"error": "Falha ao realizar associação"}), 500

# DELETE /src/sections/<id>/products/<id> -> Remove a associação
@section_bp.route('/<int:section_id>/products/<int:product_id>', methods=['DELETE'])
@require_role('admin', 'manager')
def remove_product_from_section_route(section_id, product_id):
    if product_service.remove_product_from_section(product_id, section_id):
        return jsonify({"msg": f"Associação do produto {product_id} com a seção {section_id} removida"}), 200
    return jsonify({"error": "Falha ao remover associação ou associação não encontrada"}), 404

# GET /src/sections/<id> -> Busca uma seção específica pelo ID
@section_bp.route('/<int:section_id>', methods=['GET'])
def get_section_by_id_route(section_id):
    """Busca uma seção específica pelo ID."""
    section = product_service.get_section_by_id(section_id)
    if section:
        return jsonify(section), 200
    return jsonify({"error": "Seção não encontrada"}), 404
