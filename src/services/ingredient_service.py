import fdb  # importa driver do Firebird
from ..database import get_db_connection  # importa função de conexão com o banco

def create_ingredient(data):  # cria novo ingrediente com estoque
    conn = None  # inicializa conexão
    try:  # tenta criar ingrediente
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = "INSERT INTO INGREDIENTS (NAME, DESCRIPTION, PRICE, CURRENT_STOCK, STOCK_UNIT, MIN_STOCK_THRESHOLD) VALUES (?, ?, ?, ?, ?, ?) RETURNING ID, NAME, DESCRIPTION, PRICE, IS_AVAILABLE, CURRENT_STOCK, STOCK_UNIT, MIN_STOCK_THRESHOLD;"  # SQL de inserção
        cur.execute(sql, (  # executa inserção
            data['name'], 
            data.get('description'), 
            data.get('price', 0.0),
            data.get('current_stock', 0.0),
            data.get('stock_unit', 'un'),
            data.get('min_stock_threshold', 0.0)
        ))
        row = cur.fetchone()  # obtém dados do ingrediente criado
        conn.commit()  # confirma transação
        return {  # retorna dados do ingrediente
            "id": row[0], "name": row[1], "description": row[2],
            "price": row[3], "is_available": row[4],
            "current_stock": float(row[5]) if row[5] is not None else 0.0,
            "stock_unit": row[6],
            "min_stock_threshold": float(row[7]) if row[7] is not None else 0.0
        }
    except fdb.Error as e:  # captura erros
        print(f"Erro ao criar ingrediente: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return None  # retorna None em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def get_all_ingredients(status_filter=None):  # busca ingredientes com filtros de estoque
    conn = None  # inicializa conexão
    try:  # tenta buscar ingredientes
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        base_sql = """
            SELECT ID, NAME, DESCRIPTION, PRICE, IS_AVAILABLE, 
                   CURRENT_STOCK, STOCK_UNIT, MIN_STOCK_THRESHOLD
            FROM INGREDIENTS 
        """  # query base com campos de estoque
        if status_filter == 'low_stock':  # filtro estoque baixo
            base_sql += " WHERE CURRENT_STOCK <= MIN_STOCK_THRESHOLD AND CURRENT_STOCK > 0"  # adiciona condição
        elif status_filter == 'out_of_stock':  # filtro sem estoque
            base_sql += " WHERE CURRENT_STOCK = 0"  # adiciona condição
        elif status_filter == 'in_stock':  # filtro com estoque
            base_sql += " WHERE CURRENT_STOCK > MIN_STOCK_THRESHOLD"  # adiciona condição
        base_sql += " ORDER BY NAME;"  # adiciona ordenação
        cur.execute(base_sql)  # executa query
        ingredients = [{  # monta lista de ingredientes
            "id": row[0], 
            "name": row[1], 
            "description": row[2],
            "price": row[3], 
            "is_available": row[4],
            "current_stock": float(row[5]) if row[5] is not None else 0.0,
            "stock_unit": row[6],
            "min_stock_threshold": float(row[7]) if row[7] is not None else 0.0
        } for row in cur.fetchall()]  # itera resultados
        return ingredients  # retorna lista
    except fdb.Error as e:  # captura erros
        print(f"Erro ao buscar ingredientes: {e}")  # exibe erro
        return []  # retorna vazio em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def update_ingredient(ingredient_id, data):  # atualiza dados de um ingrediente
    allowed_fields = ['name', 'description', 'price']  # campos permitidos
    set_parts = [f"{key.upper()} = ?" for key in data if key in allowed_fields]  # monta partes do SET
    if not set_parts: return True  # retorna True se nada para atualizar
    values = [value for key, value in data.items() if key in allowed_fields]  # extrai valores
    values.append(ingredient_id)  # adiciona ID para WHERE
    conn = None  # inicializa conexão
    try:  # tenta atualizar
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = f"UPDATE INGREDIENTS SET {', '.join(set_parts)} WHERE ID = ?;"  # SQL de update
        cur.execute(sql, tuple(values))  # executa update
        conn.commit()  # confirma transação
        return cur.rowcount > 0  # retorna True se atualizou
    except fdb.Error as e:  # captura erros
        print(f"Erro ao atualizar ingrediente: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return False  # retorna False em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def update_ingredient_availability(ingredient_id, is_available):  # atualiza disponibilidade do ingrediente
    conn = None  # inicializa conexão
    try:  # tenta atualizar
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = "UPDATE INGREDIENTS SET IS_AVAILABLE = ? WHERE ID = ?;"  # SQL de update
        cur.execute(sql, (is_available, ingredient_id))  # executa update
        conn.commit()  # confirma transação
        return cur.rowcount > 0  # retorna True se atualizou
    except fdb.Error as e:  # captura erros
        print(f"Erro ao atualizar disponibilidade do ingrediente: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return False  # retorna False em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def deactivate_ingredient(ingredient_id):  # inativa ingrediente (marca como indisponível)
    return update_ingredient_availability(ingredient_id, False)  # chama função de disponibilidade


def add_ingredient_to_product(product_id, ingredient_id, quantity):  # associa ingrediente a produto
    conn = None  # inicializa conexão
    try:  # tenta associar
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = """
            MERGE INTO PRODUCT_INGREDIENTS pi
            USING (SELECT ? AS PRODUCT_ID, ? AS INGREDIENT_ID, ? AS QUANTITY FROM RDB$DATABASE) AS new_data
            ON (pi.PRODUCT_ID = new_data.PRODUCT_ID AND pi.INGREDIENT_ID = new_data.INGREDIENT_ID)
            WHEN MATCHED THEN
                UPDATE SET pi.QUANTITY = new_data.QUANTITY
            WHEN NOT MATCHED THEN
                INSERT (PRODUCT_ID, INGREDIENT_ID, QUANTITY)
                VALUES (new_data.PRODUCT_ID, new_data.INGREDIENT_ID, new_data.QUANTITY);
        """  # SQL de merge (atualiza ou insere)
        cur.execute(sql, (product_id, ingredient_id, quantity))  # executa merge
        conn.commit()  # confirma transação
        return True  # retorna sucesso
    except fdb.Error as e:  # captura erros
        print(f"Erro ao associar ingrediente ao produto: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return False  # retorna False em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def remove_ingredient_from_product(product_id, ingredient_id):  # remove associação ingrediente-produto
    conn = None  # inicializa conexão
    try:  # tenta remover
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = "DELETE FROM PRODUCT_INGREDIENTS WHERE PRODUCT_ID = ? AND INGREDIENT_ID = ?;"  # SQL de remoção
        cur.execute(sql, (product_id, ingredient_id))  # executa delete
        conn.commit()  # confirma transação
        return cur.rowcount > 0  # retorna True se removeu
    except fdb.Error as e:  # captura erros
        print(f"Erro ao remover associação de ingrediente: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return False  # retorna False em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def get_ingredients_for_product(product_id):  # busca ingredientes de um produto
    conn = None  # inicializa conexão
    try:  # tenta buscar ingredientes
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = """
            SELECT i.ID, i.NAME, pi.QUANTITY, i.PRICE, i.IS_AVAILABLE
            FROM PRODUCT_INGREDIENTS pi
            JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
            WHERE pi.PRODUCT_ID = ?;
        """  # SQL de busca com JOIN
        cur.execute(sql, (product_id,))  # executa query
        ingredients = [{  # monta lista de ingredientes
            "ingredient_id": row[0], "name": row[1], "quantity": row[2],
            "price": row[3], "is_available": row[4]
        } for row in cur.fetchall()]  # itera resultados
        return ingredients  # retorna lista
    except fdb.Error as e:  # captura erros
        print(f"Erro ao buscar ingredientes do produto: {e}")  # exibe erro
        return []  # retorna vazio em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão


def adjust_ingredient_stock(ingredient_id, change_amount):  # ajusta estoque de ingrediente
    conn = None  # inicializa conexão
    try:  # tenta ajustar estoque
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        cur.execute("SELECT CURRENT_STOCK FROM INGREDIENTS WHERE ID = ?", (ingredient_id,))  # busca estoque atual
        row = cur.fetchone()  # obtém linha
        if not row:  # se ingrediente não encontrado
            return (False, "INGREDIENT_NOT_FOUND", "Ingrediente não encontrado")  # retorna erro
        current_stock = float(row[0]) if row[0] is not None else 0.0  # converte estoque atual
        new_stock = current_stock + change_amount  # calcula novo estoque
        if new_stock < 0:  # se estoque ficaria negativo
            return (False, "NEGATIVE_STOCK", "Não é possível ter estoque negativo")  # retorna erro
        cur.execute("UPDATE INGREDIENTS SET CURRENT_STOCK = ? WHERE ID = ?", (new_stock, ingredient_id))  # atualiza estoque
        conn.commit()  # confirma transação
        return (True, None, f"Estoque ajustado de {current_stock} para {new_stock}")  # retorna sucesso
    except fdb.Error as e:  # captura erros
        print(f"Erro ao ajustar estoque: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return (False, "DATABASE_ERROR", "Erro interno do servidor")  # retorna erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão


def get_stock_summary():  # retorna KPIs de estoque
    conn = None  # inicializa conexão
    try:  # tenta buscar KPIs
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        cur.execute("""
            SELECT SUM(CURRENT_STOCK * PRICE) as total_value
            FROM INGREDIENTS 
            WHERE CURRENT_STOCK > 0
        """)  # calcula valor total do estoque
        result = cur.fetchone()  # obtém resultado
        total_stock_value = float(result[0]) if result and result[0] else 0.0  # converte para float
        cur.execute("""
            SELECT 
                SUM(CASE WHEN CURRENT_STOCK = 0 THEN 1 ELSE 0 END) as out_of_stock,
                SUM(CASE WHEN CURRENT_STOCK > 0 AND CURRENT_STOCK <= MIN_STOCK_THRESHOLD THEN 1 ELSE 0 END) as low_stock,
                SUM(CASE WHEN CURRENT_STOCK > MIN_STOCK_THRESHOLD THEN 1 ELSE 0 END) as in_stock
            FROM INGREDIENTS
        """)  # conta itens por status
        row = cur.fetchone()  # obtém resultado
        return {  # retorna KPIs
            "total_stock_value": total_stock_value,
            "out_of_stock_count": int(row[0]) if row and row[0] else 0,
            "low_stock_count": int(row[1]) if row and row[1] else 0,
            "in_stock_count": int(row[2]) if row and row[2] else 0
        }
    except fdb.Error as e:  # captura erros
        print(f"Erro ao buscar resumo de estoque: {e}")  # exibe erro
        return {  # retorna estrutura padrão em erro
            "total_stock_value": 0.0,
            "out_of_stock_count": 0,
            "low_stock_count": 0,
            "in_stock_count": 0
        }
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão


def generate_purchase_order():  # gera lista de ingredientes para compra
    conn = None  # inicializa conexão
    try:  # tenta gerar pedido
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        cur.execute("""
            SELECT ID, NAME, CURRENT_STOCK, MIN_STOCK_THRESHOLD, STOCK_UNIT, PRICE
            FROM INGREDIENTS 
            WHERE CURRENT_STOCK <= MIN_STOCK_THRESHOLD
            ORDER BY CURRENT_STOCK ASC, NAME
        """)  # busca ingredientes com estoque baixo
        items_to_buy = []  # lista de itens para comprar
        for row in cur.fetchall():  # itera ingredientes
            suggested_quantity = float(row[3]) * 2  # calcula quantidade sugerida (2x threshold)
            current_stock = float(row[2]) if row[2] is not None else 0.0  # converte estoque atual
            items_to_buy.append({  # adiciona item à lista
                "ingredient_id": row[0],
                "name": row[1],
                "current_stock": current_stock,
                "min_threshold": float(row[3]),
                "stock_unit": row[4],
                "unit_price": float(row[5]) if row[5] is not None else 0.0,
                "suggested_quantity": suggested_quantity,
                "estimated_cost": suggested_quantity * (float(row[5]) if row[5] is not None else 0.0)
            })
        total_estimated_cost = sum(item["estimated_cost"] for item in items_to_buy)  # calcula custo total
        return {  # retorna pedido de compra
            "items": items_to_buy,
            "total_items": len(items_to_buy),
            "total_estimated_cost": total_estimated_cost
        }
    except fdb.Error as e:  # captura erros
        print(f"Erro ao gerar pedido de compra: {e}")  # exibe erro
        return {"items": [], "total_items": 0, "total_estimated_cost": 0.0}  # retorna estrutura vazia em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão