import fdb  
from datetime import date  
from ..database import get_db_connection  

def create_loyalty_account_if_not_exists(user_id, cur):  
    try:  
        # Primeiro verifica se já existe
        sql_check = "SELECT USER_ID FROM LOYALTY_POINTS WHERE USER_ID = ?;"
        cur.execute(sql_check, (user_id,))
        existing = cur.fetchone()
        
        # Se não existe, cria a conta
        if not existing:
            sql_insert = """
                INSERT INTO LOYALTY_POINTS (USER_ID, ACCUMULATED_POINTS, SPENT_POINTS) 
                VALUES (?, 0, 0);
            """
            cur.execute(sql_insert, (user_id,))
            print(f"Conta de fidelidade criada para o usuário {user_id}")
        
        return True  
    except fdb.Error as e:  
        print(f"Erro ao criar conta de fidelidade: {e}")  
        raise e  

def earn_points_for_order(user_id, order_id, total_amount, cur):  
    create_loyalty_account_if_not_exists(user_id, cur)  
    points_to_earn = int(total_amount)  
    sql_update_account = """
        UPDATE LOYALTY_POINTS
        SET 
            ACCUMULATED_POINTS = ACCUMULATED_POINTS + ?,
            POINTS_EXPIRATION_DATE = CURRENT_DATE + 60
        WHERE USER_ID = ?;
    """  
    cur.execute(sql_update_account, (points_to_earn, user_id))  
    sql_add_history = "INSERT INTO LOYALTY_POINTS_HISTORY (USER_ID, ORDER_ID, POINTS, REASON) VALUES (?, ?, ?, ?);"  
    reason = f"Pontos ganhos no pedido #{order_id}"
    cur.execute(sql_add_history, (user_id, order_id, points_to_earn, reason))  
    print(f"{points_to_earn} pontos ganhos e validade renovada para o usuário {user_id}.")  

def add_welcome_points(user_id, cur):
    """Adiciona 100 pontos de boas-vindas para novos clientes"""
    try:
        create_loyalty_account_if_not_exists(user_id, cur)
        
        # Adiciona 100 pontos de boas-vindas
        welcome_points = 100
        sql_update_account = """
            UPDATE LOYALTY_POINTS
            SET 
                ACCUMULATED_POINTS = ACCUMULATED_POINTS + ?,
                POINTS_EXPIRATION_DATE = CURRENT_DATE + 60
            WHERE USER_ID = ?;
        """
        cur.execute(sql_update_account, (welcome_points, user_id))
        
        # Adiciona histórico dos pontos de boas-vindas
        sql_add_history = "INSERT INTO LOYALTY_POINTS_HISTORY (USER_ID, POINTS, REASON) VALUES (?, ?, ?);"
        reason = "Pontos de boas-vindas"
        cur.execute(sql_add_history, (user_id, welcome_points, reason))
        
        print(f"Adicionados {welcome_points} pontos de boas-vindas para o usuário {user_id}.")
        return True
    except fdb.Error as e:
        print(f"Erro ao adicionar pontos de boas-vindas: {e}")
        raise e

def get_loyalty_balance(user_id):  
    conn = None
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        create_loyalty_account_if_not_exists(user_id, cur)  
        conn.commit()  
        sql_get = "SELECT ACCUMULATED_POINTS, SPENT_POINTS, POINTS_EXPIRATION_DATE FROM LOYALTY_POINTS WHERE USER_ID = ?;"  
        cur.execute(sql_get, (user_id,))  
        account = cur.fetchone()  
        accumulated, spent, expiration_date = account or (0, 0, None)  
        print(f"Saldo de pontos: {accumulated}, {spent}, {expiration_date}")
        current_balance = accumulated - spent  
        if expiration_date and expiration_date < date.today() and current_balance > 0:  
            points_to_expire = current_balance  
            sql_expire = "UPDATE LOYALTY_POINTS SET SPENT_POINTS = ACCUMULATED_POINTS WHERE USER_ID = ?;"  
            cur.execute(sql_expire, (user_id,))  
            sql_add_history = "INSERT INTO LOYALTY_POINTS_HISTORY (USER_ID, POINTS, REASON) VALUES (?, ?, 'Pontos expirados por inatividade');"  
            cur.execute(sql_add_history, (user_id, -points_to_expire))  
            conn.commit()  
            return {"accumulated_points": accumulated, "spent_points": accumulated, "current_balance": 0}  
        return {"accumulated_points": accumulated, "spent_points": spent, "current_balance": current_balance}  
    except fdb.Error as e:  
        print(f"Erro ao buscar saldo de pontos: {e}")  
        if conn: conn.rollback()  
        return None  
    finally:  
        if conn: conn.close()

def redeem_points_for_discount(user_id, points_to_redeem, order_id, cur):  
    balance_data = get_loyalty_balance(user_id)  
    current_balance = balance_data.get("current_balance", 0)  
    if current_balance < points_to_redeem:  
        raise ValueError(
            f"Saldo de pontos insuficiente. Saldo atual: {current_balance}, Pontos para resgate: {points_to_redeem}")  
    sql_update_account = "UPDATE LOYALTY_POINTS SET SPENT_POINTS = SPENT_POINTS + ? WHERE USER_ID = ?;"  
    cur.execute(sql_update_account, (points_to_redeem, user_id))  
    sql_add_history = "INSERT INTO LOYALTY_POINTS_HISTORY (USER_ID, ORDER_ID, POINTS, REASON) VALUES (?, ?, ?, ?);"  
    reason = f"Resgate de pontos no pedido #{order_id}"
    cur.execute(sql_add_history, (user_id, order_id, -points_to_redeem, reason))  
    discount_amount = points_to_redeem / 10.0  
    print(f"{points_to_redeem} pontos resgatados pelo usuário {user_id} por R${discount_amount:.2f} de desconto.")  
    return discount_amount  

def get_loyalty_history(user_id):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        sql = "SELECT POINTS, REASON, EARNED_AT FROM LOYALTY_POINTS_HISTORY WHERE USER_ID = ? ORDER BY EARNED_AT DESC;"  
        cur.execute(sql, (user_id,))  
        history = [{"points": row[0], "reason": row[1], "date": row[2].strftime('%Y-%m-%d %H:%M:%S')} for row in cur.fetchall()]  
        return history  
    except fdb.Error as e:  
        print(f"Erro ao buscar histórico de pontos: {e}")  
        return []  
    finally:  
        if conn: conn.close()  

def expire_inactive_accounts():  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        sql_find_expired = """
            SELECT USER_ID, ACCUMULATED_POINTS, SPENT_POINTS 
            FROM LOYALTY_POINTS 
            WHERE POINTS_EXPIRATION_DATE < CURRENT_DATE 
            AND ACCUMULATED_POINTS > SPENT_POINTS;
        """  
        cur.execute(sql_find_expired)  
        expired_accounts = cur.fetchall()  
        for user_id, accumulated, spent in expired_accounts:  
            points_to_expire = accumulated - spent  
            sql_expire = "UPDATE LOYALTY_POINTS SET SPENT_POINTS = ACCUMULATED_POINTS WHERE USER_ID = ?;"  
            cur.execute(sql_expire, (user_id,))  
            sql_add_history = "INSERT INTO LOYALTY_POINTS_HISTORY (USER_ID, POINTS, REASON) VALUES (?, ?, 'Pontos expirados por inatividade');"  
            cur.execute(sql_add_history, (user_id, -points_to_expire))  
            print(f"Expirado saldo de {points_to_expire} pontos para o usuário {user_id}")  
        conn.commit()  
        return len(expired_accounts)  
    except fdb.Error as e:  
        print(f"Erro durante o processo de expiração de pontos: {e}")  
        if conn: conn.rollback()  
        return -1  
    finally:  
        if conn: conn.close()  
