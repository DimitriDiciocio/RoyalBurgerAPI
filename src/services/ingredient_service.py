# src/services/ingredient_service.py

import fdb
from ..database import get_db_connection

# --- CRUD de Ingredientes ---

def create_ingredient(data):
    """Cria um novo ingrediente, incluindo preço e campos de estoque."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # ATUALIZADO: Inclui os campos de estoque no insert
        sql = "INSERT INTO INGREDIENTS (NAME, DESCRIPTION, PRICE, CURRENT_STOCK, STOCK_UNIT, MIN_STOCK_THRESHOLD) VALUES (?, ?, ?, ?, ?, ?) RETURNING ID, NAME, DESCRIPTION, PRICE, IS_AVAILABLE, CURRENT_STOCK, STOCK_UNIT, MIN_STOCK_THRESHOLD;"
        cur.execute(sql, (
            data['name'], 
            data.get('description'), 
            data.get('price', 0.0),
            data.get('current_stock', 0.0),
            data.get('stock_unit', 'un'),
            data.get('min_stock_threshold', 0.0)
        ))
        row = cur.fetchone()
        conn.commit()
        return {
            "id": row[0], "name": row[1], "description": row[2],
            "price": row[3], "is_available": row[4],
            "current_stock": float(row[5]) if row[5] is not None else 0.0,
            "stock_unit": row[6],
            "min_stock_threshold": float(row[7]) if row[7] is not None else 0.0
        }
    except fdb.Error as e:
        print(f"Erro ao criar ingrediente: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: conn.close()

def get_all_ingredients(status_filter=None):
    """Busca todos os ingredientes com filtros opcionais de status de estoque."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Query base com todos os campos de estoque
        base_sql = """
            SELECT ID, NAME, DESCRIPTION, PRICE, IS_AVAILABLE, 
                   CURRENT_STOCK, STOCK_UNIT, MIN_STOCK_THRESHOLD
            FROM INGREDIENTS 
        """
        
        # Adiciona filtros baseados no status
        if status_filter == 'low_stock':
            base_sql += " WHERE CURRENT_STOCK <= MIN_STOCK_THRESHOLD AND CURRENT_STOCK > 0"
        elif status_filter == 'out_of_stock':
            base_sql += " WHERE CURRENT_STOCK = 0"
        elif status_filter == 'in_stock':
            base_sql += " WHERE CURRENT_STOCK > MIN_STOCK_THRESHOLD"
        
        base_sql += " ORDER BY NAME;"
        
        cur.execute(base_sql)
        ingredients = [{
            "id": row[0], 
            "name": row[1], 
            "description": row[2],
            "price": row[3], 
            "is_available": row[4],
            "current_stock": float(row[5]) if row[5] is not None else 0.0,
            "stock_unit": row[6],
            "min_stock_threshold": float(row[7]) if row[7] is not None else 0.0
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


# --- Funções para Gerenciamento de Estoque ---

def adjust_ingredient_stock(ingredient_id, change_amount):
    """Ajusta o estoque de um ingrediente (adiciona ou subtrai)."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Primeiro, verifica o estoque atual
        cur.execute("SELECT CURRENT_STOCK FROM INGREDIENTS WHERE ID = ?", (ingredient_id,))
        row = cur.fetchone()
        if not row:
            return (False, "INGREDIENT_NOT_FOUND", "Ingrediente não encontrado")
        
        current_stock = float(row[0]) if row[0] is not None else 0.0
        new_stock = current_stock + change_amount
        
        # Valida se não resultará em estoque negativo
        if new_stock < 0:
            return (False, "NEGATIVE_STOCK", "Não é possível ter estoque negativo")
        
        # Atualiza o estoque
        cur.execute("UPDATE INGREDIENTS SET CURRENT_STOCK = ? WHERE ID = ?", (new_stock, ingredient_id))
        conn.commit()
        
        return (True, None, f"Estoque ajustado de {current_stock} para {new_stock}")
        
    except fdb.Error as e:
        print(f"Erro ao ajustar estoque: {e}")
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def get_stock_summary():
    """Retorna os KPIs de estoque."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Calcula total_stock_value
        cur.execute("""
            SELECT SUM(CURRENT_STOCK * PRICE) as total_value
            FROM INGREDIENTS 
            WHERE CURRENT_STOCK > 0
        """)
        result = cur.fetchone()
        total_stock_value = float(result[0]) if result and result[0] else 0.0
        
        # Conta itens por status
        cur.execute("""
            SELECT 
                SUM(CASE WHEN CURRENT_STOCK = 0 THEN 1 ELSE 0 END) as out_of_stock,
                SUM(CASE WHEN CURRENT_STOCK > 0 AND CURRENT_STOCK <= MIN_STOCK_THRESHOLD THEN 1 ELSE 0 END) as low_stock,
                SUM(CASE WHEN CURRENT_STOCK > MIN_STOCK_THRESHOLD THEN 1 ELSE 0 END) as in_stock
            FROM INGREDIENTS
        """)
        row = cur.fetchone()
        
        return {
            "total_stock_value": total_stock_value,
            "out_of_stock_count": int(row[0]) if row and row[0] else 0,
            "low_stock_count": int(row[1]) if row and row[1] else 0,
            "in_stock_count": int(row[2]) if row and row[2] else 0
        }
        
    except fdb.Error as e:
        print(f"Erro ao buscar resumo de estoque: {e}")
        return {
            "total_stock_value": 0.0,
            "out_of_stock_count": 0,
            "low_stock_count": 0,
            "in_stock_count": 0
        }
    finally:
        if conn: conn.close()


def generate_purchase_order():
    """Gera lista de ingredientes que precisam ser comprados (estoque baixo ou zerado)."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca ingredientes com estoque baixo ou zerado
        cur.execute("""
            SELECT ID, NAME, CURRENT_STOCK, MIN_STOCK_THRESHOLD, STOCK_UNIT, PRICE
            FROM INGREDIENTS 
            WHERE CURRENT_STOCK <= MIN_STOCK_THRESHOLD
            ORDER BY CURRENT_STOCK ASC, NAME
        """)
        
        items_to_buy = []
        for row in cur.fetchall():
            # Calcula quantidade sugerida para compra (dobra o estoque mínimo)
            suggested_quantity = float(row[3]) * 2  # 2x o threshold mínimo
            current_stock = float(row[2]) if row[2] is not None else 0.0
            
            items_to_buy.append({
                "ingredient_id": row[0],
                "name": row[1],
                "current_stock": current_stock,
                "min_threshold": float(row[3]),
                "stock_unit": row[4],
                "unit_price": float(row[5]) if row[5] is not None else 0.0,
                "suggested_quantity": suggested_quantity,
                "estimated_cost": suggested_quantity * (float(row[5]) if row[5] is not None else 0.0)
            })
        
        # Calcula total estimado
        total_estimated_cost = sum(item["estimated_cost"] for item in items_to_buy)
        
        return {
            "items": items_to_buy,
            "total_items": len(items_to_buy),
            "total_estimated_cost": total_estimated_cost
        }
        
    except fdb.Error as e:
        print(f"Erro ao gerar pedido de compra: {e}")
        return {"items": [], "total_items": 0, "total_estimated_cost": 0.0}
    finally:
        if conn: conn.close()