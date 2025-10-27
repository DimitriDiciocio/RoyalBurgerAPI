from flask import Blueprint, request, jsonify
from ..services import settings_service
from ..services.auth_service import require_role
from flask_jwt_extended import get_jwt

settings_bp = Blueprint('settings', __name__)

@settings_bp.route('/', methods=['GET'])
@require_role('admin')
def get_all_settings_route():
    """Retorna as configurações atuais"""
    try:
        settings = settings_service.get_all_settings()
        if settings:
            return jsonify({"settings": settings}), 200
        return jsonify({"error": "Configurações não encontradas"}), 404
    except Exception as e:
        print(f"Erro ao buscar configurações: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500

@settings_bp.route('/', methods=['POST'])
@require_role('admin')
def update_settings_route():
    """Atualiza configurações (cria nova versão completa)"""
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "Corpo da requisição não pode estar vazio"}), 400
    
    if not data:
        return jsonify({"error": "Nenhuma configuração fornecida"}), 400
    
    claims = get_jwt()
    user_id = int(claims.get('sub'))
    
    success = settings_service.update_settings(data, user_id)
    
    if success:
        updated_fields = list(data.keys())
        return jsonify({
            "msg": f"Configurações atualizadas com sucesso",
            "updated_fields": updated_fields
        }), 200
    
    return jsonify({"error": "Erro ao atualizar configurações"}), 500

@settings_bp.route('/history', methods=['GET'])
@require_role('admin')
def get_settings_history_route():
    """Retorna o histórico de configurações"""
    try:
        history = settings_service.get_settings_history()
        return jsonify({"history": history}), 200
    except Exception as e:
        print(f"Erro ao buscar histórico: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500

@settings_bp.route('/rollback', methods=['POST'])
@require_role('admin')
def rollback_setting_route():
    """Faz rollback para uma versão anterior"""
    data = request.get_json()
    
    if not data or 'history_id' not in data:
        return jsonify({"error": "Corpo da requisição deve conter 'history_id'"}), 400
    
    history_id = data['history_id']
    if not isinstance(history_id, int):
        return jsonify({"error": "O campo 'history_id' deve ser um número inteiro"}), 400
    
    claims = get_jwt()
    user_id = int(claims.get('sub'))
    
    success = settings_service.rollback_setting(history_id, user_id)
    
    if success:
        return jsonify({"msg": "Configuração restaurada com sucesso"}), 200
    
    return jsonify({"error": "Erro ao fazer rollback ou versão não encontrada"}), 500
