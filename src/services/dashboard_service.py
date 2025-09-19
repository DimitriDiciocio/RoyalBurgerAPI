# src/services/dashboard_service.py

import fdb
from datetime import datetime, date
from ..database import get_db_connection


def get_dashboard_metrics():
    """Retorna as métricas principais do dashboard para o dia atual."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        today = date.today()
        
        # Total de pedidos hoje
        cur.execute("""
            SELECT COUNT(*) 
            FROM ORDERS 
            WHERE DATE(CREATED_AT) = ?
        """, (today,))
        total_orders_today = cur.fetchone()[0]
        
        # Receita hoje
        cur.execute("""
            SELECT COALESCE(SUM(TOTAL_AMOUNT), 0) 
            FROM ORDERS 
            WHERE DATE(CREATED_AT) = ? AND STATUS != 'cancelled'
        """, (today,))
        revenue_today = float(cur.fetchone()[0])
        
        # Ticket médio hoje
        cur.execute("""
            SELECT COALESCE(AVG(TOTAL_AMOUNT), 0) 
            FROM ORDERS 
            WHERE DATE(CREATED_AT) = ? AND STATUS != 'cancelled'
        """, (today,))
        average_ticket = float(cur.fetchone()[0])
        
        # Tempo médio de preparo (baseado nos pedidos concluídos)
        cur.execute("""
            SELECT COALESCE(AVG(EXTRACT(EPOCH FROM (UPDATED_AT - CREATED_AT))/60), 0)
            FROM ORDERS 
            WHERE DATE(CREATED_AT) = ? AND STATUS = 'delivered' AND UPDATED_AT IS NOT NULL
        """, (today,))
        avg_prep_time = float(cur.fetchone()[0])
        
        # Pedidos concluídos hoje
        cur.execute("""
            SELECT COUNT(*) 
            FROM ORDERS 
            WHERE DATE(CREATED_AT) = ? AND STATUS = 'delivered'
        """, (today,))
        completed_orders = cur.fetchone()[0]
        
        # Pedidos em andamento
        cur.execute("""
            SELECT COUNT(*) 
            FROM ORDERS 
            WHERE STATUS IN ('pending', 'confirmed', 'preparing', 'ready', 'out_for_delivery')
        """)
        ongoing_orders = cur.fetchone()[0]
        
        # Pedidos cancelados hoje
        cur.execute("""
            SELECT COUNT(*) 
            FROM ORDERS 
            WHERE DATE(CREATED_AT) = ? AND STATUS = 'cancelled'
        """, (today,))
        cancelled_orders = cur.fetchone()[0]
        
        # Itens com estoque baixo
        cur.execute("""
            SELECT COUNT(*) 
            FROM INGREDIENTS 
            WHERE CURRENT_STOCK <= MIN_STOCK_THRESHOLD
        """)
        low_stock_items_count = cur.fetchone()[0]
        
        # Distribuição por canal
        cur.execute("""
            SELECT ORDER_TYPE, COUNT(*) 
            FROM ORDERS 
            WHERE DATE(CREATED_AT) = ?
            GROUP BY ORDER_TYPE
        """, (today,))
        order_distribution = {row[0]: row[1] for row in cur.fetchall()}
        
        # Pedidos recentes (últimos 5)
        cur.execute("""
            SELECT ID, TOTAL_AMOUNT, STATUS, ORDER_TYPE, CREATED_AT
            FROM ORDERS 
            ORDER BY CREATED_AT DESC 
            LIMIT 5
        """)
        recent_orders = []
        for row in cur.fetchall():
            recent_orders.append({
                "id": row[0],
                "total_amount": float(row[1]),
                "status": row[2],
                "order_type": row[3],
                "created_at": row[4].isoformat() if row[4] else None
            })
        
        return {
            "total_orders_today": total_orders_today,
            "revenue_today": revenue_today,
            "average_ticket": round(average_ticket, 2),
            "average_preparation_time": round(avg_prep_time, 1),
            "completed_orders": completed_orders,
            "ongoing_orders": ongoing_orders,
            "low_stock_items_count": low_stock_items_count,
            "cancelled_orders": cancelled_orders,
            "order_distribution": order_distribution,
            "recent_orders": recent_orders
        }
        
    except fdb.Error as e:
        print(f"Erro ao buscar métricas do dashboard: {e}")
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
