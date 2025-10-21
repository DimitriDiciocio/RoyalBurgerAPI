import fdb
from ..database import get_db_connection


# =============================
# Serviço de Grupos de Extras
# Tabelas: GROUPS_EXTRAS, GROUP_INGREDIENTS_EXTRAS
# =============================


def create_group(name, is_active=True):
    name = (name or '').strip()
    if not name:
        return (None, "INVALID_NAME", "Nome do grupo é obrigatório")

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Nome único (case-insensitive) por conveniência de UX (opcional)
        cur.execute("SELECT ID FROM GROUPS_EXTRAS WHERE UPPER(TRIM(NAME)) = UPPER(TRIM(?))", (name,))
        if cur.fetchone():
            return (None, "GROUP_NAME_EXISTS", "Já existe um grupo com este nome")

        sql = "INSERT INTO GROUPS_EXTRAS (NAME, IS_ACTIVE) VALUES (?, ?) RETURNING ID, NAME, IS_ACTIVE;"
        cur.execute(sql, (name, bool(is_active)))
        row = cur.fetchone()
        conn.commit()
        return ({"id": row[0], "name": row[1], "is_active": row[2]}, None, None)
    except fdb.Error as e:
        print(f"Erro ao criar grupo: {e}")
        if conn:
            conn.rollback()
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()


def get_group_by_id(group_id):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT ID, NAME, IS_ACTIVE, CREATED_AT, UPDATED_AT FROM GROUPS_EXTRAS WHERE ID = ?", (group_id,))
        row = cur.fetchone()
        if not row:
            return None
        group = {
            "id": row[0],
            "name": row[1],
            "is_active": row[2],
            "created_at": row[3].strftime('%Y-%m-%d %H:%M:%S') if row[3] else None,
            "updated_at": row[4].strftime('%Y-%m-%d %H:%M:%S') if row[4] else None,
        }

        # carrega ingredientes vinculados
        group["ingredients"] = get_ingredients_for_group(group_id)
        return group
    except fdb.Error as e:
        print(f"Erro ao buscar grupo por ID: {e}")
        return None
    finally:
        if conn:
            conn.close()


def get_all_groups(active_only=True):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        where = "WHERE IS_ACTIVE = TRUE" if active_only else ""
        cur.execute(f"SELECT ID, NAME, IS_ACTIVE, CREATED_AT, UPDATED_AT FROM GROUPS_EXTRAS {where} ORDER BY NAME")
        items = []
        for row in cur.fetchall():
            items.append({
                "id": row[0],
                "name": row[1],
                "is_active": row[2],
                "created_at": row[3].strftime('%Y-%m-%d %H:%M:%S') if row[3] else None,
                "updated_at": row[4].strftime('%Y-%m-%d %H:%M:%S') if row[4] else None,
            })
        return items
    except fdb.Error as e:
        print(f"Erro ao listar grupos: {e}")
        return []
    finally:
        if conn:
            conn.close()


def update_group(group_id, name=None, is_active=None):
    fields_to_update = {}
    if name is not None:
        name = (name or '').strip()
        if not name:
            return (False, "INVALID_NAME", "Nome do grupo é obrigatório")
        fields_to_update['NAME'] = name
    if is_active is not None:
        fields_to_update['IS_ACTIVE'] = bool(is_active)

    if not fields_to_update:
        return (False, "NO_VALID_FIELDS", "Nenhum campo válido para atualização foi fornecido")

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Verifica existência
        cur.execute("SELECT 1 FROM GROUPS_EXTRAS WHERE ID = ?", (group_id,))
        if not cur.fetchone():
            return (False, "GROUP_NOT_FOUND", "Grupo não encontrado")

        # Nome único (case-insensitive) se for alterar nome
        if 'NAME' in fields_to_update:
            cur.execute("SELECT 1 FROM GROUPS_EXTRAS WHERE UPPER(NAME) = UPPER(?) AND ID <> ?", (fields_to_update['NAME'], group_id))
            if cur.fetchone():
                return (False, "GROUP_NAME_EXISTS", "Já existe um grupo com este nome")

        set_parts = [f"{k} = ?" for k in fields_to_update.keys()]
        values = list(fields_to_update.values())
        values.append(group_id)

        sql = f"UPDATE GROUPS_EXTRAS SET {', '.join(set_parts)}, UPDATED_AT = CURRENT_TIMESTAMP WHERE ID = ?;"
        cur.execute(sql, tuple(values))
        conn.commit()
        return (True, None, "Grupo atualizado com sucesso")
    except fdb.Error as e:
        print(f"Erro ao atualizar grupo: {e}")
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()


def delete_group(group_id):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Exclui relações (ON DELETE CASCADE já deve cuidar, mas garantimos)
        cur.execute("DELETE FROM GROUP_INGREDIENTS_EXTRAS WHERE GROUP_ID = ?", (group_id,))
        # Exclui o grupo
        cur.execute("DELETE FROM GROUPS_EXTRAS WHERE ID = ?", (group_id,))
        affected = cur.rowcount
        conn.commit()
        return affected > 0
    except fdb.Error as e:
        print(f"Erro ao excluir grupo: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


# Relações Grupo <-> Ingredientes
def add_ingredient_to_group(group_id, ingredient_id):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Verifica existência de grupo e ingrediente
        cur.execute("SELECT 1 FROM GROUPS_EXTRAS WHERE ID = ?", (group_id,))
        if not cur.fetchone():
            return (False, "GROUP_NOT_FOUND", "Grupo não encontrado")
        cur.execute("SELECT 1 FROM INGREDIENTS WHERE ID = ?", (ingredient_id,))
        if not cur.fetchone():
            return (False, "INGREDIENT_NOT_FOUND", "Ingrediente não encontrado")

        # Insere (ou ignora se já existir - trata erro de unique)
        try:
            cur.execute(
                "INSERT INTO GROUP_INGREDIENTS_EXTRAS (GROUP_ID, INGREDIENT_ID) VALUES (?, ?)",
                (group_id, ingredient_id)
            )
            conn.commit()
            return (True, None, "Ingrediente adicionado ao grupo")
        except fdb.Error as e:
            # Código -803 para violação de unique no Firebird
            if e.args and len(e.args) > 1 and e.args[1] == -803:
                return (True, None, "Ingrediente já estava no grupo")
            raise
    except fdb.Error as e:
        print(f"Erro ao adicionar ingrediente ao grupo: {e}")
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()


def remove_ingredient_from_group(group_id, ingredient_id):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM GROUP_INGREDIENTS_EXTRAS WHERE GROUP_ID = ? AND INGREDIENT_ID = ?",
            (group_id, ingredient_id)
        )
        affected = cur.rowcount
        conn.commit()
        return affected > 0
    except fdb.Error as e:
        print(f"Erro ao remover ingrediente do grupo: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


def get_ingredients_for_group(group_id):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT i.ID, i.NAME, i.ADDITIONAL_PRICE, i.IS_AVAILABLE
            FROM GROUP_INGREDIENTS_EXTRAS gie
            JOIN INGREDIENTS i ON i.ID = gie.INGREDIENT_ID
            WHERE gie.GROUP_ID = ?
            ORDER BY i.NAME
            """,
            (group_id,)
        )
        items = []
        for row in cur.fetchall():
            items.append({
                "id": row[0],
                "name": row[1],
                "additional_price": float(row[2]) if row[2] is not None else 0.0,
                "is_available": bool(row[3])
            })
        return items
    except fdb.Error as e:
        print(f"Erro ao listar ingredientes do grupo: {e}")
        return []
    finally:
        if conn:
            conn.close()


