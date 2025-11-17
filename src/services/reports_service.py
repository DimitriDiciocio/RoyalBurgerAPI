import fdb
import logging
from datetime import datetime, date, timedelta
from ..database import get_db_connection
from .pdf_report_service import generate_pdf_report

logger = logging.getLogger(__name__)

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
        logger.error(f"Erro ao gerar relatório: {e}", exc_info=True)
        return {"error": "Erro interno do servidor"}
    finally:
        if conn: conn.close()


def _get_sales_report(cur, start_date, end_date):
    # OTIMIZAÇÃO: Converter datas para range queries (substitui DATE() por range para usar índices)
    from datetime import datetime, timedelta
    # Converte start_date e end_date para datetime se necessário
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Converte para datetime range
    start_datetime = datetime.combine(start_date, datetime.min.time()) if isinstance(start_date, date) else start_date
    end_datetime = datetime.combine(end_date + timedelta(days=1), datetime.min.time()) if isinstance(end_date, date) else end_date
    
    cur.execute("""
        SELECT CAST(CREATED_AT AS DATE) as date, 
               COUNT(*) as total_orders,
               SUM(TOTAL_AMOUNT) as total_revenue
        FROM ORDERS 
        WHERE CREATED_AT >= ? AND CREATED_AT < ?
        GROUP BY CAST(CREATED_AT AS DATE)
        ORDER BY date
    """, (start_datetime, end_datetime))
    sales_by_date = []
    for row in cur.fetchall():
        sales_by_date.append({
            "date": row[0].isoformat() if hasattr(row[0], 'isoformat') else str(row[0]),
            "total_orders": row[1],
            "total_revenue": float(row[2]) if row[2] else 0.0
        })
    cur.execute("""
        SELECT EXTRACT(HOUR FROM CREATED_AT) as hour,
               COUNT(*) as total_orders
        FROM ORDERS 
        WHERE CREATED_AT >= ? AND CREATED_AT < ?
        GROUP BY EXTRACT(HOUR FROM CREATED_AT)
        ORDER BY hour
    """, (start_datetime, end_datetime))
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
    # OTIMIZAÇÃO: Converter datas para range queries (substitui DATE() por range para usar índices)
    from datetime import datetime, timedelta
    # Converte start_date e end_date para datetime se necessário
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Converte para datetime range
    start_datetime = datetime.combine(start_date, datetime.min.time()) if isinstance(start_date, date) else start_date
    end_datetime = datetime.combine(end_date + timedelta(days=1), datetime.min.time()) if isinstance(end_date, date) else end_date
    
    cur.execute("""
        SELECT CAST(TRANSACTION_DATE AS DATE) as date,
               SUM(CASE WHEN TYPE = 'revenue' THEN AMOUNT ELSE 0 END) as revenue,
               SUM(CASE WHEN TYPE = 'expense' THEN AMOUNT ELSE 0 END) as expense
        FROM FINANCIAL_TRANSACTIONS 
        WHERE TRANSACTION_DATE >= ? AND TRANSACTION_DATE < ?
        GROUP BY CAST(TRANSACTION_DATE AS DATE)
        ORDER BY date
    """, (start_datetime, end_datetime))  
    financial_by_date = []  
    for row in cur.fetchall():  
        financial_by_date.append({  
            "date": row[0].isoformat() if hasattr(row[0], 'isoformat') else str(row[0]),
            "revenue": float(row[1]) if row[1] else 0.0,
            "expense": float(row[2]) if row[2] else 0.0,
            "profit": float(row[1]) - float(row[2]) if row[1] and row[2] else 0.0
        })
    cur.execute("""
        SELECT SUM(CASE WHEN TYPE = 'revenue' THEN AMOUNT ELSE 0 END) as total_revenue,
               SUM(CASE WHEN TYPE = 'expense' THEN AMOUNT ELSE 0 END) as total_expense
        FROM FINANCIAL_TRANSACTIONS 
        WHERE TRANSACTION_DATE >= ? AND TRANSACTION_DATE < ?
    """, (start_datetime, end_datetime))  
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
    # OTIMIZAÇÃO: Converter datas para range queries (substitui DATE() por range para usar índices)
    from datetime import datetime, timedelta
    # Converte start_date e end_date para datetime se necessário
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Converte para datetime range
    start_datetime = datetime.combine(start_date, datetime.min.time()) if isinstance(start_date, date) else start_date
    end_datetime = datetime.combine(end_date + timedelta(days=1), datetime.min.time()) if isinstance(end_date, date) else end_date
    
    cur.execute("""
        SELECT CAST(CREATED_AT AS DATE) as date,
               AVG(EXTRACT(EPOCH FROM (UPDATED_AT - CREATED_AT))/60) as avg_prep_time
        FROM ORDERS 
        WHERE CREATED_AT >= ? AND CREATED_AT < ?
        AND STATUS = 'delivered' AND UPDATED_AT IS NOT NULL
        GROUP BY CAST(CREATED_AT AS DATE)
        ORDER BY date
    """, (start_datetime, end_datetime))  
    performance_by_date = []  
    for row in cur.fetchall():  
        performance_by_date.append({  
            "date": row[0].isoformat() if hasattr(row[0], 'isoformat') else str(row[0]),
            "avg_prep_time": round(float(row[1]), 1) if row[1] else 0.0
        })
    cur.execute("""
        SELECT COUNT(*) as total_orders,
               SUM(CASE WHEN STATUS = 'cancelled' THEN 1 ELSE 0 END) as cancelled_orders
        FROM ORDERS 
        WHERE CREATED_AT >= ? AND CREATED_AT < ?
    """, (start_datetime, end_datetime))  
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
    # OTIMIZAÇÃO: Converter datas para range queries (substitui DATE() por range para usar índices)
    from datetime import datetime, timedelta
    # Converte start_date e end_date para datetime se necessário
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Converte para datetime range
    start_datetime = datetime.combine(start_date, datetime.min.time()) if isinstance(start_date, date) else start_date
    end_datetime = datetime.combine(end_date + timedelta(days=1), datetime.min.time()) if isinstance(end_date, date) else end_date
    
    cur.execute("""
        SELECT u.FULL_NAME, u.ID,
               COUNT(o.ID) as total_orders,
               SUM(o.TOTAL_AMOUNT) as total_revenue,
               AVG(EXTRACT(EPOCH FROM (o.UPDATED_AT - o.CREATED_AT))/60) as avg_prep_time
        FROM USERS u
        LEFT JOIN ORDERS o ON u.ID = o.ATTENDANT_ID 
        WHERE u.ROLE = 'attendant' 
        AND (o.CREATED_AT IS NULL OR (o.CREATED_AT >= ? AND o.CREATED_AT < ?))
        GROUP BY u.ID, u.FULL_NAME
        ORDER BY total_orders DESC
    """, (start_datetime, end_datetime))  
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
    orders_result = get_orders_with_filters(filters or {})
    # OTIMIZAÇÃO: get_orders_with_filters agora retorna dict com items e pagination
    orders = orders_result.get('items', []) if isinstance(orders_result, dict) else orders_result
    
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


def get_detailed_financial_report(start_date, end_date):
    """
    Gera relatório financeiro detalhado usando o novo sistema FINANCIAL_MOVEMENTS
    
    Args:
        start_date: datetime/date/str - Data de início
        end_date: datetime/date/str - Data de fim
    
    Returns:
        dict com:
            - summary: resumo geral
            - revenue_by_category: receitas por categoria
            - expense_by_category: despesas por categoria
            - cash_flow_by_date: fluxo de caixa por data
            - top_expenses: maiores despesas
            - pending_payments: contas a pagar
    """
    from . import financial_movement_service
    
    # Converter datas se necessário
    if isinstance(start_date, str):
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        except:
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00')).date()
    
    if isinstance(end_date, str):
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except:
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00')).date()
    
    # Converter para datetime para o serviço
    start_datetime = datetime.combine(start_date, datetime.min.time()) if isinstance(start_date, date) else start_date
    end_datetime = datetime.combine(end_date, datetime.min.time()) if isinstance(end_date, date) else end_date
    
    # Resumo geral usando o novo sistema
    # Nota: get_cash_flow_summary não suporta período customizado diretamente,
    # então vamos calcular manualmente com base nas movimentações
    filters = {
        'start_date': start_datetime,
        'end_date': end_datetime
    }
    movements = financial_movement_service.get_financial_movements(filters)
    
    # Calcular resumo
    summary = {
        'total_revenue': 0.0,
        'total_expense': 0.0,
        'total_cmv': 0.0,
        'total_tax': 0.0,
        'gross_profit': 0.0,
        'net_profit': 0.0,
        'cash_flow': 0.0
    }
    
    # Agrupar por categoria e calcular totais
    revenue_by_category = {}
    expense_by_category = {}
    cash_flow_by_date = {}
    top_expenses = []
    
    for movement in movements:
        if movement['payment_status'] != 'Paid':
            continue
        
        category = movement['category']
        value = movement['value']
        movement_type = movement['type']
        movement_date = movement.get('movement_date')
        
        # Agrupar por data para fluxo de caixa
        if movement_date:
            date_key = movement_date[:10] if isinstance(movement_date, str) else movement_date.date().isoformat()
            if date_key not in cash_flow_by_date:
                cash_flow_by_date[date_key] = {
                    'date': date_key,
                    'revenue': 0.0,
                    'expense': 0.0,
                    'cmv': 0.0,
                    'tax': 0.0,
                    'cash_flow': 0.0
                }
        
        # Calcular totais e agrupar por categoria
        if movement_type == 'REVENUE':
            summary['total_revenue'] += value
            revenue_by_category[category] = revenue_by_category.get(category, 0) + value
            if movement_date:
                date_key = movement_date[:10] if isinstance(movement_date, str) else movement_date.date().isoformat()
                cash_flow_by_date[date_key]['revenue'] += value
                cash_flow_by_date[date_key]['cash_flow'] += value
        elif movement_type == 'CMV':
            summary['total_cmv'] += value
            expense_by_category[category] = expense_by_category.get(category, 0) + value
            if movement_date:
                date_key = movement_date[:10] if isinstance(movement_date, str) else movement_date.date().isoformat()
                cash_flow_by_date[date_key]['cmv'] += value
                cash_flow_by_date[date_key]['cash_flow'] -= value
        elif movement_type == 'TAX':
            summary['total_tax'] += value
            expense_by_category[category] = expense_by_category.get(category, 0) + value
            if movement_date:
                date_key = movement_date[:10] if isinstance(movement_date, str) else movement_date.date().isoformat()
                cash_flow_by_date[date_key]['tax'] += value
                cash_flow_by_date[date_key]['cash_flow'] -= value
        elif movement_type == 'EXPENSE':
            summary['total_expense'] += value
            expense_by_category[category] = expense_by_category.get(category, 0) + value
            top_expenses.append({
                'description': movement['description'],
                'category': category,
                'value': value,
                'date': movement_date
            })
            if movement_date:
                date_key = movement_date[:10] if isinstance(movement_date, str) else movement_date.date().isoformat()
                cash_flow_by_date[date_key]['expense'] += value
                cash_flow_by_date[date_key]['cash_flow'] -= value
    
    # Calcular métricas finais
    summary['gross_profit'] = summary['total_revenue'] - summary['total_cmv']
    summary['net_profit'] = summary['total_revenue'] - summary['total_cmv'] - summary['total_expense'] - summary['total_tax']
    summary['cash_flow'] = summary['total_revenue'] - summary['total_expense'] - summary['total_cmv'] - summary['total_tax']
    
    # Ordenar top expenses por valor (maiores primeiro)
    top_expenses.sort(key=lambda x: x['value'], reverse=True)
    top_expenses = top_expenses[:10]  # Top 10
    
    # Ordenar fluxo de caixa por data
    cash_flow_by_date_list = sorted(cash_flow_by_date.values(), key=lambda x: x['date'])
    
    # Contas a pagar
    pending_filters = {
        'payment_status': 'Pending',
        'start_date': start_datetime,
        'end_date': end_datetime
    }
    pending = financial_movement_service.get_financial_movements(pending_filters)
    
    return {
        "summary": summary,
        "revenue_by_category": revenue_by_category,
        "expense_by_category": expense_by_category,
        "cash_flow_by_date": cash_flow_by_date_list,
        "top_expenses": top_expenses,
        "pending_payments": pending,
        "period": {
            "start_date": start_date.isoformat() if isinstance(start_date, date) else start_date,
            "end_date": end_date.isoformat() if isinstance(end_date, date) else end_date
        }
    }