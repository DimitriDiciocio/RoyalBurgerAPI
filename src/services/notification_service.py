import fdb  
import logging
from ..database import get_db_connection  
from ..services import user_service  

logger = logging.getLogger(__name__)

def create_notification(user_id, message, link=None, notification_type='order'):  
    """
    Cria uma notificação para o usuário, respeitando suas preferências.
    
    Args:
        user_id: ID do usuário
        message: Mensagem da notificação
        link: Link opcional relacionado à notificação
        notification_type: Tipo da notificação ('order' para pedidos, 'promotion' para promoções)
                          Por padrão, assume 'order' para manter compatibilidade
    
    Returns:
        bool: True se a notificação foi criada, False caso contrário
    """
    # ALTERAÇÃO: Verificar preferências de notificação do usuário
    try:
        preferences = user_service.get_notification_preferences(user_id)
        
        # Se não conseguir obter preferências, assume que deve enviar (comportamento padrão)
        if preferences is None:
            logger.warning(f"Não foi possível obter preferências de notificação para usuário {user_id}. Enviando notificação por padrão.")
        else:
            # Verificar se o tipo de notificação está habilitado
            if notification_type == 'order':
                if not preferences.get('notify_order_updates', True):
                    # Usuário desabilitou notificações de pedidos
                    logger.debug(f"Notificação de pedido não enviada para usuário {user_id} (preferência desabilitada)")
                    return False
            elif notification_type == 'promotion':
                if not preferences.get('notify_promotions', True):
                    # Usuário desabilitou notificações de promoções
                    logger.debug(f"Notificação de promoção não enviada para usuário {user_id} (preferência desabilitada)")
                    return False
    except Exception as e:
        # Em caso de erro ao verificar preferências, loga mas continua (comportamento seguro)
        logger.warning(f"Erro ao verificar preferências de notificação para usuário {user_id}: {e}. Enviando notificação por padrão.")
    
    # Criar notificação normalmente se passou na verificação de preferências
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        sql = "INSERT INTO NOTIFICATIONS (USER_ID, MESSAGE, LINK) VALUES (?, ?, ?);"  
        cur.execute(sql, (user_id, message, link))  
        conn.commit()  
        
        # NOVA LÓGICA: Enviar Push Notification (Background)
        try:
            from .push_service import send_push_to_user
            
            # Define título baseado no tipo de notificação
            push_title = "Atualização do Pedido"
            if notification_type == 'promotion':
                push_title = "Promoção Royal Burger"
            
            # Envia push notification (não bloqueia se falhar)
            send_push_to_user(user_id, push_title, message, data={"link": link} if link else {})
        except Exception as push_error:
            # Loga erro mas não falha a criação da notificação
            logger.warning(f"Erro ao enviar push notification para usuário {user_id}: {push_error}")
        
        return True  
    except fdb.Error as e:  
        logger.error(f"Erro ao criar notificação: {e}")  
        if conn: conn.rollback()  
        return False  
    finally:  
        if conn: conn.close()  

def get_unread_notifications(user_id):  
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
        logger.error(f"Erro ao buscar notificações: {e}")  
        return []  
    finally:  
        if conn: conn.close()  

def mark_notification_as_read(notification_id, user_id):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        sql = "UPDATE NOTIFICATIONS SET IS_READ = TRUE WHERE ID = ? AND USER_ID = ?;"  
        cur.execute(sql, (notification_id, user_id))  
        conn.commit()  
        return cur.rowcount > 0  
    except fdb.Error as e:  
        logger.error(f"Erro ao marcar notificação como lida: {e}")  
        if conn: conn.rollback()  
        return False  
    finally:  
        if conn: conn.close()  

def create_notification_for_roles(roles, message, link=None, notification_type='promotion'):  
    """
    Cria notificações para todos os usuários com os roles especificados, respeitando preferências.
    
    Args:
        roles: Lista de roles (ex: ['customer'])
        message: Mensagem da notificação
        link: Link opcional
        notification_type: Tipo da notificação ('order' ou 'promotion')
    
    Returns:
        bool: True se pelo menos uma notificação foi criada
    """
    user_ids = user_service.get_user_ids_by_roles(roles)  
    success_count = 0
    for user_id in user_ids:  
        if create_notification(user_id, message, link, notification_type):  
            success_count += 1
    # Retorna True se pelo menos uma notificação foi criada
    return success_count > 0

def send_order_confirmation(user_id, order_data):
    """
    Envia notificação de confirmação de pedido, respeitando preferências do usuário.
    
    Args:
        user_id: ID do usuário
        order_data: Dados do pedido (deve conter 'id' ou 'order_id')
    
    Returns:
        bool: True se a notificação foi enviada
    """
    try:
        order_id = order_data.get('id') or order_data.get('order_id')
        if not order_id:
            logger.warning(f"Não foi possível obter ID do pedido para notificação: {order_data}")
            return False
        
        message = f"Seu pedido #{order_id} foi confirmado! Acompanhe o status em tempo real."
        link = f"/my-orders/{order_id}"
        
        # Usa notification_type='order' para verificar preferências de pedidos
        return create_notification(user_id, message, link, notification_type='order')
    except Exception as e:
        logger.error(f"Erro ao enviar notificação de confirmação de pedido: {e}", exc_info=True)
        return False  

def mark_all_notifications_as_read(user_id):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        sql = "UPDATE NOTIFICATIONS SET IS_READ = TRUE WHERE USER_ID = ? AND IS_READ = FALSE;"  
        cur.execute(sql, (user_id,))  
        conn.commit()  
        return cur.rowcount  
    except fdb.Error as e:  
        logger.error(f"Erro ao marcar todas as notificações como lidas: {e}")  
        if conn: conn.rollback()  
        return -1  
    finally:  
        if conn: conn.close()  
