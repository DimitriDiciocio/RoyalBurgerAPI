import fdb  
from ..database import get_db_connection
from ..utils.image_handler import get_product_image_url  

def create_product(product_data):  
    name = product_data.get('name')  
    description = product_data.get('description')  
    price = product_data.get('price')  
    cost_price = product_data.get('cost_price', 0.0)  
    preparation_time_minutes = product_data.get('preparation_time_minutes', 0)  
    category_id = product_data.get('category_id')  
    if not name or not name.strip():  
        return (None, "INVALID_NAME", "Nome do produto é obrigatório")  
    if price is None or price <= 0:  
        return (None, "INVALID_PRICE", "Preço deve ser maior que zero")  
    if cost_price is not None and cost_price < 0:  
        return (None, "INVALID_COST_PRICE", "Preço de custo não pode ser negativo")  
    if preparation_time_minutes is not None and preparation_time_minutes < 0:  
        return (None, "INVALID_PREP_TIME", "Tempo de preparo não pode ser negativo")  
    if category_id is None:  
        return (None, "INVALID_CATEGORY", "Categoria é obrigatória")  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        # valida categoria existente e ativa  
        cur.execute("SELECT 1 FROM CATEGORIES WHERE ID = ? AND IS_ACTIVE = TRUE;", (category_id,))  
        if not cur.fetchone():  
            return (None, "CATEGORY_NOT_FOUND", "Categoria informada não existe ou está inativa")  
        sql_check = "SELECT ID FROM PRODUCTS WHERE UPPER(NAME) = UPPER(?) AND IS_ACTIVE = TRUE;"  
        cur.execute(sql_check, (name,))  
        if cur.fetchone():  
            return (None, "PRODUCT_NAME_EXISTS", "Já existe um produto com este nome")  
        sql = "INSERT INTO PRODUCTS (NAME, DESCRIPTION, PRICE, COST_PRICE, PREPARATION_TIME_MINUTES, CATEGORY_ID, IMAGE_URL) VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING ID;"  
        cur.execute(sql, (name, description, price, cost_price, preparation_time_minutes, category_id, None))  
        new_product_id = cur.fetchone()[0]  
        conn.commit()  
        return ({"id": new_product_id, "name": name, "description": description, "price": price, "cost_price": cost_price, "preparation_time_minutes": preparation_time_minutes, "category_id": category_id}, None, None)  
    except fdb.Error as e:  
        print(f"Erro ao criar produto: {e}")  
        if conn: conn.rollback()  
        return (None, "DATABASE_ERROR", "Erro interno do servidor")  
    finally:  
        if conn: conn.close()  


def _get_image_hash(image_url):
    """Gera hash da imagem baseado no arquivo"""
    if not image_url:
        return None
    try:
        import os
        import hashlib
        upload_dir = os.path.join(os.getcwd(), 'uploads', 'products')
        filename = os.path.basename(image_url)
        file_path = os.path.join(upload_dir, filename)
        if os.path.exists(file_path):
            # Gera hash baseado no conteúdo e data de modificação
            file_mtime = os.path.getmtime(file_path)
            file_size = os.path.getsize(file_path)
            hash_input = f"{filename}_{file_mtime}_{file_size}"
            return hashlib.md5(hash_input.encode()).hexdigest()[:8]
    except Exception as e:
        print(f"Erro ao gerar hash da imagem: {e}")
    return None

def _get_product_availability_status(product_id, cur):
    """Verifica o status de disponibilidade do produto baseado no estoque dos ingredientes"""
    try:
        # Busca ingredientes do produto
        sql = """
            SELECT i.IS_AVAILABLE, i.STOCK_STATUS, i.CURRENT_STOCK, i.MIN_STOCK_THRESHOLD
            FROM PRODUCT_INGREDIENTS pi
            JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
            WHERE pi.PRODUCT_ID = ? AND i.IS_AVAILABLE = TRUE
        """
        cur.execute(sql, (product_id,))
        ingredients = cur.fetchall()
        
        if not ingredients:
            return "unavailable"  # Produto sem ingredientes
        
        has_unavailable = False
        has_low_stock = False
        
        for is_available, stock_status, current_stock, min_threshold in ingredients:
            if not is_available or stock_status == 'out_of_stock':
                has_unavailable = True
                break
            elif stock_status == 'low' or (current_stock and min_threshold and current_stock <= min_threshold):
                has_low_stock = True
        
        if has_unavailable:
            return "unavailable"
        elif has_low_stock:
            return "low_stock"
        else:
            return "available"
            
    except Exception as e:
        print(f"Erro ao verificar disponibilidade do produto {product_id}: {e}")
        return "unknown"

def list_products(name_filter=None, category_id=None, page=1, page_size=10, include_inactive=False):  
    page = max(int(page or 1), 1)  
    page_size = max(int(page_size or 10), 1)  
    offset = (page - 1) * page_size  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        where_clauses = [] if include_inactive else ["IS_ACTIVE = TRUE"]  
        params = []  
        if name_filter:  
            where_clauses.append("UPPER(NAME) LIKE UPPER(?)")  
            params.append(f"%{name_filter}%")  
        if category_id:  
            where_clauses.append("CATEGORY_ID = ?")  
            params.append(category_id)  
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"  
        # total  
        cur.execute(f"SELECT COUNT(*) FROM PRODUCTS WHERE {where_sql};", tuple(params))  
        total = cur.fetchone()[0] or 0  
        # page  
        cur.execute(  
            f"SELECT FIRST {page_size} SKIP {offset} p.ID, p.NAME, p.DESCRIPTION, p.PRICE, p.COST_PRICE, p.PREPARATION_TIME_MINUTES, p.CATEGORY_ID, p.IMAGE_URL, p.IS_ACTIVE, c.NAME as CATEGORY_NAME "  
            f"FROM PRODUCTS p LEFT JOIN CATEGORIES c ON p.CATEGORY_ID = c.ID WHERE {where_sql} ORDER BY p.NAME;",  
            tuple(params)  
        )  
        items = []  
        for row in cur.fetchall():
            product_id = row[0]
            item = {  
                "id": product_id,  
                "name": row[1],  
                "description": row[2],  
                "price": str(row[3]),  
                "cost_price": str(row[4]) if row[4] else "0.00",  
                "preparation_time_minutes": row[5] if row[5] else 0,  
                "category_id": row[6],
                "is_active": row[8] if len(row) > 8 else True,
                "category_name": row[9] if len(row) > 9 and row[9] else "Sem categoria"
            }
            # Adiciona URL da imagem do banco se existir
            if row[7]:  # IMAGE_URL
                item["image_url"] = row[7]
                item["image_hash"] = _get_image_hash(row[7])
            
            # Adiciona status de disponibilidade baseado no estoque
            item["availability_status"] = _get_product_availability_status(product_id, cur)
            
            items.append(item)  
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
        print(f"Erro ao listar produtos: {e}")  
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


def get_product_by_id(product_id):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        sql = "SELECT ID, NAME, DESCRIPTION, PRICE, COST_PRICE, PREPARATION_TIME_MINUTES, CATEGORY_ID, IMAGE_URL FROM PRODUCTS WHERE ID = ? AND IS_ACTIVE = TRUE;"  
        cur.execute(sql, (product_id,))  
        row = cur.fetchone()  
        if row:  
            product_id = row[0]
            product = {"id": product_id, "name": row[1], "description": row[2], "price": str(row[3]), "cost_price": str(row[4]) if row[4] else "0.00", "preparation_time_minutes": row[5] if row[5] else 0, "category_id": row[6]}
            # Adiciona URL da imagem do banco se existir
            if row[7]:  # IMAGE_URL
                product["image_url"] = row[7]
                product["image_hash"] = _get_image_hash(row[7])
            
            # Adiciona status de disponibilidade baseado no estoque
            product["availability_status"] = _get_product_availability_status(product_id, cur)
            
            return product
        return None  
    except fdb.Error as e:  
        print(f"Erro ao buscar produto por ID: {e}")  
        return None  
    finally:  
        if conn: conn.close()  


def update_product(product_id, update_data):  
    allowed_fields = ['name', 'description', 'price', 'cost_price', 'preparation_time_minutes', 'is_active', 'category_id']  
    fields_to_update = {k: v for k, v in update_data.items() if k in allowed_fields}  
    if not fields_to_update:  
        return (False, "NO_VALID_FIELDS", "Nenhum campo válido para atualização foi fornecido")  
    if 'name' in fields_to_update:  
        name = fields_to_update['name']  
        if not name or not name.strip():  
            return (False, "INVALID_NAME", "Nome do produto é obrigatório")  
    if 'price' in fields_to_update:  
        price = fields_to_update['price']  
        if price is None or price <= 0:  
            return (False, "INVALID_PRICE", "Preço deve ser maior que zero")  
    if 'cost_price' in fields_to_update:  
        cost_price = fields_to_update['cost_price']  
        if cost_price is not None and cost_price < 0:  
            return (False, "INVALID_COST_PRICE", "Preço de custo não pode ser negativo")  
    if 'preparation_time_minutes' in fields_to_update:  
        prep_time = fields_to_update['preparation_time_minutes']  
        if prep_time is not None and prep_time < 0:  
            return (False, "INVALID_PREP_TIME", "Tempo de preparo não pode ser negativo")  
    if 'category_id' in fields_to_update:  
        category_id = fields_to_update['category_id']  
        if category_id == -1:  # Valor especial para remoção de categoria
            # Remove a categoria (define como NULL no banco)
            fields_to_update['category_id'] = None
        elif category_id is None:  
            return (False, "INVALID_CATEGORY", "Categoria é obrigatória")  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        sql_check_exists = "SELECT 1 FROM PRODUCTS WHERE ID = ? AND IS_ACTIVE = TRUE;"  
        cur.execute(sql_check_exists, (product_id,))  
        if not cur.fetchone():  
            return (False, "PRODUCT_NOT_FOUND", "Produto não encontrado")  
        if 'name' in fields_to_update:  
            sql_check_name = "SELECT ID FROM PRODUCTS WHERE UPPER(NAME) = UPPER(?) AND ID <> ? AND IS_ACTIVE = TRUE;"  
            cur.execute(sql_check_name, (fields_to_update['name'], product_id))  
            if cur.fetchone():  
                return (False, "PRODUCT_NAME_EXISTS", "Já existe um produto com este nome")  
        if 'category_id' in fields_to_update and fields_to_update['category_id'] is not None:  
            cur.execute("SELECT 1 FROM CATEGORIES WHERE ID = ? AND IS_ACTIVE = TRUE;", (fields_to_update['category_id'],))  
            if not cur.fetchone():  
                return (False, "CATEGORY_NOT_FOUND", "Categoria informada não existe ou está inativa")  
        set_parts = [f"{key} = ?" for key in fields_to_update]  
        values = list(fields_to_update.values())  
        values.append(product_id)  
        sql = f"UPDATE PRODUCTS SET {', '.join(set_parts)} WHERE ID = ? AND IS_ACTIVE = TRUE;"  
        cur.execute(sql, tuple(values))  
        conn.commit()  
        return (True, None, "Produto atualizado com sucesso")  
    except fdb.Error as e:  
        print(f"Erro ao atualizar produto: {e}")  
        if conn: conn.rollback()  
        return (False, "DATABASE_ERROR", "Erro interno do servidor")  
    finally:  
        if conn: conn.close()  


def deactivate_product(product_id):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        
        # Primeiro verifica se o produto existe
        sql_check = "SELECT ID FROM PRODUCTS WHERE ID = ?;"
        cur.execute(sql_check, (product_id,))
        if not cur.fetchone():
            return False  # Produto não existe
        
        # Atualiza o produto para inativo
        sql = "UPDATE PRODUCTS SET IS_ACTIVE = FALSE WHERE ID = ?;"  
        cur.execute(sql, (product_id,))  
        conn.commit()  
        return True  # Sempre retorna True se o produto existe
    except fdb.Error as e:  
        print(f"Erro ao inativar produto: {e}")  
        if conn: conn.rollback()  
        return False  
    finally:  
        if conn: conn.close()  


def update_product_image_url(product_id, image_url):
    """Atualiza a URL da imagem do produto no banco de dados"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se o produto existe
        sql_check = "SELECT ID FROM PRODUCTS WHERE ID = ?;"
        cur.execute(sql_check, (product_id,))
        if not cur.fetchone():
            return False  # Produto não existe
        
        # Atualiza a URL da imagem
        sql = "UPDATE PRODUCTS SET IMAGE_URL = ? WHERE ID = ?;"
        cur.execute(sql, (image_url, product_id))
        conn.commit()
        return True
    except fdb.Error as e:
        print(f"Erro ao atualizar URL da imagem: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()


def reactivate_product(product_id):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        
        # Primeiro verifica se o produto existe
        sql_check = "SELECT ID FROM PRODUCTS WHERE ID = ?;"
        cur.execute(sql_check, (product_id,))
        if not cur.fetchone():
            return False  # Produto não existe
        
        # Atualiza o produto para ativo
        sql = "UPDATE PRODUCTS SET IS_ACTIVE = TRUE WHERE ID = ?;"  
        cur.execute(sql, (product_id,))
        conn.commit()
        return True  # Sempre retorna True se o produto existe
    except fdb.Error as e:  
        print(f"Erro ao reativar produto: {e}")  
        if conn: conn.rollback()  
        return False  
    finally:  
        if conn: conn.close()


def search_products(name=None, category_id=None, page=1, page_size=10, include_inactive=False):  
    # Alias para list_products com mesmos filtros — mantém rota semanticamente distinta
    return list_products(name_filter=name, category_id=category_id, page=page, page_size=page_size, include_inactive=include_inactive)



def get_products_by_category_id(category_id, page=1, page_size=10, include_inactive=False):  
    """
    Busca produtos por ID da categoria específica
    """
    page = max(int(page or 1), 1)  
    page_size = max(int(page_size or 10), 1)  
    offset = (page - 1) * page_size  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        
        # Primeiro verifica se a categoria existe
        cur.execute("SELECT ID, NAME FROM CATEGORIES WHERE ID = ? AND IS_ACTIVE = TRUE;", (category_id,))  
        category_row = cur.fetchone()
        if not category_row:
            return (None, "CATEGORY_NOT_FOUND", "Categoria não encontrada ou inativa")
        
        category_name = category_row[1]
        
        # Monta a query para buscar produtos
        where_clauses = ["CATEGORY_ID = ?"]
        params = [category_id]
        
        if not include_inactive:
            where_clauses.append("IS_ACTIVE = TRUE")
            
        where_sql = " AND ".join(where_clauses)
        
        # Conta total de produtos na categoria
        cur.execute(f"SELECT COUNT(*) FROM PRODUCTS WHERE {where_sql};", tuple(params))  
        total = cur.fetchone()[0] or 0  
        
        # Busca os produtos paginados
        cur.execute(  
            f"SELECT FIRST {page_size} SKIP {offset} p.ID, p.NAME, p.DESCRIPTION, p.PRICE, p.COST_PRICE, p.PREPARATION_TIME_MINUTES, p.CATEGORY_ID, p.IMAGE_URL, p.IS_ACTIVE, c.NAME as CATEGORY_NAME "  
            f"FROM PRODUCTS p LEFT JOIN CATEGORIES c ON p.CATEGORY_ID = c.ID WHERE {where_sql} ORDER BY p.NAME;",  
            tuple(params)  
        )  
        
        items = []  
        for row in cur.fetchall():
            product_id = row[0]
            item = {  
                "id": product_id,  
                "name": row[1],  
                "description": row[2],  
                "price": str(row[3]),  
                "cost_price": str(row[4]) if row[4] else "0.00",  
                "preparation_time_minutes": row[5] if row[5] else 0,  
                "category_id": row[6],
                "is_active": row[8] if len(row) > 8 else True,
                "category_name": row[9] if len(row) > 9 and row[9] else "Sem categoria"
            }
            # Adiciona URL da imagem do banco se existir
            if row[7]:  # IMAGE_URL
                item["image_url"] = row[7]
                item["image_hash"] = _get_image_hash(row[7])
            items.append(item)  
            
        total_pages = (total + page_size - 1) // page_size  
        
        result = {  
            "category": {
                "id": category_id,
                "name": category_name
            },
            "items": items,  
            "pagination": {  
                "total": total,  
                "page": page,  
                "page_size": page_size,  
                "total_pages": total_pages  
            }  
        }
        
        return (result, None, None)
        
    except fdb.Error as e:  
        print(f"Erro ao buscar produtos por categoria: {e}")  
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    finally:  
        if conn: conn.close()


def get_menu_summary():  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        cur.execute("SELECT COUNT(*) FROM PRODUCTS WHERE IS_ACTIVE = TRUE")  
        total_items = cur.fetchone()[0]  
        cur.execute("SELECT AVG(PRICE) FROM PRODUCTS WHERE IS_ACTIVE = TRUE AND PRICE > 0")  
        price_result = cur.fetchone()  
        avg_price = float(price_result[0]) if price_result and price_result[0] else 0.0  
        cur.execute("""
            SELECT AVG(PRICE - COST_PRICE) 
            FROM PRODUCTS 
            WHERE IS_ACTIVE = TRUE AND PRICE > 0 AND COST_PRICE > 0
        """)  
        margin_result = cur.fetchone()  
        avg_margin = float(margin_result[0]) if margin_result and margin_result[0] else 0.0  
        cur.execute("""
            SELECT AVG(PREPARATION_TIME_MINUTES) 
            FROM PRODUCTS 
            WHERE IS_ACTIVE = TRUE AND PREPARATION_TIME_MINUTES > 0
        """)  
        prep_result = cur.fetchone()  
        avg_prep_time = float(prep_result[0]) if prep_result and prep_result[0] else 0.0  
        return {  
            "total_items": total_items,
            "average_price": round(avg_price, 2),
            "average_margin": round(avg_margin, 2),
            "average_preparation_time": round(avg_prep_time, 1)
        }
    except fdb.Error as e:  
        print(f"Erro ao buscar resumo do cardápio: {e}")  
        return {  
            "total_items": 0,
            "average_price": 0.0,
            "average_margin": 0.0,
            "average_preparation_time": 0.0
        }
    finally:  
        if conn: conn.close()


def calculate_product_cost_by_ingredients(product_id):
    """
    Calcula o custo do produto baseado nas porções dos ingredientes
    """
    from .ingredient_service import calculate_product_cost_by_portions
    return calculate_product_cost_by_portions(product_id)


def consume_ingredients_for_sale(product_id, quantity=1):
    """
    Consome ingredientes do estoque quando um produto é vendido
    """
    from .ingredient_service import consume_ingredients_for_product
    return consume_ingredients_for_product(product_id, quantity)


def get_product_ingredients_with_costs(product_id):
    """
    Retorna os ingredientes do produto com cálculos de custo baseados em porções
    """
    from .ingredient_service import get_ingredients_for_product
    return get_ingredients_for_product(product_id)


def delete_product(product_id):
    """
    Exclui permanentemente um produto e todos os seus relacionamentos
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. Verificar se o produto existe
        cur.execute("SELECT ID, NAME FROM PRODUCTS WHERE ID = ?", (product_id,))
        product = cur.fetchone()
        if not product:
            return (False, "PRODUCT_NOT_FOUND", "Produto não encontrado")
        
        product_name = product[1]
        
        # 2. Verificar se o produto tem pedidos associados
        cur.execute("""
            SELECT COUNT(*) FROM ORDER_ITEMS oi
            JOIN ORDERS o ON oi.ORDER_ID = o.ID
            WHERE oi.PRODUCT_ID = ? AND o.STATUS NOT IN ('cancelled', 'delivered')
        """, (product_id,))
        active_orders = cur.fetchone()[0] or 0
        
        if active_orders > 0:
            return (False, "PRODUCT_IN_ACTIVE_ORDERS", 
                   f"Produto não pode ser excluído pois possui {active_orders} pedido(s) ativo(s)")
        
        # 3. Verificar se o produto tem itens no carrinho
        cur.execute("""
            SELECT COUNT(*) FROM CART_ITEMS ci
            JOIN CARTS c ON ci.CART_ID = c.ID
            WHERE ci.PRODUCT_ID = ? AND c.IS_ACTIVE = TRUE
        """, (product_id,))
        cart_items = cur.fetchone()[0] or 0
        
        if cart_items > 0:
            return (False, "PRODUCT_IN_CART", 
                   f"Produto não pode ser excluído pois está em {cart_items} carrinho(s) ativo(s)")
        
        # 4. Remover ingredientes relacionados (PRODUCT_INGREDIENTS)
        cur.execute("DELETE FROM PRODUCT_INGREDIENTS WHERE PRODUCT_ID = ?", (product_id,))
        ingredients_removed = cur.rowcount
        
        # 5. Remover extras relacionados (ORDER_ITEM_EXTRAS) - se existir
        cur.execute("""
            DELETE FROM ORDER_ITEM_EXTRAS 
            WHERE ORDER_ITEM_ID IN (
                SELECT ID FROM ORDER_ITEMS WHERE PRODUCT_ID = ?
            )
        """, (product_id,))
        extras_removed = cur.rowcount
        
        # 6. Remover itens de pedido relacionados (ORDER_ITEMS)
        cur.execute("DELETE FROM ORDER_ITEMS WHERE PRODUCT_ID = ?", (product_id,))
        order_items_removed = cur.rowcount
        
        # 7. Remover itens do carrinho relacionados (CART_ITEMS)
        cur.execute("DELETE FROM CART_ITEMS WHERE PRODUCT_ID = ?", (product_id,))
        cart_items_removed = cur.rowcount
        
        # 8. Remover extras do carrinho relacionados (CART_ITEM_EXTRAS) - se existir
        cur.execute("""
            DELETE FROM CART_ITEM_EXTRAS 
            WHERE CART_ITEM_ID IN (
                SELECT ID FROM CART_ITEMS WHERE PRODUCT_ID = ?
            )
        """, (product_id,))
        cart_extras_removed = cur.rowcount
        
        # 9. Finalmente, excluir o produto
        cur.execute("DELETE FROM PRODUCTS WHERE ID = ?", (product_id,))
        product_removed = cur.rowcount
        
        if product_removed == 0:
            return (False, "DELETE_FAILED", "Falha ao excluir o produto")
        
        conn.commit()
        
        # 10. Remover imagem do produto se existir
        try:
            from ..utils.image_handler import delete_product_image
            delete_product_image(product_id)
        except Exception as e:
            print(f"Aviso: Erro ao remover imagem do produto {product_id}: {e}")
        
        return (True, None, {
            "message": f"Produto '{product_name}' excluído permanentemente",
            "details": {
                "ingredients_removed": ingredients_removed,
                "order_items_removed": order_items_removed,
                "cart_items_removed": cart_items_removed,
                "extras_removed": extras_removed,
                "cart_extras_removed": cart_extras_removed
            }
        })
        
    except fdb.Error as e:
        print(f"Erro ao excluir produto: {e}")
        if conn: 
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    except Exception as e:
        print(f"Erro geral ao excluir produto: {e}")
        if conn: 
            conn.rollback()
        return (False, "GENERAL_ERROR", "Erro interno do servidor")
    finally:
        if conn: 
            conn.close()  
