"""
Serviço de Relatórios Avançados
Gera relatórios detalhados com gráficos, análises e métricas avançadas
"""

import fdb
import logging
from datetime import datetime, date, timedelta
from ..database import get_db_connection
from ..utils.report_formatters import (
    format_currency, format_percentage, format_date, 
    calculate_growth_percentage, safe_divide
)
from ..utils.chart_generators import (
    generate_line_chart, generate_bar_chart, generate_pie_chart, generate_multi_line_chart
)
from ..utils.report_validators import validate_filters, validate_date_range
from .pdf_report_service import DetailedSalesReportPDF, OrdersPerformanceReportPDF, ProductsAnalysisReportPDF
from .financial_reports_functions import generate_cmv_report, generate_taxes_report_data
from .operational_reports_functions import (
    generate_complete_stock_report_data, generate_purchases_report_data,
    generate_customers_analysis_report_data, generate_loyalty_report_data,
    generate_tables_report_data, generate_executive_dashboard_data,
    generate_reconciliation_report_data
)

logger = logging.getLogger(__name__)


def generate_detailed_sales_report(filters=None):
    """
    Gera relatório de vendas detalhado com gráficos e análises
    
    Args:
        filters: dict com filtros (start_date, end_date, order_type, payment_method, status, customer_id, product_id)
    
    Returns:
        bytes: Conteúdo do PDF em bytes
    """
    conn = None
    try:
        # Valida filtros
        allowed_filters = {
            'start_date': {'type': 'date', 'required': False},
            'end_date': {'type': 'date', 'required': False, 'max_days': 365},
            'order_type': {'type': 'enum', 'values': ['delivery', 'pickup', 'on_site'], 'required': False},
            'payment_method': {'type': 'string', 'required': False},
            'status': {'type': 'enum', 'values': ['pending', 'confirmed', 'preparing', 'ready', 'on_the_way', 'delivered', 'cancelled', 'completed'], 'required': False},
            'customer_id': {'type': 'id', 'required': False},
            'product_id': {'type': 'id', 'required': False}
        }
        
        is_valid, error_msg, validated_filters = validate_filters(filters or {}, allowed_filters)
        if not is_valid:
            raise ValueError(error_msg)
        
        # Valida range de datas
        start_date = validated_filters.get('start_date')
        end_date = validated_filters.get('end_date')
        is_valid, error_msg, start_dt, end_dt = validate_date_range(start_date, end_date, max_days=365)
        if not is_valid:
            raise ValueError(error_msg)
        
        # Se não fornecido, usa últimos 30 dias
        if not start_dt:
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(days=30)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Converte para datetime range para usar índices
        start_datetime = datetime.combine(start_dt.date(), datetime.min.time()) if isinstance(start_dt, date) else start_dt
        end_datetime = datetime.combine(end_dt.date() + timedelta(days=1), datetime.min.time()) if isinstance(end_dt, date) else end_dt
        
        # 1. RESUMO EXECUTIVO
        summary_conditions = ["o.CREATED_AT >= ?", "o.CREATED_AT < ?"]
        summary_params = [start_datetime, end_datetime]
        
        if validated_filters.get('order_type'):
            summary_conditions.append("o.ORDER_TYPE = ?")
            summary_params.append(validated_filters['order_type'])
        
        if validated_filters.get('status'):
            summary_conditions.append("o.STATUS = ?")
            summary_params.append(validated_filters['status'])
        
        if validated_filters.get('customer_id'):
            summary_conditions.append("o.USER_ID = ?")
            summary_params.append(validated_filters['customer_id'])
        
        where_clause = " AND ".join(summary_conditions)
        
        # CORREÇÃO: Adicionar CASTs explícitos e COALESCE para evitar erro SQLDA -804
        cur.execute(f"""
            SELECT 
                CAST(COUNT(*) AS INTEGER) as total_orders,
                CAST(COALESCE(SUM(CASE WHEN o.STATUS NOT IN ('cancelled') THEN o.TOTAL_AMOUNT ELSE 0 END), 0) AS NUMERIC(18,2)) as total_revenue,
                CAST(COALESCE(AVG(CASE WHEN o.STATUS NOT IN ('cancelled') THEN o.TOTAL_AMOUNT ELSE NULL END), 0) AS NUMERIC(18,2)) as avg_ticket,
                CAST(COUNT(CASE WHEN o.STATUS = 'cancelled' THEN 1 END) AS INTEGER) as cancelled_orders
            FROM ORDERS o
            WHERE {where_clause}
        """, tuple(summary_params))
        
        summary_row = cur.fetchone()
        total_orders = int(summary_row[0]) if summary_row[0] is not None else 0
        total_revenue = float(summary_row[1]) if summary_row[1] is not None else 0.0
        avg_ticket = float(summary_row[2]) if summary_row[2] is not None else 0.0
        cancelled_orders = int(summary_row[3]) if summary_row[3] is not None else 0
        
        # Calcula período anterior para comparação
        period_days = (end_dt - start_dt).days
        prev_start_dt = start_dt - timedelta(days=period_days)
        prev_end_dt = start_dt
        
        # Converte datas anteriores para datetime
        prev_start_datetime = datetime.combine(prev_start_dt.date(), datetime.min.time()) if isinstance(prev_start_dt, date) else prev_start_dt
        prev_end_datetime = datetime.combine(prev_end_dt.date() + timedelta(days=1), datetime.min.time()) if isinstance(prev_end_dt, date) else prev_end_dt
        
        prev_summary_params = [prev_start_datetime, prev_end_datetime] + summary_params[2:]
        # CORREÇÃO: Adicionar CASTs explícitos e COALESCE para evitar erro SQLDA -804
        cur.execute(f"""
            SELECT 
                CAST(COUNT(*) AS INTEGER) as total_orders,
                CAST(COALESCE(SUM(CASE WHEN o.STATUS NOT IN ('cancelled') THEN o.TOTAL_AMOUNT ELSE 0 END), 0) AS NUMERIC(18,2)) as total_revenue
            FROM ORDERS o
            WHERE {where_clause}
        """, tuple(prev_summary_params))
        
        prev_row = cur.fetchone()
        prev_total_orders = int(prev_row[0]) if prev_row[0] is not None else 0
        prev_total_revenue = float(prev_row[1]) if prev_row[1] is not None else 0.0
        
        # Calcula crescimento
        revenue_growth = calculate_growth_percentage(total_revenue, prev_total_revenue)
        orders_growth = calculate_growth_percentage(total_orders, prev_total_orders)
        cancellation_rate = safe_divide(cancelled_orders, total_orders, 0) * 100
        
        # 2. VENDAS POR DATA
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        # CORREÇÃO: "date" é palavra reservada no Firebird, usar alias diferente
        cur.execute(f"""
            SELECT CAST(o.CREATED_AT AS DATE) as sale_date,
                   CAST(COUNT(*) AS INTEGER) as total_orders,
                   CAST(COALESCE(SUM(CASE WHEN o.STATUS NOT IN ('cancelled') THEN o.TOTAL_AMOUNT ELSE 0 END), 0) AS NUMERIC(18,2)) as revenue
            FROM ORDERS o
            WHERE {where_clause}
            GROUP BY CAST(o.CREATED_AT AS DATE)
            ORDER BY sale_date
        """, tuple(summary_params))
        
        sales_by_date = []
        for row in cur.fetchall():
            sales_by_date.append({
                'date': row[0].isoformat() if hasattr(row[0], 'isoformat') else str(row[0]),
                'orders': row[1],
                'revenue': float(row[2] or 0)
            })
        
        # 3. VENDAS POR TIPO DE PEDIDO
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        cur.execute(f"""
            SELECT o.ORDER_TYPE,
                   CAST(COUNT(*) AS INTEGER) as total_orders,
                   CAST(COALESCE(SUM(CASE WHEN o.STATUS NOT IN ('cancelled') THEN o.TOTAL_AMOUNT ELSE 0 END), 0) AS NUMERIC(18,2)) as revenue
            FROM ORDERS o
            WHERE {where_clause}
            GROUP BY o.ORDER_TYPE
            ORDER BY revenue DESC
        """, tuple(summary_params))
        
        sales_by_type = []
        for row in cur.fetchall():
            sales_by_type.append({
                'type': row[0] or 'N/A',
                'orders': int(row[1]) if row[1] is not None else 0,
                'revenue': float(row[2]) if row[2] is not None else 0.0
            })
        
        # 4. VENDAS POR MÉTODO DE PAGAMENTO
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        cur.execute(f"""
            SELECT o.PAYMENT_METHOD,
                   CAST(COUNT(*) AS INTEGER) as total_orders,
                   CAST(COALESCE(SUM(CASE WHEN o.STATUS NOT IN ('cancelled') THEN o.TOTAL_AMOUNT ELSE 0 END), 0) AS NUMERIC(18,2)) as revenue
            FROM ORDERS o
            WHERE {where_clause} AND o.PAYMENT_METHOD IS NOT NULL
            GROUP BY o.PAYMENT_METHOD
            ORDER BY revenue DESC
        """, tuple(summary_params))
        
        sales_by_payment = []
        for row in cur.fetchall():
            sales_by_payment.append({
                'method': row[0] or 'N/A',
                'orders': int(row[1]) if row[1] is not None else 0,
                'revenue': float(row[2]) if row[2] is not None else 0.0
            })
        
        # 5. TOP 10 PRODUTOS MAIS VENDIDOS
        product_filter = ""
        product_params = list(summary_params)
        if validated_filters.get('product_id'):
            product_filter = " AND oi.PRODUCT_ID = ?"
            product_params.append(validated_filters['product_id'])
        
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        cur.execute(f"""
            SELECT p.NAME,
                   CAST(COALESCE(SUM(oi.QUANTITY), 0) AS INTEGER) as total_quantity,
                   CAST(COALESCE(SUM(oi.QUANTITY * oi.UNIT_PRICE), 0) AS NUMERIC(18,2)) as total_revenue
            FROM ORDER_ITEMS oi
            JOIN ORDERS o ON oi.ORDER_ID = o.ID
            JOIN PRODUCTS p ON oi.PRODUCT_ID = p.ID
            WHERE {where_clause}{product_filter}
            GROUP BY p.ID, p.NAME
            ORDER BY total_quantity DESC
            ROWS 10
        """, tuple(product_params))
        
        top_products = []
        for row in cur.fetchall():
            top_products.append({
                'name': row[0],
                'quantity': int(row[1]) if row[1] is not None else 0,
                'revenue': float(row[2]) if row[2] is not None else 0.0
            })
        
        # 6. TOP 10 CLIENTES
        if not validated_filters.get('customer_id'):
            # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
            cur.execute(f"""
                SELECT u.FULL_NAME,
                       CAST(COUNT(o.ID) AS INTEGER) as orders_count,
                       CAST(COALESCE(SUM(CASE WHEN o.STATUS NOT IN ('cancelled') THEN o.TOTAL_AMOUNT ELSE 0 END), 0) AS NUMERIC(18,2)) as total_spent
                FROM ORDERS o
                JOIN USERS u ON o.USER_ID = u.ID
                WHERE {where_clause}
                GROUP BY u.ID, u.FULL_NAME
                ORDER BY total_spent DESC
                ROWS 10
            """, tuple(summary_params))
            
            top_customers = []
            for row in cur.fetchall():
                top_customers.append({
                    'name': row[0] or 'N/A',
                    'orders': int(row[1]) if row[1] is not None else 0,
                    'spent': float(row[2]) if row[2] is not None else 0.0
                })
        else:
            top_customers = []
        
        # 7. ANÁLISE DE HORÁRIOS DE PICO
        # CORREÇÃO: Adicionar CAST explícito para evitar erro SQLDA -804
        # CORREÇÃO: "hour" e "orders" são palavras reservadas, usar aliases diferentes
        cur.execute(f"""
            SELECT EXTRACT(HOUR FROM o.CREATED_AT) as hour_of_day,
                   CAST(COUNT(*) AS INTEGER) as total_orders
            FROM ORDERS o
            WHERE {where_clause}
            GROUP BY EXTRACT(HOUR FROM o.CREATED_AT)
            ORDER BY hour_of_day
        """, tuple(summary_params))
        
        peak_hours = []
        for row in cur.fetchall():
            peak_hours.append({
                'hour': int(row[0]) if row[0] is not None else 0,
                'orders': int(row[1]) if row[1] is not None else 0
            })
        
        # Prepara dados para gráficos
        chart_data = {}
        
        # Gráfico de linha: Vendas por data
        if sales_by_date:
            chart_data['sales_timeline'] = generate_line_chart(
                data={'dates': [item['date'] for item in sales_by_date],
                      'values': [item['revenue'] for item in sales_by_date]},
                title='Vendas por Data',
                x_label='Data',
                y_label='Receita (R$)'
            )
        
        # Gráfico de pizza: Métodos de pagamento
        if sales_by_payment:
            chart_data['payment_methods'] = generate_pie_chart(
                data={'labels': [item['method'] for item in sales_by_payment],
                      'values': [item['revenue'] for item in sales_by_payment]},
                title='Vendas por Método de Pagamento'
            )
        
        # Gráfico de barras: Top produtos
        if top_products:
            chart_data['top_products'] = generate_bar_chart(
                data={'labels': [item['name'][:20] for item in top_products],
                      'values': [item['quantity'] for item in top_products]},
                title='Top 10 Produtos Mais Vendidos',
                x_label='Produto',
                y_label='Quantidade Vendida',
                horizontal=True
            )
        
        # Prepara dados para PDF
        report_data = {
            'summary': {
                'total_revenue': total_revenue,
                'total_orders': total_orders,
                'avg_ticket': avg_ticket,
                'cancellation_rate': cancellation_rate,
                'revenue_growth': revenue_growth,
                'orders_growth': orders_growth,
                'previous_period': {
                    'total_revenue': prev_total_revenue,
                    'total_orders': prev_total_orders
                }
            },
            'sales_by_date': sales_by_date,
            'sales_by_type': sales_by_type,
            'sales_by_payment': sales_by_payment,
            'top_products': top_products,
            'top_customers': top_customers,
            'peak_hours': peak_hours,
            'charts': chart_data,
            'period': {
                'start_date': start_dt.isoformat() if isinstance(start_dt, date) else start_dt.strftime('%Y-%m-%d'),
                'end_date': end_dt.isoformat() if isinstance(end_dt, date) else end_dt.strftime('%Y-%m-%d')
            },
            'filters': validated_filters
        }
        
        # Gera PDF
        pdf = DetailedSalesReportPDF()
        pdf.generate_report(report_data)
        
        pdf_content = pdf.output(dest='S')
        if isinstance(pdf_content, str):
            pdf_content = pdf_content.encode('latin-1')
        elif isinstance(pdf_content, bytearray):
            pdf_content = bytes(pdf_content)
        
        if not isinstance(pdf_content, bytes):
            pdf_content = str(pdf_content).encode('utf-8')
        
        return pdf_content
        
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar relatório de vendas: {e}")
        raise
    except fdb.Error as e:
        logger.error(f"Erro ao gerar relatório de vendas: {e}", exc_info=True)
        raise Exception("Erro interno do servidor ao gerar relatório")
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar relatório de vendas: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def generate_orders_performance_report(filters=None):
    """
    Gera relatório de performance de pedidos
    
    Args:
        filters: dict com filtros (start_date, end_date, attendant_id, deliverer_id, status, order_type)
    
    Returns:
        bytes: Conteúdo do PDF em bytes
    """
    conn = None
    try:
        # Valida filtros
        allowed_filters = {
            'start_date': {'type': 'date', 'required': False},
            'end_date': {'type': 'date', 'required': False, 'max_days': 365},
            'attendant_id': {'type': 'id', 'required': False},
            'deliverer_id': {'type': 'id', 'required': False},
            'status': {'type': 'enum', 'values': ['pending', 'confirmed', 'preparing', 'ready', 'on_the_way', 'delivered', 'cancelled', 'completed'], 'required': False},
            'order_type': {'type': 'enum', 'values': ['delivery', 'pickup', 'on_site'], 'required': False}
        }
        
        is_valid, error_msg, validated_filters = validate_filters(filters or {}, allowed_filters)
        if not is_valid:
            raise ValueError(error_msg)
        
        # Valida range de datas
        start_date = validated_filters.get('start_date')
        end_date = validated_filters.get('end_date')
        is_valid, error_msg, start_dt, end_dt = validate_date_range(start_date, end_date, max_days=365)
        if not is_valid:
            raise ValueError(error_msg)
        
        if not start_dt:
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(days=30)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        start_datetime = datetime.combine(start_dt.date(), datetime.min.time()) if isinstance(start_dt, date) else start_dt
        end_datetime = datetime.combine(end_dt.date() + timedelta(days=1), datetime.min.time()) if isinstance(end_dt, date) else end_dt
        
        # Condições base
        conditions = ["o.CREATED_AT >= ?", "o.CREATED_AT < ?"]
        params = [start_datetime, end_datetime]
        
        if validated_filters.get('attendant_id'):
            conditions.append("o.ATTENDANT_ID = ?")
            params.append(validated_filters['attendant_id'])
        
        if validated_filters.get('deliverer_id'):
            conditions.append("o.DELIVERER_ID = ?")
            params.append(validated_filters['deliverer_id'])
        
        if validated_filters.get('status'):
            conditions.append("o.STATUS = ?")
            params.append(validated_filters['status'])
        
        if validated_filters.get('order_type'):
            conditions.append("o.ORDER_TYPE = ?")
            params.append(validated_filters['order_type'])
        
        where_clause = " AND ".join(conditions)
        
        # 1. TEMPO MÉDIO DE PREPARO
        cur.execute(f"""
            SELECT AVG(EXTRACT(EPOCH FROM (o.UPDATED_AT - o.CREATED_AT))/60) as avg_prep_time
            FROM ORDERS o
            WHERE {where_clause} 
            AND o.STATUS IN ('ready', 'on_the_way', 'delivered', 'completed')
            AND o.UPDATED_AT IS NOT NULL
        """, tuple(params))
        
        avg_prep_time = cur.fetchone()[0]
        avg_prep_time = float(avg_prep_time) if avg_prep_time else 0.0
        
        # 2. TAXA DE CANCELAMENTO
        cur.execute(f"""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN o.STATUS = 'cancelled' THEN 1 END) as cancelled
            FROM ORDERS o
            WHERE {where_clause}
        """, tuple(params))
        
        cancel_row = cur.fetchone()
        total_orders = cancel_row[0] or 0
        cancelled_orders = cancel_row[1] or 0
        cancellation_rate = safe_divide(cancelled_orders, total_orders, 0) * 100
        
        # 3. PERFORMANCE POR ATENDENTE
        # CORREÇÃO: "orders" é palavra reservada, usar alias diferente
        cur.execute(f"""
            SELECT u.FULL_NAME,
                   CAST(COUNT(o.ID) AS INTEGER) as orders_count,
                   CAST(COALESCE(SUM(CASE WHEN o.STATUS NOT IN ('cancelled') THEN o.TOTAL_AMOUNT ELSE 0 END), 0) AS NUMERIC(18,2)) as revenue,
                   CAST(COALESCE(AVG(EXTRACT(EPOCH FROM (o.UPDATED_AT - o.CREATED_AT))/60), 0) AS NUMERIC(18,2)) as avg_time
            FROM ORDERS o
            JOIN USERS u ON o.ATTENDANT_ID = u.ID
            WHERE {where_clause} AND o.ATTENDANT_ID IS NOT NULL
            GROUP BY u.ID, u.FULL_NAME
            ORDER BY orders_count DESC
        """, tuple(params))
        
        attendants_performance = []
        for row in cur.fetchall():
            attendants_performance.append({
                'name': row[0] or 'N/A',
                'orders': row[1],
                'revenue': float(row[2] or 0),
                'avg_time': float(row[3] or 0)
            })
        
        # 4. PERFORMANCE POR ENTREGADOR
        cur.execute(f"""
            SELECT u.FULL_NAME,
                   COUNT(o.ID) as deliveries,
                   AVG(EXTRACT(EPOCH FROM (o.UPDATED_AT - o.CREATED_AT))/60) as avg_delivery_time
            FROM ORDERS o
            JOIN USERS u ON o.DELIVERER_ID = u.ID
            WHERE {where_clause} 
            AND o.DELIVERER_ID IS NOT NULL
            AND o.ORDER_TYPE = 'delivery'
            AND o.STATUS IN ('delivered', 'completed')
            GROUP BY u.ID, u.FULL_NAME
            ORDER BY deliveries DESC
        """, tuple(params))
        
        deliverers_performance = []
        for row in cur.fetchall():
            deliverers_performance.append({
                'name': row[0] or 'N/A',
                'deliveries': row[1],
                'avg_time': float(row[2] or 0)
            })
        
        # Prepara dados para PDF
        report_data = {
            'summary': {
                'total_orders': total_orders,
                'cancelled_orders': cancelled_orders,
                'cancellation_rate': cancellation_rate,
                'avg_prep_time': avg_prep_time
            },
            'attendants_performance': attendants_performance,
            'deliverers_performance': deliverers_performance,
            'period': {
                'start_date': start_dt.isoformat() if isinstance(start_dt, date) else start_dt.strftime('%Y-%m-%d'),
                'end_date': end_dt.isoformat() if isinstance(end_dt, date) else end_dt.strftime('%Y-%m-%d')
            },
            'filters': validated_filters
        }
        
        # Gera PDF
        pdf = OrdersPerformanceReportPDF()
        pdf.generate_report(report_data)
        
        pdf_content = pdf.output(dest='S')
        if isinstance(pdf_content, str):
            pdf_content = pdf_content.encode('latin-1')
        elif isinstance(pdf_content, bytearray):
            pdf_content = bytes(pdf_content)
        
        if not isinstance(pdf_content, bytes):
            pdf_content = str(pdf_content).encode('utf-8')
        
        return pdf_content
        
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar relatório de performance: {e}")
        raise
    except fdb.Error as e:
        logger.error(f"Erro ao gerar relatório de performance: {e}", exc_info=True)
        raise Exception("Erro interno do servidor ao gerar relatório")
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar relatório de performance: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def generate_products_analysis_report(filters=None):
    """
    Gera relatório de análise de produtos
    
    Args:
        filters: dict com filtros (start_date, end_date, category_id, product_id, price_min, price_max, status)
    
    Returns:
        bytes: Conteúdo do PDF em bytes
    """
    conn = None
    try:
        # Valida filtros
        allowed_filters = {
            'start_date': {'type': 'date', 'required': False},
            'end_date': {'type': 'date', 'required': False, 'max_days': 365},
            'category_id': {'type': 'id', 'required': False},
            'product_id': {'type': 'id', 'required': False},
            'price_min': {'type': 'number', 'min': 0, 'required': False},
            'price_max': {'type': 'number', 'min': 0, 'required': False},
            'status': {'type': 'enum', 'values': ['active', 'inactive'], 'required': False}
        }
        
        is_valid, error_msg, validated_filters = validate_filters(filters or {}, allowed_filters)
        if not is_valid:
            raise ValueError(error_msg)
        
        # Valida range de datas
        start_date = validated_filters.get('start_date')
        end_date = validated_filters.get('end_date')
        is_valid, error_msg, start_dt, end_dt = validate_date_range(start_date, end_date, max_days=365)
        if not is_valid:
            raise ValueError(error_msg)
        
        if not start_dt:
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(days=30)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        start_datetime = datetime.combine(start_dt.date(), datetime.min.time()) if isinstance(start_dt, date) else start_dt
        end_datetime = datetime.combine(end_dt.date() + timedelta(days=1), datetime.min.time()) if isinstance(end_dt, date) else end_dt
        
        # Condições para produtos
        product_conditions = ["p.IS_ACTIVE = 1"]
        product_params = []
        
        if validated_filters.get('category_id'):
            product_conditions.append("p.SECTION_ID = ?")
            product_params.append(validated_filters['category_id'])
        
        if validated_filters.get('product_id'):
            product_conditions.append("p.ID = ?")
            product_params.append(validated_filters['product_id'])
        
        if validated_filters.get('price_min'):
            product_conditions.append("p.PRICE >= ?")
            product_params.append(validated_filters['price_min'])
        
        if validated_filters.get('price_max'):
            product_conditions.append("p.PRICE <= ?")
            product_params.append(validated_filters['price_max'])
        
        if validated_filters.get('status'):
            product_conditions.append("p.IS_ACTIVE = ?")
            product_params.append(1 if validated_filters['status'] == 'active' else 0)
        
        product_where = " AND ".join(product_conditions)
        
        # 1. TOP 20 PRODUTOS MAIS VENDIDOS (QUANTIDADE)
        cur.execute(f"""
            SELECT p.ID, p.NAME, p.PRICE, p.COST_PRICE,
                   SUM(oi.QUANTITY) as total_quantity,
                   SUM(oi.QUANTITY * oi.UNIT_PRICE) as total_revenue
            FROM PRODUCTS p
            JOIN ORDER_ITEMS oi ON p.ID = oi.PRODUCT_ID
            JOIN ORDERS o ON oi.ORDER_ID = o.ID
            WHERE {product_where}
            AND o.CREATED_AT >= ? AND o.CREATED_AT < ?
            AND o.STATUS NOT IN ('cancelled')
            GROUP BY p.ID, p.NAME, p.PRICE, p.COST_PRICE
            ORDER BY total_quantity DESC
            ROWS 20
        """, tuple(product_params + [start_datetime, end_datetime]))
        
        top_products_qty = []
        for row in cur.fetchall():
            cost_price = float(row[3] or 0)
            revenue = float(row[5] or 0)
            quantity = int(row[4] or 0)
            profit = revenue - (cost_price * quantity)
            margin = safe_divide(profit, revenue, 0) * 100 if revenue > 0 else 0
            
            top_products_qty.append({
                'id': row[0],
                'name': row[1],
                'price': float(row[2] or 0),
                'cost_price': cost_price,
                'quantity': quantity,
                'revenue': revenue,
                'profit': profit,
                'margin': margin
            })
        
        # 2. TOP 20 PRODUTOS POR RECEITA
        cur.execute(f"""
            SELECT p.ID, p.NAME, p.PRICE, p.COST_PRICE,
                   SUM(oi.QUANTITY) as total_quantity,
                   SUM(oi.QUANTITY * oi.UNIT_PRICE) as total_revenue
            FROM PRODUCTS p
            JOIN ORDER_ITEMS oi ON p.ID = oi.PRODUCT_ID
            JOIN ORDERS o ON oi.ORDER_ID = o.ID
            WHERE {product_where}
            AND o.CREATED_AT >= ? AND o.CREATED_AT < ?
            AND o.STATUS NOT IN ('cancelled')
            GROUP BY p.ID, p.NAME, p.PRICE, p.COST_PRICE
            ORDER BY total_revenue DESC
            ROWS 20
        """, tuple(product_params + [start_datetime, end_datetime]))
        
        top_products_revenue = []
        for row in cur.fetchall():
            cost_price = float(row[3] or 0)
            revenue = float(row[5] or 0)
            quantity = int(row[4] or 0)
            profit = revenue - (cost_price * quantity)
            margin = safe_divide(profit, revenue, 0) * 100 if revenue > 0 else 0
            
            top_products_revenue.append({
                'id': row[0],
                'name': row[1],
                'price': float(row[2] or 0),
                'cost_price': cost_price,
                'quantity': quantity,
                'revenue': revenue,
                'profit': profit,
                'margin': margin
            })
        
        # Prepara dados para gráficos
        chart_data = {}
        
        if top_products_qty:
            chart_data['top_products_qty'] = generate_bar_chart(
                data={'labels': [p['name'][:20] for p in top_products_qty[:10]],
                      'values': [p['quantity'] for p in top_products_qty[:10]]},
                title='Top 10 Produtos por Quantidade Vendida',
                x_label='Produto',
                y_label='Quantidade',
                horizontal=True
            )
        
        if top_products_revenue:
            chart_data['top_products_revenue'] = generate_bar_chart(
                data={'labels': [p['name'][:20] for p in top_products_revenue[:10]],
                      'values': [p['revenue'] for p in top_products_revenue[:10]]},
                title='Top 10 Produtos por Receita',
                x_label='Produto',
                y_label='Receita (R$)',
                horizontal=True
            )
        
        # Prepara dados para PDF
        report_data = {
            'top_products_by_quantity': top_products_qty,
            'top_products_by_revenue': top_products_revenue,
            'charts': chart_data,
            'period': {
                'start_date': start_dt.isoformat() if isinstance(start_dt, date) else start_dt.strftime('%Y-%m-%d'),
                'end_date': end_dt.isoformat() if isinstance(end_dt, date) else end_dt.strftime('%Y-%m-%d')
            },
            'filters': validated_filters
        }
        
        # Gera PDF
        pdf = ProductsAnalysisReportPDF()
        pdf.generate_report(report_data)
        
        pdf_content = pdf.output(dest='S')
        if isinstance(pdf_content, str):
            pdf_content = pdf_content.encode('latin-1')
        elif isinstance(pdf_content, bytearray):
            pdf_content = bytes(pdf_content)
        
        if not isinstance(pdf_content, bytes):
            pdf_content = str(pdf_content).encode('utf-8')
        
        return pdf_content
        
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar relatório de produtos: {e}")
        raise
    except fdb.Error as e:
        logger.error(f"Erro ao gerar relatório de produtos: {e}", exc_info=True)
        raise Exception("Erro interno do servidor ao gerar relatório")
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar relatório de produtos: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def generate_complete_financial_report(filters=None):
    """
    Gera relatório financeiro completo usando FINANCIAL_MOVEMENTS com gráficos e análises
    
    Args:
        filters: dict com filtros (start_date, end_date, type, category, payment_status, payment_method)
    
    Returns:
        bytes: Conteúdo do PDF em bytes
    """
    conn = None
    try:
        # Valida filtros
        allowed_filters = {
            'start_date': {'type': 'date', 'required': False},
            'end_date': {'type': 'date', 'required': False, 'max_days': 365},
            'type': {'type': 'enum', 'values': ['REVENUE', 'EXPENSE', 'CMV', 'TAX'], 'required': False},
            'category': {'type': 'string', 'required': False},
            'payment_status': {'type': 'enum', 'values': ['Pending', 'Paid'], 'required': False},
            'payment_method': {'type': 'string', 'required': False}
        }
        
        is_valid, error_msg, validated_filters = validate_filters(filters or {}, allowed_filters)
        if not is_valid:
            raise ValueError(error_msg)
        
        # Valida range de datas
        start_date = validated_filters.get('start_date')
        end_date = validated_filters.get('end_date')
        is_valid, error_msg, start_dt, end_dt = validate_date_range(start_date, end_date, max_days=365)
        if not is_valid:
            raise ValueError(error_msg)
        
        if not start_dt:
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(days=30)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Usa MOVEMENT_DATE para fluxo de caixa real (apenas Paid)
        start_datetime = datetime.combine(start_dt.date(), datetime.min.time()) if isinstance(start_dt, date) else start_dt
        end_datetime = datetime.combine(end_dt.date() + timedelta(days=1), datetime.min.time()) if isinstance(end_dt, date) else end_dt
        
        # Condições base
        conditions = ["fm.MOVEMENT_DATE >= ?", "fm.MOVEMENT_DATE < ?", "fm.PAYMENT_STATUS = 'Paid'"]
        params = [start_datetime, end_datetime]
        
        if validated_filters.get('type'):
            conditions.append("fm.TYPE = ?")
            params.append(validated_filters['type'])
        
        if validated_filters.get('category'):
            conditions.append("fm.CATEGORY = ?")
            params.append(validated_filters['category'])
        
        if validated_filters.get('payment_method'):
            conditions.append("fm.PAYMENT_METHOD = ?")
            params.append(validated_filters['payment_method'])
        
        where_clause = " AND ".join(conditions)
        
        # 1. RESUMO EXECUTIVO
        cur.execute(f"""
            SELECT 
                SUM(CASE WHEN fm.TYPE = 'REVENUE' THEN fm."VALUE" ELSE 0 END) as total_revenue,
                SUM(CASE WHEN fm.TYPE = 'EXPENSE' THEN fm."VALUE" ELSE 0 END) as total_expense,
                SUM(CASE WHEN fm.TYPE = 'CMV' THEN fm."VALUE" ELSE 0 END) as total_cmv,
                SUM(CASE WHEN fm.TYPE = 'TAX' THEN fm."VALUE" ELSE 0 END) as total_taxes
            FROM FINANCIAL_MOVEMENTS fm
            WHERE {where_clause}
        """, tuple(params))
        
        summary_row = cur.fetchone()
        total_revenue = float(summary_row[0] or 0)
        total_expense = float(summary_row[1] or 0)
        total_cmv = float(summary_row[2] or 0)
        total_taxes = float(summary_row[3] or 0)
        
        gross_profit = total_revenue - total_cmv
        net_profit = total_revenue - total_expense - total_cmv - total_taxes
        
        gross_margin = safe_divide(gross_profit, total_revenue, 0) * 100 if total_revenue > 0 else 0
        net_margin = safe_divide(net_profit, total_revenue, 0) * 100 if total_revenue > 0 else 0
        
        # Calcula período anterior para comparação
        period_days = (end_dt - start_dt).days
        prev_start_dt = start_dt - timedelta(days=period_days)
        prev_end_dt = start_dt
        
        prev_start_datetime = datetime.combine(prev_start_dt.date(), datetime.min.time()) if isinstance(prev_start_dt, date) else prev_start_dt
        prev_end_datetime = datetime.combine(prev_end_dt.date() + timedelta(days=1), datetime.min.time()) if isinstance(prev_end_dt, date) else prev_end_dt
        
        prev_params = [prev_start_datetime, prev_end_datetime] + params[2:]
        cur.execute(f"""
            SELECT 
                SUM(CASE WHEN fm.TYPE = 'REVENUE' THEN fm."VALUE" ELSE 0 END) as total_revenue,
                SUM(CASE WHEN fm.TYPE = 'EXPENSE' THEN fm."VALUE" ELSE 0 END) as total_expense
            FROM FINANCIAL_MOVEMENTS fm
            WHERE {where_clause}
        """, tuple(prev_params))
        
        prev_row = cur.fetchone()
        prev_revenue = float(prev_row[0] or 0)
        prev_expense = float(prev_row[1] or 0)
        
        revenue_growth = calculate_growth_percentage(total_revenue, prev_revenue)
        
        # 2. FLUXO DE CAIXA DIÁRIO
        # CORREÇÃO: "date" é palavra reservada no Firebird, usar alias diferente
        cur.execute(f"""
            SELECT CAST(fm.MOVEMENT_DATE AS DATE) as movement_date,
                   CAST(COALESCE(SUM(CASE WHEN fm.TYPE = 'REVENUE' THEN fm."VALUE" ELSE 0 END), 0) AS NUMERIC(18,2)) as revenue,
                   CAST(COALESCE(SUM(CASE WHEN fm.TYPE IN ('EXPENSE', 'CMV', 'TAX') THEN fm."VALUE" ELSE 0 END), 0) AS NUMERIC(18,2)) as expenses
            FROM FINANCIAL_MOVEMENTS fm
            WHERE {where_clause}
            GROUP BY CAST(fm.MOVEMENT_DATE AS DATE)
            ORDER BY movement_date
        """, tuple(params))
        
        cashflow_by_date = []
        for row in cur.fetchall():
            revenue = float(row[1] or 0)
            expenses = float(row[2] or 0)
            cashflow_by_date.append({
                'date': row[0].isoformat() if hasattr(row[0], 'isoformat') else str(row[0]),
                'revenue': revenue,
                'expenses': expenses,
                'net': revenue - expenses
            })
        
        # 3. RECEITAS POR CATEGORIA
        cur.execute(f"""
            SELECT fm.CATEGORY,
                   SUM(fm."VALUE") as total
            FROM FINANCIAL_MOVEMENTS fm
            WHERE {where_clause} AND fm.TYPE = 'REVENUE'
            GROUP BY fm.CATEGORY
            ORDER BY total DESC
        """, tuple(params))
        
        revenue_by_category = []
        for row in cur.fetchall():
            revenue_by_category.append({
                'category': row[0] or 'N/A',
                'total': float(row[1] or 0)
            })
        
        # 4. DESPESAS POR CATEGORIA
        cur.execute(f"""
            SELECT fm.CATEGORY,
                   SUM(fm."VALUE") as total
            FROM FINANCIAL_MOVEMENTS fm
            WHERE {where_clause} AND fm.TYPE = 'EXPENSE'
            GROUP BY fm.CATEGORY
            ORDER BY total DESC
        """, tuple(params))
        
        expenses_by_category = []
        for row in cur.fetchall():
            expenses_by_category.append({
                'category': row[0] or 'N/A',
                'total': float(row[1] or 0)
            })
        
        # 5. CONTAS A PAGAR (Pendentes)
        pending_conditions = ["fm.PAYMENT_STATUS = 'Pending'"]
        pending_params = []
        
        if validated_filters.get('start_date'):
            pending_conditions.append("COALESCE(fm.MOVEMENT_DATE, fm.CREATED_AT) >= ?")
            pending_params.append(start_datetime)
        
        if validated_filters.get('end_date'):
            pending_conditions.append("COALESCE(fm.MOVEMENT_DATE, fm.CREATED_AT) < ?")
            pending_params.append(end_datetime)
        
        if validated_filters.get('type'):
            pending_conditions.append("fm.TYPE = ?")
            pending_params.append(validated_filters['type'])
        
        pending_where = " AND ".join(pending_conditions)
        
        cur.execute(f"""
            SELECT 
                SUM(CASE WHEN fm.TYPE = 'EXPENSE' THEN fm."VALUE" ELSE 0 END) as pending_expenses,
                SUM(CASE WHEN fm.TYPE = 'TAX' THEN fm."VALUE" ELSE 0 END) as pending_taxes
            FROM FINANCIAL_MOVEMENTS fm
            WHERE {pending_where}
        """, tuple(pending_params))
        
        pending_row = cur.fetchone()
        pending_expenses = float(pending_row[0] or 0)
        pending_taxes = float(pending_row[1] or 0)
        
        # Prepara dados para gráficos
        chart_data = {}
        
        # Gráfico de linha: Fluxo de caixa
        if cashflow_by_date:
            chart_data['cashflow_timeline'] = generate_multi_line_chart(
                data_series=[
                    {'dates': [item['date'] for item in cashflow_by_date],
                     'values': [item['revenue'] for item in cashflow_by_date]},
                    {'dates': [item['date'] for item in cashflow_by_date],
                     'values': [item['expenses'] for item in cashflow_by_date]},
                    {'dates': [item['date'] for item in cashflow_by_date],
                     'values': [item['net'] for item in cashflow_by_date]}
                ],
                title='Fluxo de Caixa Diário',
                x_label='Data',
                y_label='Valor (R$)',
                legend_labels=['Receitas', 'Despesas', 'Líquido']
            )
        
        # Gráfico de pizza: Receitas por categoria
        if revenue_by_category:
            chart_data['revenue_by_category'] = generate_pie_chart(
                data={'labels': [item['category'] for item in revenue_by_category],
                      'values': [item['total'] for item in revenue_by_category]},
                title='Receitas por Categoria'
            )
        
        # Gráfico de pizza: Despesas por categoria
        if expenses_by_category:
            chart_data['expenses_by_category'] = generate_pie_chart(
                data={'labels': [item['category'] for item in expenses_by_category],
                      'values': [item['total'] for item in expenses_by_category]},
                title='Despesas por Categoria'
            )
        
        # Prepara dados para PDF
        report_data = {
            'summary': {
                'total_revenue': total_revenue,
                'total_expense': total_expense,
                'total_cmv': total_cmv,
                'total_taxes': total_taxes,
                'gross_profit': gross_profit,
                'net_profit': net_profit,
                'gross_margin': gross_margin,
                'net_margin': net_margin,
                'revenue_growth': revenue_growth,
                'pending_expenses': pending_expenses,
                'pending_taxes': pending_taxes,
                'previous_period': {
                    'total_revenue': prev_revenue,
                    'total_expense': prev_expense
                }
            },
            'cashflow_by_date': cashflow_by_date,
            'revenue_by_category': revenue_by_category,
            'expenses_by_category': expenses_by_category,
            'charts': chart_data,
            'period': {
                'start_date': start_dt.isoformat() if isinstance(start_dt, date) else start_dt.strftime('%Y-%m-%d'),
                'end_date': end_dt.isoformat() if isinstance(end_dt, date) else end_dt.strftime('%Y-%m-%d')
            },
            'filters': validated_filters
        }
        
        # Gera PDF
        from .pdf_report_service import CompleteFinancialReportPDF
        pdf = CompleteFinancialReportPDF()
        pdf.generate_report(report_data)
        
        pdf_content = pdf.output(dest='S')
        if isinstance(pdf_content, str):
            pdf_content = pdf_content.encode('latin-1')
        elif isinstance(pdf_content, bytearray):
            pdf_content = bytes(pdf_content)
        
        if not isinstance(pdf_content, bytes):
            pdf_content = str(pdf_content).encode('utf-8')
        
        return pdf_content
        
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar relatório financeiro: {e}")
        raise
    except fdb.Error as e:
        logger.error(f"Erro ao gerar relatório financeiro: {e}", exc_info=True)
        raise Exception("Erro interno do servidor ao gerar relatório")
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar relatório financeiro: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def generate_cmv_report_pdf(filters=None):
    """
    Gera relatório de CMV (Custo das Mercadorias Vendidas) em PDF
    
    Args:
        filters: dict com filtros (start_date, end_date, category_id, product_id)
    
    Returns:
        bytes: Conteúdo do PDF em bytes
    """
    try:
        # Busca dados do relatório
        report_data = generate_cmv_report(filters)
        
        # Gera PDF
        from .pdf_report_service import CMVReportPDF
        pdf = CMVReportPDF()
        pdf.generate_report(report_data)
        
        pdf_content = pdf.output(dest='S')
        if isinstance(pdf_content, str):
            pdf_content = pdf_content.encode('latin-1')
        elif isinstance(pdf_content, bytearray):
            pdf_content = bytes(pdf_content)
        
        if not isinstance(pdf_content, bytes):
            pdf_content = str(pdf_content).encode('utf-8')
        
        return pdf_content
        
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar relatório de CMV: {e}")
        raise
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar relatório de CMV: {e}", exc_info=True)
        raise


def generate_taxes_report_pdf(filters=None):
    """
    Gera relatório de impostos e taxas em PDF
    
    Args:
        filters: dict com filtros (start_date, end_date, category, status)
    
    Returns:
        bytes: Conteúdo do PDF em bytes
    """
    try:
        # Busca dados do relatório
        report_data = generate_taxes_report_data(filters)
        
        # Gera PDF
        from .pdf_report_service import TaxesReportPDF
        pdf = TaxesReportPDF()
        pdf.generate_report(report_data)
        
        pdf_content = pdf.output(dest='S')
        if isinstance(pdf_content, str):
            pdf_content = pdf_content.encode('latin-1')
        elif isinstance(pdf_content, bytearray):
            pdf_content = bytes(pdf_content)
        
        if not isinstance(pdf_content, bytes):
            pdf_content = str(pdf_content).encode('utf-8')
        
        return pdf_content
        
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar relatório de impostos: {e}")
        raise
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar relatório de impostos: {e}", exc_info=True)
        raise


def generate_complete_stock_report_pdf(filters=None):
    """Gera relatório completo de estoque em PDF"""
    try:
        report_data = generate_complete_stock_report_data(filters)
        from .pdf_report_service import CompleteStockReportPDF
        pdf = CompleteStockReportPDF()
        pdf.generate_report(report_data)
        
        pdf_content = pdf.output(dest='S')
        if isinstance(pdf_content, str):
            pdf_content = pdf_content.encode('latin-1')
        elif isinstance(pdf_content, bytearray):
            pdf_content = bytes(pdf_content)
        
        if not isinstance(pdf_content, bytes):
            pdf_content = str(pdf_content).encode('utf-8')
        
        return pdf_content
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar relatório de estoque: {e}")
        raise
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar relatório de estoque: {e}", exc_info=True)
        raise


def generate_purchases_report_pdf(filters=None):
    """Gera relatório de compras em PDF"""
    try:
        report_data = generate_purchases_report_data(filters)
        from .pdf_report_service import PurchasesReportPDF
        pdf = PurchasesReportPDF()
        pdf.generate_report(report_data)
        
        pdf_content = pdf.output(dest='S')
        if isinstance(pdf_content, str):
            pdf_content = pdf_content.encode('latin-1')
        elif isinstance(pdf_content, bytearray):
            pdf_content = bytes(pdf_content)
        
        if not isinstance(pdf_content, bytes):
            pdf_content = str(pdf_content).encode('utf-8')
        
        return pdf_content
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar relatório de compras: {e}")
        raise
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar relatório de compras: {e}", exc_info=True)
        raise


def generate_customers_analysis_report_pdf(filters=None):
    """Gera relatório de análise de clientes em PDF"""
    try:
        report_data = generate_customers_analysis_report_data(filters)
        from .pdf_report_service import CustomersAnalysisReportPDF
        pdf = CustomersAnalysisReportPDF()
        pdf.generate_report(report_data)
        
        pdf_content = pdf.output(dest='S')
        if isinstance(pdf_content, str):
            pdf_content = pdf_content.encode('latin-1')
        elif isinstance(pdf_content, bytearray):
            pdf_content = bytes(pdf_content)
        
        if not isinstance(pdf_content, bytes):
            pdf_content = str(pdf_content).encode('utf-8')
        
        return pdf_content
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar relatório de clientes: {e}")
        raise
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar relatório de clientes: {e}", exc_info=True)
        raise


def generate_loyalty_report_pdf(filters=None):
    """Gera relatório de fidelidade em PDF"""
    try:
        report_data = generate_loyalty_report_data(filters)
        from .pdf_report_service import LoyaltyReportPDF
        pdf = LoyaltyReportPDF()
        pdf.generate_report(report_data)
        
        pdf_content = pdf.output(dest='S')
        if isinstance(pdf_content, str):
            pdf_content = pdf_content.encode('latin-1')
        elif isinstance(pdf_content, bytearray):
            pdf_content = bytes(pdf_content)
        
        if not isinstance(pdf_content, bytes):
            pdf_content = str(pdf_content).encode('utf-8')
        
        return pdf_content
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar relatório de fidelidade: {e}")
        raise
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar relatório de fidelidade: {e}", exc_info=True)
        raise


def generate_tables_report_pdf(filters=None):
    """Gera relatório de mesas em PDF"""
    try:
        report_data = generate_tables_report_data(filters)
        from .pdf_report_service import TablesReportPDF
        pdf = TablesReportPDF()
        pdf.generate_report(report_data)
        
        pdf_content = pdf.output(dest='S')
        if isinstance(pdf_content, str):
            pdf_content = pdf_content.encode('latin-1')
        elif isinstance(pdf_content, bytearray):
            pdf_content = bytes(pdf_content)
        
        if not isinstance(pdf_content, bytes):
            pdf_content = str(pdf_content).encode('utf-8')
        
        return pdf_content
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar relatório de mesas: {e}")
        raise
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar relatório de mesas: {e}", exc_info=True)
        raise


def generate_executive_dashboard_pdf(filters=None):
    """Gera dashboard executivo em PDF"""
    try:
        report_data = generate_executive_dashboard_data(filters)
        from .pdf_report_service import ExecutiveDashboardPDF
        pdf = ExecutiveDashboardPDF()
        pdf.generate_report(report_data)
        
        pdf_content = pdf.output(dest='S')
        if isinstance(pdf_content, str):
            pdf_content = pdf_content.encode('latin-1')
        elif isinstance(pdf_content, bytearray):
            pdf_content = bytes(pdf_content)
        
        if not isinstance(pdf_content, bytes):
            pdf_content = str(pdf_content).encode('utf-8')
        
        return pdf_content
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar dashboard executivo: {e}")
        raise
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar dashboard executivo: {e}", exc_info=True)
        raise


def generate_reconciliation_report_pdf(filters=None):
    """Gera relatório de conciliação bancária em PDF"""
    try:
        report_data = generate_reconciliation_report_data(filters)
        from .pdf_report_service import ReconciliationReportPDF
        pdf = ReconciliationReportPDF()
        pdf.generate_report(report_data)
        
        pdf_content = pdf.output(dest='S')
        if isinstance(pdf_content, str):
            pdf_content = pdf_content.encode('latin-1')
        elif isinstance(pdf_content, bytearray):
            pdf_content = bytes(pdf_content)
        
        if not isinstance(pdf_content, bytes):
            pdf_content = str(pdf_content).encode('utf-8')
        
        return pdf_content
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar relatório de conciliação: {e}")
        raise
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar relatório de conciliação: {e}", exc_info=True)
        raise

