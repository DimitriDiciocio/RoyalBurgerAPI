import fdb  # importa driver do Firebird
from ..database import get_db_connection  # importa função de conexão com o banco
from ..services import user_service  # importa serviço de usuários para buscar IDs por cargos

def create_notification(user_id, message, link=None):  # cria nova notificação
    conn = None  # inicializa conexão
    try:  # tenta inserir notificação
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = "INSERT INTO NOTIFICATIONS (USER_ID, MESSAGE, LINK) VALUES (?, ?, ?);"  # SQL de inserção
        cur.execute(sql, (user_id, message, link))  # executa inserção
        conn.commit()  # confirma transação
        return True  # sucesso
    except fdb.Error as e:  # captura erros
        print(f"Erro ao criar notificação: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return False  # retorna falso em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def get_unread_notifications(user_id):  # busca notificações não lidas do usuário
    conn = None  # inicializa conexão
    try:  # tenta buscar notificações
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = "SELECT ID, MESSAGE, LINK, CREATED_AT FROM NOTIFICATIONS WHERE USER_ID = ? AND IS_READ = FALSE ORDER BY CREATED_AT DESC;"  # SQL
        cur.execute(sql, (user_id,))  # executa query
        notifications = []  # lista de notificações
        for row in cur.fetchall():  # itera resultados
            notifications.append({  # monta dicionário da notificação
                "id": row[0],
                "message": row[1],
                "link": row[2],
                "created_at": row[3].strftime('%Y-%m-%d %H:%M:%S')
            })
        return notifications  # retorna lista
    except fdb.Error as e:  # captura erros
        print(f"Erro ao buscar notificações: {e}")  # exibe erro
        return []  # retorna vazio em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def mark_notification_as_read(notification_id, user_id):  # marca notificação como lida
    conn = None  # inicializa conexão
    try:  # tenta atualizar notificação
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = "UPDATE NOTIFICATIONS SET IS_READ = TRUE WHERE ID = ? AND USER_ID = ?;"  # garante propriedade do usuário
        cur.execute(sql, (notification_id, user_id))  # executa update
        conn.commit()  # confirma transação
        return cur.rowcount > 0  # retorna True se atualizou
    except fdb.Error as e:  # captura erros
        print(f"Erro ao marcar notificação como lida: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return False  # retorna falso em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def create_notification_for_roles(roles, message, link=None):  # cria notificação para cargos
    user_ids = user_service.get_user_ids_by_roles(roles)  # obtém IDs por cargos
    success = True  # flag de sucesso acumulado
    for user_id in user_ids:  # itera usuários
        if not create_notification(user_id, message, link):  # tenta notificar
            success = False  # marca falha se alguma notificação falhar
    return success  # retorna sucesso agregado

def mark_all_notifications_as_read(user_id):  # marca todas como lidas
    conn = None  # inicializa conexão
    try:  # tenta marcar
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = "UPDATE NOTIFICATIONS SET IS_READ = TRUE WHERE USER_ID = ? AND IS_READ = FALSE;"  # SQL de atualização em massa
        cur.execute(sql, (user_id,))  # executa update
        conn.commit()  # confirma transação
        return cur.rowcount  # retorna número de linhas afetadas
    except fdb.Error as e:  # captura erros
        print(f"Erro ao marcar todas as notificações como lidas: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return -1  # retorna -1 em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão