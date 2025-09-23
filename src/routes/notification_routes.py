from flask import Blueprint, jsonify  # importa Blueprint e jsonify do Flask
from ..services import notification_service  # importa o serviço de notificações
from ..services.auth_service import require_role  # importa decorator de autorização por papel
from flask_jwt_extended import get_jwt  # importa utilitário para ler claims do JWT

notification_bp = Blueprint('notifications', __name__)  # cria o blueprint de notificações

@notification_bp.route('/', methods=['GET'])  # lista notificações não lidas do usuário logado
@require_role('admin', 'manager', 'attendant', 'customer')  # perfis autorizados
def get_my_notifications_route():  # função handler da listagem de notificações
    claims = get_jwt()  # obtém claims do token
    user_id = int(claims.get('sub'))  # extrai ID do usuário
    notifications = notification_service.get_unread_notifications(user_id)  # busca notificações não lidas
    return jsonify(notifications), 200  # retorna lista com status 200

@notification_bp.route('/<int:notification_id>/read', methods=['PATCH'])  # marca uma notificação como lida
@require_role('admin', 'manager', 'attendant', 'customer')  # perfis autorizados
def mark_as_read_route(notification_id):  # função handler de marcação individual
    claims = get_jwt()  # obtém claims do token
    user_id = int(claims.get('sub'))  # extrai ID do usuário
    if notification_service.mark_notification_as_read(notification_id, user_id):  # marca como lida no serviço
        return jsonify({"msg": "Notificação marcada como lida."}), 200  # retorna 200
    return jsonify({"error": "Não foi possível marcar a notificação como lida."}), 404  # retorna 404

@notification_bp.route('/read-all', methods=['PATCH'])  # marca todas as notificações do usuário como lidas
@require_role('admin', 'manager', 'attendant', 'customer')  # perfis autorizados
def mark_all_as_read_route():  # função handler de marcação em massa
    claims = get_jwt()  # obtém claims do token
    user_id = int(claims.get('sub'))  # extrai ID do usuário
    rows_affected = notification_service.mark_all_notifications_as_read(user_id)  # marca todas como lidas
    if rows_affected >= 0:  # operação bem-sucedida
        return jsonify({"msg": f"{rows_affected} notificações marcadas como lidas."}), 200  # retorna 200
    else:  # erro interno
        return jsonify({"error": "Ocorreu um erro ao marcar as notificações como lidas."}), 500  # retorna 500
