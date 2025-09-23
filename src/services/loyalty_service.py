import fdb  # importa driver do Firebird
from datetime import date  # importa classe de data
from ..database import get_db_connection  # importa função de conexão com o banco

def create_loyalty_account_if_not_exists(user_id, cur):  # garante conta de fidelidade
    try:  # tenta executar MERGE
        sql = """
            MERGE INTO LOYALTY_POINTS lp
            USING (SELECT ? AS USER_ID FROM RDB$DATABASE) AS new_data
            ON (lp.USER_ID = new_data.USER_ID)
            WHEN NOT MATCHED THEN
                INSERT (USER_ID, ACCUMULATED_POINTS, SPENT_POINTS) 
                VALUES (new_data.USER_ID, 0, 0);
        """  # cria conta se não existir
        cur.execute(sql, (user_id,))  # executa MERGE
        return True  # sucesso
    except fdb.Error as e:  # captura erros
        print(f"Erro ao criar conta de fidelidade (MERGE): {e}")  # exibe erro
        raise e  # propaga erro para controle transacional

def earn_points_for_order(user_id, order_id, total_amount, cur):  # adiciona pontos por pedido
    create_loyalty_account_if_not_exists(user_id, cur)  # garante conta criada
    points_to_earn = int(total_amount)  # converte valor em pontos (1 ponto por real)
    sql_update_account = """
        UPDATE LOYALTY_POINTS
        SET 
            ACCUMULATED_POINTS = ACCUMULATED_POINTS + ?,
            POINTS_EXPIRATION_DATE = CURRENT_DATE + 60
        WHERE USER_ID = ?;
    """  # atualiza saldo e renova expiração
    cur.execute(sql_update_account, (points_to_earn, user_id))  # executa update
    sql_add_history = "INSERT INTO LOYALTY_POINTS_HISTORY (USER_ID, ORDER_ID, POINTS, REASON) VALUES (?, ?, ?, ?);"  # insere histórico
    reason = f"Pontos ganhos no pedido #{order_id}"  # motivo do crédito
    cur.execute(sql_add_history, (user_id, order_id, points_to_earn, reason))  # registra histórico
    print(f"{points_to_earn} pontos ganhos e validade renovada para o usuário {user_id}.")  # log informativo

def get_loyalty_balance(user_id):  # busca saldo de pontos
    conn = None  # inicializa conexão
    try:  # tenta buscar saldo
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        create_loyalty_account_if_not_exists(user_id, cur)  # garante conta criada
        conn.commit()  # confirma criação
        sql_get = "SELECT ACCUMULATED_POINTS, SPENT_POINTS, POINTS_EXPIRATION_DATE FROM LOYALTY_POINTS WHERE USER_ID = ?;"  # busca conta
        cur.execute(sql_get, (user_id,))  # executa query
        account = cur.fetchone()  # obtém dados
        accumulated, spent, expiration_date = account or (0, 0, None)  # valores padrão
        current_balance = accumulated - spent  # saldo atual
        if expiration_date and expiration_date < date.today() and current_balance > 0:  # expiração de pontos
            points_to_expire = current_balance  # pontos a expirar
            sql_expire = "UPDATE LOYALTY_POINTS SET SPENT_POINTS = ACCUMULATED_POINTS WHERE USER_ID = ?;"  # zera saldo
            cur.execute(sql_expire, (user_id,))  # executa update
            sql_add_history = "INSERT INTO LOYALTY_POINTS_HISTORY (USER_ID, POINTS, REASON) VALUES (?, ?, 'Pontos expirados por inatividade');"  # histórico
            cur.execute(sql_add_history, (user_id, -points_to_expire))  # registra expiração
            conn.commit()  # confirma
            return {"accumulated_points": accumulated, "spent_points": accumulated, "current_balance": 0}  # retorna zerado
        return {"accumulated_points": accumulated, "spent_points": spent, "current_balance": current_balance}  # retorno normal
    except fdb.Error as e:  # captura erros
        print(f"Erro ao buscar saldo de pontos: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return None  # retorna None em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def redeem_points_for_discount(user_id, points_to_redeem, order_id, cur):  # resgata pontos por desconto
    balance_data = get_loyalty_balance(user_id)  # busca saldo atual
    current_balance = balance_data.get("current_balance", 0)  # extrai saldo
    if current_balance < points_to_redeem:  # saldo insuficiente
        raise ValueError(
            f"Saldo de pontos insuficiente. Saldo atual: {current_balance}, Pontos para resgate: {points_to_redeem}")  # lança erro
    sql_update_account = "UPDATE LOYALTY_POINTS SET SPENT_POINTS = SPENT_POINTS + ? WHERE USER_ID = ?;"  # debita pontos
    cur.execute(sql_update_account, (points_to_redeem, user_id))  # executa débito
    sql_add_history = "INSERT INTO LOYALTY_POINTS_HISTORY (USER_ID, ORDER_ID, POINTS, REASON) VALUES (?, ?, ?, ?);"  # histórico
    reason = f"Resgate de pontos no pedido #{order_id}"  # motivo do débito
    cur.execute(sql_add_history, (user_id, order_id, -points_to_redeem, reason))  # registra histórico
    discount_amount = points_to_redeem / 10.0  # conversão pontos->desconto
    print(f"{points_to_redeem} pontos resgatados pelo usuário {user_id} por R${discount_amount:.2f} de desconto.")  # log
    return discount_amount  # retorna valor do desconto

def get_loyalty_history(user_id):  # busca histórico de pontos
    conn = None  # inicializa conexão
    try:  # tenta buscar histórico
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = "SELECT POINTS, REASON, EARNED_AT FROM LOYALTY_POINTS_HISTORY WHERE USER_ID = ? ORDER BY EARNED_AT DESC;"  # query
        cur.execute(sql, (user_id,))  # executa
        history = [{"points": row[0], "reason": row[1], "date": row[2].strftime('%Y-%m-%d %H:%M:%S')} for row in cur.fetchall()]  # monta lista
        return history  # retorna histórico
    except fdb.Error as e:  # captura erros
        print(f"Erro ao buscar histórico de pontos: {e}")  # exibe erro
        return []  # retorna vazio em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def expire_inactive_accounts():  # expira contas inativas (cron)
    conn = None  # inicializa conexão
    try:  # tenta expirar contas
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql_find_expired = """
            SELECT USER_ID, ACCUMULATED_POINTS, SPENT_POINTS 
            FROM LOYALTY_POINTS 
            WHERE POINTS_EXPIRATION_DATE < CURRENT_DATE 
            AND ACCUMULATED_POINTS > SPENT_POINTS;
        """  # busca contas expiradas com saldo
        cur.execute(sql_find_expired)  # executa busca
        expired_accounts = cur.fetchall()  # obtém resultados
        for user_id, accumulated, spent in expired_accounts:  # itera contas
            points_to_expire = accumulated - spent  # calcula pontos a expirar
            sql_expire = "UPDATE LOYALTY_POINTS SET SPENT_POINTS = ACCUMULATED_POINTS WHERE USER_ID = ?;"  # zera saldo
            cur.execute(sql_expire, (user_id,))  # executa update
            sql_add_history = "INSERT INTO LOYALTY_POINTS_HISTORY (USER_ID, POINTS, REASON) VALUES (?, ?, 'Pontos expirados por inatividade');"  # histórico
            cur.execute(sql_add_history, (user_id, -points_to_expire))  # registra histórico
            print(f"Expirado saldo de {points_to_expire} pontos para o usuário {user_id}")  # log
        conn.commit()  # confirma transações
        return len(expired_accounts)  # retorna quantidade de contas expiradas
    except fdb.Error as e:  # captura erros
        print(f"Erro durante o processo de expiração de pontos: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transações
        return -1  # retorna -1 em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão