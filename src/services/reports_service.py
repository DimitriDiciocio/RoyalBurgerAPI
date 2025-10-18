import fdb
from datetime import datetime, date, timedelta
from ..database import get_db_connection
from .pdf_report_service import generate_pdf_report

def get_reports(report_type, period):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        end_date = date.today()
        if period == 'last_7_days':
            start_date = end_date - timedelta(days=7)
        elif period == 'last_30_days':
            start_date = end_date - timedelta(days=30)
        elif period == 'this_month':
            start_date = end_date.replace(day=1)
        else:
            start_date = end_date - timedelta(days=7)
        if report_type == 'sales':
            return _get_sales_report(cur, start_date, end_date)
        elif report_type == 'financial':
            return _get_financial_report(cur, start_date, end_date)
        elif report_type == 'performance':
            return _get_performance_report(cur, start_date, end_date)
        elif report_type == 'employees':
            return _get_employees_report(cur, start_date, end_date)
        else:
            return {"error": "Tipo de relatório inválido"}
    except fdb.Error as e:
        print(f"Erro ao gerar relatório: {e}")
        return {"error": "Erro interno do servidor"}
    finally:
        if conn: conn.close()


def _get_sales_report(cur, start_date, end_date):
    cur.execute("""
        SELECT DATE(CREATED_AT) as date, 
               COUNT(*) as total_orders,
               SUM(TOTAL_AMOUNT) as total_revenue
        FROM ORDERS 
        WHERE DATE(CREATED_AT) BETWEEN ? AND ?
        GROUP BY DATE(CREATED_AT)
        ORDER BY date
    """, (start_date, end_date))
    sales_by_date = []
    for row in cur.fetchall():
        sales_by_date.append({
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
    """, (start_date, end_date))
    sales_by_hour = []
    for row in cur.fetchall():
        sales_by_hour.append({
            "hour": f"{int(row[0]):02d}:00",
            "total_orders": row[1]
        })
    return {
        "type": "sales",
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        },
        "sales_by_date": sales_by_date,
        "sales_by_hour": sales_by_hour
    }


def _get_financial_report(cur, start_date, end_date):  
    cur.execute("""
        SELECT DATE(TRANSACTION_DATE) as date,
               SUM(CASE WHEN TYPE = 'revenue' THEN AMOUNT ELSE 0 END) as revenue,
               SUM(CASE WHEN TYPE = 'expense' THEN AMOUNT ELSE 0 END) as expense
        FROM FINANCIAL_TRANSACTIONS 
        WHERE DATE(TRANSACTION_DATE) BETWEEN ? AND ?
        GROUP BY DATE(TRANSACTION_DATE)
        ORDER BY date
    """, (start_date, end_date))  
    financial_by_date = []  
    for row in cur.fetchall():  
        financial_by_date.append({  
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
    """, (start_date, end_date))  
    summary_row = cur.fetchone()  
    total_revenue = float(summary_row[0]) if summary_row[0] else 0.0  
    total_expense = float(summary_row[1]) if summary_row[1] else 0.0  
    return {  
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


def _get_performance_report(cur, start_date, end_date):  
    cur.execute("""
        SELECT DATE(CREATED_AT) as date,
               AVG(EXTRACT(EPOCH FROM (UPDATED_AT - CREATED_AT))/60) as avg_prep_time
        FROM ORDERS 
        WHERE DATE(CREATED_AT) BETWEEN ? AND ?
        AND STATUS = 'delivered' AND UPDATED_AT IS NOT NULL
        GROUP BY DATE(CREATED_AT)
        ORDER BY date
    """, (start_date, end_date))  
    performance_by_date = []  
    for row in cur.fetchall():  
        performance_by_date.append({  
            "date": row[0].isoformat(),
            "avg_prep_time": round(float(row[1]), 1) if row[1] else 0.0
        })
    cur.execute("""
        SELECT COUNT(*) as total_orders,
               SUM(CASE WHEN STATUS = 'cancelled' THEN 1 ELSE 0 END) as cancelled_orders
        FROM ORDERS 
        WHERE DATE(CREATED_AT) BETWEEN ? AND ?
    """, (start_date, end_date))  
    cancel_row = cur.fetchone()  
    total_orders = cancel_row[0] if cancel_row[0] else 0  
    cancelled_orders = cancel_row[1] if cancel_row[1] else 0  
    cancellation_rate = (cancelled_orders / total_orders * 100) if total_orders > 0 else 0  
    return {  
        "type": "performance",
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        },
        "performance_by_date": performance_by_date,
        "cancellation_rate": round(cancellation_rate, 2)
    }


def _get_employees_report(cur, start_date, end_date):  
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
    """, (start_date, end_date))  
    employees_performance = []  
    for row in cur.fetchall():  
        employees_performance.append({  
            "employee_id": row[1],
            "name": row[2],
            "total_orders": row[3] if row[3] else 0,
            "total_revenue": float(row[4]) if row[4] else 0.0,
            "avg_prep_time": round(float(row[5]), 1) if row[5] else 0.0
        })
        return {  
        "type": "employees",
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        },
        "employees_performance": employees_performance
    }


def generate_users_pdf_report(filters=None):
    """
    Gera relatório de usuários em PDF
    """
    from .user_service import get_users_paginated
    
    # Busca todos os usuários (sem paginação para o relatório)
    result = get_users_paginated(page=1, per_page=10000, filters=filters)
    users = result.get('users', [])
    
    # Calcula resumo
    summary = {
        "Total de Usuários": len(users),
        "Usuários Ativos": len([u for u in users if u.get('is_active', True)]),
        "Usuários Inativos": len([u for u in users if not u.get('is_active', True)]),
        "Por Cargo": {}
    }
    
    # Conta por cargo
    for user in users:
        role = user.get('role', 'N/A')
        summary["Por Cargo"][role] = summary["Por Cargo"].get(role, 0) + 1
    
    # Gera PDF
    return generate_pdf_report('users', users, filters, summary)


def generate_ingredients_pdf_report(filters=None):
    """
    Gera relatório de ingredientes em PDF
    """
    from .ingredient_service import list_ingredients, get_stock_summary
    
    # Busca todos os ingredientes
    result = list_ingredients(
        name_filter=filters.get('name') if filters else None,
        status_filter=filters.get('stock_status') if filters else None,
        page=1,
        page_size=10000
    )
    ingredients = result.get('items', [])
    
    # Busca resumo do estoque
    stock_summary = get_stock_summary()
    
    # Calcula resumo
    summary = {
        "Total de Ingredientes": len(ingredients),
        "Valor Total do Estoque": f"R$ {stock_summary.get('total_stock_value', 0):.2f}",
        "Esgotados": stock_summary.get('out_of_stock_count', 0),
        "Estoque Baixo": stock_summary.get('low_stock_count', 0),
        "Em Estoque": stock_summary.get('in_stock_count', 0)
    }
    
    # Gera PDF
    return generate_pdf_report('ingredients', ingredients, filters, summary)


def generate_products_pdf_report(filters=None):
    """
    Gera relatório de produtos em PDF
    """
    from .product_service import list_products, get_menu_summary
    
    # Busca todos os produtos
    result = list_products(
        name_filter=filters.get('name') if filters else None,
        category_id=filters.get('section_id') if filters else None,
        page=1,
        page_size=10000,
        include_inactive=filters.get('include_inactive', False) if filters else False
    )
    products = result.get('items', [])
    
    # Busca resumo do cardápio
    menu_summary = get_menu_summary()
    
    # Calcula resumo
    summary = {
        "Total de Produtos": len(products),
        "Produtos Ativos": len([p for p in products if p.get('is_active', True)]),
        "Produtos Inativos": len([p for p in products if not p.get('is_active', True)]),
        "Preço Médio": f"R$ {menu_summary.get('average_price', 0):.2f}",
        "Margem Média": f"R$ {menu_summary.get('average_margin', 0):.2f}"
    }
    
    # Gera PDF
    return generate_pdf_report('products', products, filters, summary)


def generate_orders_pdf_report(filters=None):
    """
    Gera relatório de pedidos em PDF
    """
    from .order_service import get_orders_with_filters
    
    # Busca pedidos com filtros
    orders = get_orders_with_filters(filters or {})
    
    # Calcula resumo
    total_orders = len(orders)
    total_revenue = sum(float(order.get('total_amount', 0)) for order in orders)
    
    # Conta por status
    status_count = {}
    for order in orders:
        status = order.get('status', 'N/A')
        status_count[status] = status_count.get(status, 0) + 1
    
    summary = {
        "Período Analisado": f"{filters.get('start_date', 'N/A')} a {filters.get('end_date', 'N/A')}" if filters else "Todos os períodos",
        "Total de Pedidos": total_orders,
        "Valor Total Faturado": f"R$ {total_revenue:.2f}",
        "Por Status": status_count
    }
    
    # Gera PDF
    return generate_pdf_report('orders', orders, filters, summary)
