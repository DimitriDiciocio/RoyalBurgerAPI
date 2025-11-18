"""
Funções auxiliares para relatórios financeiros (CMV e Impostos)
Separado para manter o código organizado
"""

import fdb
import logging
from datetime import datetime, date, timedelta
from ..database import get_db_connection
from ..utils.report_formatters import calculate_growth_percentage, safe_divide
from ..utils.chart_generators import generate_bar_chart, generate_pie_chart
from ..utils.report_validators import validate_filters, validate_date_range

logger = logging.getLogger(__name__)


def generate_cmv_report(filters=None):
    """
    Gera relatório de CMV (Custo das Mercadorias Vendidas)
    
    Args:
        filters: dict com filtros (start_date, end_date, category_id, product_id)
    
    Returns:
        dict: Dados do relatório para geração de PDF
    """
    conn = None
    try:
        # Valida filtros
        allowed_filters = {
            'start_date': {'type': 'date', 'required': False},
            'end_date': {'type': 'date', 'required': False, 'max_days': 365},
            'category_id': {'type': 'id', 'required': False},
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
        
        if not start_dt:
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(days=30)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        start_datetime = datetime.combine(start_dt.date(), datetime.min.time()) if isinstance(start_dt, date) else start_dt
        end_datetime = datetime.combine(end_dt.date() + timedelta(days=1), datetime.min.time()) if isinstance(end_dt, date) else end_dt
        
        # 1. CMV TOTAL E POR PERÍODO
        conditions = ["fm.TYPE = 'CMV'", "fm.PAYMENT_STATUS = 'Paid'", 
                     "fm.MOVEMENT_DATE >= ?", "fm.MOVEMENT_DATE < ?"]
        params = [start_datetime, end_datetime]
        
        cur.execute(f"""
            SELECT 
                SUM(fm."VALUE") as total_cmv,
                COUNT(*) as total_movements
            FROM FINANCIAL_MOVEMENTS fm
            WHERE {' AND '.join(conditions)}
        """, tuple(params))
        
        cmv_row = cur.fetchone()
        total_cmv = float(cmv_row[0] or 0)
        total_movements = cmv_row[1] or 0
        
        # 2. CMV POR CATEGORIA DE INGREDIENTE
        cur.execute(f"""
            SELECT fm.CATEGORY,
                   SUM(fm."VALUE") as total_cmv
            FROM FINANCIAL_MOVEMENTS fm
            WHERE {' AND '.join(conditions)}
            GROUP BY fm.CATEGORY
            ORDER BY total_cmv DESC
        """, tuple(params))
        
        cmv_by_category = []
        for row in cur.fetchall():
            cmv_by_category.append({
                'category': row[0] or 'N/A',
                'total': float(row[1] or 0)
            })
        
        # 3. CMV POR PRODUTO (via ORDER_ITEMS)
        product_conditions = ["o.CREATED_AT >= ?", "o.CREATED_AT < ?", "o.STATUS NOT IN ('cancelled')"]
        product_params = [start_datetime, end_datetime]
        
        if validated_filters.get('product_id'):
            product_conditions.append("oi.PRODUCT_ID = ?")
            product_params.append(validated_filters['product_id'])
        
        if validated_filters.get('category_id'):
            product_conditions.append("p.SECTION_ID = ?")
            product_params.append(validated_filters['category_id'])
        
        cur.execute(f"""
            SELECT p.NAME,
                   SUM(oi.QUANTITY) as total_quantity,
                   SUM(oi.QUANTITY * p.COST_PRICE) as total_cmv
            FROM ORDER_ITEMS oi
            JOIN ORDERS o ON oi.ORDER_ID = o.ID
            JOIN PRODUCTS p ON oi.PRODUCT_ID = p.ID
            WHERE {' AND '.join(product_conditions)}
            GROUP BY p.ID, p.NAME
            ORDER BY total_cmv DESC
            ROWS 20
        """, tuple(product_params))
        
        cmv_by_product = []
        for row in cur.fetchall():
            cmv_by_product.append({
                'product': row[0],
                'quantity': int(row[1] or 0),
                'cmv': float(row[2] or 0)
            })
        
        # 4. COMPARAÇÃO CMV vs RECEITA
        cur.execute("""
            SELECT 
                SUM(CASE WHEN fm.TYPE = 'CMV' THEN fm."VALUE" ELSE 0 END) as total_cmv,
                SUM(CASE WHEN fm.TYPE = 'REVENUE' THEN fm."VALUE" ELSE 0 END) as total_revenue
            FROM FINANCIAL_MOVEMENTS fm
            WHERE fm.MOVEMENT_DATE >= ? AND fm.MOVEMENT_DATE < ?
            AND fm.PAYMENT_STATUS = 'Paid'
        """, (start_datetime, end_datetime))
        
        comparison_row = cur.fetchone()
        cmv_total = float(comparison_row[0] or 0)
        revenue_total = float(comparison_row[1] or 0)
        cmv_percentage = safe_divide(cmv_total, revenue_total, 0) * 100 if revenue_total > 0 else 0
        
        # Prepara dados para gráficos
        chart_data = {}
        
        if cmv_by_category:
            chart_data['cmv_by_category'] = generate_bar_chart(
                data={'labels': [item['category'][:20] for item in cmv_by_category],
                      'values': [item['total'] for item in cmv_by_category]},
                title='CMV por Categoria',
                x_label='Categoria',
                y_label='CMV (R$)',
                horizontal=True
            )
        
        if cmv_by_product:
            chart_data['cmv_by_product'] = generate_bar_chart(
                data={'labels': [item['product'][:20] for item in cmv_by_product[:10]],
                      'values': [item['cmv'] for item in cmv_by_product[:10]]},
                title='Top 10 Produtos por CMV',
                x_label='Produto',
                y_label='CMV (R$)',
                horizontal=True
            )
        
        return {
            'summary': {
                'total_cmv': total_cmv,
                'total_movements': total_movements,
                'cmv_percentage': cmv_percentage,
                'revenue_total': revenue_total
            },
            'cmv_by_category': cmv_by_category,
            'cmv_by_product': cmv_by_product,
            'charts': chart_data,
            'period': {
                'start_date': start_dt.isoformat() if isinstance(start_dt, date) else start_dt.strftime('%Y-%m-%d'),
                'end_date': end_dt.isoformat() if isinstance(end_dt, date) else end_dt.strftime('%Y-%m-%d')
            },
            'filters': validated_filters
        }
        
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar relatório de CMV: {e}")
        raise
    except fdb.Error as e:
        logger.error(f"Erro ao gerar relatório de CMV: {e}", exc_info=True)
        raise Exception("Erro interno do servidor ao gerar relatório")
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar relatório de CMV: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def generate_taxes_report_data(filters=None):
    """
    Gera dados para relatório de impostos e taxas
    
    Args:
        filters: dict com filtros (start_date, end_date, category, status)
    
    Returns:
        dict: Dados do relatório para geração de PDF
    """
    conn = None
    try:
        # Valida filtros
        allowed_filters = {
            'start_date': {'type': 'date', 'required': False},
            'end_date': {'type': 'date', 'required': False, 'max_days': 365},
            'category': {'type': 'string', 'required': False},
            'status': {'type': 'enum', 'values': ['Pending', 'Paid'], 'required': False}
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
        conditions = ["fm.TYPE = 'TAX'"]
        params = []
        
        if validated_filters.get('status') == 'Paid':
            conditions.append("fm.MOVEMENT_DATE >= ?")
            conditions.append("fm.MOVEMENT_DATE < ?")
            conditions.append("fm.PAYMENT_STATUS = 'Paid'")
            params.extend([start_datetime, end_datetime])
        else:
            # Para Pending, usa CREATED_AT
            conditions.append("COALESCE(fm.MOVEMENT_DATE, fm.CREATED_AT) >= ?")
            conditions.append("COALESCE(fm.MOVEMENT_DATE, fm.CREATED_AT) < ?")
            params.extend([start_datetime, end_datetime])
            if validated_filters.get('status'):
                conditions.append("fm.PAYMENT_STATUS = ?")
                params.append(validated_filters['status'])
        
        if validated_filters.get('category'):
            conditions.append("fm.CATEGORY = ?")
            params.append(validated_filters['category'])
        
        where_clause = " AND ".join(conditions)
        
        # 1. TOTAL DE IMPOSTOS
        cur.execute(f"""
            SELECT 
                SUM(fm."VALUE") as total_taxes,
                COUNT(*) as total_movements,
                SUM(CASE WHEN fm.PAYMENT_STATUS = 'Paid' THEN fm."VALUE" ELSE 0 END) as paid_taxes,
                SUM(CASE WHEN fm.PAYMENT_STATUS = 'Pending' THEN fm."VALUE" ELSE 0 END) as pending_taxes
            FROM FINANCIAL_MOVEMENTS fm
            WHERE {where_clause}
        """, tuple(params))
        
        summary_row = cur.fetchone()
        total_taxes = float(summary_row[0] or 0)
        total_movements = summary_row[1] or 0
        paid_taxes = float(summary_row[2] or 0)
        pending_taxes = float(summary_row[3] or 0)
        
        # 2. IMPOSTOS POR CATEGORIA
        # CORREÇÃO: "count" é palavra reservada, usar alias diferente
        cur.execute(f"""
            SELECT fm.CATEGORY,
                   CAST(COALESCE(SUM(fm."VALUE"), 0) AS NUMERIC(18,2)) as total,
                   CAST(COUNT(*) AS INTEGER) as category_count
            FROM FINANCIAL_MOVEMENTS fm
            WHERE {where_clause}
            GROUP BY fm.CATEGORY
            ORDER BY total DESC
        """, tuple(params))
        
        taxes_by_category = []
        for row in cur.fetchall():
            taxes_by_category.append({
                'category': row[0] or 'N/A',
                'total': float(row[1] or 0),
                'count': row[2]
            })
        
        # 3. IMPOSTOS RECORRENTES (RECURRING_TAXES)
        cur.execute("""
            SELECT rt.NAME, rt.AMOUNT, rt.FREQUENCY, rt.IS_ACTIVE
            FROM RECURRING_TAXES rt
            ORDER BY rt.IS_ACTIVE DESC, rt.NAME
        """)
        
        recurring_taxes = []
        for row in cur.fetchall():
            recurring_taxes.append({
                'name': row[0] or 'N/A',
                'amount': float(row[1] or 0),
                'frequency': row[2] or 'N/A',
                'is_active': bool(row[3])
            })
        
        # 4. IMPACTO NA RECEITA
        cur.execute("""
            SELECT SUM(fm."VALUE") as total_revenue
            FROM FINANCIAL_MOVEMENTS fm
            WHERE fm.TYPE = 'REVENUE'
            AND fm.MOVEMENT_DATE >= ? AND fm.MOVEMENT_DATE < ?
            AND fm.PAYMENT_STATUS = 'Paid'
        """, (start_datetime, end_datetime))
        
        revenue_row = cur.fetchone()
        total_revenue = float(revenue_row[0] or 0)
        tax_impact = safe_divide(total_taxes, total_revenue, 0) * 100 if total_revenue > 0 else 0
        
        # Prepara dados para gráficos
        chart_data = {}
        
        if taxes_by_category:
            chart_data['taxes_by_category'] = generate_pie_chart(
                data={'labels': [item['category'] for item in taxes_by_category],
                      'values': [item['total'] for item in taxes_by_category]},
                title='Impostos por Categoria'
            )
        
        return {
            'summary': {
                'total_taxes': total_taxes,
                'total_movements': total_movements,
                'paid_taxes': paid_taxes,
                'pending_taxes': pending_taxes,
                'tax_impact': tax_impact,
                'total_revenue': total_revenue
            },
            'taxes_by_category': taxes_by_category,
            'recurring_taxes': recurring_taxes,
            'charts': chart_data,
            'period': {
                'start_date': start_dt.isoformat() if isinstance(start_dt, date) else start_dt.strftime('%Y-%m-%d'),
                'end_date': end_dt.isoformat() if isinstance(end_dt, date) else end_dt.strftime('%Y-%m-%d')
            },
            'filters': validated_filters
        }
        
    except ValueError as e:
        logger.error(f"Erro de validação ao gerar relatório de impostos: {e}")
        raise
    except fdb.Error as e:
        logger.error(f"Erro ao gerar relatório de impostos: {e}", exc_info=True)
        raise Exception("Erro interno do servidor ao gerar relatório")
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar relatório de impostos: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()

