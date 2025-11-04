import fdb  
from datetime import datetime, date, timedelta
from ..database import get_db_connection  

def get_financial_summary(period='this_month'):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        if period == 'this_month':  
            cur.execute("""
                SELECT 
                    SUM(CASE WHEN TYPE = 'revenue' THEN AMOUNT ELSE 0 END) as total_revenue,
                    SUM(CASE WHEN TYPE = 'expense' THEN AMOUNT ELSE 0 END) as total_expense
                FROM FINANCIAL_TRANSACTIONS 
                WHERE EXTRACT(MONTH FROM TRANSACTION_DATE) = EXTRACT(MONTH FROM CURRENT_DATE)
                AND EXTRACT(YEAR FROM TRANSACTION_DATE) = EXTRACT(YEAR FROM CURRENT_DATE)
            """)  
        else:  
            cur.execute("""
                SELECT 
                    SUM(CASE WHEN TYPE = 'revenue' THEN AMOUNT ELSE 0 END) as total_revenue,
                    SUM(CASE WHEN TYPE = 'expense' THEN AMOUNT ELSE 0 END) as total_expense
                FROM FINANCIAL_TRANSACTIONS 
                WHERE TRANSACTION_DATE >= CURRENT_DATE - INTERVAL '30 days'
            """)  
        row = cur.fetchone()  
        total_revenue = float(row[0]) if row and row[0] else 0.0  
        total_expense = float(row[1]) if row and row[1] else 0.0  
        profit_loss = total_revenue - total_expense  
        cur.execute("""
            SELECT 
                SUM(CASE WHEN TYPE = 'revenue' THEN AMOUNT ELSE -AMOUNT END) as current_balance
            FROM FINANCIAL_TRANSACTIONS
        """)  
        balance_result = cur.fetchone()  
        current_balance = float(balance_result[0]) if balance_result and balance_result[0] else 0.0  
        return {  
            "current_balance": current_balance,
            "total_revenue": total_revenue,
            "total_expense": total_expense,
            "profit_loss": profit_loss,
            "period": period
        }
    except fdb.Error as e:  
        print(f"Erro ao buscar resumo financeiro: {e}")  
        return {  
            "current_balance": 0.0,
            "total_revenue": 0.0,
            "total_expense": 0.0,
            "profit_loss": 0.0,
            "period": period
        }
    finally:  
        if conn: conn.close()  

def get_financial_transactions(filters=None):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        base_sql = """
            SELECT ft.ID, ft.DESCRIPTION, ft.AMOUNT, ft.TYPE, 
                   ft.TRANSACTION_DATE, ft.PAYMENT_METHOD, ft.NOTES,
                   u.FULL_NAME as created_by_name
            FROM FINANCIAL_TRANSACTIONS ft
            LEFT JOIN USERS u ON ft.CREATED_BY = u.ID
        """  
        conditions = []  
        params = []  
        if filters:  
            # OTIMIZAÇÃO: Converter datas para range queries (substitui DATE() por range para usar índices)
            if filters.get('start_date'):  
                start_date = filters['start_date']
                if isinstance(start_date, str):
                    try:
                        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                    except:
                        pass
                if isinstance(start_date, date) and not isinstance(start_date, datetime):
                    start_date = datetime.combine(start_date, datetime.min.time())
                conditions.append("ft.TRANSACTION_DATE >= ?")
                params.append(start_date)
            if filters.get('end_date'):  
                end_date = filters['end_date']
                if isinstance(end_date, str):
                    try:
                        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                    except:
                        pass
                if isinstance(end_date, date) and not isinstance(end_date, datetime):
                    end_date = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
                conditions.append("ft.TRANSACTION_DATE < ?")
                params.append(end_date)
            if filters.get('type'):  
                conditions.append("ft.TYPE = ?")
                params.append(filters['type'])
        if conditions:  
            base_sql += " WHERE " + " AND ".join(conditions)
        base_sql += " ORDER BY ft.TRANSACTION_DATE DESC"  
        cur.execute(base_sql, params)  
        transactions = []  
        for row in cur.fetchall():  
            transactions.append({  
                "id": row[0],
                "description": row[1],
                "amount": float(row[2]),
                "type": row[3],
                "transaction_date": row[4].isoformat() if row[4] else None,
                "payment_method": row[5],
                "notes": row[6],
                "created_by_name": row[7]
            })
        return transactions  
    except fdb.Error as e:  
        print(f"Erro ao buscar transações financeiras: {e}")  
        return []  
    finally:  
        if conn: conn.close()  

def create_financial_transaction(transaction_data, created_by_user_id):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        required_fields = ['description', 'amount', 'type']  
        for field in required_fields:  
            if not transaction_data.get(field):  
                return (False, f"INVALID_{field.upper()}", f"Campo {field} é obrigatório")  
        if transaction_data['type'] not in ['revenue', 'expense']:  
            return (False, "INVALID_TYPE", "Tipo deve ser 'revenue' ou 'expense'")  
        try:  
            amount = float(transaction_data['amount'])  
            if amount <= 0:  
                return (False, "INVALID_AMOUNT", "Valor deve ser maior que zero")  
        except (ValueError, TypeError):  
            return (False, "INVALID_AMOUNT", "Valor deve ser um número válido")  
        sql = """
            INSERT INTO FINANCIAL_TRANSACTIONS 
            (DESCRIPTION, AMOUNT, TYPE, PAYMENT_METHOD, NOTES, CREATED_BY)
            VALUES (?, ?, ?, ?, ?, ?)
            RETURNING ID, TRANSACTION_DATE
        """  
        cur.execute(sql, (
            transaction_data['description'],
            amount,
            transaction_data['type'],
            transaction_data.get('payment_method'),
            transaction_data.get('notes'),
            created_by_user_id
        ))  
        row = cur.fetchone()  
        transaction_id = row[0]  
        transaction_date = row[1]  
        conn.commit()  
        return (True, None, {  
            "id": transaction_id,
            "description": transaction_data['description'],
            "amount": amount,
            "type": transaction_data['type'],
            "transaction_date": transaction_date.isoformat() if transaction_date else None,
            "payment_method": transaction_data.get('payment_method'),
            "notes": transaction_data.get('notes')
        })
    except fdb.Error as e:  
        print(f"Erro ao criar transação financeira: {e}")  
        if conn: conn.rollback()  
        return (False, "DATABASE_ERROR", "Erro interno do servidor")  
    finally:  
        if conn: conn.close()  
