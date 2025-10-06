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

        cur.execute("INSERT INTO CATEGORIES (NAME) VALUES (?) RETURNING ID;", (name,))
        new_id = cur.fetchone()[0]
        conn.commit()

        return ({"id": new_id, "name": name, "is_active": True}, None, None)
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
                f"SELECT FIRST {page_size} SKIP {offset} ID, NAME "
                "FROM CATEGORIES "
                "WHERE IS_ACTIVE = TRUE AND UPPER(NAME) LIKE UPPER(?) "
                "ORDER BY NAME;",
                (f"%{name_filter}%",)
            )
        else:
            cur.execute(
                f"SELECT FIRST {page_size} SKIP {offset} ID, NAME "
                "FROM CATEGORIES "
                "WHERE IS_ACTIVE = TRUE "
                "ORDER BY NAME;"
            )
        items = [{"id": row[0], "name": row[1]} for row in cur.fetchall()]

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

        cur.execute("SELECT 1 FROM CATEGORIES WHERE ID = ? AND IS_ACTIVE = TRUE;", (category_id,))
        if not cur.fetchone():
            return (False, "CATEGORY_NOT_FOUND", "Categoria não encontrada")

        cur.execute("SELECT COUNT(*) FROM PRODUCTS WHERE CATEGORY_ID = ? AND IS_ACTIVE = TRUE;", (category_id,))
        count_linked = cur.fetchone()[0] or 0
        if count_linked > 0:
            return (False, "CATEGORY_IN_USE", "Exclusão bloqueada: há produtos vinculados a esta categoria")

        cur.execute("DELETE FROM CATEGORIES WHERE ID = ?;", (category_id,))
        conn.commit()
        return (cur.rowcount > 0, None, "Categoria excluída com sucesso")
    except fdb.Error as e:
        if conn: conn.rollback()
        print(f"Erro ao excluir categoria: {e}")
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


