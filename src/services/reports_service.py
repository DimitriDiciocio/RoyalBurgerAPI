import fdb  # importa driver do Firebird
from datetime import datetime, date, timedelta  # importa classes de data
from ..database import get_db_connection  # importa função de conexão com o banco

def get_reports(report_type, period):  # gera relatórios por tipo e período
    conn = None  # inicializa conexão
    try:  # tenta gerar relatório
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        end_date = date.today()  # data final (hoje)
        if period == 'last_7_days':  # últimos 7 dias
            start_date = end_date - timedelta(days=7)  # calcula data inicial
        elif period == 'last_30_days':  # últimos 30 dias
            start_date = end_date - timedelta(days=30)  # calcula data inicial
        elif period == 'this_month':  # mês atual
            start_date = end_date.replace(day=1)  # primeiro dia do mês
        else:  # padrão
            start_date = end_date - timedelta(days=7)  # últimos 7 dias
        if report_type == 'sales':  # relatório de vendas
            return _get_sales_report(cur, start_date, end_date)  # chama função específica
        elif report_type == 'financial':  # relatório financeiro
            return _get_financial_report(cur, start_date, end_date)  # chama função específica
        elif report_type == 'performance':  # relatório de performance
            return _get_performance_report(cur, start_date, end_date)  # chama função específica
        elif report_type == 'employees':  # relatório de funcionários
            return _get_employees_report(cur, start_date, end_date)  # chama função específica
        else:  # tipo inválido
            return {"error": "Tipo de relatório inválido"}  # retorna erro
    except fdb.Error as e:  # captura erros
        print(f"Erro ao gerar relatório: {e}")  # exibe erro
        return {"error": "Erro interno do servidor"}  # retorna erro genérico
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão


def _get_sales_report(cur, start_date, end_date):  # relatório de vendas por data e hora
    cur.execute("""
        SELECT DATE(CREATED_AT) as date, 
               COUNT(*) as total_orders,
               SUM(TOTAL_AMOUNT) as total_revenue
        FROM ORDERS 
        WHERE DATE(CREATED_AT) BETWEEN ? AND ?
        GROUP BY DATE(CREATED_AT)
        ORDER BY date
    """, (start_date, end_date))  # vendas por data
    sales_by_date = []  # lista de vendas por data
    for row in cur.fetchall():  # itera resultados
        sales_by_date.append({  # monta dicionário da venda
            "date": row[0].isoformat(),
            "total_orders": row[1],
            "total_revenue": float(row[2]) if row[2] else 0.0
        })
    cur.execute("""
        SELECT EXTRACT(HOUR FROM CREATED_AT) as hour,
               COUNT(*) as total_orders
        FROM ORDERS 
        WHERE DATE(CREATED_AT) BETWEEN ? AND ?
        GROUP BY EXTRACT(HOUR FROM CREATED_AT)
        ORDER BY hour
    """, (start_date, end_date))  # vendas por hora
    sales_by_hour = []  # lista de vendas por hora
    for row in cur.fetchall():  # itera resultados
        sales_by_hour.append({  # monta dicionário da venda por hora
            "hour": f"{int(row[0]):02d}:00",
            "total_orders": row[1]
        })
    return {  # retorna relatório de vendas
        "type": "sales",
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        },
        "sales_by_date": sales_by_date,
        "sales_by_hour": sales_by_hour
    }


def _get_financial_report(cur, start_date, end_date):  # relatório financeiro
    cur.execute("""
        SELECT DATE(TRANSACTION_DATE) as date,
               SUM(CASE WHEN TYPE = 'revenue' THEN AMOUNT ELSE 0 END) as revenue,
               SUM(CASE WHEN TYPE = 'expense' THEN AMOUNT ELSE 0 END) as expense
        FROM FINANCIAL_TRANSACTIONS 
        WHERE DATE(TRANSACTION_DATE) BETWEEN ? AND ?
        GROUP BY DATE(TRANSACTION_DATE)
        ORDER BY date
    """, (start_date, end_date))  # receitas e despesas por data
    financial_by_date = []  # lista financeira por data
    for row in cur.fetchall():  # itera resultados
        financial_by_date.append({  # monta dicionário financeiro
            "date": row[0].isoformat(),
            "revenue": float(row[1]) if row[1] else 0.0,
            "expense": float(row[2]) if row[2] else 0.0,
            "profit": float(row[1]) - float(row[2]) if row[1] and row[2] else 0.0
        })
    cur.execute("""
        SELECT SUM(CASE WHEN TYPE = 'revenue' THEN AMOUNT ELSE 0 END) as total_revenue,
               SUM(CASE WHEN TYPE = 'expense' THEN AMOUNT ELSE 0 END) as total_expense
        FROM FINANCIAL_TRANSACTIONS 
        WHERE DATE(TRANSACTION_DATE) BETWEEN ? AND ?
    """, (start_date, end_date))  # resumo total
    summary_row = cur.fetchone()  # obtém linha de resumo
    total_revenue = float(summary_row[0]) if summary_row[0] else 0.0  # receita total
    total_expense = float(summary_row[1]) if summary_row[1] else 0.0  # despesa total
    return {  # retorna relatório financeiro
        "type": "financial",
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        },
        "financial_by_date": financial_by_date,
        "summary": {
            "total_revenue": total_revenue,
            "total_expense": total_expense,
            "total_profit": total_revenue - total_expense
        }
    }


def _get_performance_report(cur, start_date, end_date):  # relatório de performance operacional
    cur.execute("""
        SELECT DATE(CREATED_AT) as date,
               AVG(EXTRACT(EPOCH FROM (UPDATED_AT - CREATED_AT))/60) as avg_prep_time
        FROM ORDERS 
        WHERE DATE(CREATED_AT) BETWEEN ? AND ?
        AND STATUS = 'delivered' AND UPDATED_AT IS NOT NULL
        GROUP BY DATE(CREATED_AT)
        ORDER BY date
    """, (start_date, end_date))  # tempo médio de preparo por dia
    performance_by_date = []  # lista de performance por data
    for row in cur.fetchall():  # itera resultados
        performance_by_date.append({  # monta dicionário de performance
            "date": row[0].isoformat(),
            "avg_prep_time": round(float(row[1]), 1) if row[1] else 0.0
        })
    cur.execute("""
        SELECT COUNT(*) as total_orders,
               SUM(CASE WHEN STATUS = 'cancelled' THEN 1 ELSE 0 END) as cancelled_orders
        FROM ORDERS 
        WHERE DATE(CREATED_AT) BETWEEN ? AND ?
    """, (start_date, end_date))  # taxa de cancelamento
    cancel_row = cur.fetchone()  # obtém linha de cancelamento
    total_orders = cancel_row[0] if cancel_row[0] else 0  # total de pedidos
    cancelled_orders = cancel_row[1] if cancel_row[1] else 0  # pedidos cancelados
    cancellation_rate = (cancelled_orders / total_orders * 100) if total_orders > 0 else 0  # taxa de cancelamento
    return {  # retorna relatório de performance
        "type": "performance",
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        },
        "performance_by_date": performance_by_date,
        "cancellation_rate": round(cancellation_rate, 2)
    }


def _get_employees_report(cur, start_date, end_date):  # relatório de performance dos funcionários
    cur.execute("""
        SELECT u.FULL_NAME, u.ID,
               COUNT(o.ID) as total_orders,
               SUM(o.TOTAL_AMOUNT) as total_revenue,
               AVG(EXTRACT(EPOCH FROM (o.UPDATED_AT - o.CREATED_AT))/60) as avg_prep_time
        FROM USERS u
        LEFT JOIN ORDERS o ON u.ID = o.ATTENDANT_ID 
        WHERE u.ROLE = 'attendant' 
        AND (o.CREATED_AT IS NULL OR DATE(o.CREATED_AT) BETWEEN ? AND ?)
        GROUP BY u.ID, u.FULL_NAME
        ORDER BY total_orders DESC
    """, (start_date, end_date))  # performance por atendente
    employees_performance = []  # lista de performance dos funcionários
    for row in cur.fetchall():  # itera resultados
        employees_performance.append({  # monta dicionário do funcionário
            "employee_id": row[1],
            "name": row[2],
            "total_orders": row[3] if row[3] else 0,
            "total_revenue": float(row[4]) if row[4] else 0.0,
            "avg_prep_time": round(float(row[5]), 1) if row[5] else 0.0
        })
    return {  # retorna relatório de funcionários
        "type": "employees",
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        },
        "employees_performance": employees_performance
    }
