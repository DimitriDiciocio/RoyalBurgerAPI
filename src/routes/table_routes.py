from flask import Blueprint, request, jsonify
from ..services import table_service
from ..services.auth_service import require_role
from flask_jwt_extended import jwt_required

table_bp = Blueprint('tables', __name__)


@table_bp.route('/', methods=['POST'])
@require_role('admin', 'manager')
def create_table_route():
    """Cria uma nova mesa no restaurante"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception:
        return jsonify({"error": "Erro ao processar JSON"}), 400

    name = data.get('name')
    x_position = data.get('x_position', 0)
    y_position = data.get('y_position', 0)

    table, error_code, message = table_service.create_table(name, x_position, y_position)
    if table:
        return jsonify(table), 201
    if error_code == 'INVALID_NAME':
        return jsonify({"error": message}), 400
    if error_code == 'TABLE_NAME_EXISTS':
        return jsonify({"error": message}), 409
    if error_code == 'DATABASE_ERROR':
        return jsonify({"error": message}), 500
    return jsonify({"error": "Falha ao criar mesa"}), 500


@table_bp.route('/', methods=['GET'])
@jwt_required()
def list_tables_route():
    """Lista todas as mesas do restaurante"""
    tables = table_service.get_all_tables()
    return jsonify(tables), 200


@table_bp.route('/status', methods=['GET'])
@jwt_required()
def get_tables_status_route():
    """Retorna o status de todas as mesas (usado pelo painel do atendente)"""
    tables = table_service.get_tables_status()
    return jsonify(tables), 200


@table_bp.route('/<int:table_id>', methods=['GET'])
@jwt_required()
def get_table_route(table_id):
    """Busca uma mesa por ID"""
    table = table_service.get_table_by_id(table_id)
    if not table:
        return jsonify({"error": "Mesa não encontrada"}), 404
    return jsonify(table), 200


@table_bp.route('/<int:table_id>', methods=['PUT'])
@require_role('admin', 'manager')
def update_table_route(table_id):
    """Atualiza dados de uma mesa"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception:
        return jsonify({"error": "Erro ao processar JSON"}), 400

    name = data.get('name')
    status = data.get('status')
    x_position = data.get('x_position')
    y_position = data.get('y_position')

    success, error_code, message = table_service.update_table(
        table_id, name=name, status=status, x_position=x_position, y_position=y_position
    )
    if success:
        return jsonify({"msg": message}), 200
    if error_code in ['INVALID_NAME', 'INVALID_STATUS', 'INVALID_X_POSITION', 'INVALID_Y_POSITION', 'NO_VALID_FIELDS']:
        return jsonify({"error": message}), 400
    if error_code == 'TABLE_NOT_FOUND':
        return jsonify({"error": message}), 404
    if error_code == 'TABLE_NAME_EXISTS':
        return jsonify({"error": message}), 409
    if error_code == 'DATABASE_ERROR':
        return jsonify({"error": message}), 500
    return jsonify({"error": "Falha ao atualizar mesa"}), 500


@table_bp.route('/<int:table_id>', methods=['DELETE'])
@require_role('admin', 'manager')
def delete_table_route(table_id):
    """Remove uma mesa do restaurante"""
    deleted = table_service.delete_table(table_id)
    if deleted:
        return jsonify({"msg": "Mesa excluída com sucesso"}), 200
    return jsonify({"error": "Mesa não encontrada, está ocupada ou falha ao excluir"}), 404


@table_bp.route('/layout', methods=['PUT'])
@require_role('admin', 'manager')
def update_layout_route():
    """Atualiza o layout de todas as mesas (posições X e Y)"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
        
        layout_data = data.get('layout')
        if not layout_data:
            return jsonify({"error": "Campo 'layout' é obrigatório"}), 400
    except Exception:
        return jsonify({"error": "Erro ao processar JSON"}), 400

    success, error_code, message = table_service.update_layout(layout_data)
    if success:
        return jsonify({"msg": message}), 200
    if error_code in ['INVALID_DATA', 'INVALID_ITEM', 'MISSING_TABLE_ID', 'MISSING_POSITION', 'INVALID_TYPE']:
        return jsonify({"error": message}), 400
    if error_code == 'TABLE_NOT_FOUND':
        return jsonify({"error": message}), 404
    if error_code == 'DATABASE_ERROR':
        return jsonify({"error": message}), 500
    return jsonify({"error": "Falha ao atualizar layout"}), 500

