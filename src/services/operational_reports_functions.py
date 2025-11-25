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
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        cur.execute(f"""
            SELECT 
                CAST(COUNT(*) AS INTEGER) as total_ingredients,
                CAST(COALESCE(SUM(i.CURRENT_STOCK * i.PRICE), 0) AS NUMERIC(18,2)) as total_value,
                CAST(COUNT(CASE WHEN i.STOCK_STATUS = 'out_of_stock' THEN 1 END) AS INTEGER) as out_of_stock,
                CAST(COUNT(CASE WHEN i.STOCK_STATUS = 'low' THEN 1 END) AS INTEGER) as low_stock,
                CAST(COUNT(CASE WHEN i.STOCK_STATUS = 'ok' THEN 1 END) AS INTEGER) as ok_stock
            FROM INGREDIENTS i
            WHERE {where_clause}
        """, tuple(params))
        
        summary_row = cur.fetchone()
        total_ingredients = int(summary_row[0] or 0) if summary_row and summary_row[0] is not None else 0
        total_value = float(summary_row[1] or 0) if summary_row and summary_row[1] is not None else 0.0
        out_of_stock = int(summary_row[2] or 0) if summary_row and summary_row[2] is not None else 0
        low_stock = int(summary_row[3] or 0) if summary_row and summary_row[3] is not None else 0
        ok_stock = int(summary_row[4] or 0) if summary_row and summary_row[4] is not None else 0
        
        # 2. INGREDIENTES POR STATUS
        # CORREÇÃO: "count" é palavra reservada, usar alias diferente
        cur.execute(f"""
            SELECT i.STOCK_STATUS,
                   CAST(COUNT(*) AS INTEGER) as status_count,
                   CAST(COALESCE(SUM(i.CURRENT_STOCK * i.PRICE), 0) AS NUMERIC(18,2)) as total_value
            FROM INGREDIENTS i
            WHERE {where_clause}
            GROUP BY i.STOCK_STATUS
            ORDER BY status_count DESC
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
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        start_date = datetime.now() - timedelta(days=30)
        cur.execute("""
            SELECT i.NAME,
                   CAST(COALESCE(SUM(COALESCE(oi.QUANTITY, 0) + COALESCE(oie.QUANTITY, 0)), 0) AS NUMERIC(18,2)) as total_usage
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
                'name': row[0] or 'N/A',
                'usage': float(row[1] or 0) if row[1] is not None else 0.0
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
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        cur.execute(f"""
            SELECT 
                CAST(COUNT(*) AS INTEGER) as total_invoices,
                CAST(COALESCE(SUM(pi.TOTAL_AMOUNT), 0) AS NUMERIC(18,2)) as total_amount,
                CAST(COALESCE(AVG(pi.TOTAL_AMOUNT), 0) AS NUMERIC(18,2)) as avg_amount,
                CAST(COALESCE(SUM(CASE WHEN pi.PAYMENT_STATUS = 'Paid' THEN pi.TOTAL_AMOUNT ELSE 0 END), 0) AS NUMERIC(18,2)) as paid_amount,
                CAST(COALESCE(SUM(CASE WHEN pi.PAYMENT_STATUS = 'Pending' THEN pi.TOTAL_AMOUNT ELSE 0 END), 0) AS NUMERIC(18,2)) as pending_amount
            FROM PURCHASE_INVOICES pi
            WHERE {where_clause}
        """, tuple(params))
        
        summary_row = cur.fetchone()
        total_invoices = int(summary_row[0] or 0) if summary_row and summary_row[0] is not None else 0
        total_amount = float(summary_row[1] or 0) if summary_row and summary_row[1] is not None else 0.0
        avg_amount = float(summary_row[2] or 0) if summary_row and summary_row[2] is not None else 0.0
        paid_amount = float(summary_row[3] or 0) if summary_row and summary_row[3] is not None else 0.0
        pending_amount = float(summary_row[4] or 0) if summary_row and summary_row[4] is not None else 0.0
        
        # 2. COMPRAS POR FORNECEDOR
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        cur.execute(f"""
            SELECT pi.SUPPLIER_NAME,
                   CAST(COUNT(*) AS INTEGER) as invoice_count,
                   CAST(COALESCE(SUM(pi.TOTAL_AMOUNT), 0) AS NUMERIC(18,2)) as total_amount,
                   CAST(COALESCE(AVG(pi.TOTAL_AMOUNT), 0) AS NUMERIC(18,2)) as avg_amount
            FROM PURCHASE_INVOICES pi
            WHERE {where_clause}
            GROUP BY pi.SUPPLIER_NAME
            ORDER BY total_amount DESC
        """, tuple(params))
        
        purchases_by_supplier = []
        for row in cur.fetchall():
            purchases_by_supplier.append({
                'supplier': row[0] or 'N/A',
                'invoice_count': int(row[1] or 0) if row[1] is not None else 0,
                'total_amount': float(row[2] or 0) if row[2] is not None else 0.0,
                'avg_amount': float(row[3] or 0) if row[3] is not None else 0.0
            })
        
        # 3. ITENS MAIS COMPRADOS
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        cur.execute(f"""
            SELECT i.NAME,
                   CAST(COALESCE(SUM(pii.QUANTITY), 0) AS NUMERIC(18,3)) as total_quantity,
                   CAST(COALESCE(SUM(pii.TOTAL_PRICE), 0) AS NUMERIC(18,2)) as total_spent,
                   CAST(COALESCE(AVG(pii.UNIT_PRICE), 0) AS NUMERIC(18,2)) as avg_price
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
                'ingredient': row[0] or 'N/A',
                'quantity': float(row[1] or 0) if row[1] is not None else 0.0,
                'total_spent': float(row[2] or 0) if row[2] is not None else 0.0,
                'avg_price': float(row[3] or 0) if row[3] is not None else 0.0
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
        
        # CORREÇÃO: Filtro de região deve ser aplicado via subquery para evitar duplicação
        region_filter = ""
        if validated_filters.get('region'):
            region_filter = " AND EXISTS (SELECT 1 FROM ADDRESSES a WHERE a.USER_ID = u.ID AND (a.CITY = ? OR a.STATE = ?))"
            params.extend([validated_filters['region'], validated_filters['region']])
        
        where_clause = " AND ".join(conditions) + region_filter
        
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
            having_clause.append("COUNT(DISTINCT o.ID) >= ?")
            order_params.append(validated_filters['min_orders'])
        
        if validated_filters.get('min_spent'):
            # CORREÇÃO: Usar subquery no HAVING para filtrar por valor gasto
            having_clause.append("""
                (SELECT SUM(o2.TOTAL_AMOUNT) 
                 FROM ORDERS o2 
                 WHERE o2.USER_ID = u.ID 
                 AND o2.CREATED_AT >= ? 
                 AND o2.CREATED_AT < ? 
                 AND o2.STATUS NOT IN ('cancelled')) >= ?
            """)
            order_params.extend([start_datetime, end_datetime, validated_filters['min_spent']])
        
        having_sql = " HAVING " + " AND ".join(having_clause) if having_clause else ""
        
        # CORREÇÃO: Remover JOIN com ADDRESSES para evitar duplicação de pedidos
        # Usar COUNT(DISTINCT o.ID) para contar pedidos únicos
        # Usar subquery para SUM para evitar duplicação quando há múltiplos endereços
        cur.execute(f"""
            SELECT CAST(u.ID AS INTEGER) as user_id,
                   CAST(u.FULL_NAME AS VARCHAR(255)) as full_name,
                   CAST(u.EMAIL AS VARCHAR(255)) as email,
                   CAST(COUNT(DISTINCT o.ID) AS INTEGER) as total_orders,
                   CAST(COALESCE(
                       (SELECT SUM(o2.TOTAL_AMOUNT) 
                        FROM ORDERS o2 
                        WHERE o2.USER_ID = u.ID 
                        AND o2.CREATED_AT >= ? 
                        AND o2.CREATED_AT < ? 
                        AND o2.STATUS NOT IN ('cancelled')), 
                       0
                   ) AS NUMERIC(18,2)) as total_spent,
                   CAST(COALESCE(
                       (SELECT AVG(o2.TOTAL_AMOUNT) 
                        FROM ORDERS o2 
                        WHERE o2.USER_ID = u.ID 
                        AND o2.CREATED_AT >= ? 
                        AND o2.CREATED_AT < ? 
                        AND o2.STATUS NOT IN ('cancelled')), 
                       0
                   ) AS NUMERIC(18,2)) as avg_ticket,
                   MAX(o.CREATED_AT) as last_order_date
            FROM USERS u
            LEFT JOIN ORDERS o ON u.ID = o.USER_ID 
                AND o.CREATED_AT >= ? 
                AND o.CREATED_AT < ? 
                AND o.STATUS NOT IN ('cancelled')
            WHERE {where_clause}
            GROUP BY u.ID, u.FULL_NAME, u.EMAIL
            {having_sql}
            ORDER BY total_spent DESC
            ROWS 50
        """, tuple(params + order_params + order_params + order_params))
        
        top_customers = []
        for row in cur.fetchall():
            last_order = row[6]
            if last_order:
                days_since_last = (datetime.now() - last_order).days if isinstance(last_order, datetime) else 0
            else:
                # CORREÇÃO: Para clientes sem pedidos, usar None ou -1 em vez de 999
                days_since_last = None  # Será tratado no PDF como "Nunca"
            
            top_customers.append({
                'id': int(row[0] or 0) if row[0] is not None else 0,
                'name': row[1] or 'N/A' if row[1] is not None else 'N/A',
                'email': row[2] or 'N/A' if row[2] is not None else 'N/A',
                'total_orders': int(row[3] or 0) if row[3] is not None else 0,
                'total_spent': float(row[4] or 0) if row[4] is not None else 0.0,
                'avg_ticket': float(row[5] or 0) if row[5] is not None else 0.0,
                'days_since_last_order': days_since_last
            })
        
        # 2. CLIENTES INATIVOS (último pedido há mais de 30 dias)
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        cur.execute("""
            SELECT CAST(u.ID AS INTEGER) as user_id,
                   CAST(u.FULL_NAME AS VARCHAR(255)) as full_name,
                   CAST(u.EMAIL AS VARCHAR(255)) as email,
                   MAX(o.CREATED_AT) as last_order_date,
                   CAST(COUNT(o.ID) AS INTEGER) as total_orders
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
                'id': int(row[0] or 0) if row[0] is not None else 0,
                'name': row[1] or 'N/A' if row[1] is not None else 'N/A',
                'email': row[2] or 'N/A' if row[2] is not None else 'N/A',
                'last_order_date': row[3].isoformat() if row[3] and hasattr(row[3], 'isoformat') else str(row[3]) if row[3] else None,
                'total_orders': int(row[4] or 0) if row[4] is not None else 0
            })
        
        # 3. RESUMO GERAL
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        cur.execute("""
            SELECT 
                CAST(COUNT(DISTINCT u.ID) AS INTEGER) as total_customers,
                CAST(COUNT(DISTINCT CASE WHEN o.CREATED_AT >= ? THEN u.ID END) AS INTEGER) as active_customers,
                CAST(COUNT(DISTINCT CASE WHEN o.CREATED_AT < ? OR o.CREATED_AT IS NULL THEN u.ID END) AS INTEGER) as inactive_customers
            FROM USERS u
            LEFT JOIN ORDERS o ON u.ID = o.USER_ID
            WHERE u.ROLE = 'customer'
        """, (datetime.now() - timedelta(days=30), datetime.now() - timedelta(days=30)))
        
        summary_row = cur.fetchone()
        total_customers = int(summary_row[0] or 0) if summary_row and summary_row[0] is not None else 0
        active_customers = int(summary_row[1] or 0) if summary_row and summary_row[1] is not None else 0
        inactive_customers = int(summary_row[2] or 0) if summary_row and summary_row[2] is not None else 0
        
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
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        cur.execute(f"""
            SELECT 
                CAST(COUNT(DISTINCT lph.USER_ID) AS INTEGER) as total_participants,
                CAST(COALESCE(SUM(CASE WHEN lph.POINTS > 0 THEN lph.POINTS ELSE 0 END), 0) AS NUMERIC(18,2)) as total_earned,
                CAST(COALESCE(SUM(CASE WHEN lph.POINTS < 0 THEN ABS(lph.POINTS) ELSE 0 END), 0) AS NUMERIC(18,2)) as total_redeemed,
                CAST(COUNT(CASE WHEN lph.POINTS > 0 THEN 1 END) AS INTEGER) as earn_transactions,
                CAST(COUNT(CASE WHEN lph.POINTS < 0 THEN 1 END) AS INTEGER) as redeem_transactions
            FROM LOYALTY_POINTS_HISTORY lph
            WHERE {where_clause}
        """, tuple(params))
        
        summary_row = cur.fetchone()
        total_participants = int(summary_row[0] or 0) if summary_row and summary_row[0] is not None else 0
        total_earned = float(summary_row[1] or 0) if summary_row and summary_row[1] is not None else 0.0
        total_redeemed = float(summary_row[2] or 0) if summary_row and summary_row[2] is not None else 0.0
        earn_transactions = int(summary_row[3] or 0) if summary_row and summary_row[3] is not None else 0
        redeem_transactions = int(summary_row[4] or 0) if summary_row and summary_row[4] is not None else 0
        
        # 2. TOP PARTICIPANTES
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        cur.execute(f"""
            SELECT CAST(u.FULL_NAME AS VARCHAR(255)) as full_name,
                   CAST(COALESCE(SUM(CASE WHEN lph.POINTS > 0 THEN lph.POINTS ELSE 0 END), 0) AS NUMERIC(18,2)) as total_earned,
                   CAST(COALESCE(SUM(CASE WHEN lph.POINTS < 0 THEN ABS(lph.POINTS) ELSE 0 END), 0) AS NUMERIC(18,2)) as total_redeemed,
                   CAST(COALESCE((SELECT ACCUMULATED_POINTS - SPENT_POINTS FROM LOYALTY_POINTS WHERE USER_ID = u.ID), 0) AS NUMERIC(18,2)) as current_balance
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
                'name': row[0] or 'N/A' if row[0] is not None else 'N/A',
                'total_earned': float(row[1] or 0) if row[1] is not None else 0.0,
                'total_redeemed': float(row[2] or 0) if row[2] is not None else 0.0,
                'current_balance': float(row[3] or 0) if row[3] is not None else 0.0
            })
        
        # 3. ANÁLISE DE RESGATES
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        cur.execute(f"""
            SELECT 
                CAST(COUNT(*) AS INTEGER) as total_redemptions,
                CAST(COALESCE(SUM(ABS(lph.POINTS)), 0) AS NUMERIC(18,2)) as total_points_redeemed,
                CAST(COALESCE(AVG(ABS(lph.POINTS)), 0) AS NUMERIC(18,2)) as avg_redemption
            FROM LOYALTY_POINTS_HISTORY lph
            WHERE {where_clause} AND lph.POINTS < 0
        """, tuple(params))
        
        redemption_row = cur.fetchone()
        total_redemptions = int(redemption_row[0] or 0) if redemption_row and redemption_row[0] is not None else 0
        total_points_redeemed = float(redemption_row[1] or 0) if redemption_row and redemption_row[1] is not None else 0.0
        avg_redemption = float(redemption_row[2] or 0) if redemption_row and redemption_row[2] is not None else 0.0
        
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
        # ALTERAÇÃO: Corrigir consulta SQL para tratar NULLs corretamente e evitar erro SQLCODE -804
        # Separar em duas queries mais simples para evitar problemas com LEFT JOIN complexo
        # Query 1: Total de mesas
        cur.execute("SELECT COUNT(*) FROM RESTAURANT_TABLES")
        total_tables_result = cur.fetchone()
        total_tables = int(total_tables_result[0]) if total_tables_result and total_tables_result[0] is not None else 0
        
        # Query 2: Estatísticas de pedidos no período
        cur.execute("""
            SELECT 
                CAST(COUNT(DISTINCT o.TABLE_ID) AS INTEGER) as used_tables,
                CAST(COUNT(o.ID) AS INTEGER) as total_orders,
                CAST(COALESCE(SUM(o.TOTAL_AMOUNT), 0) AS NUMERIC(18,2)) as total_revenue,
                CAST(COALESCE(AVG(CAST(DATEDIFF(SECOND, o.CREATED_AT, o.UPDATED_AT) AS DOUBLE PRECISION) / 60.0), 0) AS NUMERIC(18,2)) as avg_duration
            FROM ORDERS o
            WHERE o.ORDER_TYPE = 'on_site'
                AND o.CREATED_AT >= ?
                AND o.CREATED_AT < ?
        """, (start_datetime, end_datetime))
        
        summary_row = cur.fetchone()
        # ALTERAÇÃO: Tratar valores NULL do resultado de forma segura
        if summary_row is None or len(summary_row) < 4:
            used_tables = total_orders = 0
            total_revenue = avg_duration = 0.0
        else:
            used_tables = int(summary_row[0]) if summary_row[0] is not None else 0
            total_orders = int(summary_row[1]) if summary_row[1] is not None else 0
            total_revenue = float(summary_row[2]) if summary_row[2] is not None else 0.0
            avg_duration = float(summary_row[3]) if summary_row[3] is not None else 0.0
        
        occupancy_rate = safe_divide(used_tables, total_tables, 0) * 100 if total_tables > 0 else 0
        
        # 2. PERFORMANCE POR MESA
        # ALTERAÇÃO: Corrigir consulta SQL para tratar NULLs e usar filtro correto no LEFT JOIN
        join_clause = " AND ".join(conditions)
        cur.execute(f"""
            SELECT rt.NAME,
                   CAST(COUNT(CASE WHEN o.ID IS NOT NULL THEN o.ID END) AS INTEGER) as order_count,
                   CAST(COALESCE(SUM(CASE WHEN o.ID IS NOT NULL THEN o.TOTAL_AMOUNT END), 0) AS NUMERIC(18,2)) as revenue,
                   CAST(COALESCE(AVG(CASE WHEN o.ID IS NOT NULL THEN CAST(DATEDIFF(SECOND, o.CREATED_AT, o.UPDATED_AT) AS DOUBLE PRECISION) / 60.0 END), 0) AS NUMERIC(18,2)) as avg_duration
            FROM RESTAURANT_TABLES rt
            LEFT JOIN ORDERS o ON rt.ID = o.TABLE_ID AND {join_clause}
            GROUP BY rt.ID, rt.NAME
            ORDER BY revenue DESC NULLS LAST
        """, tuple(params))
        
        tables_performance = []
        for row in cur.fetchall():
            if row and len(row) >= 4:
                tables_performance.append({
                    'name': row[0] or 'N/A',
                    'order_count': int(row[1]) if row[1] is not None else 0,
                    'revenue': float(row[2]) if row[2] is not None else 0.0,
                    'avg_duration': float(row[3]) if row[3] is not None else 0.0
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
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        cur.execute("""
            SELECT CAST(COALESCE(SUM(fm.FINANCIAL_VALUE), 0) AS NUMERIC(18,2)) as total_revenue
            FROM FINANCIAL_MOVEMENTS fm
            WHERE fm.MOVEMENT_TYPE = 'REVENUE'
            AND fm.MOVEMENT_DATE >= ? AND fm.MOVEMENT_DATE < ?
            AND fm.PAYMENT_STATUS = 'Paid'
        """, (start_datetime, end_datetime))
        revenue_row = cur.fetchone()
        total_revenue = float(revenue_row[0] or 0) if revenue_row and revenue_row[0] is not None else 0.0
        
        # Pedidos
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        cur.execute("""
            SELECT CAST(COUNT(*) AS INTEGER) as total_orders,
                   CAST(COALESCE(AVG(TOTAL_AMOUNT), 0) AS NUMERIC(18,2)) as avg_ticket
            FROM ORDERS
            WHERE CREATED_AT >= ? AND CREATED_AT < ?
            AND STATUS NOT IN ('cancelled')
        """, (start_datetime, end_datetime))
        orders_row = cur.fetchone()
        total_orders = int(orders_row[0] or 0) if orders_row and orders_row[0] is not None else 0
        avg_ticket = float(orders_row[1] or 0) if orders_row and orders_row[1] is not None else 0.0
        
        # Lucro
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        cur.execute("""
            SELECT 
                CAST(COALESCE(SUM(CASE WHEN fm.MOVEMENT_TYPE = 'REVENUE' THEN fm.FINANCIAL_VALUE ELSE 0 END), 0) AS NUMERIC(18,2)) as revenue,
                CAST(COALESCE(SUM(CASE WHEN fm.MOVEMENT_TYPE IN ('EXPENSE', 'CMV', 'TAX') THEN fm.FINANCIAL_VALUE ELSE 0 END), 0) AS NUMERIC(18,2)) as expenses
            FROM FINANCIAL_MOVEMENTS fm
            WHERE fm.MOVEMENT_DATE >= ? AND fm.MOVEMENT_DATE < ?
            AND fm.PAYMENT_STATUS = 'Paid'
        """, (start_datetime, end_datetime))
        profit_row = cur.fetchone()
        revenue = float(profit_row[0] or 0) if profit_row and profit_row[0] is not None else 0.0
        expenses = float(profit_row[1] or 0) if profit_row and profit_row[1] is not None else 0.0
        net_profit = revenue - expenses
        
        # 2. TOP 5 PRODUTOS
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        cur.execute("""
            SELECT CAST(p.NAME AS VARCHAR(255)) as name,
                   CAST(COALESCE(SUM(oi.QUANTITY), 0) AS INTEGER) as total_quantity
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
                'name': row[0] or 'N/A' if row[0] is not None else 'N/A',
                'quantity': int(row[1] or 0) if row[1] is not None else 0
            })
        
        # 3. TOP 5 CLIENTES
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        cur.execute("""
            SELECT CAST(u.FULL_NAME AS VARCHAR(255)) as full_name,
                   CAST(COALESCE(SUM(o.TOTAL_AMOUNT), 0) AS NUMERIC(18,2)) as total_spent
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
                'name': row[0] or 'N/A' if row[0] is not None else 'N/A',
                'spent': float(row[1] or 0) if row[1] is not None else 0.0
            })
        
        # 4. ALERTAS (estoque baixo)
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        cur.execute("""
            SELECT CAST(COUNT(*) AS INTEGER) as low_stock_count
            FROM INGREDIENTS
            WHERE STOCK_STATUS IN ('low', 'out_of_stock')
        """)
        alert_row = cur.fetchone()
        low_stock_count = int(alert_row[0] or 0) if alert_row and alert_row[0] is not None else 0
        
        # 5. COMPARAÇÃO COM PERÍODO ANTERIOR
        period_days = (end_dt - start_dt).days
        prev_start_dt = start_dt - timedelta(days=period_days)
        prev_end_dt = start_dt
        
        prev_start_datetime = datetime.combine(prev_start_dt.date(), datetime.min.time()) if isinstance(prev_start_dt, date) else prev_start_dt
        prev_end_datetime = datetime.combine(prev_end_dt.date() + timedelta(days=1), datetime.min.time()) if isinstance(prev_end_dt, date) else prev_end_dt
        
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        cur.execute("""
            SELECT CAST(COALESCE(SUM(fm.FINANCIAL_VALUE), 0) AS NUMERIC(18,2)) as total_revenue
            FROM FINANCIAL_MOVEMENTS fm
            WHERE fm.MOVEMENT_TYPE = 'REVENUE'
            AND fm.MOVEMENT_DATE >= ? AND fm.MOVEMENT_DATE < ?
            AND fm.PAYMENT_STATUS = 'Paid'
        """, (prev_start_datetime, prev_end_datetime))
        prev_revenue_row = cur.fetchone()
        prev_revenue = float(prev_revenue_row[0] or 0) if prev_revenue_row and prev_revenue_row[0] is not None else 0.0
        
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
            # ALTERAÇÃO: Comparar diretamente com BOOLEAN (Firebird aceita TRUE/FALSE diretamente)
            conditions.append("fm.RECONCILED = ?")
            params.append(reconciled)
        
        where_clause = " AND ".join(conditions)
        
        # 1. RESUMO DE CONCILIAÇÃO
        # CORREÇÃO: Adicionar CASTs explícitos para evitar erro SQLDA -804
        # ALTERAÇÃO: Usar comparação direta com BOOLEAN (TRUE/FALSE) ao invés de CAST para INTEGER
        cur.execute(f"""
            SELECT 
                CAST(COUNT(*) AS INTEGER) as total_movements,
                CAST(COUNT(CASE WHEN fm.RECONCILED = TRUE THEN 1 END) AS INTEGER) as reconciled_count,
                CAST(COUNT(CASE WHEN fm.RECONCILED = FALSE OR fm.RECONCILED IS NULL THEN 1 END) AS INTEGER) as pending_count,
                CAST(COALESCE(SUM(CASE WHEN fm.RECONCILED = TRUE THEN fm.FINANCIAL_VALUE ELSE 0 END), 0) AS NUMERIC(18,2)) as reconciled_amount,
                CAST(COALESCE(SUM(CASE WHEN fm.RECONCILED = FALSE OR fm.RECONCILED IS NULL THEN fm.FINANCIAL_VALUE ELSE 0 END), 0) AS NUMERIC(18,2)) as pending_amount
            FROM FINANCIAL_MOVEMENTS fm
            WHERE {where_clause}
        """, tuple(params))
        
        summary_row = cur.fetchone()
        total_movements = int(summary_row[0] or 0) if summary_row and summary_row[0] is not None else 0
        reconciled_count = int(summary_row[1] or 0) if summary_row and summary_row[1] is not None else 0
        pending_count = int(summary_row[2] or 0) if summary_row and summary_row[2] is not None else 0
        reconciled_amount = float(summary_row[3] or 0) if summary_row and summary_row[3] is not None else 0.0
        pending_amount = float(summary_row[4] or 0) if summary_row and summary_row[4] is not None else 0.0
        
        # 2. MOVIMENTAÇÕES PENDENTES DE CONCILIAÇÃO
        # ALTERAÇÃO: Comparar diretamente com BOOLEAN FALSE ao invés de CAST para INTEGER
        cur.execute(f"""
            SELECT fm.ID, fm.MOVEMENT_TYPE, fm.FINANCIAL_VALUE, fm.DESCRIPTION,
                   fm.MOVEMENT_DATE, fm.PAYMENT_GATEWAY_ID, fm.TRANSACTION_ID,
                   fm.BANK_ACCOUNT, fm.CREATED_AT
            FROM FINANCIAL_MOVEMENTS fm
            WHERE {where_clause} AND (fm.RECONCILED = FALSE OR fm.RECONCILED IS NULL)
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

