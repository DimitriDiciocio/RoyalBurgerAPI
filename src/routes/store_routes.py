from flask import Blueprint, request, jsonify
from ..services import store_service
from ..services.auth_service import require_role

store_bp = Blueprint('store', __name__)

@store_bp.route('/hours', methods=['GET'])
def get_store_hours_route():
    """Retorna os horários de funcionamento da loja (público - sem autenticação)"""
    try:
        hours = store_service.get_store_hours()
        return jsonify({"hours": hours}), 200
    except Exception as e:
        print(f"Erro ao buscar horários: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500

@store_bp.route('/is-open', methods=['GET'])
def is_store_open_route():
    """Verifica se a loja está aberta no momento (público - sem autenticação)"""
    try:
        is_open, message = store_service.is_store_open()
        return jsonify({"is_open": is_open, "message": message}), 200
    except Exception as e:
        print(f"Erro ao verificar status da loja: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500

@store_bp.route('/hours', methods=['PUT'])
@require_role('admin', 'manager')
def update_store_hours_route():
    """Atualiza os horários de funcionamento (requer autenticação de admin/manager)"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Dados não fornecidos"}), 400
        
        # Validação de campos obrigatórios
        if 'day_of_week' not in data:
            return jsonify({"error": "day_of_week é obrigatório"}), 400
        
        day_of_week = data.get('day_of_week')
        opening_time = data.get('opening_time')
        closing_time = data.get('closing_time')
        is_open = data.get('is_open')
        
        # Valida se pelo menos um campo para atualizar foi fornecido
        if opening_time is None and closing_time is None and is_open is None:
            return jsonify({"error": "Pelo menos um campo deve ser fornecido (opening_time, closing_time ou is_open)"}), 400
        
        success, message = store_service.update_store_hours(day_of_week, opening_time, closing_time, is_open)
        
        if success:
            return jsonify({"message": message}), 200
        else:
            return jsonify({"error": message}), 400
            
    except Exception as e:
        print(f"Erro ao atualizar horários: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500

@store_bp.route('/hours/bulk', methods=['PUT'])
@require_role('admin', 'manager')
def bulk_update_store_hours_route():
    """Atualiza múltiplos dias de uma vez (requer autenticação de admin/manager)"""
    try:
        data = request.get_json()
        
        if not data or 'hours' not in data:
            return jsonify({"error": "Lista de horários (hours) é obrigatória"}), 400
        
        hours_data = data.get('hours', [])
        
        if not isinstance(hours_data, list) or len(hours_data) == 0:
            return jsonify({"error": "hours deve ser uma lista não vazia"}), 400
        
        success_count, failed_count, errors = store_service.bulk_update_store_hours(hours_data)
        
        if failed_count == 0:
            return jsonify({
                "message": f"{success_count} dias atualizados com sucesso",
                "success_count": success_count
            }), 200
        else:
            return jsonify({
                "message": f"{success_count} dias atualizados, {failed_count} falharam",
                "success_count": success_count,
                "failed_count": failed_count,
                "errors": errors
            }), 207  # 207 Multi-Status (alguns sucessos, alguns falhas)
            
    except Exception as e:
        print(f"Erro ao atualizar horários em massa: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500

