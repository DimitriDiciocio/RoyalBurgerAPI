from flask import Blueprint, request, jsonify
from ..services import category_service
from ..services.auth_service import require_role

category_bp = Blueprint('categories', __name__)


@category_bp.route('/', methods=['POST'])
@require_role('admin', 'manager')
def create_category_route():
    data = request.get_json() or {}
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
    data = request.get_json() or {}
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
    if error_code == "CATEGORY_IN_USE":
        return jsonify({"error": message}), 409
    if error_code == "DATABASE_ERROR":
        return jsonify({"error": message}), 500
    return jsonify({"error": "Falha ao excluir categoria"}), 500


