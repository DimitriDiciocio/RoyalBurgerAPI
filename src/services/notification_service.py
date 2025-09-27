import fdb  
from ..database import get_db_connection  
from ..services import user_service  

def create_notification(user_id, message, link=None):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        sql = "INSERT INTO NOTIFICATIONS (USER_ID, MESSAGE, LINK) VALUES (?, ?, ?);"  
        cur.execute(sql, (user_id, message, link))  
        conn.commit()  
        return True  
    except fdb.Error as e:  
        print(f"Erro ao criar notificação: {e}")  
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
        print(f"Erro ao buscar notificações: {e}")  
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
        print(f"Erro ao marcar notificação como lida: {e}")  
        if conn: conn.rollback()  
        return False  
    finally:  
        if conn: conn.close()  

def create_notification_for_roles(roles, message, link=None):  
    user_ids = user_service.get_user_ids_by_roles(roles)  
    success = True  
    for user_id in user_ids:  
        if not create_notification(user_id, message, link):  
            success = False  
    return success  

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
        print(f"Erro ao marcar todas as notificações como lidas: {e}")  
        if conn: conn.rollback()  
        return -1  
    finally:  
        if conn: conn.close()  
