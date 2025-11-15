from flask import Blueprint, request, jsonify
from ..services import settings_service
from ..services.auth_service import require_role
from flask_jwt_extended import get_jwt
import logging  # ALTERAÇÃO: Import centralizado para logging estruturado

settings_bp = Blueprint('settings', __name__)
logger = logging.getLogger(__name__)  # ALTERAÇÃO: Logger centralizado

@settings_bp.route('/public', methods=['GET'])
def get_public_settings_route():
    """Retorna configurações públicas (sem autenticação) - taxas, prazos, info da empresa e taxas de conversão de pontos"""
    try:
        settings = settings_service.get_all_settings()
        if not settings:
            return jsonify({"error": "Configurações não encontradas"}), 404
        
        # Retorna apenas informações públicas
        return jsonify({
            "delivery_fee": settings.get('taxa_entrega'),
            "estimated_delivery_time": {
                "initiation_minutes": settings.get('prazo_iniciacao'),
                "preparation_minutes": settings.get('prazo_preparo'),
                "dispatch_minutes": settings.get('prazo_envio'),
                "delivery_minutes": settings.get('prazo_entrega')
            },
            "company_info": {
                "nome_fantasia": settings.get('nome_fantasia'),
                "razao_social": settings.get('razao_social'),
                "cnpj": settings.get('cnpj'),
                "endereco": settings.get('endereco'),
                "telefone": settings.get('telefone'),
                "email": settings.get('email')
            },
            "loyalty_rates": {
                "gain_rate": settings.get('taxa_conversao_ganho_clube'),
                "redemption_rate": settings.get('taxa_conversao_resgate_clube'),
                "expiration_days": settings.get('taxa_expiracao_pontos_clube')
            }
        }), 200
    except Exception as e:
        # ALTERAÇÃO: Usar logger ao invés de print() em código de produção
        logger.error(f"Erro ao buscar configurações públicas: {e}", exc_info=True)
        # ALTERAÇÃO: Retornar erro 500 com mensagem genérica para evitar exposição de informações sensíveis
        return jsonify({"error": "Erro interno do servidor ao buscar configurações públicas"}), 500

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
        # ALTERAÇÃO: Usar logger ao invés de print() em código de produção
        logger.error(f"Erro ao buscar configurações: {e}", exc_info=True)
        # ALTERAÇÃO: Retornar erro 500 com mensagem genérica para evitar exposição de informações sensíveis
        return jsonify({"error": "Erro interno do servidor ao buscar configurações"}), 500

@settings_bp.route('/', methods=['POST'])
@require_role('admin')
def update_settings_route():
    """Atualiza configurações (cria nova versão completa)"""
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "Corpo da requisição não pode estar vazio"}), 400
    
    claims = get_jwt()
    user_id = int(claims.get('sub'))
    
    success = settings_service.update_settings(data, user_id)
    
    if success:
        updated_fields = list(data.keys())
        return jsonify({
            "msg": "Configurações atualizadas com sucesso",
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
        # ALTERAÇÃO: Usar logger ao invés de print() em código de produção
        logger.error(f"Erro ao buscar histórico: {e}", exc_info=True)
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
