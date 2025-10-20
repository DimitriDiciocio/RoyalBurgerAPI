import fdb  
from ..database import get_db_connection  

def create_ingredient(data):  
    name = (data.get('name') or '').strip()  
    stock_unit = (data.get('stock_unit') or '').strip()  
    price = data.get('price', 0.0)  
    additional_price = data.get('additional_price', 0.0)
    current_stock = data.get('current_stock', 0.0)  
    min_stock_threshold = data.get('min_stock_threshold', 0.0)  
    max_stock = data.get('max_stock', 0.0)  
    supplier = (data.get('supplier') or '').strip()  
    category = (data.get('category') or '').strip()  
    # Campos para porção base
    base_portion_quantity = data.get('base_portion_quantity', 1.0)
    base_portion_unit = (data.get('base_portion_unit') or 'un').strip()
    
    if not name:  
        return (None, "INVALID_NAME", "Nome do insumo é obrigatório")  
    if not stock_unit:  
        return (None, "INVALID_UNIT", "Unidade do insumo é obrigatória")  
    if price is None or float(price) < 0:  
        return (None, "INVALID_COST", "Custo (price) deve ser maior ou igual a zero")  
    if additional_price is None or float(additional_price) < 0:
        return (None, "INVALID_ADDITIONAL_PRICE", "additional_price deve ser maior ou igual a zero")
    if current_stock is not None and float(current_stock) < 0:  
        return (None, "INVALID_STOCK", "Estoque atual não pode ser negativo")  
    if min_stock_threshold is not None and float(min_stock_threshold) < 0:  
        return (None, "INVALID_MIN_STOCK", "Estoque mínimo não pode ser negativo")  
    if max_stock is not None and float(max_stock) < 0:  
        return (None, "INVALID_MAX_STOCK", "Estoque máximo não pode ser negativo")
    if base_portion_quantity is None or float(base_portion_quantity) <= 0:  
        return (None, "INVALID_BASE_PORTION_QUANTITY", "Quantidade da porção base deve ser maior que zero")  
    if not base_portion_unit:  
        return (None, "INVALID_BASE_PORTION_UNIT", "Unidade da porção base é obrigatória")  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        # nome único (case-insensitive) - verificação mais robusta
        cur.execute("SELECT ID, NAME FROM INGREDIENTS WHERE UPPER(TRIM(NAME)) = UPPER(TRIM(?))", (name,))  
        existing = cur.fetchone()
        if existing:  
            return (None, "INGREDIENT_NAME_EXISTS", f"Já existe um insumo com o nome '{existing[1]}' (ID: {existing[0]})")  
        sql = "INSERT INTO INGREDIENTS (NAME, PRICE, ADDITIONAL_PRICE, CURRENT_STOCK, STOCK_UNIT, MIN_STOCK_THRESHOLD, MAX_STOCK, SUPPLIER, CATEGORY, BASE_PORTION_QUANTITY, BASE_PORTION_UNIT) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING ID, NAME, PRICE, ADDITIONAL_PRICE, IS_AVAILABLE, CURRENT_STOCK, STOCK_UNIT, MIN_STOCK_THRESHOLD, MAX_STOCK, SUPPLIER, CATEGORY, BASE_PORTION_QUANTITY, BASE_PORTION_UNIT;"  
        cur.execute(sql, (  
            name,  
            price,
            additional_price,
            current_stock,  
            stock_unit,  
            min_stock_threshold,  
            max_stock,  
            supplier,  
            category,
            base_portion_quantity,
            base_portion_unit
        ))  
        row = cur.fetchone()  
        conn.commit()  
        return ({  
            "id": row[0], "name": row[1],  
            "price": float(row[2]) if row[2] is not None else 0.0,
            "additional_price": float(row[3]) if row[3] is not None else 0.0,
            "is_available": row[4],  
            "current_stock": float(row[5]) if row[5] is not None else 0.0,  
            "stock_unit": row[6],  
            "min_stock_threshold": float(row[7]) if row[7] is not None else 0.0,  
            "max_stock": float(row[8]) if row[8] is not None else 0.0,  
            "supplier": row[9] if row[9] else "",  
            "category": row[10] if row[10] else "",
            "base_portion_quantity": float(row[11]) if row[11] is not None else 1.0,
            "base_portion_unit": row[12] if row[12] else "un"
        }, None, None)
    except fdb.Error as e:  
        print(f"Erro ao criar ingrediente: {e}")  
        if conn: conn.rollback()  
        
        # Verificar se é erro de constraint de nome único
        if e.args and len(e.args) > 1 and e.args[1] == -803:
            return (None, "INGREDIENT_NAME_EXISTS", f"Já existe um insumo com o nome '{name}'. Verifique se não há duplicatas.")
        
        return (None, "DATABASE_ERROR", "Erro interno do servidor")  
    finally:  
        if conn: conn.close()  

def list_ingredients(name_filter=None, status_filter=None, page=1, page_size=10):  
    page = max(int(page or 1), 1)  
    page_size = max(int(page_size or 10), 1)  
    offset = (page - 1) * page_size  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        where = []  
        params = []  
        if name_filter:  
            where.append("UPPER(NAME) LIKE UPPER(?)")  
            params.append(f"%{name_filter}%")  
        if status_filter == 'low_stock':  
            where.append("CURRENT_STOCK <= MIN_STOCK_THRESHOLD AND CURRENT_STOCK > 0")  
        elif status_filter == 'out_of_stock':  
            where.append("CURRENT_STOCK = 0")  
        elif status_filter == 'in_stock':  
            where.append("CURRENT_STOCK > MIN_STOCK_THRESHOLD")  
        elif status_filter == 'unavailable':  
            where.append("IS_AVAILABLE = FALSE")  
        elif status_filter == 'available':  
            where.append("IS_AVAILABLE = TRUE")  
        elif status_filter == 'overstock':  
            where.append("CURRENT_STOCK > MAX_STOCK AND MAX_STOCK > 0")  
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""  
        # total  
        cur.execute(f"SELECT COUNT(*) FROM INGREDIENTS{where_sql};", tuple(params))  
        total = cur.fetchone()[0] or 0  
        # page  
        cur.execute(  
            f"SELECT FIRST {page_size} SKIP {offset} ID, NAME, PRICE, ADDITIONAL_PRICE, IS_AVAILABLE, CURRENT_STOCK, STOCK_UNIT, MIN_STOCK_THRESHOLD, MAX_STOCK, SUPPLIER, CATEGORY, BASE_PORTION_QUANTITY, BASE_PORTION_UNIT "  
            f"FROM INGREDIENTS{where_sql} ORDER BY NAME;",  
            tuple(params)  
        )  
        items = [{  
            "id": row[0],  
            "name": row[1],  
            "price": float(row[2]) if row[2] is not None else 0.0,
            "additional_price": float(row[3]) if row[3] is not None else 0.0,
            "is_available": row[4],  
            "current_stock": float(row[5]) if row[5] is not None else 0.0,  
            "stock_unit": row[6],  
            "min_stock_threshold": float(row[7]) if row[7] is not None else 0.0,  
            "max_stock": float(row[8]) if row[8] is not None else 0.0,  
            "supplier": row[9] if row[9] else "",  
            "category": row[10] if row[10] else "",
            "base_portion_quantity": float(row[11]) if row[11] is not None else 1.0,
            "base_portion_unit": row[12] if row[12] else "un"
        } for row in cur.fetchall()]  
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
        print(f"Erro ao buscar ingredientes: {e}")  
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

def update_ingredient(ingredient_id, data):  
    allowed_fields = ['name', 'price', 'additional_price', 'stock_unit', 'current_stock', 'min_stock_threshold', 'max_stock', 'supplier', 'category', 'is_available', 'base_portion_quantity', 'base_portion_unit']
    fields_to_update = {k: v for k, v in data.items() if k in allowed_fields}  
    if not fields_to_update:  
        return (False, "NO_VALID_FIELDS", "Nenhum campo válido para atualização foi fornecido")  
    if 'name' in fields_to_update:  
        new_name = (fields_to_update['name'] or '').strip()  
        if not new_name:  
            return (False, "INVALID_NAME", "Nome do insumo é obrigatório")  
    if 'stock_unit' in fields_to_update:  
        unit = (fields_to_update['stock_unit'] or '').strip()  
        if not unit:  
            return (False, "INVALID_UNIT", "Unidade do insumo é obrigatória")  
    if 'price' in fields_to_update and float(fields_to_update['price']) < 0:  
        return (False, "INVALID_COST", "Custo (price) deve ser maior ou igual a zero")  
    if 'additional_price' in fields_to_update and float(fields_to_update['additional_price']) < 0:
        return (False, "INVALID_ADDITIONAL_PRICE", "additional_price deve ser maior ou igual a zero")
    if 'current_stock' in fields_to_update and float(fields_to_update['current_stock']) < 0:  
        return (False, "INVALID_STOCK", "Estoque atual não pode ser negativo")  
    if 'min_stock_threshold' in fields_to_update and float(fields_to_update['min_stock_threshold']) < 0:  
        return (False, "INVALID_MIN_STOCK", "Estoque mínimo não pode ser negativo")  
    if 'max_stock' in fields_to_update and float(fields_to_update['max_stock']) < 0:  
        return (False, "INVALID_MAX_STOCK", "Estoque máximo não pode ser negativo")
    if 'base_portion_quantity' in fields_to_update and float(fields_to_update['base_portion_quantity']) <= 0:  
        return (False, "INVALID_BASE_PORTION_QUANTITY", "Quantidade da porção base deve ser maior que zero")
    if 'base_portion_unit' in fields_to_update:  
        unit = (fields_to_update['base_portion_unit'] or '').strip()  
        if not unit:  
            return (False, "INVALID_BASE_PORTION_UNIT", "Unidade da porção base é obrigatória")  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        # verificar existência  
        cur.execute("SELECT 1 FROM INGREDIENTS WHERE ID = ?", (ingredient_id,))  
        if not cur.fetchone():  
            return (False, "INGREDIENT_NOT_FOUND", "Ingrediente não encontrado")  
        # nome único  
        if 'name' in fields_to_update:  
            cur.execute("SELECT 1 FROM INGREDIENTS WHERE UPPER(NAME) = UPPER(?) AND ID <> ?", (fields_to_update['name'], ingredient_id))  
            if cur.fetchone():  
                return (False, "INGREDIENT_NAME_EXISTS", "Já existe um insumo com este nome")  
        set_parts = [f"{key.upper()} = ?" for key in fields_to_update]  
        values = list(fields_to_update.values())  
        values.append(ingredient_id)  
        sql = f"UPDATE INGREDIENTS SET {', '.join(set_parts)} WHERE ID = ?;"  
        cur.execute(sql, tuple(values))  
        conn.commit()  
        return (True, None, "Ingrediente atualizado com sucesso")  
    except fdb.Error as e:  
        print(f"Erro ao atualizar ingrediente: {e}")  
        if conn: conn.rollback()  
        return (False, "DATABASE_ERROR", "Erro interno do servidor")  
    finally:  
        if conn: conn.close()  

def update_ingredient_availability(ingredient_id, is_available):  
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

def delete_ingredient(ingredient_id):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        
        # Verificar se existe
        cur.execute("SELECT 1 FROM INGREDIENTS WHERE ID = ?", (ingredient_id,))  
        if not cur.fetchone():  
            return (False, "INGREDIENT_NOT_FOUND", "Ingrediente não encontrado")  
        
        # Verificar vínculos com produtos
        cur.execute("SELECT COUNT(*) FROM PRODUCT_INGREDIENTS WHERE INGREDIENT_ID = ?", (ingredient_id,))  
        count_links = cur.fetchone()[0] or 0  
        
        if count_links > 0:  
            return (False, "INGREDIENT_IN_USE", "Exclusão bloqueada: há produtos vinculados a este insumo")  
        
        # Excluir
        cur.execute("DELETE FROM INGREDIENTS WHERE ID = ?", (ingredient_id,))  
        rows_affected = cur.rowcount
        
        conn.commit()  
        
        if rows_affected > 0:
            return (True, None, "Ingrediente excluído com sucesso")
        else:
            return (False, "NO_ROWS_AFFECTED", "Nenhuma linha foi afetada na exclusão")
            
    except fdb.Error as e:  
        print(f"Erro ao excluir ingrediente: {e}")  
        if conn: conn.rollback()  
        return (False, "DATABASE_ERROR", "Erro interno do servidor")  
    except Exception as e:
        print(f"Erro geral ao excluir ingrediente: {e}")
        if conn: conn.rollback()
        return (False, "GENERAL_ERROR", "Erro geral")
    finally:  
        if conn: conn.close()  


def add_ingredient_to_product(product_id, ingredient_id, portions):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        
        # Verificar se a vinculação já existe
        cur.execute("SELECT 1 FROM PRODUCT_INGREDIENTS WHERE PRODUCT_ID = ? AND INGREDIENT_ID = ?", (product_id, ingredient_id))
        existing = cur.fetchone()
        
        if existing:
            # Atualizar vinculação existente
            sql = "UPDATE PRODUCT_INGREDIENTS SET PORTIONS = ? WHERE PRODUCT_ID = ? AND INGREDIENT_ID = ?"
            cur.execute(sql, (portions, product_id, ingredient_id))
        else:
            # Inserir nova vinculação
            sql = "INSERT INTO PRODUCT_INGREDIENTS (PRODUCT_ID, INGREDIENT_ID, PORTIONS) VALUES (?, ?, ?)"
            cur.execute(sql, (product_id, ingredient_id, portions))
        
        conn.commit()  
        return True  
    except fdb.Error as e:  
        print(f"Erro ao associar ingrediente ao produto: {e}")  
        if conn: conn.rollback()  
        return False  
    finally:  
        if conn: conn.close()  


def update_product_ingredient(product_id, ingredient_id, portions=None):
    if portions is None:
        return (False, "NO_VALID_FIELDS", "Forneça 'portions' para atualizar")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # verificar existência do vínculo
        cur.execute("SELECT 1 FROM PRODUCT_INGREDIENTS WHERE PRODUCT_ID = ? AND INGREDIENT_ID = ?", (product_id, ingredient_id))
        if not cur.fetchone():
            return (False, "LINK_NOT_FOUND", "Vínculo produto-insumo não encontrado")
        
        sql = "UPDATE PRODUCT_INGREDIENTS SET PORTIONS = ? WHERE PRODUCT_ID = ? AND INGREDIENT_ID = ?;"
        cur.execute(sql, (portions, product_id, ingredient_id))
        conn.commit()
        return (cur.rowcount > 0, None, "Vínculo atualizado com sucesso")
    except fdb.Error as e:
        print(f"Erro ao atualizar vínculo: {e}")
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()

def remove_ingredient_from_product(product_id, ingredient_id):  
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
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        sql = """
            SELECT i.ID, i.NAME, pi.PORTIONS, i.BASE_PORTION_QUANTITY, i.BASE_PORTION_UNIT, 
                   i.PRICE, i.IS_AVAILABLE, i.STOCK_UNIT
            FROM PRODUCT_INGREDIENTS pi
            JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
            WHERE pi.PRODUCT_ID = ?;
        """  
        cur.execute(sql, (product_id,))  
        items = []
        estimated_cost = 0.0
        for row in cur.fetchall():
            ingredient_id = row[0]
            name = row[1]
            portions = float(row[2]) if row[2] is not None else 0.0
            base_portion_quantity = float(row[3]) if row[3] is not None else 1.0
            base_portion_unit = row[4] if row[4] else "un"
            price = float(row[5]) if row[5] is not None else 0.0
            is_available = row[6]
            stock_unit = row[7] if row[7] else "un"
            
            # Calcular quantidade real consumida baseada na porção
            actual_quantity = portions * base_portion_quantity
            # Calcular custo por porção (preço por unidade base * quantidade da porção base)
            portion_cost = price * base_portion_quantity
            # Calcular custo total da linha (custo por porção * número de porções)
            line_cost = portion_cost * portions
            
            items.append({
                "ingredient_id": ingredient_id,
                "name": name,
                "portions": portions,
                "base_portion_quantity": base_portion_quantity,
                "base_portion_unit": base_portion_unit,
                "actual_quantity": round(actual_quantity, 3),
                "actual_unit": base_portion_unit,
                "stock_unit": stock_unit,
                "price": price,
                "portion_cost": round(portion_cost, 2),
                "is_available": is_available,
                "line_cost": round(line_cost, 2)
            })
            estimated_cost += line_cost
        return {"items": items, "estimated_cost": round(estimated_cost, 2)}  
    except fdb.Error as e:  
        print(f"Erro ao buscar ingredientes do produto: {e}")  
        return {"items": [], "estimated_cost": 0.0}  
    finally:  
        if conn: conn.close()  


def adjust_ingredient_stock(ingredient_id, change_amount):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        cur.execute("SELECT CURRENT_STOCK FROM INGREDIENTS WHERE ID = ?", (ingredient_id,))  
        row = cur.fetchone()  
        if not row:  
            return (False, "INGREDIENT_NOT_FOUND", "Ingrediente não encontrado")  
        current_stock = float(row[0]) if row[0] is not None else 0.0  
        new_stock = current_stock + change_amount  
        if new_stock < 0:  
            return (False, "NEGATIVE_STOCK", "Não é possível ter estoque negativo")  
        cur.execute("UPDATE INGREDIENTS SET CURRENT_STOCK = ? WHERE ID = ?", (new_stock, ingredient_id))  
        conn.commit()  
        return (True, None, f"Estoque ajustado de {current_stock} para {new_stock}")  
    except fdb.Error as e:  
        print(f"Erro ao ajustar estoque: {e}")  
        if conn: conn.rollback()  
        return (False, "DATABASE_ERROR", "Erro interno do servidor")  
    finally:  
        if conn: conn.close()


def add_ingredient_quantity(ingredient_id, quantity_to_add):  
    """Adiciona uma quantidade ao estoque atual do ingrediente"""  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        
        # Verifica se o ingrediente existe e busca o estoque atual
        cur.execute("SELECT CURRENT_STOCK FROM INGREDIENTS WHERE ID = ?", (ingredient_id,))  
        row = cur.fetchone()  
        if not row:  
            return (False, "INGREDIENT_NOT_FOUND", "Ingrediente não encontrado")  
        
        current_stock = float(row[0]) if row[0] is not None else 0.0
        
        if quantity_to_add < 0:  
            return (False, "INVALID_QUANTITY", "Quantidade a adicionar não pode ser negativa")  
        
        new_stock = current_stock + quantity_to_add
        cur.execute("UPDATE INGREDIENTS SET CURRENT_STOCK = ? WHERE ID = ?", (new_stock, ingredient_id))  
        conn.commit()  
        return (True, None, f"Estoque atualizado de {current_stock} para {new_stock} (+{quantity_to_add})")  
    except fdb.Error as e:  
        print(f"Erro ao adicionar quantidade ao estoque: {e}")  
        if conn: conn.rollback()  
        return (False, "DATABASE_ERROR", "Erro interno do servidor")  
    finally:  
        if conn: conn.close()


def check_ingredient_name_exists(name):
    """
    Verifica se um nome de ingrediente já existe (case-insensitive)
    Retorna: (exists: bool, existing_ingredient: dict or None)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca ingrediente com nome similar (case-insensitive, ignorando espaços)
        cur.execute("SELECT ID, NAME FROM INGREDIENTS WHERE UPPER(TRIM(NAME)) = UPPER(TRIM(?))", (name,))
        existing = cur.fetchone()
        
        if existing:
            return (True, {
                "id": existing[0],
                "name": existing[1]
            })
        
        return (False, None)
        
    except fdb.Error as e:
        print(f"Erro ao verificar nome do ingrediente: {e}")
        return (False, None)
    finally:
        if conn: conn.close()  


def get_stock_summary():  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        cur.execute("""
            SELECT SUM(CURRENT_STOCK * PRICE) as total_value
            FROM INGREDIENTS 
            WHERE CURRENT_STOCK > 0
        """)  
        result = cur.fetchone()  
        total_stock_value = float(result[0]) if result and result[0] else 0.0  
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
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        cur.execute("""
            SELECT ID, NAME, CURRENT_STOCK, MIN_STOCK_THRESHOLD, STOCK_UNIT, PRICE
            FROM INGREDIENTS 
            WHERE CURRENT_STOCK <= MIN_STOCK_THRESHOLD
            ORDER BY CURRENT_STOCK ASC, NAME
        """)  
        items_to_buy = []  
        for row in cur.fetchall():  
            suggested_quantity = float(row[3]) * 2  
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


def consume_ingredients_for_product(product_id, quantity=1):
    """
    Consome ingredientes do estoque baseado na ficha técnica do produto
    quantity: quantidade de unidades do produto a ser produzida
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Buscar ingredientes do produto com suas porções
        sql = """
            SELECT i.ID, i.NAME, pi.PORTIONS, i.BASE_PORTION_QUANTITY, i.BASE_PORTION_UNIT, 
                   i.CURRENT_STOCK, i.STOCK_UNIT
            FROM PRODUCT_INGREDIENTS pi
            JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
            WHERE pi.PRODUCT_ID = ? AND i.IS_AVAILABLE = TRUE;
        """
        cur.execute(sql, (product_id,))
        ingredients = cur.fetchall()
        
        if not ingredients:
            return (False, "NO_INGREDIENTS", "Produto não possui ingredientes cadastrados")
        
        # Verificar se há estoque suficiente para todos os ingredientes
        consumption_plan = []
        for row in ingredients:
            ingredient_id = row[0]
            name = row[1]
            portions = float(row[2])
            base_portion_quantity = float(row[3])
            base_portion_unit = row[4]
            current_stock = float(row[5]) if row[5] is not None else 0.0
            stock_unit = row[6]
            
            # Calcular consumo total (porções * quantidade da porção base * quantidade do produto)
            total_consumption = portions * base_portion_quantity * quantity
            
            if current_stock < total_consumption:
                return (False, "INSUFFICIENT_STOCK", 
                       f"Estoque insuficiente para {name}. Necessário: {total_consumption:.3f} {base_portion_unit}, "
                       f"disponível: {current_stock:.3f} {stock_unit}")
            
            consumption_plan.append({
                "ingredient_id": ingredient_id,
                "name": name,
                "consumption": total_consumption,
                "new_stock": current_stock - total_consumption
            })
        
        # Executar baixa de estoque para todos os ingredientes
        for item in consumption_plan:
            cur.execute(
                "UPDATE INGREDIENTS SET CURRENT_STOCK = ? WHERE ID = ?",
                (item["new_stock"], item["ingredient_id"])
            )
        
        conn.commit()
        return (True, None, f"Estoque consumido com sucesso para {quantity} unidade(s) do produto")
        
    except fdb.Error as e:
        print(f"Erro ao consumir ingredientes: {e}")
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def calculate_product_cost_by_portions(product_id):
    """
    Calcula o custo do produto baseado nas porções dos ingredientes
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT i.ID, i.NAME, pi.PORTIONS, i.BASE_PORTION_QUANTITY, i.PRICE
            FROM PRODUCT_INGREDIENTS pi
            JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
            WHERE pi.PRODUCT_ID = ? AND i.IS_AVAILABLE = TRUE;
        """
        cur.execute(sql, (product_id,))
        ingredients = cur.fetchall()
        
        total_cost = 0.0
        cost_breakdown = []
        
        for row in ingredients:
            ingredient_id = row[0]
            name = row[1]
            portions = float(row[2])
            base_portion_quantity = float(row[3])
            price = float(row[4]) if row[4] is not None else 0.0
            
            # Custo por porção = preço por unidade base * quantidade da porção base
            portion_cost = price * base_portion_quantity
            # Custo total do ingrediente = custo por porção * número de porções
            ingredient_cost = portion_cost * portions
            
            cost_breakdown.append({
                "ingredient_id": ingredient_id,
                "name": name,
                "portions": portions,
                "base_portion_quantity": base_portion_quantity,
                "portion_cost": round(portion_cost, 2),
                "ingredient_cost": round(ingredient_cost, 2)
            })
            
            total_cost += ingredient_cost
        
        return {
            "total_cost": round(total_cost, 2),
            "cost_breakdown": cost_breakdown
        }
        
    except fdb.Error as e:
        print(f"Erro ao calcular custo do produto: {e}")
        return {"total_cost": 0.0, "cost_breakdown": []}
    finally:
        if conn: conn.close()  
