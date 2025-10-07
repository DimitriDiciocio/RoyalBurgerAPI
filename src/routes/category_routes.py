from flask import Blueprint, request, jsonify
from ..services import category_service
from ..services.auth_service import require_role

category_bp = Blueprint('categories', __name__)


@category_bp.route('/', methods=['POST'])
@require_role('admin', 'manager')
def create_category_route():
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception as e:
        return jsonify({"error": "Erro ao processar JSON"}), 400
    new_category, error_code, message = category_service.create_category(data)
    if new_category:
        return jsonify(new_category), 201
    if error_code == "INVALID_NAME":
        return jsonify({"error": message}), 400
    if error_code == "CATEGORY_NAME_EXISTS":
        return jsonify({"error": message}), 409
    if error_code == "DATABASE_ERROR":
        return jsonify({"error": message}), 500
    return jsonify({"error": "Não foi possível criar a categoria"}), 500


@category_bp.route('/', methods=['GET'])
def list_categories_route():
    name = request.args.get('name')
    page = request.args.get('page', type=int, default=1)
    page_size = request.args.get('page_size', type=int, default=10)
    result = category_service.list_categories(name_filter=name, page=page, page_size=page_size)
    return jsonify(result), 200


@category_bp.route('/<int:category_id>', methods=['PUT'])
@require_role('admin', 'manager')
def update_category_route(category_id):
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception as e:
        return jsonify({"error": "Erro ao processar JSON"}), 400
    success, error_code, message = category_service.update_category(category_id, data)
    if success:
        return jsonify({"msg": message}), 200
    if error_code == "NO_VALID_FIELDS":
        return jsonify({"error": message}), 400
    if error_code == "INVALID_NAME":
        return jsonify({"error": message}), 400
    if error_code == "CATEGORY_NOT_FOUND":
        return jsonify({"error": message}), 404
    if error_code == "CATEGORY_NAME_EXISTS":
        return jsonify({"error": message}), 409
    if error_code == "DATABASE_ERROR":
        return jsonify({"error": message}), 500
    return jsonify({"error": "Falha ao atualizar categoria"}), 500


@category_bp.route('/<int:category_id>', methods=['DELETE'])
@require_role('admin', 'manager')
def delete_category_route(category_id):
    success, error_code, message = category_service.delete_category(category_id)
    if success:
        return jsonify({"msg": message}), 200
    if error_code == "CATEGORY_NOT_FOUND":
        return jsonify({"error": message}), 404
    if error_code == "DELETE_FAILED":
        return jsonify({"error": message}), 500
    if error_code == "DATABASE_ERROR":
        return jsonify({"error": message}), 500
    return jsonify({"error": "Falha ao excluir categoria"}), 500


@category_bp.route('/reorder', methods=['POST'])
@require_role('admin', 'manager')
def reorder_categories_route():
    """
    Reordena categorias baseado em uma lista de {id, display_order}.
    Body: {"categories": [{"id": 1, "display_order": 1}, {"id": 2, "display_order": 2}]}
    """
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception as e:
        return jsonify({"error": "Erro ao processar JSON"}), 400
    categories = data.get('categories', [])
    
    if not categories:
        return jsonify({"error": "Lista de categorias é obrigatória"}), 400
    
    success, error_code, message = category_service.reorder_categories(categories)
    if success:
        return jsonify({"msg": message}), 200
    
    if error_code == "INVALID_DATA":
        return jsonify({"error": message}), 400
    if error_code == "CATEGORY_NOT_FOUND":
        return jsonify({"error": message}), 404
    if error_code == "INVALID_ORDER":
        return jsonify({"error": message}), 400
    if error_code == "DATABASE_ERROR":
        return jsonify({"error": message}), 500
    
    return jsonify({"error": "Falha ao reordenar categorias"}), 500


@category_bp.route('/reorder', methods=['GET'])
@require_role('admin', 'manager')
def get_categories_for_reorder_route():
    """
    Retorna todas as categorias ativas ordenadas por display_order para reordenação.
    """
    categories, error_code, message = category_service.get_categories_for_reorder()
    if categories is not None:
        return jsonify({"categories": categories}), 200
    
    if error_code == "DATABASE_ERROR":
        return jsonify({"error": message}), 500
    
    return jsonify({"error": "Falha ao buscar categorias"}), 500


@category_bp.route('/<int:category_id>/move', methods=['PUT'])
@require_role('admin', 'manager')
def move_category_route(category_id):
    """
    Move uma categoria para uma nova posição.
    Body: {"position": 2}
    """
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception as e:
        return jsonify({"error": "Erro ao processar JSON"}), 400
    new_position = data.get('position')
    
    if new_position is None or not isinstance(new_position, int):
        return jsonify({"error": "Posição é obrigatória e deve ser um número inteiro"}), 400
    
    success, error_code, message = category_service.move_category_to_position(category_id, new_position)
    if success:
        return jsonify({"msg": message}), 200
    
    if error_code == "CATEGORY_NOT_FOUND":
        return jsonify({"error": message}), 404
    if error_code == "INVALID_POSITION":
        return jsonify({"error": message}), 400
    if error_code == "DATABASE_ERROR":
        return jsonify({"error": message}), 500
    
    return jsonify({"error": "Falha ao mover categoria"}), 500


@category_bp.route('/select', methods=['GET'])
def get_categories_for_select_route():
    """
    Retorna todas as categorias ativas apenas com ID e nome para uso em selects.
    """
    categories, error_code, message = category_service.get_categories_for_select()
    if categories is not None:
        return jsonify({"categories": categories}), 200
    
    if error_code == "DATABASE_ERROR":
        return jsonify({"error": message}), 500
    
    return jsonify({"error": "Falha ao buscar categorias"}), 500


