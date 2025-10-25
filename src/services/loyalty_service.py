import fdb  
from datetime import date  
from ..database import get_db_connection

def _validate_points(points):
    """Valida se pontos é um valor válido"""
    if not isinstance(points, (int, float)) or points < 0:
        raise ValueError("Pontos devem ser um número não negativo")

def _expire_points_if_needed(user_id, cur):
    """Centraliza lógica de expiração de pontos"""
    try:
        cur.execute("""
            SELECT ACCUMULATED_POINTS, SPENT_POINTS, POINTS_EXPIRATION_DATE
            FROM LOYALTY_POINTS WHERE USER_ID = ?
        """, (user_id,))
        account = cur.fetchone()
        
        if not account:
            return 0
            
        accumulated, spent, expiration_date = account
        current_balance = accumulated - spent
        
        if expiration_date and expiration_date < date.today() and current_balance > 0:
            points_to_expire = current_balance
            cur.execute("UPDATE LOYALTY_POINTS SET SPENT_POINTS = ACCUMULATED_POINTS WHERE USER_ID = ?;", (user_id,))
            cur.execute("""
                INSERT INTO LOYALTY_POINTS_HISTORY (USER_ID, POINTS, REASON) 
                VALUES (?, ?, 'Pontos expirados por inatividade');
            """, (user_id, -points_to_expire))
            return points_to_expire
        
        return 0
    except Exception as e:
        print(f"Erro ao verificar expiração de pontos: {e}")
        return 0  

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
    try:
        _validate_points(total_amount)
        create_loyalty_account_if_not_exists(user_id, cur)  
        
        # R$ 1,00 = 10 pontos Royal (conforme documentação)
        points_to_earn = int(total_amount * 10)  
        
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
    except Exception as e:
        print(f"Erro ao ganhar pontos: {e}")
        raise e  

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
        
        # Verifica expiração
        expired_points = _expire_points_if_needed(user_id, cur)
        if expired_points > 0:
            conn.commit()
            return {"accumulated_points": accumulated, "spent_points": accumulated, "current_balance": 0}  
        
        current_balance = accumulated - spent  
        return {"accumulated_points": accumulated, "spent_points": spent, "current_balance": current_balance}  
    except fdb.Error as e:  
        print(f"Erro ao buscar saldo de pontos: {e}")  
        if conn: conn.rollback()  
        return None  
    finally:  
        if conn: conn.close()

def redeem_points_for_discount(user_id, points_to_redeem, order_id, cur):  
    try:
        _validate_points(points_to_redeem)
        
        balance_data = get_loyalty_balance(user_id)  
        current_balance = balance_data.get("current_balance", 0)  
        
        if current_balance < points_to_redeem:  
            raise ValueError(f"Saldo de pontos insuficiente. Saldo atual: {current_balance}, Pontos para resgate: {points_to_redeem}")  
        
        sql_update_account = "UPDATE LOYALTY_POINTS SET SPENT_POINTS = SPENT_POINTS + ? WHERE USER_ID = ?;"  
        cur.execute(sql_update_account, (points_to_redeem, user_id))  
        
        sql_add_history = "INSERT INTO LOYALTY_POINTS_HISTORY (USER_ID, ORDER_ID, POINTS, REASON) VALUES (?, ?, ?, ?);"  
        reason = f"Resgate de pontos no pedido #{order_id}"
        cur.execute(sql_add_history, (user_id, order_id, -points_to_redeem, reason))  
        
        # 100 pontos = R$ 1,00 de desconto (conforme documentação)
        discount_amount = points_to_redeem / 100.0  
        print(f"{points_to_redeem} pontos resgatados pelo usuário {user_id} por R${discount_amount:.2f} de desconto.")  
        return discount_amount  
    except Exception as e:
        print(f"Erro ao resgatar pontos: {e}")
        raise e  

def get_loyalty_history(user_id):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        sql = """
            SELECT POINTS, REASON, EARNED_AT, ORDER_ID,
                   CASE 
                       WHEN POINTS > 0 THEN 'earned'
                       WHEN POINTS < 0 THEN 'spent'
                       ELSE 'neutral'
                   END as transaction_type
            FROM LOYALTY_POINTS_HISTORY 
            WHERE USER_ID = ? 
            ORDER BY EARNED_AT DESC
        """  
        cur.execute(sql, (user_id,))  
        history = []
        for row in cur.fetchall():
            points, reason, earned_at, order_id, transaction_type = row
            history.append({
                "points": points,
                "reason": reason,
                "date": earned_at.strftime('%Y-%m-%d %H:%M:%S'),
                "order_id": order_id,
                "transaction_type": transaction_type,
                "expiration_date": None  # Será calculado se necessário
            })
        return history  
    except fdb.Error as e:  
        print(f"Erro ao buscar histórico de pontos: {e}")  
        return []  
    finally:  
        if conn: conn.close()

def add_points_manually(user_id, points, reason, order_id=None):
    """Adiciona pontos manualmente (para admin)"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Cria conta se não existir
        create_loyalty_account_if_not_exists(user_id, cur)
        
        # Atualiza pontos acumulados
        sql_update = """
            UPDATE LOYALTY_POINTS
            SET 
                ACCUMULATED_POINTS = ACCUMULATED_POINTS + ?,
                POINTS_EXPIRATION_DATE = CURRENT_DATE + 60
            WHERE USER_ID = ?;
        """
        cur.execute(sql_update, (points, user_id))
        
        # Adiciona ao histórico
        sql_history = "INSERT INTO LOYALTY_POINTS_HISTORY (USER_ID, ORDER_ID, POINTS, REASON) VALUES (?, ?, ?, ?);"
        cur.execute(sql_history, (user_id, order_id, points, reason))
        
        conn.commit()
        print(f"Adicionados {points} pontos para o usuário {user_id}: {reason}")
        return True
    except fdb.Error as e:
        print(f"Erro ao adicionar pontos manualmente: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

def spend_points_manually(user_id, points, reason, order_id=None):
    """Gasta pontos manualmente (para admin)"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica saldo
        balance_data = get_loyalty_balance(user_id)
        current_balance = balance_data.get("current_balance", 0)
        
        if current_balance < points:
            raise ValueError(f"Saldo insuficiente. Saldo atual: {current_balance}, Pontos para gastar: {points}")
        
        # Atualiza pontos gastos
        sql_update = "UPDATE LOYALTY_POINTS SET SPENT_POINTS = SPENT_POINTS + ? WHERE USER_ID = ?;"
        cur.execute(sql_update, (points, user_id))
        
        # Adiciona ao histórico
        sql_history = "INSERT INTO LOYALTY_POINTS_HISTORY (USER_ID, ORDER_ID, POINTS, REASON) VALUES (?, ?, ?, ?);"
        cur.execute(sql_history, (user_id, order_id, -points, reason))
        
        conn.commit()
        print(f"Gastos {points} pontos do usuário {user_id}: {reason}")
        return True
    except fdb.Error as e:
        print(f"Erro ao gastar pontos manualmente: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

def get_loyalty_balance_detailed(user_id):
    """Retorna saldo detalhado com informações de expiração"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Cria conta se não existir
        create_loyalty_account_if_not_exists(user_id, cur)
        conn.commit()
        
        sql_get = """
            SELECT ACCUMULATED_POINTS, SPENT_POINTS, POINTS_EXPIRATION_DATE,
                   (ACCUMULATED_POINTS - SPENT_POINTS) as CURRENT_BALANCE
            FROM LOYALTY_POINTS 
            WHERE USER_ID = ?;
        """
        cur.execute(sql_get, (user_id,))
        account = cur.fetchone()
        
        if not account:
            return None
            
        accumulated, spent, expiration_date, current_balance = account
        
        # Verifica se pontos expiraram
        if expiration_date and expiration_date < date.today() and current_balance > 0:
            # Expira pontos
            sql_expire = "UPDATE LOYALTY_POINTS SET SPENT_POINTS = ACCUMULATED_POINTS WHERE USER_ID = ?;"
            cur.execute(sql_expire, (user_id,))
            sql_add_history = "INSERT INTO LOYALTY_POINTS_HISTORY (USER_ID, POINTS, REASON) VALUES (?, ?, 'Pontos expirados por inatividade');"
            cur.execute(sql_add_history, (user_id, -current_balance))
            conn.commit()
            
            return {
                "accumulated_points": accumulated,
                "spent_points": accumulated,
                "current_balance": 0,
                "expiration_date": expiration_date.strftime('%Y-%m-%d'),
                "points_expired": True,
                "expired_points": current_balance
            }
        
        return {
            "accumulated_points": accumulated,
            "spent_points": spent,
            "current_balance": current_balance,
            "expiration_date": expiration_date.strftime('%Y-%m-%d') if expiration_date else None,
            "points_expired": False,
            "expired_points": 0
        }
    except fdb.Error as e:
        print(f"Erro ao buscar saldo detalhado: {e}")
        if conn: conn.rollback()
        return None
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

def get_loyalty_statistics():
    """Retorna estatísticas do sistema de fidelidade"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Inicializa valores padrão
        total_users_with_points = 0
        total_points_in_circulation = 0
        total_points_expired = 0
        average_points_per_user = 0
        
        # Verifica se as tabelas existem e busca dados
        try:
            # Total de usuários com pontos
            cur.execute("SELECT COUNT(*) FROM LOYALTY_POINTS WHERE ACCUMULATED_POINTS > SPENT_POINTS")
            result = cur.fetchone()
            if result and result[0] is not None:
                total_users_with_points = int(result[0])
            
            # Total de pontos em circulação
            cur.execute("SELECT SUM(ACCUMULATED_POINTS - SPENT_POINTS) FROM LOYALTY_POINTS WHERE ACCUMULATED_POINTS > SPENT_POINTS")
            result = cur.fetchone()
            if result and result[0] is not None:
                total_points_in_circulation = int(result[0])
            
            # Total de pontos expirados
            cur.execute("SELECT SUM(ABS(POINTS)) FROM LOYALTY_POINTS_HISTORY WHERE REASON = 'Pontos expirados por inatividade'")
            result = cur.fetchone()
            if result and result[0] is not None:
                total_points_expired = int(result[0])
            
            # Média de pontos por usuário
            if total_users_with_points > 0:
                average_points_per_user = round(total_points_in_circulation / total_users_with_points, 2)
            
        except fdb.Error as e:
            print(f"Erro ao executar queries de estatísticas: {e}")
            # Retorna dados vazios mas sem erro para não quebrar a API
            pass
        
        return {
            "total_users_with_points": total_users_with_points,
            "total_points_in_circulation": total_points_in_circulation,
            "total_points_expired": total_points_expired,
            "average_points_per_user": average_points_per_user
        }
        
    except fdb.Error as e:
        print(f"Erro de conexão com banco: {e}")
        return {
            "total_users_with_points": 0,
            "total_points_in_circulation": 0,
            "total_points_expired": 0,
            "average_points_per_user": 0,
            "error": f"Erro de banco de dados: {str(e)}"
        }
    except Exception as e:
        print(f"Erro inesperado: {e}")
        return {
            "total_users_with_points": 0,
            "total_points_in_circulation": 0,
            "total_points_expired": 0,
            "average_points_per_user": 0,
            "error": f"Erro inesperado: {str(e)}"
        }
    finally:
        if conn: conn.close()  
