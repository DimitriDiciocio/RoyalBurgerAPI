"""
Funções auxiliares para relatórios operacionais (Fases 4, 5 e 6)
Inclui: Estoque, Compras, Clientes, Fidelidade, Mesas, Dashboard Executivo
"""

import fdb
import logging
from datetime import datetime, date, timedelta
from ..database import get_db_connection
from ..utils.report_formatters import calculate_growth_percentage, safe_divide, format_currency, format_percentage
from ..utils.chart_generators import generate_bar_chart, generate_pie_chart, generate_line_chart
from ..utils.report_validators import validate_filters, validate_date_range

logger = logging.getLogger(__name__)


def generate_complete_stock_report_data(filters=None):
    """
    Gera dados para relatório completo de estoque
    
    Args:
        filters: dict com filtros (status, category, supplier, price_min, price_max)
    
    Returns:
        dict: Dados do relatório para geração de PDF
    """
    conn = None
    try:
        # Valida filtros
        allowed_filters = {
            'status': {'type': 'enum', 'values': ['ok', 'low', 'out_of_stock', 'unavailable', 'available', 'overstock'], 'required': False},
            'category': {'type': 'string', 'required': False},
            'supplier': {'type': 'string', 'required': False},
            'price_min': {'type': 'number', 'min': 0, 'required': False},
            'price_max': {'type': 'number', 'min': 0, 'required': False}
        }
        
        is_valid, error_msg, validated_filters = validate_filters(filters or {}, allowed_filters)
        if not is_valid:
            raise ValueError(error_msg)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Condições base
        conditions = []
        params = []
        
        if validated_filters.get('status'):
            status = validated_filters['status']
            if status == 'ok':
                conditions.append("i.STOCK_STATUS = 'ok'")
            elif status == 'low':
                conditions.append("i.STOCK_STATUS = 'low'")
            elif status == 'out_of_stock':
                conditions.append("i.STOCK_STATUS = 'out_of_stock'")
            elif status == 'available':
                conditions.append("i.IS_AVAILABLE = 1")
            elif status == 'unavailable':
                conditions.append("i.IS_AVAILABLE = 0")
        
        if validated_filters.get('category'):
            conditions.append("i.CATEGORY = ?")
            params.append(validated_filters['category'])
        
        if validated_filters.get('supplier'):
            conditions.append("i.SUPPLIER = ?")
            params.append(validated_filters['supplier'])
        
        if validated_filters.get('price_min'):
            conditions.append("i.PRICE >= ?")
            params.append(validated_filters['price_min'])
        
        if validated_filters.get('price_max'):
            conditions.append("i.PRICE <= ?")
            params.append(validated_filters['price_max'])
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # 1. RESUMO DE ESTOQUE
        cur.execute(f"""
            SELECT 
                COUNT(*) as total_ingredients,
                SUM(i.CURRENT_STOCK * i.PRICE) as total_value,
                COUNT(CASE WHEN i.STOCK_STATUS = 'out_of_stock' THEN 1 END) as out_of_stock,
                COUNT(CASE WHEN i.STOCK_STATUS = 'low' THEN 1 END) as low_stock,
                COUNT(CASE WHEN i.STOCK_STATUS = 'ok' THEN 1 END) as ok_stock
            FROM INGREDIENTS i
            WHERE {where_clause}
        """, tuple(params))
        
        summary_row = cur.fetchone()
        total_ingredients = summary_row[0] or 0
        total_value = float(summary_row[1] or 0)
        out_of_stock = summary_row[2] or 0
        low_stock = summary_row[3] or 0
        ok_stock = summary_row[4] or 0
        
        # 2. INGREDIENTES POR STATUS
        cur.execute(f"""
            SELECT i.STOCK_STATUS,
                   COUNT(*) as count,
                   SUM(i.CURRENT_STOCK * i.PRICE) as total_value
            FROM INGREDIENTS i
            WHERE {where_clause}
            GROUP BY i.STOCK_STATUS
            ORDER BY count DESC
        """, tuple(params))
        
        ingredients_by_status = []
        for row in cur.fetchall():
            ingredients_by_status.append({
                'status': row[0] or 'N/A',
                'count': row[1],
                'total_value': float(row[2] or 0)
            })
        
        # 3. INGREDIENTES MAIS UTILIZADOS (via ORDER_ITEMS e ORDER_ITEM_EXTRAS)
        # Busca últimos 30 dias
        start_date = datetime.now() - timedelta(days=30)
        cur.execute("""
            SELECT i.NAME,
                   SUM(COALESCE(oi.QUANTITY, 0) + COALESCE(oie.QUANTITY, 0)) as total_usage
            FROM INGREDIENTS i
            LEFT JOIN PRODUCT_INGREDIENTS pi ON i.ID = pi.INGREDIENT_ID
            LEFT JOIN ORDER_ITEMS oi ON pi.PRODUCT_ID = oi.PRODUCT_ID
            LEFT JOIN ORDERS o ON oi.ORDER_ID = o.ID
            LEFT JOIN ORDER_ITEM_EXTRAS oie ON oi.ID = oie.ORDER_ITEM_ID
            WHERE o.CREATED_AT >= ? AND o.STATUS NOT IN ('cancelled')
            GROUP BY i.ID, i.NAME
            ORDER BY total_usage DESC
            ROWS 20
        """, (start_date,))
        
        most_used = []
        for row in cur.fetchall():
            most_used.append({
                'name': row[0],
                'usage': float(row[1] or 0)
            })
        
        # 4. INGREDIENTES PARADOS (sem movimentação)
        cur.execute("""
            SELECT i.ID, i.NAME, i.CURRENT_STOCK, i.PRICE
            FROM INGREDIENTS i
            LEFT JOIN PRODUCT_INGREDIENTS pi ON i.ID = pi.INGREDIENT_ID
            LEFT JOIN ORDER_ITEMS oi ON pi.PRODUCT_ID = oi.PRODUCT_ID
            LEFT JOIN ORDERS o ON oi.ORDER_ID = o.ID
            WHERE o.CREATED_AT >= ? OR o.CREATED_AT IS NULL
            GROUP BY i.ID, i.NAME, i.CURRENT_STOCK, i.PRICE
            HAVING COUNT(o.ID) = 0
            ORDER BY i.CURRENT_STOCK * i.PRICE DESC
            ROWS 10
        """, (start_date,))
        
        inactive_ingredients = []
        for row in cur.fetchall():
            inactive_ingredients.append({
                'id': row[0],
                'name': row[1],
                'stock': float(row[2] or 0),
                'value': float(row[2] or 0) * float(row[3] or 0)
            })
        
        # Prepara dados para gráficos
        chart_data = {}
        
        if ingredients_by_status:
            chart_data['status_distribution'] = generate_pie_chart(
                data={'labels': [item['status'] for item in ingredients_by_status],
                      'values': [item['count'] for item in ingredients_by_status]},
                title='Distribuição de Ingredientes por Status'
            )
        
        if most_used:
            chart_data['most_used'] = generate_bar_chart(
                data={'labels': [item['name'][:20] for item in most_used[:10]],
                      'values': [item['usage'] for item in most_used[:10]]},
                title='Top 10 Ingredientes Mais Utilizados',
                x_label='Ingrediente',
                y_label='Uso',
                horizontal=True
            )
        
        return {
            'summary': {
                'total_ingredients': total_ingredients,
                'total_value': total_value,
                'out_of_stock': out_of_stock,
                'low_stock': low_stock,
                'ok_stock': ok_stock
            },
            'ingredients_by_status': ingredients_by_status,
            'most_used_ingredients': most_used,
            'inactive_ingredients': inactive_ingredients,
            'charts': chart_data,
            'filters': validated_filters
        }
        
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar relatório de estoque: {e}")
        raise
    except fdb.Error as e:
        logger.error(f"Erro ao gerar relatório de estoque: {e}", exc_info=True)
        raise Exception("Erro interno do servidor ao gerar relatório")
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar relatório de estoque: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def generate_purchases_report_data(filters=None):
    """
    Gera dados para relatório de compras e fornecedores
    
    Args:
        filters: dict com filtros (start_date, end_date, supplier, payment_status)
    
    Returns:
        dict: Dados do relatório para geração de PDF
    """
    conn = None
    try:
        # Valida filtros
        allowed_filters = {
            'start_date': {'type': 'date', 'required': False},
            'end_date': {'type': 'date', 'required': False, 'max_days': 365},
            'supplier': {'type': 'string', 'required': False},
            'payment_status': {'type': 'enum', 'values': ['Pending', 'Paid'], 'required': False}
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
        conditions = ["pi.PURCHASE_DATE >= ?", "pi.PURCHASE_DATE < ?"]
        params = [start_datetime, end_datetime]
        
        if validated_filters.get('supplier'):
            conditions.append("pi.SUPPLIER_NAME = ?")
            params.append(validated_filters['supplier'])
        
        if validated_filters.get('payment_status'):
            conditions.append("pi.PAYMENT_STATUS = ?")
            params.append(validated_filters['payment_status'])
        
        where_clause = " AND ".join(conditions)
        
        # 1. RESUMO DE COMPRAS
        cur.execute(f"""
            SELECT 
                COUNT(*) as total_invoices,
                SUM(pi.TOTAL_AMOUNT) as total_amount,
                AVG(pi.TOTAL_AMOUNT) as avg_amount,
                SUM(CASE WHEN pi.PAYMENT_STATUS = 'Paid' THEN pi.TOTAL_AMOUNT ELSE 0 END) as paid_amount,
                SUM(CASE WHEN pi.PAYMENT_STATUS = 'Pending' THEN pi.TOTAL_AMOUNT ELSE 0 END) as pending_amount
            FROM PURCHASE_INVOICES pi
            WHERE {where_clause}
        """, tuple(params))
        
        summary_row = cur.fetchone()
        total_invoices = summary_row[0] or 0
        total_amount = float(summary_row[1] or 0)
        avg_amount = float(summary_row[2] or 0)
        paid_amount = float(summary_row[3] or 0)
        pending_amount = float(summary_row[4] or 0)
        
        # 2. COMPRAS POR FORNECEDOR
        cur.execute(f"""
            SELECT pi.SUPPLIER_NAME,
                   COUNT(*) as invoice_count,
                   SUM(pi.TOTAL_AMOUNT) as total_amount,
                   AVG(pi.TOTAL_AMOUNT) as avg_amount
            FROM PURCHASE_INVOICES pi
            WHERE {where_clause}
            GROUP BY pi.SUPPLIER_NAME
            ORDER BY total_amount DESC
        """, tuple(params))
        
        purchases_by_supplier = []
        for row in cur.fetchall():
            purchases_by_supplier.append({
                'supplier': row[0] or 'N/A',
                'invoice_count': row[1],
                'total_amount': float(row[2] or 0),
                'avg_amount': float(row[3] or 0)
            })
        
        # 3. ITENS MAIS COMPRADOS
        cur.execute(f"""
            SELECT i.NAME,
                   SUM(pii.QUANTITY) as total_quantity,
                   SUM(pii.TOTAL_PRICE) as total_spent,
                   AVG(pii.UNIT_PRICE) as avg_price
            FROM PURCHASE_INVOICE_ITEMS pii
            JOIN PURCHASE_INVOICES pi ON pii.PURCHASE_INVOICE_ID = pi.ID
            JOIN INGREDIENTS i ON pii.INGREDIENT_ID = i.ID
            WHERE {where_clause}
            GROUP BY i.ID, i.NAME
            ORDER BY total_spent DESC
            ROWS 20
        """, tuple(params))
        
        most_purchased = []
        for row in cur.fetchall():
            most_purchased.append({
                'ingredient': row[0],
                'quantity': float(row[1] or 0),
                'total_spent': float(row[2] or 0),
                'avg_price': float(row[3] or 0)
            })
        
        # Prepara dados para gráficos
        chart_data = {}
        
        if purchases_by_supplier:
            chart_data['purchases_by_supplier'] = generate_bar_chart(
                data={'labels': [item['supplier'][:20] for item in purchases_by_supplier[:10]],
                      'values': [item['total_amount'] for item in purchases_by_supplier[:10]]},
                title='Top 10 Fornecedores por Valor',
                x_label='Fornecedor',
                y_label='Valor Total (R$)',
                horizontal=True
            )
        
        if most_purchased:
            chart_data['most_purchased'] = generate_bar_chart(
                data={'labels': [item['ingredient'][:20] for item in most_purchased[:10]],
                      'values': [item['total_spent'] for item in most_purchased[:10]]},
                title='Top 10 Itens Mais Comprados',
                x_label='Ingrediente',
                y_label='Valor Total (R$)',
                horizontal=True
            )
        
        return {
            'summary': {
                'total_invoices': total_invoices,
                'total_amount': total_amount,
                'avg_amount': avg_amount,
                'paid_amount': paid_amount,
                'pending_amount': pending_amount
            },
            'purchases_by_supplier': purchases_by_supplier,
            'most_purchased_items': most_purchased,
            'charts': chart_data,
            'period': {
                'start_date': start_dt.isoformat() if isinstance(start_dt, date) else start_dt.strftime('%Y-%m-%d'),
                'end_date': end_dt.isoformat() if isinstance(end_dt, date) else end_dt.strftime('%Y-%m-%d')
            },
            'filters': validated_filters
        }
        
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar relatório de compras: {e}")
        raise
    except fdb.Error as e:
        logger.error(f"Erro ao gerar relatório de compras: {e}", exc_info=True)
        raise Exception("Erro interno do servidor ao gerar relatório")
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar relatório de compras: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def generate_customers_analysis_report_data(filters=None):
    """
    Gera dados para relatório de análise de clientes (RFV)
    
    Args:
        filters: dict com filtros (start_date, end_date, region, min_orders, min_spent)
    
    Returns:
        dict: Dados do relatório para geração de PDF
    """
    conn = None
    try:
        # Valida filtros
        allowed_filters = {
            'start_date': {'type': 'date', 'required': False},
            'end_date': {'type': 'date', 'required': False, 'max_days': 365},
            'region': {'type': 'string', 'required': False},
            'min_orders': {'type': 'number', 'min': 0, 'required': False},
            'min_spent': {'type': 'number', 'min': 0, 'required': False}
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
        conditions = ["u.ROLE = 'customer'"]
        params = []
        
        if validated_filters.get('region'):
            conditions.append("a.CITY = ? OR a.STATE = ?")
            params.extend([validated_filters['region'], validated_filters['region']])
        
        where_clause = " AND ".join(conditions)
        
        # 1. TOP 50 CLIENTES POR VALOR GASTO
        order_conditions = ["o.CREATED_AT >= ?", "o.CREATED_AT < ?", "o.STATUS NOT IN ('cancelled')"]
        order_params = [start_datetime, end_datetime]
        
        if validated_filters.get('min_orders'):
            # Será aplicado no HAVING
            pass
        
        if validated_filters.get('min_spent'):
            # Será aplicado no HAVING
            pass
        
        having_clause = []
        if validated_filters.get('min_orders'):
            having_clause.append("COUNT(o.ID) >= ?")
            order_params.append(validated_filters['min_orders'])
        
        if validated_filters.get('min_spent'):
            having_clause.append("SUM(o.TOTAL_AMOUNT) >= ?")
            order_params.append(validated_filters['min_spent'])
        
        having_sql = " HAVING " + " AND ".join(having_clause) if having_clause else ""
        
        cur.execute(f"""
            SELECT u.ID, u.FULL_NAME, u.EMAIL,
                   COUNT(o.ID) as total_orders,
                   SUM(o.TOTAL_AMOUNT) as total_spent,
                   AVG(o.TOTAL_AMOUNT) as avg_ticket,
                   MAX(o.CREATED_AT) as last_order_date
            FROM USERS u
            LEFT JOIN ORDERS o ON u.ID = o.USER_ID
            LEFT JOIN ADDRESSES a ON u.ID = a.USER_ID
            WHERE {where_clause}
            AND ({' AND '.join(order_conditions)} OR o.ID IS NULL)
            GROUP BY u.ID, u.FULL_NAME, u.EMAIL
            {having_sql}
            ORDER BY total_spent DESC
            ROWS 50
        """, tuple(params + order_params))
        
        top_customers = []
        for row in cur.fetchall():
            last_order = row[6]
            if last_order:
                days_since_last = (datetime.now() - last_order).days if isinstance(last_order, datetime) else 0
            else:
                days_since_last = 999
            
            top_customers.append({
                'id': row[0],
                'name': row[1] or 'N/A',
                'email': row[2] or 'N/A',
                'total_orders': row[3] or 0,
                'total_spent': float(row[4] or 0),
                'avg_ticket': float(row[5] or 0),
                'days_since_last_order': days_since_last
            })
        
        # 2. CLIENTES INATIVOS (último pedido há mais de 30 dias)
        cur.execute("""
            SELECT u.ID, u.FULL_NAME, u.EMAIL,
                   MAX(o.CREATED_AT) as last_order_date,
                   COUNT(o.ID) as total_orders
            FROM USERS u
            LEFT JOIN ORDERS o ON u.ID = o.USER_ID
            WHERE u.ROLE = 'customer'
            GROUP BY u.ID, u.FULL_NAME, u.EMAIL
            HAVING MAX(o.CREATED_AT) < ? OR MAX(o.CREATED_AT) IS NULL
            ORDER BY last_order_date DESC NULLS LAST
            ROWS 50
        """, (datetime.now() - timedelta(days=30),))
        
        inactive_customers = []
        for row in cur.fetchall():
            inactive_customers.append({
                'id': row[0],
                'name': row[1] or 'N/A',
                'email': row[2] or 'N/A',
                'last_order_date': row[3].isoformat() if row[3] and hasattr(row[3], 'isoformat') else str(row[3]) if row[3] else None,
                'total_orders': row[4] or 0
            })
        
        # 3. RESUMO GERAL
        cur.execute("""
            SELECT 
                COUNT(DISTINCT u.ID) as total_customers,
                COUNT(DISTINCT CASE WHEN o.CREATED_AT >= ? THEN u.ID END) as active_customers,
                COUNT(DISTINCT CASE WHEN o.CREATED_AT < ? OR o.CREATED_AT IS NULL THEN u.ID END) as inactive_customers
            FROM USERS u
            LEFT JOIN ORDERS o ON u.ID = o.USER_ID
            WHERE u.ROLE = 'customer'
        """, (datetime.now() - timedelta(days=30), datetime.now() - timedelta(days=30)))
        
        summary_row = cur.fetchone()
        total_customers = summary_row[0] or 0
        active_customers = summary_row[1] or 0
        inactive_customers = summary_row[2] or 0
        
        # Prepara dados para gráficos
        chart_data = {}
        
        if top_customers:
            chart_data['top_customers'] = generate_bar_chart(
                data={'labels': [item['name'][:20] for item in top_customers[:10]],
                      'values': [item['total_spent'] for item in top_customers[:10]]},
                title='Top 10 Clientes por Valor Gasto',
                x_label='Cliente',
                y_label='Valor Gasto (R$)',
                horizontal=True
            )
        
        return {
            'summary': {
                'total_customers': total_customers,
                'active_customers': active_customers,
                'inactive_customers': inactive_customers
            },
            'top_customers': top_customers,
            'inactive_customers': inactive_customers,
            'charts': chart_data,
            'period': {
                'start_date': start_dt.isoformat() if isinstance(start_dt, date) else start_dt.strftime('%Y-%m-%d'),
                'end_date': end_dt.isoformat() if isinstance(end_dt, date) else end_dt.strftime('%Y-%m-%d')
            },
            'filters': validated_filters
        }
        
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar relatório de clientes: {e}")
        raise
    except fdb.Error as e:
        logger.error(f"Erro ao gerar relatório de clientes: {e}", exc_info=True)
        raise Exception("Erro interno do servidor ao gerar relatório")
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar relatório de clientes: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def generate_loyalty_report_data(filters=None):
    """
    Gera dados para relatório de programa de fidelidade
    
    Args:
        filters: dict com filtros (start_date, end_date, user_id)
    
    Returns:
        dict: Dados do relatório para geração de PDF
    """
    conn = None
    try:
        # Valida filtros
        allowed_filters = {
            'start_date': {'type': 'date', 'required': False},
            'end_date': {'type': 'date', 'required': False, 'max_days': 365},
            'user_id': {'type': 'id', 'required': False}
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
        conditions = ["lph.EARNED_AT >= ?", "lph.EARNED_AT < ?"]
        params = [start_datetime, end_datetime]
        
        if validated_filters.get('user_id'):
            conditions.append("lph.USER_ID = ?")
            params.append(validated_filters['user_id'])
        
        where_clause = " AND ".join(conditions)
        
        # 1. RESUMO DO PROGRAMA
        cur.execute(f"""
            SELECT 
                COUNT(DISTINCT lph.USER_ID) as total_participants,
                SUM(CASE WHEN lph.POINTS > 0 THEN lph.POINTS ELSE 0 END) as total_earned,
                SUM(CASE WHEN lph.POINTS < 0 THEN ABS(lph.POINTS) ELSE 0 END) as total_redeemed,
                COUNT(CASE WHEN lph.POINTS > 0 THEN 1 END) as earn_transactions,
                COUNT(CASE WHEN lph.POINTS < 0 THEN 1 END) as redeem_transactions
            FROM LOYALTY_POINTS_HISTORY lph
            WHERE {where_clause}
        """, tuple(params))
        
        summary_row = cur.fetchone()
        total_participants = summary_row[0] or 0
        total_earned = summary_row[1] or 0
        total_redeemed = summary_row[2] or 0
        earn_transactions = summary_row[3] or 0
        redeem_transactions = summary_row[4] or 0
        
        # 2. TOP PARTICIPANTES
        cur.execute(f"""
            SELECT u.FULL_NAME,
                   SUM(CASE WHEN lph.POINTS > 0 THEN lph.POINTS ELSE 0 END) as total_earned,
                   SUM(CASE WHEN lph.POINTS < 0 THEN ABS(lph.POINTS) ELSE 0 END) as total_redeemed,
                   (SELECT ACCUMULATED_POINTS - SPENT_POINTS FROM LOYALTY_POINTS WHERE USER_ID = u.ID) as current_balance
            FROM LOYALTY_POINTS_HISTORY lph
            JOIN USERS u ON lph.USER_ID = u.ID
            WHERE {where_clause}
            GROUP BY u.ID, u.FULL_NAME
            ORDER BY total_earned DESC
            ROWS 20
        """, tuple(params))
        
        top_participants = []
        for row in cur.fetchall():
            top_participants.append({
                'name': row[0] or 'N/A',
                'total_earned': row[1] or 0,
                'total_redeemed': row[2] or 0,
                'current_balance': row[3] or 0
            })
        
        # 3. ANÁLISE DE RESGATES
        cur.execute(f"""
            SELECT 
                COUNT(*) as total_redemptions,
                SUM(ABS(lph.POINTS)) as total_points_redeemed,
                AVG(ABS(lph.POINTS)) as avg_redemption
            FROM LOYALTY_POINTS_HISTORY lph
            WHERE {where_clause} AND lph.POINTS < 0
        """, tuple(params))
        
        redemption_row = cur.fetchone()
        total_redemptions = redemption_row[0] or 0
        total_points_redeemed = redemption_row[1] or 0
        avg_redemption = float(redemption_row[2] or 0)
        
        # Prepara dados para gráficos
        chart_data = {}
        
        if top_participants:
            chart_data['top_participants'] = generate_bar_chart(
                data={'labels': [item['name'][:20] for item in top_participants[:10]],
                      'values': [item['total_earned'] for item in top_participants[:10]]},
                title='Top 10 Participantes por Pontos Ganhos',
                x_label='Cliente',
                y_label='Pontos Ganhos',
                horizontal=True
            )
        
        return {
            'summary': {
                'total_participants': total_participants,
                'total_earned': total_earned,
                'total_redeemed': total_redeemed,
                'earn_transactions': earn_transactions,
                'redeem_transactions': redeem_transactions,
                'total_redemptions': total_redemptions,
                'total_points_redeemed': total_points_redeemed,
                'avg_redemption': avg_redemption
            },
            'top_participants': top_participants,
            'charts': chart_data,
            'period': {
                'start_date': start_dt.isoformat() if isinstance(start_dt, date) else start_dt.strftime('%Y-%m-%d'),
                'end_date': end_dt.isoformat() if isinstance(end_dt, date) else end_dt.strftime('%Y-%m-%d')
            },
            'filters': validated_filters
        }
        
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar relatório de fidelidade: {e}")
        raise
    except fdb.Error as e:
        logger.error(f"Erro ao gerar relatório de fidelidade: {e}", exc_info=True)
        raise Exception("Erro interno do servidor ao gerar relatório")
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar relatório de fidelidade: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def generate_tables_report_data(filters=None):
    """
    Gera dados para relatório de mesas e salão
    
    Args:
        filters: dict com filtros (start_date, end_date, table_id, attendant_id)
    
    Returns:
        dict: Dados do relatório para geração de PDF
    """
    conn = None
    try:
        # Valida filtros
        allowed_filters = {
            'start_date': {'type': 'date', 'required': False},
            'end_date': {'type': 'date', 'required': False, 'max_days': 365},
            'table_id': {'type': 'id', 'required': False},
            'attendant_id': {'type': 'id', 'required': False}
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
        conditions = ["o.ORDER_TYPE = 'on_site'", "o.CREATED_AT >= ?", "o.CREATED_AT < ?"]
        params = [start_datetime, end_datetime]
        
        if validated_filters.get('table_id'):
            conditions.append("o.TABLE_ID = ?")
            params.append(validated_filters['table_id'])
        
        if validated_filters.get('attendant_id'):
            conditions.append("o.ATTENDANT_ID = ?")
            params.append(validated_filters['attendant_id'])
        
        where_clause = " AND ".join(conditions)
        
        # 1. RESUMO DE MESAS
        cur.execute(f"""
            SELECT 
                COUNT(DISTINCT rt.ID) as total_tables,
                COUNT(DISTINCT o.TABLE_ID) as used_tables,
                COUNT(o.ID) as total_orders,
                SUM(o.TOTAL_AMOUNT) as total_revenue,
                AVG(EXTRACT(EPOCH FROM (o.UPDATED_AT - o.CREATED_AT))/60) as avg_duration
            FROM RESTAURANT_TABLES rt
            LEFT JOIN ORDERS o ON rt.ID = o.TABLE_ID
            WHERE o.CREATED_AT >= ? AND o.CREATED_AT < ? OR o.ID IS NULL
        """, (start_datetime, end_datetime))
        
        summary_row = cur.fetchone()
        total_tables = summary_row[0] or 0
        used_tables = summary_row[1] or 0
        total_orders = summary_row[2] or 0
        total_revenue = float(summary_row[3] or 0)
        avg_duration = float(summary_row[4] or 0)
        
        occupancy_rate = safe_divide(used_tables, total_tables, 0) * 100 if total_tables > 0 else 0
        
        # 2. PERFORMANCE POR MESA
        cur.execute(f"""
            SELECT rt.NAME,
                   COUNT(o.ID) as order_count,
                   SUM(o.TOTAL_AMOUNT) as revenue,
                   AVG(EXTRACT(EPOCH FROM (o.UPDATED_AT - o.CREATED_AT))/60) as avg_duration
            FROM RESTAURANT_TABLES rt
            LEFT JOIN ORDERS o ON rt.ID = o.TABLE_ID
            WHERE {where_clause} OR o.ID IS NULL
            GROUP BY rt.ID, rt.NAME
            ORDER BY revenue DESC NULLS LAST
        """, tuple(params))
        
        tables_performance = []
        for row in cur.fetchall():
            tables_performance.append({
                'name': row[0] or 'N/A',
                'order_count': row[1] or 0,
                'revenue': float(row[2] or 0),
                'avg_duration': float(row[3] or 0)
            })
        
        # Prepara dados para gráficos
        chart_data = {}
        
        if tables_performance:
            chart_data['tables_revenue'] = generate_bar_chart(
                data={'labels': [item['name'] for item in tables_performance[:10]],
                      'values': [item['revenue'] for item in tables_performance[:10]]},
                title='Top 10 Mesas por Receita',
                x_label='Mesa',
                y_label='Receita (R$)',
                horizontal=True
            )
        
        return {
            'summary': {
                'total_tables': total_tables,
                'used_tables': used_tables,
                'occupancy_rate': occupancy_rate,
                'total_orders': total_orders,
                'total_revenue': total_revenue,
                'avg_duration': avg_duration
            },
            'tables_performance': tables_performance,
            'charts': chart_data,
            'period': {
                'start_date': start_dt.isoformat() if isinstance(start_dt, date) else start_dt.strftime('%Y-%m-%d'),
                'end_date': end_dt.isoformat() if isinstance(end_dt, date) else end_dt.strftime('%Y-%m-%d')
            },
            'filters': validated_filters
        }
        
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar relatório de mesas: {e}")
        raise
    except fdb.Error as e:
        logger.error(f"Erro ao gerar relatório de mesas: {e}", exc_info=True)
        raise Exception("Erro interno do servidor ao gerar relatório")
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar relatório de mesas: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def generate_executive_dashboard_data(filters=None):
    """
    Gera dados para dashboard executivo (visão geral consolidada)
    
    Args:
        filters: dict com filtros (start_date, end_date)
    
    Returns:
        dict: Dados do relatório para geração de PDF
    """
    conn = None
    try:
        # Valida filtros
        allowed_filters = {
            'start_date': {'type': 'date', 'required': False},
            'end_date': {'type': 'date', 'required': False, 'max_days': 365}
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
        
        # 1. KPIs PRINCIPAIS
        # Receita
        cur.execute("""
            SELECT SUM(fm."VALUE") as total_revenue
            FROM FINANCIAL_MOVEMENTS fm
            WHERE fm.TYPE = 'REVENUE'
            AND fm.MOVEMENT_DATE >= ? AND fm.MOVEMENT_DATE < ?
            AND fm.PAYMENT_STATUS = 'Paid'
        """, (start_datetime, end_datetime))
        revenue_row = cur.fetchone()
        total_revenue = float(revenue_row[0] or 0)
        
        # Pedidos
        cur.execute("""
            SELECT COUNT(*) as total_orders,
                   AVG(TOTAL_AMOUNT) as avg_ticket
            FROM ORDERS
            WHERE CREATED_AT >= ? AND CREATED_AT < ?
            AND STATUS NOT IN ('cancelled')
        """, (start_datetime, end_datetime))
        orders_row = cur.fetchone()
        total_orders = orders_row[0] or 0
        avg_ticket = float(orders_row[1] or 0)
        
        # Lucro
        cur.execute("""
            SELECT 
                SUM(CASE WHEN fm.TYPE = 'REVENUE' THEN fm."VALUE" ELSE 0 END) as revenue,
                SUM(CASE WHEN fm.TYPE IN ('EXPENSE', 'CMV', 'TAX') THEN fm."VALUE" ELSE 0 END) as expenses
            FROM FINANCIAL_MOVEMENTS fm
            WHERE fm.MOVEMENT_DATE >= ? AND fm.MOVEMENT_DATE < ?
            AND fm.PAYMENT_STATUS = 'Paid'
        """, (start_datetime, end_datetime))
        profit_row = cur.fetchone()
        net_profit = float(profit_row[0] or 0) - float(profit_row[1] or 0)
        
        # 2. TOP 5 PRODUTOS
        cur.execute("""
            SELECT p.NAME,
                   SUM(oi.QUANTITY) as total_quantity
            FROM ORDER_ITEMS oi
            JOIN ORDERS o ON oi.ORDER_ID = o.ID
            JOIN PRODUCTS p ON oi.PRODUCT_ID = p.ID
            WHERE o.CREATED_AT >= ? AND o.CREATED_AT < ?
            AND o.STATUS NOT IN ('cancelled')
            GROUP BY p.ID, p.NAME
            ORDER BY total_quantity DESC
            ROWS 5
        """, (start_datetime, end_datetime))
        
        top_products = []
        for row in cur.fetchall():
            top_products.append({
                'name': row[0],
                'quantity': int(row[1] or 0)
            })
        
        # 3. TOP 5 CLIENTES
        cur.execute("""
            SELECT u.FULL_NAME,
                   SUM(o.TOTAL_AMOUNT) as total_spent
            FROM ORDERS o
            JOIN USERS u ON o.USER_ID = u.ID
            WHERE o.CREATED_AT >= ? AND o.CREATED_AT < ?
            AND o.STATUS NOT IN ('cancelled')
            GROUP BY u.ID, u.FULL_NAME
            ORDER BY total_spent DESC
            ROWS 5
        """, (start_datetime, end_datetime))
        
        top_customers = []
        for row in cur.fetchall():
            top_customers.append({
                'name': row[0] or 'N/A',
                'spent': float(row[1] or 0)
            })
        
        # 4. ALERTAS (estoque baixo)
        cur.execute("""
            SELECT COUNT(*) as low_stock_count
            FROM INGREDIENTS
            WHERE STOCK_STATUS IN ('low', 'out_of_stock')
        """)
        alert_row = cur.fetchone()
        low_stock_count = alert_row[0] or 0
        
        # 5. COMPARAÇÃO COM PERÍODO ANTERIOR
        period_days = (end_dt - start_dt).days
        prev_start_dt = start_dt - timedelta(days=period_days)
        prev_end_dt = start_dt
        
        prev_start_datetime = datetime.combine(prev_start_dt.date(), datetime.min.time()) if isinstance(prev_start_dt, date) else prev_start_dt
        prev_end_datetime = datetime.combine(prev_end_dt.date() + timedelta(days=1), datetime.min.time()) if isinstance(prev_end_dt, date) else prev_end_dt
        
        cur.execute("""
            SELECT SUM(fm."VALUE") as total_revenue
            FROM FINANCIAL_MOVEMENTS fm
            WHERE fm.TYPE = 'REVENUE'
            AND fm.MOVEMENT_DATE >= ? AND fm.MOVEMENT_DATE < ?
            AND fm.PAYMENT_STATUS = 'Paid'
        """, (prev_start_datetime, prev_end_datetime))
        prev_revenue_row = cur.fetchone()
        prev_revenue = float(prev_revenue_row[0] or 0)
        
        revenue_growth = calculate_growth_percentage(total_revenue, prev_revenue)
        
        return {
            'summary': {
                'total_revenue': total_revenue,
                'total_orders': total_orders,
                'avg_ticket': avg_ticket,
                'net_profit': net_profit,
                'revenue_growth': revenue_growth,
                'low_stock_alerts': low_stock_count
            },
            'top_products': top_products,
            'top_customers': top_customers,
            'period': {
                'start_date': start_dt.isoformat() if isinstance(start_dt, date) else start_dt.strftime('%Y-%m-%d'),
                'end_date': end_dt.isoformat() if isinstance(end_dt, date) else end_dt.strftime('%Y-%m-%d')
            },
            'filters': validated_filters
        }
        
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar dashboard executivo: {e}")
        raise
    except fdb.Error as e:
        logger.error(f"Erro ao gerar dashboard executivo: {e}", exc_info=True)
        raise Exception("Erro interno do servidor ao gerar relatório")
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar dashboard executivo: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def generate_reconciliation_report_data(filters=None):
    """
    Gera dados para relatório de conciliação bancária
    
    Args:
        filters: dict com filtros (start_date, end_date, payment_gateway, bank_account, reconciled)
    
    Returns:
        dict: Dados do relatório para geração de PDF
    """
    conn = None
    try:
        # Valida filtros
        allowed_filters = {
            'start_date': {'type': 'date', 'required': False},
            'end_date': {'type': 'date', 'required': False, 'max_days': 365},
            'payment_gateway': {'type': 'string', 'required': False},
            'bank_account': {'type': 'string', 'required': False},
            'reconciled': {'type': 'enum', 'values': ['true', 'false'], 'required': False}
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
        conditions = ["fm.MOVEMENT_DATE >= ?", "fm.MOVEMENT_DATE < ?"]
        params = [start_datetime, end_datetime]
        
        if validated_filters.get('payment_gateway'):
            conditions.append("fm.PAYMENT_GATEWAY_ID = ?")
            params.append(validated_filters['payment_gateway'])
        
        if validated_filters.get('bank_account'):
            conditions.append("fm.BANK_ACCOUNT = ?")
            params.append(validated_filters['bank_account'])
        
        if validated_filters.get('reconciled'):
            reconciled = validated_filters['reconciled'] == 'true'
            conditions.append("fm.RECONCILED = ?")
            params.append(reconciled)
        
        where_clause = " AND ".join(conditions)
        
        # 1. RESUMO DE CONCILIAÇÃO
        cur.execute(f"""
            SELECT 
                COUNT(*) as total_movements,
                COUNT(CASE WHEN fm.RECONCILED = 1 THEN 1 END) as reconciled_count,
                COUNT(CASE WHEN fm.RECONCILED = 0 THEN 1 END) as pending_count,
                SUM(CASE WHEN fm.RECONCILED = 1 THEN fm."VALUE" ELSE 0 END) as reconciled_amount,
                SUM(CASE WHEN fm.RECONCILED = 0 THEN fm."VALUE" ELSE 0 END) as pending_amount
            FROM FINANCIAL_MOVEMENTS fm
            WHERE {where_clause}
        """, tuple(params))
        
        summary_row = cur.fetchone()
        total_movements = summary_row[0] or 0
        reconciled_count = summary_row[1] or 0
        pending_count = summary_row[2] or 0
        reconciled_amount = float(summary_row[3] or 0)
        pending_amount = float(summary_row[4] or 0)
        
        # 2. MOVIMENTAÇÕES PENDENTES DE CONCILIAÇÃO
        cur.execute(f"""
            SELECT fm.ID, fm.TYPE, fm."VALUE", fm.DESCRIPTION,
                   fm.MOVEMENT_DATE, fm.PAYMENT_GATEWAY_ID, fm.TRANSACTION_ID,
                   fm.BANK_ACCOUNT, fm.CREATED_AT
            FROM FINANCIAL_MOVEMENTS fm
            WHERE {where_clause} AND fm.RECONCILED = 0
            ORDER BY fm.MOVEMENT_DATE DESC
            ROWS 50
        """, tuple(params))
        
        pending_movements = []
        for row in cur.fetchall():
            pending_movements.append({
                'id': row[0],
                'type': row[1],
                'value': float(row[2] or 0),
                'description': row[3] or 'N/A',
                'movement_date': row[4].isoformat() if row[4] and hasattr(row[4], 'isoformat') else str(row[4]) if row[4] else None,
                'gateway_id': row[5],
                'transaction_id': row[6],
                'bank_account': row[7],
                'created_at': row[8].isoformat() if row[8] and hasattr(row[8], 'isoformat') else str(row[8]) if row[8] else None
            })
        
        return {
            'summary': {
                'total_movements': total_movements,
                'reconciled_count': reconciled_count,
                'pending_count': pending_count,
                'reconciled_amount': reconciled_amount,
                'pending_amount': pending_amount
            },
            'pending_movements': pending_movements,
            'period': {
                'start_date': start_dt.isoformat() if isinstance(start_dt, date) else start_dt.strftime('%Y-%m-%d'),
                'end_date': end_dt.isoformat() if isinstance(end_dt, date) else end_dt.strftime('%Y-%m-%d')
            },
            'filters': validated_filters
        }
        
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar relatório de conciliação: {e}")
        raise
    except fdb.Error as e:
        logger.error(f"Erro ao gerar relatório de conciliação: {e}", exc_info=True)
        raise Exception("Erro interno do servidor ao gerar relatório")
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar relatório de conciliação: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()

