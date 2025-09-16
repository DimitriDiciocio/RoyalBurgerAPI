# src/services/notification_service.py

import fdb
from ..database import get_db_connection


# Importaremos o socketio para notificações em tempo real no futuro
# from .. import socketio

def create_notification(user_id, message, link=None):
    """
    Cria uma nova notificação interna no banco de dados.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = "INSERT INTO NOTIFICATIONS (USER_ID, MESSAGE, LINK) VALUES (?, ?, ?);"
        cur.execute(sql, (user_id, message, link))
        conn.commit()

        # Futuramente, aqui podemos emitir um evento via Socket.IO
        # para notificar o usuário em tempo real.
        # socketio.emit('new_notification', {'message': message, 'link': link}, room=f'user_{user_id}')

        return True
    except fdb.Error as e:
        print(f"Erro ao criar notificação: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()


def get_unread_notifications(user_id):
    """Busca as notificações não lidas de um usuário."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = "SELECT ID, MESSAGE, LINK, CREATED_AT FROM NOTIFICATIONS WHERE USER_ID = ? AND IS_READ = FALSE ORDER BY CREATED_AT DESC;"
        cur.execute(sql, (user_id,))
        notifications = []
        for row in cur.fetchall():
            notifications.append({
                "id": row[0],
                "message": row[1],
                "link": row[2],
                "created_at": row[3].strftime('%Y-%m-%d %H:%M:%S')
            })
        return notifications
    except fdb.Error as e:
        print(f"Erro ao buscar notificações: {e}")
        return []
    finally:
        if conn: conn.close()


def mark_notification_as_read(notification_id, user_id):
    """Marca uma notificação específica como lida, garantindo que pertence ao usuário."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # A cláusula WHERE garante que um usuário só pode marcar suas próprias notificações como lidas
        sql = "UPDATE NOTIFICATIONS SET IS_READ = TRUE WHERE ID = ? AND USER_ID = ?;"
        cur.execute(sql, (notification_id, user_id))
        conn.commit()
        return cur.rowcount > 0
    except fdb.Error as e:
        print(f"Erro ao marcar notificação como lida: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

# Adicionar ao final de src/services/notification_service.py
from ..services import user_service # Importar no topo do arquivo

def create_notification_for_roles(roles, message, link=None):
    """Cria uma notificação para todos os usuários com os cargos especificados."""
    user_ids = user_service.get_user_ids_by_roles(roles)
    success = True
    for user_id in user_ids:
        if not create_notification(user_id, message, link):
            success = False # Tenta notificar todos, mesmo que um falhe
    return success

def mark_all_notifications_as_read(user_id):
    """Marca todas as notificações de um usuário como lidas."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = "UPDATE NOTIFICATIONS SET IS_READ = TRUE WHERE USER_ID = ? AND IS_READ = FALSE;"
        cur.execute(sql, (user_id,))
        conn.commit()
        # Retorna o número de notificações que foram atualizadas
        return cur.rowcount
    except fdb.Error as e:
        print(f"Erro ao marcar todas as notificações como lidas: {e}")
        if conn: conn.rollback()
        return -1 # Retorna -1 para indicar um erro
    finally:
        if conn: conn.close()