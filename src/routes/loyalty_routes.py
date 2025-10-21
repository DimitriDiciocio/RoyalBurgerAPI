from flask import Blueprint, request, jsonify
from ..services import loyalty_service
from ..services.auth_service import require_role
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity

def validate_required_fields(data, required_fields):
    """Valida se todos os campos obrigatórios estão presentes no JSON"""
    if not data:
        return False
    for field in required_fields:
        if field not in data or data[field] is None:
            return False
    return True

loyalty_bp = Blueprint('loyalty', __name__, url_prefix='/api/loyalty')

@loyalty_bp.route('/balance/<int:user_id>', methods=['GET'])
@jwt_required()
@require_role('customer', 'admin', 'manager')
def get_loyalty_balance_route(user_id):
    """
    Retorna saldo detalhado de pontos do usuário
    """
    try:
        claims = get_jwt()
        current_user_id = int(claims.get('sub'))
        user_roles = claims.get('roles', [])
        
        # Verifica se o usuário pode acessar os dados
        if 'admin' not in user_roles and 'manager' not in user_roles and current_user_id != user_id:
            return jsonify({"error": "Acesso não autorizado"}), 403
        
        balance = loyalty_service.get_loyalty_balance_detailed(user_id)
        if balance is not None:
            return jsonify(balance), 200
        return jsonify({"error": "Não foi possível buscar o saldo"}), 500
    except Exception as e:
        print(f"Erro ao buscar saldo de pontos: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500

@loyalty_bp.route('/history/<int:user_id>', methods=['GET'])
@jwt_required()
@require_role('customer', 'admin', 'manager')
def get_loyalty_history_route(user_id):
    """
    Retorna histórico completo de pontos do usuário
    """
    try:
        claims = get_jwt()
        current_user_id = int(claims.get('sub'))
        user_roles = claims.get('roles', [])
        
        # Verifica se o usuário pode acessar os dados
        if 'admin' not in user_roles and 'manager' not in user_roles and current_user_id != user_id:
            return jsonify({"error": "Acesso não autorizado"}), 403
        
        history = loyalty_service.get_loyalty_history(user_id)
        return jsonify(history), 200
    except Exception as e:
        print(f"Erro ao buscar histórico de pontos: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500

@loyalty_bp.route('/add-points', methods=['POST'])
@jwt_required()
@require_role('admin', 'manager')
def add_points_route():
    """
    Adiciona pontos manualmente (apenas admin/manager)
    """
    try:
        data = request.get_json()
        required_fields = ['user_id', 'points', 'reason']
        
        if not validate_required_fields(data, required_fields):
            return jsonify({"error": "Campos obrigatórios: user_id, points, reason"}), 400
        
        user_id = data['user_id']
        points = int(data['points'])
        reason = data['reason']
        order_id = data.get('order_id')
        
        if points <= 0:
            return jsonify({"error": "Pontos devem ser positivos"}), 400
        
        success = loyalty_service.add_points_manually(user_id, points, reason, order_id)
        if success:
            return jsonify({"message": f"Adicionados {points} pontos com sucesso"}), 200
        else:
            return jsonify({"error": "Erro ao adicionar pontos"}), 500
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"Erro ao adicionar pontos: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500

@loyalty_bp.route('/spend-points', methods=['POST'])
@jwt_required()
@require_role('admin', 'manager')
def spend_points_route():
    """
    Gasta pontos manualmente (apenas admin/manager)
    """
    try:
        data = request.get_json()
        required_fields = ['user_id', 'points', 'reason']
        
        if not validate_required_fields(data, required_fields):
            return jsonify({"error": "Campos obrigatórios: user_id, points, reason"}), 400
        
        user_id = data['user_id']
        points = int(data['points'])
        reason = data['reason']
        order_id = data.get('order_id')
        
        if points <= 0:
            return jsonify({"error": "Pontos devem ser positivos"}), 400
        
        success = loyalty_service.spend_points_manually(user_id, points, reason, order_id)
        if success:
            return jsonify({"message": f"Gastos {points} pontos com sucesso"}), 200
        else:
            return jsonify({"error": "Erro ao gastar pontos"}), 500
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"Erro ao gastar pontos: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500

@loyalty_bp.route('/expire-accounts', methods=['POST'])
@jwt_required()
@require_role('admin', 'manager')
def expire_accounts_route():
    """
    Executa processo de expiração de pontos (apenas admin/manager)
    """
    try:
        expired_count = loyalty_service.expire_inactive_accounts()
        return jsonify({
            "message": f"Processo de expiração concluído",
            "expired_accounts": expired_count
        }), 200
    except Exception as e:
        print(f"Erro ao expirar contas: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500

@loyalty_bp.route('/stats', methods=['GET'])
@jwt_required()
@require_role('admin', 'manager')
def get_loyalty_stats_route():
    """
    Retorna estatísticas do sistema de fidelidade (apenas admin/manager)
    """
    try:
        stats = loyalty_service.get_loyalty_statistics()
        if stats is not None:
            # Se há erro nas estatísticas, retorna 200 com dados vazios e mensagem
            if "error" in stats:
                return jsonify({
                    "total_users_with_points": 0,
                    "total_points_in_circulation": 0,
                    "total_points_expired": 0,
                    "average_points_per_user": 0,
                    "message": "Sistema de fidelidade não inicializado. Execute o script de criação das tabelas.",
                    "error": stats["error"]
                }), 200
            return jsonify(stats), 200
        else:
            return jsonify({
                "total_users_with_points": 0,
                "total_points_in_circulation": 0,
                "total_points_expired": 0,
                "average_points_per_user": 0,
                "message": "Sistema de fidelidade não inicializado",
                "error": "Erro ao buscar estatísticas"
            }), 200
    except Exception as e:
        print(f"Erro ao buscar estatísticas: {e}")
        return jsonify({
            "total_users_with_points": 0,
            "total_points_in_circulation": 0,
            "total_points_expired": 0,
            "average_points_per_user": 0,
            "message": "Sistema de fidelidade não inicializado",
            "error": f"Erro interno do servidor: {str(e)}"
        }), 200
