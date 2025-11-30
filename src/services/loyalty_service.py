import fdb  
from datetime import date, timedelta
from ..database import get_db_connection
from . import settings_service

def _get_loyalty_settings():
    """Retorna configurações de pontos do sistema"""
    settings = settings_service.get_all_settings()
    
    # Proteção contra settings None
    if not settings:
        settings = {}
    
    # Taxa para GANHAR pontos (valor de 1 ponto em reais)
    gain_rate = float(settings.get('taxa_conversao_ganho_clube', 0.01) or 0.01)
    if gain_rate <= 0:
        gain_rate = 0.01  # Fallback seguro
    
    # Taxa para RESGATAR pontos (valor de 1 ponto em reais ao resgatar)
    redemption_rate = float(settings.get('taxa_conversao_resgate_clube', 0.01) or 0.01)
    if redemption_rate <= 0:
        redemption_rate = 0.01  # Fallback seguro
    
    return {
        'gain_rate': gain_rate,  # Taxa de ganho de pontos
        'redemption_rate': redemption_rate,  # Taxa de resgate de pontos
        'expiration_days': int(settings.get('taxa_expiracao_pontos_clube', 60) or 60),
        'welcome_points': 100  # Pontos de boas-vindas (mantido fixo ou pode configurar)
    }

def _validate_points(points):
    """Valida se pontos é um valor válido"""
    if not isinstance(points, (int, float)) or points < 0:
        raise ValueError("Pontos devem ser um número não negativo")

def _calculate_expiration_date(expiration_days):
    """Calcula data de expiração a partir de hoje + dias (compatível com Firebird)"""
    return date.today() + timedelta(days=expiration_days)

def _get_current_balance_from_cursor(user_id, cur):
    """Busca saldo atual usando cursor existente (para uso dentro de transações)"""
    cur.execute("""
        SELECT ACCUMULATED_POINTS, SPENT_POINTS 
        FROM LOYALTY_POINTS 
        WHERE USER_ID = ?
    """, (user_id,))
    account = cur.fetchone()
    if not account:
        return 0
    accumulated, spent = account
    return max(0, accumulated - spent)

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
    except (fdb.Error, ValueError, TypeError) as e:
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
    """
    Calcula e credita pontos baseado no valor da compra.
    
    Nota: Esta função calcula pontos sobre o total final do pedido após descontos.
    Use earn_points_for_order_with_details para cálculo mais preciso com subtotal e desconto proporcional.
    """
    try:
        # Valida que total_amount é positivo antes de calcular pontos
        if not isinstance(total_amount, (int, float)) or total_amount < 0:
            raise ValueError("total_amount deve ser um número não negativo")
        
        create_loyalty_account_if_not_exists(user_id, cur)  
        
        # Obter taxas de conversão das configurações
        loyalty_config = _get_loyalty_settings()
        gain_rate = loyalty_config['gain_rate']  # Taxa para GANHAR pontos
        expiration_days = loyalty_config['expiration_days']
        
        # Calcular pontos usando taxa configurável
        # gain_rate é o valor de 1 ponto em reais (ex: 0.01 = 1 ponto vale R$ 0,01)
        points_to_earn = int(total_amount / gain_rate)
        
        # Calcula data de expiração (Firebird não suporta CURRENT_DATE + ?)
        expiration_date = _calculate_expiration_date(expiration_days)
        
        sql_update_account = """
            UPDATE LOYALTY_POINTS
            SET 
                ACCUMULATED_POINTS = ACCUMULATED_POINTS + ?,
                POINTS_EXPIRATION_DATE = ?
            WHERE USER_ID = ?;
        """  
        cur.execute(sql_update_account, (points_to_earn, expiration_date, user_id))  
        
        sql_add_history = "INSERT INTO LOYALTY_POINTS_HISTORY (USER_ID, ORDER_ID, POINTS, REASON) VALUES (?, ?, ?, ?);"  
        reason = f"Pontos ganhos no pedido #{order_id}"
        cur.execute(sql_add_history, (user_id, order_id, points_to_earn, reason))  
        print(f"{points_to_earn} pontos ganhos e validade renovada para o usuário {user_id}.")  
    except (fdb.Error, ValueError, TypeError) as e:
        print(f"Erro ao ganhar pontos: {e}")
        raise

def earn_points_for_order_with_details(user_id, order_id, subtotal, discount_amount, delivery_fee, cur):
    """
    Calcula e credita pontos de forma mais precisa, considerando subtotal e desconto proporcional.
    
    Args:
        user_id: ID do usuário
        order_id: ID do pedido
        subtotal: Valor dos produtos (sem taxa de entrega)
        discount_amount: Valor do desconto aplicado (de pontos)
        delivery_fee: Taxa de entrega (0 se pickup)
        cur: Cursor do banco de dados
    
    Returns:
        int: Pontos ganhos (0 se já foram creditados anteriormente)
    """
    try:
        # CORREÇÃO: Verificar se já existem pontos creditados para este pedido
        # Isso previne crédito duplicado se o status mudar múltiplas vezes para 'delivered'
        cur.execute("""
            SELECT COUNT(*) FROM LOYALTY_POINTS_HISTORY 
            WHERE ORDER_ID = ? AND POINTS > 0
        """, (order_id,))
        existing_points_count = cur.fetchone()[0]
        
        if existing_points_count > 0:
            print(f"Pedido #{order_id}: Pontos já foram creditados anteriormente. Pulando crédito para evitar duplicação.")
            return 0
        
        create_loyalty_account_if_not_exists(user_id, cur)
        
        # Obter taxas de conversão das configurações
        loyalty_config = _get_loyalty_settings()
        gain_rate = loyalty_config['gain_rate']  # Taxa para GANHAR pontos
        expiration_days = loyalty_config['expiration_days']
        
        # Calcula desconto proporcional ao subtotal
        # Desconto distribuído proporcionalmente entre subtotal e taxa de entrega
        total_before_discount = subtotal + delivery_fee
        
        if discount_amount > 0 and total_before_discount > 0:
            # Proporção do subtotal no total
            subtotal_ratio = subtotal / total_before_discount
            # Desconto proporcional aplicado ao subtotal
            discount_proportional_subtotal = discount_amount * subtotal_ratio
        else:
            discount_proportional_subtotal = 0
        
        # Base para cálculo de pontos (subtotal após desconto proporcional)
        base_for_points = max(0, subtotal - discount_proportional_subtotal)
        
        # Calcular pontos ganhos
        points_to_earn = int(base_for_points / gain_rate)
        
        # Não creditar pontos se for 0 ou negativo
        if points_to_earn <= 0:
            print(f"Pedido #{order_id}: Nenhum ponto a ser creditado (base: R$ {base_for_points:.2f})")
            return 0
        
        # Calcula data de expiração (Firebird não suporta CURRENT_DATE + ?)
        expiration_date = _calculate_expiration_date(expiration_days)
        
        # Atualiza saldo de pontos
        sql_update_account = """
            UPDATE LOYALTY_POINTS
            SET 
                ACCUMULATED_POINTS = ACCUMULATED_POINTS + ?,
                POINTS_EXPIRATION_DATE = ?
            WHERE USER_ID = ?;
        """  
        cur.execute(sql_update_account, (points_to_earn, expiration_date, user_id))  
        
        # Registra no histórico
        sql_add_history = "INSERT INTO LOYALTY_POINTS_HISTORY (USER_ID, ORDER_ID, POINTS, REASON) VALUES (?, ?, ?, ?);"
        reason = f"Pontos ganhos no pedido #{order_id}"
        cur.execute(sql_add_history, (user_id, order_id, points_to_earn, reason))
        
        print(f"Pedido #{order_id}: {points_to_earn} pontos creditados para usuário {user_id}")
        print(f"  Detalhes: Subtotal R$ {subtotal:.2f} - Desconto proporcional R$ {discount_proportional_subtotal:.2f} = Base R$ {base_for_points:.2f}")
        
        return points_to_earn
        
    except (fdb.Error, ValueError, TypeError) as e:
        print(f"Erro ao ganhar pontos: {e}")
        raise  

def add_welcome_points(user_id, cur):
    """Adiciona pontos de boas-vindas configuráveis para novos clientes"""
    try:
        create_loyalty_account_if_not_exists(user_id, cur)
        
        # Obter configurações
        loyalty_config = _get_loyalty_settings()
        welcome_points = loyalty_config['welcome_points']
        expiration_days = loyalty_config['expiration_days']
        
        # Calcula data de expiração (Firebird não suporta CURRENT_DATE + ?)
        expiration_date = _calculate_expiration_date(expiration_days)
        
        sql_update_account = """
            UPDATE LOYALTY_POINTS
            SET 
                ACCUMULATED_POINTS = ACCUMULATED_POINTS + ?,
                POINTS_EXPIRATION_DATE = ?
            WHERE USER_ID = ?;
        """
        cur.execute(sql_update_account, (welcome_points, expiration_date, user_id))
        
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
            # Corrigido: após expiração, spent_points deve ser igual a accumulated
            return {"accumulated_points": accumulated, "spent_points": accumulated, "current_balance": 0}  
        
        current_balance = accumulated - spent  
        return {"accumulated_points": accumulated, "spent_points": spent, "current_balance": current_balance}  
    except fdb.Error as e:  
        print(f"Erro ao buscar saldo de pontos: {e}")  
        if conn:
            conn.rollback()  
        return None  
    finally:  
        if conn:
            conn.close()

def redeem_points_for_discount(user_id, points_to_redeem, order_id, cur):  
    try:
        _validate_points(points_to_redeem)
        
        # Usa cursor existente para evitar abertura de nova conexão dentro de transação
        current_balance = _get_current_balance_from_cursor(user_id, cur)
        
        if current_balance < points_to_redeem:  
            raise ValueError(f"Saldo de pontos insuficiente. Saldo atual: {current_balance}, Pontos para resgate: {points_to_redeem}")  
        
        sql_update_account = "UPDATE LOYALTY_POINTS SET SPENT_POINTS = SPENT_POINTS + ? WHERE USER_ID = ?;"  
        cur.execute(sql_update_account, (points_to_redeem, user_id))  
        
        sql_add_history = "INSERT INTO LOYALTY_POINTS_HISTORY (USER_ID, ORDER_ID, POINTS, REASON) VALUES (?, ?, ?, ?);"  
        reason = f"Resgate de pontos no pedido #{order_id}"
        cur.execute(sql_add_history, (user_id, order_id, -points_to_redeem, reason))  
        
        # Obter taxa de resgate das configurações
        loyalty_config = _get_loyalty_settings()
        redemption_rate = loyalty_config['redemption_rate']  # Taxa para RESGATAR pontos
        
        # Calcular desconto usando taxa configurável
        # redemption_rate é o valor de 1 ponto em reais (ex: 0.01 = 1 ponto vale R$ 0,01)
        discount_amount = points_to_redeem * redemption_rate
        print(f"{points_to_redeem} pontos resgatados pelo usuário {user_id} por R${discount_amount:.2f} de desconto.")  
        return discount_amount  
    except (fdb.Error, ValueError, TypeError) as e:
        print(f"Erro ao resgatar pontos: {e}")
        raise  

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
        if conn:
            conn.close()

def add_points_manually(user_id, points, reason, order_id=None):
    """Adiciona pontos manualmente (para admin)"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Cria conta se não existir
        create_loyalty_account_if_not_exists(user_id, cur)
        
        # Obter configurações de expiração das settings
        loyalty_config = _get_loyalty_settings()
        expiration_days = loyalty_config['expiration_days']
        
        # Calcula data de expiração usando o valor das settings
        expiration_date = _calculate_expiration_date(expiration_days)
        
        # Atualiza pontos acumulados
        sql_update = """
            UPDATE LOYALTY_POINTS
            SET 
                ACCUMULATED_POINTS = ACCUMULATED_POINTS + ?,
                POINTS_EXPIRATION_DATE = ?
            WHERE USER_ID = ?;
        """
        cur.execute(sql_update, (points, expiration_date, user_id))
        
        # Adiciona ao histórico
        sql_history = "INSERT INTO LOYALTY_POINTS_HISTORY (USER_ID, ORDER_ID, POINTS, REASON) VALUES (?, ?, ?, ?);"
        cur.execute(sql_history, (user_id, order_id, points, reason))
        
        conn.commit()
        print(f"Adicionados {points} pontos para o usuário {user_id}: {reason} (expira em {expiration_days} dias)")
        return True
    except fdb.Error as e:
        print(f"Erro ao adicionar pontos manualmente: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def spend_points_manually(user_id, points, reason, order_id=None):
    """Gasta pontos manualmente (para admin)"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Cria conta se não existir antes de verificar saldo
        create_loyalty_account_if_not_exists(user_id, cur)
        
        # Verifica saldo usando cursor (evita nova conexão)
        current_balance = _get_current_balance_from_cursor(user_id, cur)
        
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
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

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
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()  

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
        if conn:
            conn.rollback()  
        return -1  
    finally:  
        if conn:
            conn.close()

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
        if conn:
            conn.close()  
