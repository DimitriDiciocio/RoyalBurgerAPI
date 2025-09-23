import fdb  # importa driver do Firebird
from datetime import datetime, date  # importa classes de data
from ..database import get_db_connection  # importa função de conexão com o banco

def get_financial_summary(period='this_month'):  # retorna KPIs financeiros do período
    conn = None  # inicializa conexão
    try:  # tenta buscar dados
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        if period == 'this_month':  # período: mês atual
            cur.execute("""
                SELECT 
                    SUM(CASE WHEN TYPE = 'revenue' THEN AMOUNT ELSE 0 END) as total_revenue,
                    SUM(CASE WHEN TYPE = 'expense' THEN AMOUNT ELSE 0 END) as total_expense
                FROM FINANCIAL_TRANSACTIONS 
                WHERE EXTRACT(MONTH FROM TRANSACTION_DATE) = EXTRACT(MONTH FROM CURRENT_DATE)
                AND EXTRACT(YEAR FROM TRANSACTION_DATE) = EXTRACT(YEAR FROM CURRENT_DATE)
            """)  # soma receitas e despesas do mês
        else:  # outros períodos
            cur.execute("""
                SELECT 
                    SUM(CASE WHEN TYPE = 'revenue' THEN AMOUNT ELSE 0 END) as total_revenue,
                    SUM(CASE WHEN TYPE = 'expense' THEN AMOUNT ELSE 0 END) as total_expense
                FROM FINANCIAL_TRANSACTIONS 
                WHERE TRANSACTION_DATE >= CURRENT_DATE - INTERVAL '30 days'
            """)  # usa últimos 30 dias
        row = cur.fetchone()  # obtém linha
        total_revenue = float(row[0]) if row and row[0] else 0.0  # receita total
        total_expense = float(row[1]) if row and row[1] else 0.0  # despesa total
        profit_loss = total_revenue - total_expense  # lucro/prejuízo
        cur.execute("""
            SELECT 
                SUM(CASE WHEN TYPE = 'revenue' THEN AMOUNT ELSE -AMOUNT END) as current_balance
            FROM FINANCIAL_TRANSACTIONS
        """)  # saldo atual
        balance_result = cur.fetchone()  # obtém saldo
        current_balance = float(balance_result[0]) if balance_result and balance_result[0] else 0.0  # saldo numérico
        return {  # retorna KPIs
            "current_balance": current_balance,
            "total_revenue": total_revenue,
            "total_expense": total_expense,
            "profit_loss": profit_loss,
            "period": period
        }
    except fdb.Error as e:  # captura erros
        print(f"Erro ao buscar resumo financeiro: {e}")  # exibe erro
        return {  # retorna estrutura padrão em erro
            "current_balance": 0.0,
            "total_revenue": 0.0,
            "total_expense": 0.0,
            "profit_loss": 0.0,
            "period": period
        }
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def get_financial_transactions(filters=None):  # lista transações com filtros
    conn = None  # inicializa conexão
    try:  # tenta buscar transações
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        base_sql = """
            SELECT ft.ID, ft.DESCRIPTION, ft.AMOUNT, ft.TYPE, 
                   ft.TRANSACTION_DATE, ft.PAYMENT_METHOD, ft.NOTES,
                   u.FULL_NAME as created_by_name
            FROM FINANCIAL_TRANSACTIONS ft
            LEFT JOIN USERS u ON ft.CREATED_BY = u.ID
        """  # SQL base de listagem
        conditions = []  # condições dinâmicas
        params = []  # parâmetros da query
        if filters:  # aplica filtros se existirem
            if filters.get('start_date'):  # filtro data inicial
                conditions.append("DATE(ft.TRANSACTION_DATE) >= ?")
                params.append(filters['start_date'])
            if filters.get('end_date'):  # filtro data final
                conditions.append("DATE(ft.TRANSACTION_DATE) <= ?")
                params.append(filters['end_date'])
            if filters.get('type'):  # filtro por tipo
                conditions.append("ft.TYPE = ?")
                params.append(filters['type'])
        if conditions:  # concatena WHERE se houver condições
            base_sql += " WHERE " + " AND ".join(conditions)
        base_sql += " ORDER BY ft.TRANSACTION_DATE DESC"  # ordena por data desc
        cur.execute(base_sql, params)  # executa query com parâmetros
        transactions = []  # lista de transações
        for row in cur.fetchall():  # itera resultados
            transactions.append({  # monta dicionário da transação
                "id": row[0],
                "description": row[1],
                "amount": float(row[2]),
                "type": row[3],
                "transaction_date": row[4].isoformat() if row[4] else None,
                "payment_method": row[5],
                "notes": row[6],
                "created_by_name": row[7]
            })
        return transactions  # retorna lista
    except fdb.Error as e:  # captura erros
        print(f"Erro ao buscar transações financeiras: {e}")  # exibe erro
        return []  # retorna vazio em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def create_financial_transaction(transaction_data, created_by_user_id):  # cria transação financeira
    conn = None  # inicializa conexão
    try:  # tenta criar transação
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        required_fields = ['description', 'amount', 'type']  # campos obrigatórios
        for field in required_fields:  # valida campos
            if not transaction_data.get(field):  # campo ausente
                return (False, f"INVALID_{field.upper()}", f"Campo {field} é obrigatório")  # retorna erro
        if transaction_data['type'] not in ['revenue', 'expense']:  # valida tipo
            return (False, "INVALID_TYPE", "Tipo deve ser 'revenue' ou 'expense'")  # retorna erro
        try:  # valida valor numérico e positivo
            amount = float(transaction_data['amount'])  # converte para float
            if amount <= 0:  # verifica positivo
                return (False, "INVALID_AMOUNT", "Valor deve ser maior que zero")  # retorna erro
        except (ValueError, TypeError):  # conversão falhou
            return (False, "INVALID_AMOUNT", "Valor deve ser um número válido")  # retorna erro
        sql = """
            INSERT INTO FINANCIAL_TRANSACTIONS 
            (DESCRIPTION, AMOUNT, TYPE, PAYMENT_METHOD, NOTES, CREATED_BY)
            VALUES (?, ?, ?, ?, ?, ?)
            RETURNING ID, TRANSACTION_DATE
        """  # SQL de inserção
        cur.execute(sql, (
            transaction_data['description'],
            amount,
            transaction_data['type'],
            transaction_data.get('payment_method'),
            transaction_data.get('notes'),
            created_by_user_id
        ))  # executa inserção
        row = cur.fetchone()  # obtém retorno
        transaction_id = row[0]  # ID da transação
        transaction_date = row[1]  # data da transação
        conn.commit()  # confirma transação
        return (True, None, {  # retorna sucesso
            "id": transaction_id,
            "description": transaction_data['description'],
            "amount": amount,
            "type": transaction_data['type'],
            "transaction_date": transaction_date.isoformat() if transaction_date else None,
            "payment_method": transaction_data.get('payment_method'),
            "notes": transaction_data.get('notes')
        })
    except fdb.Error as e:  # captura erros
        print(f"Erro ao criar transação financeira: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return (False, "DATABASE_ERROR", "Erro interno do servidor")  # retorna erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão
