import fdb  # importa driver do Firebird
from datetime import datetime, date  # importa classes de data
from ..database import get_db_connection  # importa função de conexão com o banco

def get_dashboard_metrics():  # função para obter métricas do dashboard
    conn = None  # inicializa conexão
    try:  # tenta buscar métricas
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        today = date.today()  # data atual
        cur.execute("""
            SELECT COUNT(*) 
            FROM ORDERS 
            WHERE DATE(CREATED_AT) = ?
        """, (today,))  # conta pedidos do dia
        total_orders_today = cur.fetchone()[0]  # extrai total de pedidos
        cur.execute("""
            SELECT COALESCE(SUM(TOTAL_AMOUNT), 0) 
            FROM ORDERS 
            WHERE DATE(CREATED_AT) = ? AND STATUS != 'cancelled'
        """, (today,))  # soma receita do dia (exclui cancelados)
        revenue_today = float(cur.fetchone()[0])  # extrai receita
        cur.execute("""
            SELECT COALESCE(AVG(TOTAL_AMOUNT), 0) 
            FROM ORDERS 
            WHERE DATE(CREATED_AT) = ? AND STATUS != 'cancelled'
        """, (today,))  # calcula ticket médio do dia
        average_ticket = float(cur.fetchone()[0])  # extrai ticket médio
        cur.execute("""
            SELECT COALESCE(AVG(EXTRACT(EPOCH FROM (UPDATED_AT - CREATED_AT))/60), 0)
            FROM ORDERS 
            WHERE DATE(CREATED_AT) = ? AND STATUS = 'delivered' AND UPDATED_AT IS NOT NULL
        """, (today,))  # calcula tempo médio de preparo em minutos
        avg_prep_time = float(cur.fetchone()[0])  # extrai tempo médio
        cur.execute("""
            SELECT COUNT(*) 
            FROM ORDERS 
            WHERE DATE(CREATED_AT) = ? AND STATUS = 'delivered'
        """, (today,))  # conta pedidos entregues no dia
        completed_orders = cur.fetchone()[0]  # extrai total entregues
        cur.execute("""
            SELECT COUNT(*) 
            FROM ORDERS 
            WHERE STATUS IN ('pending', 'confirmed', 'preparing', 'ready', 'out_for_delivery')
        """)  # conta pedidos em andamento
        ongoing_orders = cur.fetchone()[0]  # extrai total em andamento
        cur.execute("""
            SELECT COUNT(*) 
            FROM ORDERS 
            WHERE DATE(CREATED_AT) = ? AND STATUS = 'cancelled'
        """, (today,))  # conta pedidos cancelados no dia
        cancelled_orders = cur.fetchone()[0]  # extrai total cancelados
        cur.execute("""
            SELECT COUNT(*) 
            FROM INGREDIENTS 
            WHERE CURRENT_STOCK <= MIN_STOCK_THRESHOLD
        """)  # conta ingredientes com estoque baixo
        low_stock_items_count = cur.fetchone()[0]  # extrai total com baixo estoque
        cur.execute("""
            SELECT ORDER_TYPE, COUNT(*) 
            FROM ORDERS 
            WHERE DATE(CREATED_AT) = ?
            GROUP BY ORDER_TYPE
        """, (today,))  # agrupa pedidos por tipo
        order_distribution = {row[0]: row[1] for row in cur.fetchall()}  # monta distribuição por canal
        cur.execute("""
            SELECT ID, TOTAL_AMOUNT, STATUS, ORDER_TYPE, CREATED_AT
            FROM ORDERS 
            ORDER BY CREATED_AT DESC 
            LIMIT 5
        """)  # busca últimos 5 pedidos
        recent_orders = []  # lista de pedidos recentes
        for row in cur.fetchall():  # itera resultados
            recent_orders.append({  # monta dicionário do pedido
                "id": row[0],
                "total_amount": float(row[1]),
                "status": row[2],
                "order_type": row[3],
                "created_at": row[4].isoformat() if row[4] else None
            })
        return {  # retorna métricas consolidadas
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
    except fdb.Error as e:  # captura erros do banco
        print(f"Erro ao buscar métricas do dashboard: {e}")  # exibe erro
        return {  # retorna estrutura padrão em caso de erro
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
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão
