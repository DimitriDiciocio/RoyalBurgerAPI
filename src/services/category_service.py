import fdb
from ..database import get_db_connection
from datetime import datetime

# OTIMIZAÇÃO DE PERFORMANCE: Cache em memória para listas de categorias
_category_list_cache = {}
_category_list_cache_timestamp = {}
_category_list_cache_ttl = 600  # 10 minutos de TTL (categorias mudam menos frequentemente)

def _invalidate_category_cache():
    """Invalida cache de categorias forçando refresh na próxima chamada"""
    global _category_list_cache, _category_list_cache_timestamp
    _category_list_cache = {}
    _category_list_cache_timestamp = {}
    # Também invalida caches específicos
    if "_categories_for_select" in _category_list_cache:
        del _category_list_cache["_categories_for_select"]
    if "_categories_for_select_timestamp" in _category_list_cache_timestamp:
        del _category_list_cache_timestamp["_categories_for_select_timestamp"]
    if "_categories_for_reorder" in _category_list_cache:
        del _category_list_cache["_categories_for_reorder"]
    if "_categories_for_reorder_timestamp" in _category_list_cache_timestamp:
        del _category_list_cache_timestamp["_categories_for_reorder_timestamp"]

def _get_category_cache_key(name_filter, page, page_size):
    """Gera chave única para o cache baseada nos parâmetros"""
    return f"{name_filter or ''}_{page}_{page_size}"

def _is_category_cache_valid(cache_key):
    """Verifica se o cache ainda é válido"""
    if cache_key not in _category_list_cache_timestamp:
        return False
    elapsed = (datetime.now() - _category_list_cache_timestamp[cache_key]).total_seconds()
    return elapsed < _category_list_cache_ttl


def create_category(category_data):
    name = (category_data.get('name') or '').strip()
    if not name:
        return (None, "INVALID_NAME", "Nome da categoria é obrigatório")

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT 1 FROM CATEGORIES WHERE UPPER(NAME) = UPPER(?) AND IS_ACTIVE = TRUE;", (name,))
        if cur.fetchone():
            return (None, "CATEGORY_NAME_EXISTS", "Já existe uma categoria com este nome")

        # Busca o próximo display_order (última posição)
        cur.execute("SELECT COALESCE(MAX(DISPLAY_ORDER), 0) + 1 FROM CATEGORIES WHERE IS_ACTIVE = TRUE;")
        next_order = cur.fetchone()[0]

        cur.execute("INSERT INTO CATEGORIES (NAME, DISPLAY_ORDER) VALUES (?, ?) RETURNING ID;", (name, next_order))
        new_id = cur.fetchone()[0]
        conn.commit()
        
        # OTIMIZAÇÃO: Invalida cache após criar categoria
        _invalidate_category_cache()

        return ({"id": new_id, "name": name, "is_active": True, "display_order": next_order}, None, None)
    except fdb.Error as e:
        if conn: conn.rollback()
        # ALTERAÇÃO: Substituído print() por logging estruturado
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Erro ao criar categoria: {e}", exc_info=True)
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def list_categories(name_filter=None, page=1, page_size=10):
    """
    Lista categorias com cache em memória para melhor performance.
    Cache TTL: 10 minutos. Invalidado automaticamente quando categorias são modificadas.
    """
    # OTIMIZAÇÃO: Usar validador centralizado de paginação
    from ..utils.validators import validate_pagination_params
    try:
        page, page_size, offset = validate_pagination_params(page, page_size, max_page_size=100)
    except ValueError:
        page, page_size, offset = 1, 10, 0

    # OTIMIZAÇÃO: Verifica cache antes de consultar banco
    # Cache apenas para listagens sem filtro de nome
    use_cache = not name_filter
    cache_key = _get_category_cache_key(name_filter, page, page_size)
    
    if use_cache and _is_category_cache_valid(cache_key) and cache_key in _category_list_cache:
        return _category_list_cache[cache_key]

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        if name_filter:
            cur.execute(
                "SELECT COUNT(*) FROM CATEGORIES WHERE IS_ACTIVE = TRUE AND UPPER(NAME) LIKE UPPER(?);",
                (f"%{name_filter}%",)
            )
        else:
            cur.execute("SELECT COUNT(*) FROM CATEGORIES WHERE IS_ACTIVE = TRUE;")
        total = cur.fetchone()[0] or 0

        if name_filter:
            cur.execute(
                f"SELECT FIRST {page_size} SKIP {offset} ID, NAME, DISPLAY_ORDER "
                "FROM CATEGORIES "
                "WHERE IS_ACTIVE = TRUE AND UPPER(NAME) LIKE UPPER(?) "
                "ORDER BY DISPLAY_ORDER, NAME;",
                (f"%{name_filter}%",)
            )
        else:
            cur.execute(
                f"SELECT FIRST {page_size} SKIP {offset} ID, NAME, DISPLAY_ORDER "
                "FROM CATEGORIES "
                "WHERE IS_ACTIVE = TRUE "
                "ORDER BY DISPLAY_ORDER, NAME;"
            )
        items = [{"id": row[0], "name": row[1], "display_order": row[2]} for row in cur.fetchall()]

        total_pages = (total + page_size - 1) // page_size
        result = {
            "items": items,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages
            }
        }
        
        # OTIMIZAÇÃO: Salva resultado no cache se for cacheável
        if use_cache:
            _category_list_cache[cache_key] = result
            _category_list_cache_timestamp[cache_key] = datetime.now()
        
        return result
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logging estruturado
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Erro ao listar categorias: {e}", exc_info=True)
        return {
            "items": [],
            "pagination": {
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0
            }
        }
    finally:
        if conn: conn.close()


def update_category(category_id, update_data):
    name = update_data.get('name')
    if name is None:
        return (False, "NO_VALID_FIELDS", "Nenhum campo válido para atualização foi fornecido")

    name = name.strip()
    if not name:
        return (False, "INVALID_NAME", "Nome da categoria é obrigatório")

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT 1 FROM CATEGORIES WHERE ID = ? AND IS_ACTIVE = TRUE;", (category_id,))
        if not cur.fetchone():
            return (False, "CATEGORY_NOT_FOUND", "Categoria não encontrada")

        cur.execute(
            "SELECT 1 FROM CATEGORIES WHERE UPPER(NAME) = UPPER(?) AND ID <> ? AND IS_ACTIVE = TRUE;",
            (name, category_id)
        )
        if cur.fetchone():
            return (False, "CATEGORY_NAME_EXISTS", "Já existe uma categoria com este nome")

        cur.execute("UPDATE CATEGORIES SET NAME = ? WHERE ID = ? AND IS_ACTIVE = TRUE;", (name, category_id))
        conn.commit()
        
        # OTIMIZAÇÃO: Invalida cache após atualizar categoria
        _invalidate_category_cache()
        # Também invalida cache de produtos, pois produtos podem ter categoria associada
        try:
            from .product_service import _invalidate_product_cache
            _invalidate_product_cache()
        except:
            pass
        
        return (True, None, "Categoria atualizada com sucesso")
    except fdb.Error as e:
        if conn: conn.rollback()
        # ALTERAÇÃO: Substituído print() por logging estruturado
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Erro ao atualizar categoria: {e}", exc_info=True)
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def delete_category(category_id):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Verifica se a categoria existe
        cur.execute("SELECT NAME FROM CATEGORIES WHERE ID = ? AND IS_ACTIVE = TRUE;", (category_id,))
        category_result = cur.fetchone()
        if not category_result:
            return (False, "CATEGORY_NOT_FOUND", "Categoria não encontrada")
        
        category_name = category_result[0]

        # Conta quantos produtos estão vinculados à categoria
        cur.execute("SELECT COUNT(*) FROM PRODUCTS WHERE CATEGORY_ID = ? AND IS_ACTIVE = TRUE;", (category_id,))
        count_linked = cur.fetchone()[0] or 0
        
        # Se há produtos vinculados, desvincula todos eles primeiro
        if count_linked > 0:
            cur.execute("UPDATE PRODUCTS SET CATEGORY_ID = NULL WHERE CATEGORY_ID = ? AND IS_ACTIVE = TRUE;", (category_id,))
            # ALTERAÇÃO: Substituído print() por logging estruturado
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Desvinculados {count_linked} produtos da categoria '{category_name}' (ID: {category_id})")

        # Agora exclui a categoria
        cur.execute("DELETE FROM CATEGORIES WHERE ID = ?;", (category_id,))
        
        if cur.rowcount > 0:
            conn.commit()
            
            # OTIMIZAÇÃO: Invalida cache após deletar categoria
            _invalidate_category_cache()
            # Também invalida cache de produtos, pois produtos foram desvinculados
            try:
                from .product_service import _invalidate_product_cache
                _invalidate_product_cache()
            except:
                pass
            
            message = f"Categoria '{category_name}' excluída com sucesso"
            if count_linked > 0:
                message += f". {count_linked} produtos foram desvinculados da categoria."
            return (True, None, message)
        else:
            return (False, "DELETE_FAILED", "Falha ao excluir a categoria")
            
    except fdb.Error as e:
        if conn: conn.rollback()
        # ALTERAÇÃO: Substituído print() por logging estruturado
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Erro ao excluir categoria: {e}", exc_info=True)
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def reorder_categories(category_orders):
    """
    Reordena categorias baseado em uma lista de {id, display_order}.
    Retorna (sucesso, error_code, mensagem)
    """
    if not category_orders or not isinstance(category_orders, list):
        return (False, "INVALID_DATA", "Lista de ordens de categoria é obrigatória")
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Valida se todas as categorias existem e estão ativas
        category_ids = [item.get('id') for item in category_orders if item.get('id')]
        if not category_ids:
            return (False, "INVALID_DATA", "Nenhum ID de categoria válido fornecido")
        
        placeholders = ','.join(['?' for _ in category_ids])
        cur.execute(f"SELECT ID FROM CATEGORIES WHERE ID IN ({placeholders}) AND IS_ACTIVE = TRUE;", category_ids)
        existing_ids = [row[0] for row in cur.fetchall()]
        
        if len(existing_ids) != len(category_ids):
            return (False, "CATEGORY_NOT_FOUND", "Uma ou mais categorias não foram encontradas")
        
        # Atualiza as ordens
        for item in category_orders:
            category_id = item.get('id')
            display_order = item.get('display_order')
            
            if not isinstance(display_order, int) or display_order < 0:
                return (False, "INVALID_ORDER", f"Ordem inválida para categoria {category_id}")
            
            cur.execute(
                "UPDATE CATEGORIES SET DISPLAY_ORDER = ? WHERE ID = ? AND IS_ACTIVE = TRUE;",
                (display_order, category_id)
            )
        
        conn.commit()
        
        # OTIMIZAÇÃO: Invalida cache após reordenar categorias
        _invalidate_category_cache()
        
        return (True, None, "Ordem das categorias atualizada com sucesso")
        
    except fdb.Error as e:
        if conn: conn.rollback()
        # ALTERAÇÃO: Substituído print() por logging estruturado
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Erro ao reordenar categorias: {e}", exc_info=True)
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def get_categories_for_reorder():
    """
    Retorna todas as categorias ativas ordenadas por display_order para reordenação.
    Retorna (categorias, error_code, mensagem)
    
    OTIMIZAÇÃO DE PERFORMANCE: Usa cache para reduzir queries ao banco.
    """
    # OTIMIZAÇÃO: Cache específico para categorias de reordenação
    cache_key_reorder = "_categories_for_reorder"
    cache_key_timestamp_reorder = "_categories_for_reorder_timestamp"
    
    # Verifica cache (TTL de 10 minutos)
    if cache_key_reorder in _category_list_cache:
        cache_timestamp = _category_list_cache_timestamp.get(cache_key_timestamp_reorder)
        if cache_timestamp:
            elapsed = (datetime.now() - cache_timestamp).total_seconds()
            if elapsed < _category_list_cache_ttl:
                return (_category_list_cache[cache_key_reorder], None, None)
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute(
            "SELECT ID, NAME, DISPLAY_ORDER FROM CATEGORIES WHERE IS_ACTIVE = TRUE ORDER BY DISPLAY_ORDER, NAME;"
        )
        categories = [
            {"id": row[0], "name": row[1], "display_order": row[2]} 
            for row in cur.fetchall()
        ]
        
        # OTIMIZAÇÃO: Salva no cache
        _category_list_cache[cache_key_reorder] = categories
        _category_list_cache_timestamp[cache_key_timestamp_reorder] = datetime.now()
        
        return (categories, None, None)
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logging estruturado
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Erro ao buscar categorias para reordenação: {e}", exc_info=True)
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def get_categories_for_select():
    """
    Retorna todas as categorias ativas apenas com ID e nome para uso em selects.
    Retorna (categorias, error_code, mensagem)
    
    OTIMIZAÇÃO DE PERFORMANCE: Usa cache para reduzir queries ao banco.
    Esta função é chamada frequentemente em formulários e selects.
    """
    # OTIMIZAÇÃO: Cache específico para categorias de select (mais leve, sem paginação)
    cache_key_select = "_categories_for_select"
    cache_key_timestamp_select = "_categories_for_select_timestamp"
    
    # Verifica cache (TTL de 10 minutos, mesmo das listagens)
    if cache_key_select in _category_list_cache:
        cache_timestamp = _category_list_cache_timestamp.get(cache_key_timestamp_select)
        if cache_timestamp:
            elapsed = (datetime.now() - cache_timestamp).total_seconds()
            if elapsed < _category_list_cache_ttl:
                return (_category_list_cache[cache_key_select], None, None)
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute(
            "SELECT ID, NAME FROM CATEGORIES WHERE IS_ACTIVE = TRUE ORDER BY DISPLAY_ORDER, NAME;"
        )
        categories = [
            {"id": row[0], "name": row[1]} 
            for row in cur.fetchall()
        ]
        
        # OTIMIZAÇÃO: Salva no cache
        _category_list_cache[cache_key_select] = categories
        _category_list_cache_timestamp[cache_key_timestamp_select] = datetime.now()
        
        return (categories, None, None)
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logging estruturado
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Erro ao buscar categorias para select: {e}", exc_info=True)
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def move_category_to_position(category_id, new_position):
    """
    Move uma categoria para uma nova posição, ajustando as outras automaticamente.
    Retorna (sucesso, error_code, mensagem)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se a categoria existe
        cur.execute("SELECT DISPLAY_ORDER FROM CATEGORIES WHERE ID = ? AND IS_ACTIVE = TRUE;", (category_id,))
        result = cur.fetchone()
        if not result:
            return (False, "CATEGORY_NOT_FOUND", "Categoria não encontrada")
        
        current_order = result[0]
        
        # Busca o total de categorias
        cur.execute("SELECT COUNT(*) FROM CATEGORIES WHERE IS_ACTIVE = TRUE;")
        total_categories = cur.fetchone()[0]
        
        if new_position < 1 or new_position > total_categories:
            return (False, "INVALID_POSITION", f"Posição deve estar entre 1 e {total_categories}")
        
        # Se a posição não mudou, não faz nada
        if current_order == new_position:
            return (True, None, "Categoria já está na posição solicitada")
        
        # Busca todas as categorias ordenadas
        cur.execute(
            "SELECT ID, DISPLAY_ORDER FROM CATEGORIES WHERE IS_ACTIVE = TRUE ORDER BY DISPLAY_ORDER;"
        )
        all_categories = cur.fetchall()
        
        # Cria nova lista de ordens
        new_orders = []
        for i, (cat_id, old_order) in enumerate(all_categories):
            if cat_id == category_id:
                new_orders.append((cat_id, new_position))
            else:
                # Ajusta as posições das outras categorias
                if current_order < new_position:
                    # Movendo para baixo: categorias entre current_order+1 e new_position sobem
                    if old_order > current_order and old_order <= new_position:
                        new_orders.append((cat_id, old_order - 1))
                    else:
                        new_orders.append((cat_id, old_order))
                else:
                    # Movendo para cima: categorias entre new_position e current_order-1 descem
                    if old_order >= new_position and old_order < current_order:
                        new_orders.append((cat_id, old_order + 1))
                    else:
                        new_orders.append((cat_id, old_order))
        
        # Atualiza todas as ordens
        for cat_id, new_order in new_orders:
            cur.execute(
                "UPDATE CATEGORIES SET DISPLAY_ORDER = ? WHERE ID = ?;",
                (new_order, cat_id)
            )
        
        conn.commit()
        
        # OTIMIZAÇÃO: Invalida cache após mover categoria
        _invalidate_category_cache()
        
        return (True, None, f"Categoria movida para a posição {new_position}")
        
    except fdb.Error as e:
        if conn: conn.rollback()
        # ALTERAÇÃO: Substituído print() por logging estruturado
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Erro ao mover categoria: {e}", exc_info=True)
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def get_categories_with_products(include_inactive=False):
    """
    Retorna todas as categorias ativas com seus produtos já incluídos.
    Útil para a tela inicial do mobile que precisa mostrar todas as categorias e produtos.
    Retorna (resultado, error_code, mensagem)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca todas as categorias ativas ordenadas
        cur.execute(
            "SELECT ID, NAME, DISPLAY_ORDER FROM CATEGORIES WHERE IS_ACTIVE = TRUE ORDER BY DISPLAY_ORDER, NAME;"
        )
        category_rows = cur.fetchall()
        
        if not category_rows:
            return ([], None, None)
        
        # Coleta todos os IDs de categorias
        category_ids = [row[0] for row in category_rows]
        placeholders = ','.join(['?' for _ in category_ids])
        
        # Busca todos os produtos ativos das categorias de uma vez
        where_clause = f"CATEGORY_ID IN ({placeholders})"
        if not include_inactive:
            where_clause += " AND IS_ACTIVE = TRUE"
        
        cur.execute(f"""
            SELECT 
                ID, NAME, DESCRIPTION, PRICE, COST_PRICE, 
                PREPARATION_TIME_MINUTES, CATEGORY_ID, IMAGE_URL, IS_ACTIVE
            FROM PRODUCTS 
            WHERE {where_clause}
            ORDER BY CATEGORY_ID, NAME
        """, category_ids)
        
        product_rows = cur.fetchall()
        
        # Organiza produtos por categoria
        products_by_category = {}
        for row in product_rows:
            category_id = row[6]  # CATEGORY_ID
            if category_id not in products_by_category:
                products_by_category[category_id] = []
            
            product = {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "price": str(row[3]),
                "cost_price": str(row[4]) if row[4] else "0.00",
                "preparation_time_minutes": row[5] if row[5] else 0,
                "category_id": category_id,
                "is_active": row[8] if len(row) > 8 else True
            }
            
            # Adiciona URL da imagem se existir
            if row[7]:  # IMAGE_URL
                product["image_url"] = row[7]
            
            products_by_category[category_id].append(product)
        
        # Monta o resultado final com categorias e seus produtos
        result = []
        for cat_row in category_rows:
            category_id = cat_row[0]
            category = {
                "id": category_id,
                "name": cat_row[1],
                "display_order": cat_row[2],
                "products": products_by_category.get(category_id, [])
            }
            result.append(category)
        
        return (result, None, None)
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logging estruturado
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Erro ao buscar categorias com produtos: {e}", exc_info=True)
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


