import fdb  
import logging
from datetime import datetime, date, timedelta
from ..database import get_db_connection
from . import settings_service  # ALTERAÇÃO: Import para buscar meta mensal

logger = logging.getLogger(__name__)

# OTIMIZAÇÃO DE PERFORMANCE: Cache de métricas do dashboard
_dashboard_metrics_cache = None
_dashboard_cache_timestamp = None
_dashboard_cache_ttl = 60  # 1 minuto de TTL (métricas mudam frequentemente)

def _is_dashboard_cache_valid():
    """Verifica se o cache de métricas ainda é válido"""
    global _dashboard_cache_timestamp
    if _dashboard_cache_timestamp is None:
        return False
    elapsed = (datetime.now() - _dashboard_cache_timestamp).total_seconds()
    return elapsed < _dashboard_cache_ttl

def _invalidate_dashboard_cache():
    """Invalida o cache de métricas forçando refresh na próxima chamada"""
    global _dashboard_metrics_cache, _dashboard_cache_timestamp
    _dashboard_metrics_cache = None
    _dashboard_cache_timestamp = None  

def get_dashboard_metrics():  
    """
    Retorna métricas do dashboard com cache de 1 minuto para melhor performance.
    Métricas são atualizadas frequentemente, então TTL curto é apropriado.
    """
    global _dashboard_metrics_cache, _dashboard_cache_timestamp
    
    # OTIMIZAÇÃO: Verifica cache antes de consultar banco
    if _is_dashboard_cache_valid() and _dashboard_metrics_cache is not None:
        return _dashboard_metrics_cache
    
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        
        # OTIMIZAÇÃO: Calcular range de datas (substitui DATE() por range para usar índices)
        today = date.today()  
        start_datetime = datetime.combine(today, datetime.min.time())
        end_datetime = datetime.combine(today + timedelta(days=1), datetime.min.time())
        
        # OTIMIZAÇÃO: Query única consolidada para métricas principais (substitui 5 queries)
        # ALTERAÇÃO: Tempo médio de preparo calculado separadamente para evitar problemas de tipo SQLDA
        # ALTERAÇÃO: CASTs explícitos em todos os campos numéricos para evitar erro SQLDA
        metrics_query = """
            SELECT
                -- Total de pedidos hoje
                CAST((SELECT COUNT(*) FROM ORDERS 
                 WHERE CREATED_AT >= ? AND CREATED_AT < ?) AS INTEGER) as total_orders,
                
                -- Receita hoje (sem cancelados) - CAST explícito para evitar erro SQLDA
                CAST((SELECT COALESCE(SUM(TOTAL_AMOUNT), 0) FROM ORDERS 
                 WHERE CREATED_AT >= ? AND CREATED_AT < ? AND STATUS != 'cancelled') AS NUMERIC(18,2)) as revenue,
                
                -- Ticket médio hoje - CAST explícito para evitar erro SQLDA
                CAST((SELECT COALESCE(AVG(TOTAL_AMOUNT), 0) FROM ORDERS 
                 WHERE CREATED_AT >= ? AND CREATED_AT < ? AND STATUS != 'cancelled') AS NUMERIC(18,2)) as avg_ticket,
                
                -- Pedidos entregues hoje
                CAST((SELECT COUNT(*) FROM ORDERS 
                 WHERE CREATED_AT >= ? AND CREATED_AT < ? AND STATUS = 'delivered') AS INTEGER) as completed,
                
                -- Pedidos cancelados hoje
                CAST((SELECT COUNT(*) FROM ORDERS 
                 WHERE CREATED_AT >= ? AND CREATED_AT < ? AND STATUS = 'cancelled') AS INTEGER) as cancelled,
                
                -- Pedidos em andamento (não precisa de data)
                CAST((SELECT COUNT(*) FROM ORDERS 
                 WHERE STATUS IN ('pending', 'confirmed', 'preparing', 'ready', 'out_for_delivery')) AS INTEGER) as ongoing,
                
                -- Estoque baixo
                CAST((SELECT COUNT(*) FROM INGREDIENTS 
                 WHERE CURRENT_STOCK <= MIN_STOCK_THRESHOLD) AS INTEGER) as low_stock
            FROM RDB$DATABASE
        """
        
        # ALTERAÇÃO: Executar query consolidada (5 subconsultas de hoje, cada uma com 2 parâmetros = 10 parâmetros)
        # total_orders, revenue, avg_ticket, completed, cancelled
        params = (start_datetime, end_datetime) * 5
        cur.execute(metrics_query, params)
        metrics_row = cur.fetchone()
        
        # ALTERAÇÃO: Calcular tempo médio de preparo em query separada para evitar problemas de tipo SQLDA
        # CORREÇÃO: Buscar tempos individuais e calcular média manualmente (evita problemas SQLDA com AVG)
        try:
            # Buscar todos os tempos de preparo individualmente
            cur.execute("""
                SELECT DATEDIFF(MINUTE FROM CREATED_AT TO UPDATED_AT) as prep_time
                FROM ORDERS 
                WHERE CREATED_AT >= ? AND CREATED_AT < ?
                  AND STATUS = 'delivered' 
                  AND UPDATED_AT IS NOT NULL
                  AND CREATED_AT IS NOT NULL
            """, (start_datetime, end_datetime))
            prep_times = cur.fetchall()
            
            # Calcular média manualmente para evitar problemas SQLDA com AVG
            if prep_times and len(prep_times) > 0:
                valid_times = []
                for row in prep_times:
                    if row and len(row) > 0 and row[0] is not None:
                        try:
                            time_val = float(row[0])
                            if time_val >= 0:  # Apenas valores válidos (não negativos)
                                valid_times.append(time_val)
                        except (ValueError, TypeError):
                            continue
                
                if valid_times:
                    avg_prep_time = sum(valid_times) / len(valid_times)
                else:
                    avg_prep_time = 0.0
            else:
                avg_prep_time = 0.0
        except Exception as e:
            # ALTERAÇÃO: Se houver erro, logar e usar valor padrão
            logger.warning(f"Erro ao calcular tempo médio de preparo: {e}. Usando valor padrão 0.", exc_info=True)
            avg_prep_time = 0.0
        
        # Query separada para distribuição por tipo (mais simples que consolidar)
        cur.execute("""
            SELECT ORDER_TYPE, COUNT(*) 
            FROM ORDERS 
            WHERE CREATED_AT >= ? AND CREATED_AT < ?
            GROUP BY ORDER_TYPE
        """, (start_datetime, end_datetime))
        order_distribution = {row[0]: row[1] for row in cur.fetchall()}
        
        # Query separada para pedidos recentes (usando FIRST ao invés de LIMIT no Firebird)
        # OTIMIZAÇÃO: Limita a 5 pedidos para reduzir tamanho da resposta
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
        
        # ALTERAÇÃO: Query para contar usuários ativos
        cur.execute("""
            SELECT CAST(COUNT(*) AS INTEGER) 
            FROM USERS 
            WHERE IS_ACTIVE = TRUE
        """)
        active_users_result = cur.fetchone()
        active_users_count = active_users_result[0] if active_users_result and active_users_result[0] is not None else 0
        
        # ALTERAÇÃO: Buscar meta mensal das configurações
        try:
            settings = settings_service.get_all_settings()
            monthly_goal = settings.get('meta_receita_mensal', 0) if settings else 0
        except Exception as e:
            logger.warning(f"Erro ao buscar meta mensal para dashboard: {e}")
            monthly_goal = 0
        
        # ALTERAÇÃO: Ajustar índices após remover avg_prep_time da query principal
        # ALTERAÇÃO: Adicionar active_users_count e monthly_goal ao resultado
        result = {  
            "total_orders_today": metrics_row[0] or 0,
            "revenue_today": float(metrics_row[1]) if metrics_row[1] else 0.0,
            "average_ticket": round(float(metrics_row[2]) if metrics_row[2] else 0.0, 2),
            "average_preparation_time": round(avg_prep_time, 1),  # ALTERAÇÃO: Usar valor calculado separadamente
            "completed_orders": metrics_row[3] or 0,
            "ongoing_orders": metrics_row[5] or 0,  # ALTERAÇÃO: Índice ajustado (era 6, agora é 5)
            "low_stock_items_count": metrics_row[6] or 0,  # ALTERAÇÃO: Índice ajustado (era 7, agora é 6)
            "cancelled_orders": metrics_row[4] or 0,
            "order_distribution": order_distribution,
            "recent_orders": recent_orders,
            "active_users_count": active_users_count,  # ALTERAÇÃO: Contagem de usuários ativos
            "monthly_goal": float(monthly_goal) if monthly_goal else 0.0  # ALTERAÇÃO: Meta mensal de receita
        }
        
        # OTIMIZAÇÃO: Salva resultado no cache
        _dashboard_metrics_cache = result
        _dashboard_cache_timestamp = datetime.now()
        
        return result
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
            "recent_orders": [],
            "active_users_count": 0,  # ALTERAÇÃO: Incluir active_users_count no fallback de erro
            "monthly_goal": 0.0  # ALTERAÇÃO: Incluir monthly_goal no fallback de erro
        }
    finally:  
        if conn: conn.close()


def get_menu_dashboard_metrics():
    """
    Retorna métricas do dashboard de cardápio (produtos) via consultas SQL.
    Calcula: total de itens, preço médio, margem média, tempo médio de preparo.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Query consolidada para métricas de produtos
        metrics_query = """
            SELECT
                -- Total de produtos
                CAST(COUNT(*) AS INTEGER) as total_products,
                
                -- Total de produtos inativos
                CAST(SUM(CASE WHEN IS_ACTIVE = FALSE THEN 1 ELSE 0 END) AS INTEGER) as inactive_products,
                
                -- Preço médio (apenas produtos com preço > 0)
                CAST(COALESCE(AVG(CASE WHEN PRICE > 0 THEN PRICE ELSE NULL END), 0) AS NUMERIC(18,2)) as avg_price,
                
                -- Margem média (apenas produtos com preço > 0 e cost_price preenchido)
                CAST(COALESCE(AVG(
                    CASE 
                        WHEN PRICE > 0 AND COST_PRICE IS NOT NULL AND COST_PRICE >= 0 THEN 
                            ((PRICE - COST_PRICE) / PRICE) * 100
                        ELSE NULL
                    END
                ), 0) AS NUMERIC(18,2)) as avg_margin,
                
                -- Tempo médio de preparo (apenas produtos com tempo > 0)
                CAST(COALESCE(AVG(CASE WHEN PREPARATION_TIME_MINUTES > 0 THEN PREPARATION_TIME_MINUTES ELSE NULL END), 0) AS NUMERIC(18,2)) as avg_preparation_time
            FROM PRODUCTS
        """
        
        cur.execute(metrics_query)
        row = cur.fetchone()
        
        result = {
            "total_products": row[0] or 0,
            "inactive_products": row[1] or 0,
            "avg_price": float(row[2]) if row[2] else 0.0,
            "avg_margin": float(row[3]) if row[3] else 0.0,
            "avg_preparation_time": float(row[4]) if row[4] else 0.0
        }
        
        return result
    except fdb.Error as e:
        logger.error(f"Erro ao buscar métricas do dashboard de cardápio: {e}", exc_info=True)
        return {
            "total_products": 0,
            "inactive_products": 0,
            "avg_price": 0.0,
            "avg_margin": 0.0,
            "avg_preparation_time": 0.0
        }
    finally:
        if conn:
            conn.close()


def get_promotions_dashboard_metrics():
    """
    Retorna métricas do dashboard de promoções via consultas SQL.
    Calcula: total de promoções, ativas, expiradas, desconto médio.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        now = datetime.now()
        
        # Query consolidada para métricas de promoções
        # ALTERAÇÃO: PROMOTIONS não tem campo IS_ACTIVE, apenas EXPIRES_AT determina se está ativa
        metrics_query = """
            SELECT
                -- Total de promoções
                CAST(COUNT(*) AS INTEGER) as total_promotions,
                
                -- Promoções ativas (não expiradas)
                CAST(SUM(CASE WHEN EXPIRES_AT > ? THEN 1 ELSE 0 END) AS INTEGER) as active_promotions,
                
                -- Promoções expiradas
                CAST(SUM(CASE WHEN EXPIRES_AT <= ? THEN 1 ELSE 0 END) AS INTEGER) as expired_promotions,
                
                -- Desconto médio das promoções ativas (usando discount_percentage quando disponível)
                CAST(COALESCE(AVG(
                    CASE 
                        WHEN EXPIRES_AT > ? AND DISCOUNT_PERCENTAGE IS NOT NULL AND DISCOUNT_PERCENTAGE > 0 THEN 
                            DISCOUNT_PERCENTAGE
                        ELSE NULL
                    END
                ), 0) AS NUMERIC(18,2)) as avg_discount
            FROM PROMOTIONS
        """
        
        # Parâmetros: now para cada subconsulta (3 vezes)
        params = (now, now, now)
        cur.execute(metrics_query, params)
        row = cur.fetchone()
        
        result = {
            "total_promotions": row[0] or 0,
            "active_promotions": row[1] or 0,
            "expired_promotions": row[2] or 0,
            "avg_discount": float(row[3]) if row[3] else 0.0
        }
        
        return result
    except fdb.Error as e:
        logger.error(f"Erro ao buscar métricas do dashboard de promoções: {e}", exc_info=True)
        return {
            "total_promotions": 0,
            "active_promotions": 0,
            "expired_promotions": 0,
            "avg_discount": 0.0
        }
    finally:
        if conn:
            conn.close()
