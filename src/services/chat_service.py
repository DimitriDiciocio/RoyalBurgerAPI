

import fdb
from ..database import get_db_connection
from ..services import user_service, notification_service
from .. import socketio


def get_chat_id_by_order(order_id, cur):
    """Função auxiliar para encontrar ou criar um chat_id para um pedido."""
    
    sql_find = "SELECT ID FROM CHATS WHERE ORDER_ID = ?;"
    cur.execute(sql_find, (order_id,))
    chat = cur.fetchone()
    if chat:
        return chat[0]

    
    sql_owner = "SELECT USER_ID FROM ORDERS WHERE ID = ?;"
    cur.execute(sql_owner, (order_id,))
    owner = cur.fetchone()
    if not owner:
        raise ValueError("Pedido não encontrado para criar o chat.")

    
    sql_create = "INSERT INTO CHATS (USER_ID, ORDER_ID) VALUES (?, ?) RETURNING ID;"
    cur.execute(sql_create, (owner[0], order_id))
    new_chat_id = cur.fetchone()[0]
    return new_chat_id


def get_chat_history(order_id, user_id, user_role):
    """Busca o histórico de mensagens de um chat de um pedido específico."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        
        sql_check = "SELECT USER_ID FROM ORDERS WHERE ID = ?;"
        cur.execute(sql_check, (order_id,))
        order_owner = cur.fetchone()

        if not order_owner:
            return None  

        if user_role == 'customer' and order_owner[0] != user_id:
            return 'forbidden'  

        
        chat_id = get_chat_id_by_order(order_id, cur)

        
        sql_messages = """
            SELECT m.ID, m.SENDER_TYPE, m.CONTENT, m.CREATED_AT, u.FULL_NAME
            FROM MESSAGES m
            LEFT JOIN USERS u ON m.SENDER_ID = u.ID
            WHERE m.CHAT_ID = ?
            ORDER BY m.CREATED_AT ASC;
        """
        cur.execute(sql_messages, (chat_id,))

        history = []
        for row in cur.fetchall():
            history.append({
                "id": row[0],
                "sender_type": row[1],
                "message": row[2],
                "timestamp": row[3].strftime('%Y-%m-%d %H:%M:%S'),
                "sender_name": row[4] or "Cliente"  
            })
        return history
    except (fdb.Error, ValueError) as e:
        print(f"Erro ao buscar histórico do chat: {e}")
        return None
    finally:
        if conn: conn.close()


def add_message(order_id, sender_id, message_text):
    """Adiciona uma nova mensagem a um chat via API, usando o modelo CHATS/MESSAGES."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        
        chat_id = get_chat_id_by_order(order_id, cur)

        
        sender = user_service.get_user_by_id(sender_id)
        if not sender:
            raise ValueError("Remetente não encontrado.")
        sender_type = 'customer' if sender['role'] == 'customer' else 'attendant'

        
        sql_insert = """
            INSERT INTO MESSAGES (CHAT_ID, SENDER_ID, SENDER_TYPE, CONTENT) 
            VALUES (?, ?, ?, ?) 
            RETURNING ID, CREATED_AT;
        """
        cur.execute(sql_insert, (chat_id, sender_id, sender_type, message_text))
        new_message_data = cur.fetchone()
        conn.commit()

        
        new_message = {
            "id": new_message_data[0],
            "order_id": order_id,  
            "sender_id": sender_id,
            "sender_name": sender['full_name'],
            "message": message_text,
            "timestamp": new_message_data[1].strftime('%Y-%m-%d %H:%M:%S')
        }

        
        socketio.emit('new_message', new_message, to=f'order_{order_id}')

        return new_message
    except (fdb.Error, ValueError) as e:
        print(f"Erro ao adicionar mensagem no chat: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: conn.close()
