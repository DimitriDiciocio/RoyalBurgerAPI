from flask import Blueprint, request, jsonify, g
from ..services import recurrence_service
from ..services.auth_service import require_role

recurrence_bp = Blueprint('recurrence', __name__)

@recurrence_bp.route('/rules', methods=['GET'])
@require_role('admin', 'manager')
def get_recurrence_rules_route():
    """Lista regras de recorrência"""
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    rules = recurrence_service.get_recurrence_rules(active_only)
    return jsonify(rules), 200


@recurrence_bp.route('/rules', methods=['POST'])
@require_role('admin', 'manager')
def create_recurrence_rule_route():
    """Cria uma regra de recorrência"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400
    
    user_id = g.current_user_id if hasattr(g, 'current_user_id') else None
    if not user_id:
        return jsonify({"error": "Usuário não autenticado"}), 401
    
    success, error_code, result = recurrence_service.create_recurrence_rule(data, user_id)
    
    if success:
        return jsonify(result), 201
    else:
        return jsonify({"error": result}), 400


@recurrence_bp.route('/rules/<int:rule_id>', methods=['PATCH'])
@require_role('admin', 'manager')
def update_recurrence_rule_route(rule_id):
    """Atualiza uma regra de recorrência"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400
    
    user_id = g.current_user_id if hasattr(g, 'current_user_id') else None
    
    success, error_code, result = recurrence_service.update_recurrence_rule(rule_id, data, user_id)
    
    if success:
        return jsonify(result), 200
    elif error_code == "NOT_FOUND":
        return jsonify({"error": "Regra de recorrência não encontrada"}), 404
    elif error_code in ["INVALID_VALUE", "INVALID_RECURRENCE_DAY", "INVALID_TYPE", "INVALID_RECURRENCE_TYPE", "NO_UPDATES"]:
        return jsonify({"error": result}), 400
    else:
        return jsonify({"error": "Erro interno do servidor"}), 500


@recurrence_bp.route('/rules/<int:rule_id>', methods=['DELETE'])
@require_role('admin', 'manager')
def delete_recurrence_rule_route(rule_id):
    """Desativa uma regra de recorrência"""
    success, error_code, message = recurrence_service.delete_recurrence_rule(rule_id)
    
    if success:
        return jsonify({"message": message}), 200
    elif error_code == "NOT_FOUND":
        return jsonify({"error": "Regra de recorrência não encontrada"}), 404
    else:
        return jsonify({"error": "Erro interno do servidor"}), 500


@recurrence_bp.route('/generate', methods=['POST'])
@require_role('admin', 'manager')
def generate_recurring_movements_route():
    """Gera movimentações para regras de recorrência"""
    data = request.get_json() or {}
    year = data.get('year')
    month = data.get('month')
    week = data.get('week')
    
    # Validar ano, mês e semana se fornecidos
    if year is not None:
        try:
            year = int(year)
            if year < 2000 or year > 2100:
                return jsonify({"error": "Ano deve estar entre 2000 e 2100"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Ano deve ser um número válido"}), 400
    
    if month is not None:
        try:
            month = int(month)
            if month < 1 or month > 12:
                return jsonify({"error": "Mês deve estar entre 1 e 12"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Mês deve ser um número válido"}), 400
    
    if week is not None:
        try:
            week = int(week)
            if week < 1 or week > 53:
                return jsonify({"error": "Semana deve estar entre 1 e 53"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Semana deve ser um número válido"}), 400
    
    success, count, errors = recurrence_service.generate_recurring_movements(year, month, week)
    
    if success:
        return jsonify({
            "success": True,
            "generated_count": count,
            "errors": errors
        }), 200
    else:
        return jsonify({
            "success": False,
            "generated_count": count,
            "errors": errors
        }), 500

