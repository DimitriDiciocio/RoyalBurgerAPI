# src/routes/notification_routes.py

from flask import Blueprint, jsonify
from ..services import notification_service
from ..services.auth_service import require_role
from flask_jwt_extended import get_jwt

notification_bp = Blueprint('notifications', __name__)

@notification_bp.route('/', methods=['GET'])
@require_role('admin', 'manager', 'attendant', 'customer') # Todos podem ver suas notificações
def get_my_notifications_route():
    claims = get_jwt()
    user_id = int(claims.get('sub'))
    notifications = notification_service.get_unread_notifications(user_id)
    return jsonify(notifications), 200

@notification_bp.route('/<int:notification_id>/read', methods=['PATCH'])
@require_role('admin', 'manager', 'attendant', 'customer')
def mark_as_read_route(notification_id):
    claims = get_jwt()
    user_id = int(claims.get('sub'))
    if notification_service.mark_notification_as_read(notification_id, user_id):
        return jsonify({"msg": "Notificação marcada como lida."}), 200
    return jsonify({"error": "Não foi possível marcar a notificação como lida."}), 404


@notification_bp.route('/read-all', methods=['PATCH'])
@require_role('admin', 'manager', 'attendant', 'customer')
def mark_all_as_read_route():
    """Marca todas as notificações do usuário logado como lidas."""
    claims = get_jwt()
    user_id = int(claims.get('sub'))

    rows_affected = notification_service.mark_all_notifications_as_read(user_id)

    if rows_affected >= 0:
        return jsonify({"msg": f"{rows_affected} notificações marcadas como lidas."}), 200
    else:
        return jsonify({"error": "Ocorreu um erro ao marcar as notificações como lidas."}), 500
