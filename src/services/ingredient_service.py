# src/services/ingredient_service.py

import fdb
from ..database import get_db_connection

# --- CRUD de Ingredientes ---

def create_ingredient(data):
    """Cria um novo ingrediente, incluindo preço."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # ATUALIZADO: Inclui o campo PRICE no insert
        sql = "INSERT INTO INGREDIENTS (NAME, DESCRIPTION, PRICE) VALUES (?, ?, ?) RETURNING ID, NAME, DESCRIPTION, PRICE, IS_AVAILABLE;"
        cur.execute(sql, (data['name'], data.get('description'), data.get('price', 0.0)))
        row = cur.fetchone()
        conn.commit()
        return {
            "id": row[0], "name": row[1], "description": row[2],
            "price": row[3], "is_available": row[4]
        }
    except fdb.Error as e:
        print(f"Erro ao criar ingrediente: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: conn.close()

def get_all_ingredients():
    """Busca todos os ingredientes."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # ATUALIZADO: Busca também PRICE e IS_AVAILABLE
        sql = "SELECT ID, NAME, DESCRIPTION, PRICE, IS_AVAILABLE FROM INGREDIENTS ORDER BY NAME;"
        cur.execute(sql)
        ingredients = [{
            "id": row[0], "name": row[1], "description": row[2],
            "price": row[3], "is_available": row[4]
        } for row in cur.fetchall()]
        return ingredients
    except fdb.Error as e:
        print(f"Erro ao buscar ingredientes: {e}")
        return []
    finally:
        if conn: conn.close()

def update_ingredient(ingredient_id, data):
    """Atualiza os dados de um ingrediente (nome, descrição, preço)."""
    # ATUALIZADO: Permite atualizar o preço
    allowed_fields = ['name', 'description', 'price']
    set_parts = [f"{key.upper()} = ?" for key in data if key in allowed_fields]
    if not set_parts: return True # Nada a ser atualizado

    values = [value for key, value in data.items() if key in allowed_fields]
    values.append(ingredient_id)

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = f"UPDATE INGREDIENTS SET {', '.join(set_parts)} WHERE ID = ?;"
        cur.execute(sql, tuple(values))
        conn.commit()
        return cur.rowcount > 0
    except fdb.Error as e:
        print(f"Erro ao atualizar ingrediente: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

# --- Lógica de Disponibilidade ---

# ADICIONADO: A função que faltava
def update_ingredient_availability(ingredient_id, is_available):
    """Atualiza o status de disponibilidade (disponível/esgotado) de um ingrediente."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = "UPDATE INGREDIENTS SET IS_AVAILABLE = ? WHERE ID = ?;"
        cur.execute(sql, (is_available, ingredient_id))
        conn.commit()
        return cur.rowcount > 0
    except fdb.Error as e:
        print(f"Erro ao atualizar disponibilidade do ingrediente: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

def deactivate_ingredient(ingredient_id):
    """Inativa um ingrediente marcando-o como indisponível."""
    # ATUALIZADO: Agora esta função usa a nova lógica de disponibilidade
    return update_ingredient_availability(ingredient_id, False)


# --- Associação Produto <-> Ingrediente ---
# (Todas as suas funções de associação foram mantidas, pois estão perfeitas)

def add_ingredient_to_product(product_id, ingredient_id, quantity):
    """Associa um ingrediente a um produto com uma quantidade específica."""
    # ... seu código aqui ...
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = """
            MERGE INTO PRODUCT_INGREDIENTS pi
            USING (SELECT ? AS PRODUCT_ID, ? AS INGREDIENT_ID, ? AS QUANTITY FROM RDB$DATABASE) AS new_data
            ON (pi.PRODUCT_ID = new_data.PRODUCT_ID AND pi.INGREDIENT_ID = new_data.INGREDIENT_ID)
            WHEN MATCHED THEN
                UPDATE SET pi.QUANTITY = new_data.QUANTITY
            WHEN NOT MATCHED THEN
                INSERT (PRODUCT_ID, INGREDIENT_ID, QUANTITY)
                VALUES (new_data.PRODUCT_ID, new_data.INGREDIENT_ID, new_data.QUANTITY);
        """
        cur.execute(sql, (product_id, ingredient_id, quantity))
        conn.commit()
        return True
    except fdb.Error as e:
        print(f"Erro ao associar ingrediente ao produto: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

def remove_ingredient_from_product(product_id, ingredient_id):
    """Remove a associação de um ingrediente de um produto."""
    # ... seu código aqui ...
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = "DELETE FROM PRODUCT_INGREDIENTS WHERE PRODUCT_ID = ? AND INGREDIENT_ID = ?;"
        cur.execute(sql, (product_id, ingredient_id))
        conn.commit()
        return cur.rowcount > 0
    except fdb.Error as e:
        print(f"Erro ao remover associação de ingrediente: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

def get_ingredients_for_product(product_id):
    """Busca a lista de ingredientes de um produto específico."""
    # ... seu código aqui ...
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = """
            SELECT i.ID, i.NAME, pi.QUANTITY, i.PRICE, i.IS_AVAILABLE
            FROM PRODUCT_INGREDIENTS pi
            JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
            WHERE pi.PRODUCT_ID = ?;
        """
        cur.execute(sql, (product_id,))
        ingredients = [{
            "ingredient_id": row[0], "name": row[1], "quantity": row[2],
            "price": row[3], "is_available": row[4]
        } for row in cur.fetchall()]
        return ingredients
    except fdb.Error as e:
        print(f"Erro ao buscar ingredientes do produto: {e}")
        return []
    finally:
        if conn: conn.close()