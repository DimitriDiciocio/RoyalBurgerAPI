import fdb  
import logging
from datetime import datetime, date, timedelta
from ..database import get_db_connection

logger = logging.getLogger(__name__)  

def get_dashboard_metrics():  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        
        # OTIMIZAÇÃO: Calcular range de datas (substitui DATE() por range para usar índices)
        today = date.today()  
        start_datetime = datetime.combine(today, datetime.min.time())
        end_datetime = datetime.combine(today + timedelta(days=1), datetime.min.time())
        
        # OTIMIZAÇÃO: Query única consolidada para métricas principais (substitui 6 queries)
        metrics_query = """
            SELECT
                -- Total de pedidos hoje
                (SELECT COUNT(*) FROM ORDERS 
                 WHERE CREATED_AT >= ? AND CREATED_AT < ?) as total_orders,
                
                -- Receita hoje (sem cancelados)
                (SELECT COALESCE(SUM(TOTAL_AMOUNT), 0) FROM ORDERS 
                 WHERE CREATED_AT >= ? AND CREATED_AT < ? AND STATUS != 'cancelled') as revenue,
                
                -- Ticket médio hoje
                (SELECT COALESCE(AVG(TOTAL_AMOUNT), 0) FROM ORDERS 
                 WHERE CREATED_AT >= ? AND CREATED_AT < ? AND STATUS != 'cancelled') as avg_ticket,
                
                -- Pedidos entregues hoje
                (SELECT COUNT(*) FROM ORDERS 
                 WHERE CREATED_AT >= ? AND CREATED_AT < ? AND STATUS = 'delivered') as completed,
                
                -- Pedidos cancelados hoje
                (SELECT COUNT(*) FROM ORDERS 
                 WHERE CREATED_AT >= ? AND CREATED_AT < ? AND STATUS = 'cancelled') as cancelled,
                
                -- Tempo médio de preparo (em minutos)
                (SELECT COALESCE(AVG(EXTRACT(EPOCH FROM (UPDATED_AT - CREATED_AT))/60), 0)
                 FROM ORDERS 
                 WHERE CREATED_AT >= ? AND CREATED_AT < ?
                   AND STATUS = 'delivered' AND UPDATED_AT IS NOT NULL) as avg_prep_time,
                
                -- Pedidos em andamento (não precisa de data)
                (SELECT COUNT(*) FROM ORDERS 
                 WHERE STATUS IN ('pending', 'confirmed', 'preparing', 'ready', 'out_for_delivery')) as ongoing,
                
                -- Estoque baixo
                (SELECT COUNT(*) FROM INGREDIENTS 
                 WHERE CURRENT_STOCK <= MIN_STOCK_THRESHOLD) as low_stock
            FROM RDB$DATABASE
        """
        
        # Executar query consolidada (5 subconsultas de hoje, cada uma com 2 parâmetros = 10 parâmetros)
        params = (start_datetime, end_datetime) * 5
        cur.execute(metrics_query, params)
        metrics_row = cur.fetchone()
        
        # Query separada para distribuição por tipo (mais simples que consolidar)
        cur.execute("""
            SELECT ORDER_TYPE, COUNT(*) 
            FROM ORDERS 
            WHERE CREATED_AT >= ? AND CREATED_AT < ?
            GROUP BY ORDER_TYPE
        """, (start_datetime, end_datetime))
        order_distribution = {row[0]: row[1] for row in cur.fetchall()}
        
        # Query separada para pedidos recentes (usando FIRST ao invés de LIMIT no Firebird)
        cur.execute("""
            SELECT FIRST 5 ID, TOTAL_AMOUNT, STATUS, ORDER_TYPE, CREATED_AT
            FROM ORDERS 
            ORDER BY CREATED_AT DESC
        """)
        recent_orders = []
        for row in cur.fetchall():  
            recent_orders.append({  
                "id": row[0],
                "total_amount": float(row[1]) if row[1] else 0.0,
                "status": row[2],
                "order_type": row[3],
                "created_at": row[4].isoformat() if row[4] else None
            })
        
        return {  
            "total_orders_today": metrics_row[0] or 0,
            "revenue_today": float(metrics_row[1]) if metrics_row[1] else 0.0,
            "average_ticket": round(float(metrics_row[2]) if metrics_row[2] else 0.0, 2),
            "average_preparation_time": round(float(metrics_row[5]) if metrics_row[5] else 0.0, 1),
            "completed_orders": metrics_row[3] or 0,
            "ongoing_orders": metrics_row[6] or 0,
            "low_stock_items_count": metrics_row[7] or 0,
            "cancelled_orders": metrics_row[4] or 0,
            "order_distribution": order_distribution,
            "recent_orders": recent_orders
        }
    except fdb.Error as e:  
        logger.error(f"Erro ao buscar métricas do dashboard: {e}", exc_info=True)  
        return {  
            "total_orders_today": 0,
            "revenue_today": 0.0,
            "average_ticket": 0.0,
            "average_preparation_time": 0.0,
            "completed_orders": 0,
            "ongoing_orders": 0,
            "low_stock_items_count": 0,
            "cancelled_orders": 0,
            "order_distribution": {},
            "recent_orders": []
        }
    finally:  
        if conn: conn.close()  
