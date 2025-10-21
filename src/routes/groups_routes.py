from flask import Blueprint, request, jsonify
from ..services import groups_service
from ..services.auth_service import require_role


groups_bp = Blueprint('groups', __name__)


@groups_bp.route('/', methods=['POST'])
@require_role('admin', 'manager')
def create_group_route():
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception:
        return jsonify({"error": "Erro ao processar JSON"}), 400

    name = data.get('name')
    is_active = data.get('is_active', True)
    group, error_code, message = groups_service.create_group(name, is_active)
    if group:
        return jsonify(group), 201
    if error_code == 'INVALID_NAME':
        return jsonify({"error": message}), 400
    if error_code == 'GROUP_NAME_EXISTS':
        return jsonify({"error": message}), 409
    if error_code == 'DATABASE_ERROR':
        return jsonify({"error": message}), 500
    return jsonify({"error": "Falha ao criar grupo"}), 500


@groups_bp.route('/', methods=['GET'])
def list_groups_route():
    active_only = request.args.get('active_only', default='true').lower() != 'false'
    items = groups_service.get_all_groups(active_only=active_only)
    return jsonify(items), 200


@groups_bp.route('/<int:group_id>', methods=['GET'])
def get_group_route(group_id):
    group = groups_service.get_group_by_id(group_id)
    if not group:
        return jsonify({"error": "Grupo não encontrado"}), 404
    return jsonify(group), 200


@groups_bp.route('/<int:group_id>', methods=['PUT'])
@require_role('admin', 'manager')
def update_group_route(group_id):
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception:
        return jsonify({"error": "Erro ao processar JSON"}), 400

    name = data.get('name')
    is_active = data.get('is_active')
    success, error_code, message = groups_service.update_group(group_id, name=name, is_active=is_active)
    if success:
        return jsonify({"msg": message}), 200
    if error_code in ['INVALID_NAME', 'NO_VALID_FIELDS']:
        return jsonify({"error": message}), 400
    if error_code == 'GROUP_NOT_FOUND':
        return jsonify({"error": message}), 404
    if error_code == 'GROUP_NAME_EXISTS':
        return jsonify({"error": message}), 409
    if error_code == 'DATABASE_ERROR':
        return jsonify({"error": message}), 500
    return jsonify({"error": "Falha ao atualizar grupo"}), 500


@groups_bp.route('/<int:group_id>', methods=['DELETE'])
@require_role('admin', 'manager')
def delete_group_route(group_id):
    deleted = groups_service.delete_group(group_id)
    if deleted:
        return jsonify({"msg": "Grupo excluído com sucesso"}), 200
    return jsonify({"error": "Grupo não encontrado ou falha ao excluir"}), 404


@groups_bp.route('/<int:group_id>/ingredients', methods=['POST'])
@require_role('admin', 'manager')
def add_ingredient_to_group_route(group_id):
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception:
        return jsonify({"error": "Erro ao processar JSON"}), 400

    ingredient_id = data.get('ingredient_id')
    if not ingredient_id:
        return jsonify({"error": "'ingredient_id' é obrigatório"}), 400

    success, error_code, message = groups_service.add_ingredient_to_group(group_id, ingredient_id)
    if success:
        return jsonify({"msg": message}), 201
    if error_code in ['GROUP_NOT_FOUND', 'INGREDIENT_NOT_FOUND']:
        return jsonify({"error": message}), 404
    if error_code == 'DATABASE_ERROR':
        return jsonify({"error": message}), 500
    return jsonify({"error": "Falha ao adicionar ingrediente ao grupo"}), 500


@groups_bp.route('/<int:group_id>/ingredients/<int:ingredient_id>', methods=['DELETE'])
@require_role('admin', 'manager')
def remove_ingredient_from_group_route(group_id, ingredient_id):
    removed = groups_service.remove_ingredient_from_group(group_id, ingredient_id)
    if removed:
        return jsonify({"msg": "Ingrediente removido do grupo"}), 200
    return jsonify({"error": "Associação não encontrada"}), 404


