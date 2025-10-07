import fdb
from ..database import get_db_connection


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

        return ({"id": new_id, "name": name, "is_active": True, "display_order": next_order}, None, None)
    except fdb.Error as e:
        if conn: conn.rollback()
        print(f"Erro ao criar categoria: {e}")
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def list_categories(name_filter=None, page=1, page_size=10):
    page = max(int(page or 1), 1)
    page_size = max(int(page_size or 10), 1)
    offset = (page - 1) * page_size

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
        return {
            "items": items,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages
            }
        }
    except fdb.Error as e:
        print(f"Erro ao listar categorias: {e}")
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
        return (True, None, "Categoria atualizada com sucesso")
    except fdb.Error as e:
        if conn: conn.rollback()
        print(f"Erro ao atualizar categoria: {e}")
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
            print(f"Desvinculados {count_linked} produtos da categoria '{category_name}' (ID: {category_id})")

        # Agora exclui a categoria
        cur.execute("DELETE FROM CATEGORIES WHERE ID = ?;", (category_id,))
        
        if cur.rowcount > 0:
            conn.commit()
            message = f"Categoria '{category_name}' excluída com sucesso"
            if count_linked > 0:
                message += f". {count_linked} produtos foram desvinculados da categoria."
            return (True, None, message)
        else:
            return (False, "DELETE_FAILED", "Falha ao excluir a categoria")
            
    except fdb.Error as e:
        if conn: conn.rollback()
        print(f"Erro ao excluir categoria: {e}")
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
        return (True, None, "Ordem das categorias atualizada com sucesso")
        
    except fdb.Error as e:
        if conn: conn.rollback()
        print(f"Erro ao reordenar categorias: {e}")
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def get_categories_for_reorder():
    """
    Retorna todas as categorias ativas ordenadas por display_order para reordenação.
    Retorna (categorias, error_code, mensagem)
    """
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
        
        return (categories, None, None)
        
    except fdb.Error as e:
        print(f"Erro ao buscar categorias para reordenação: {e}")
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
        return (True, None, f"Categoria movida para a posição {new_position}")
        
    except fdb.Error as e:
        if conn: conn.rollback()
        print(f"Erro ao mover categoria: {e}")
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


