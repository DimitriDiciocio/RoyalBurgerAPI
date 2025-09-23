import fdb  # importa driver do Firebird
from ..database import get_db_connection  # importa função de conexão com o banco

def create_product(product_data):  # cria novo produto no banco
    name = product_data.get('name')  # extrai nome do produto
    description = product_data.get('description')  # extrai descrição
    price = product_data.get('price')  # extrai preço
    cost_price = product_data.get('cost_price', 0.0)  # extrai preço de custo
    preparation_time_minutes = product_data.get('preparation_time_minutes', 0)  # extrai tempo de preparo
    if not name or not name.strip():  # valida nome obrigatório
        return (None, "INVALID_NAME", "Nome do produto é obrigatório")  # retorna erro
    if price is None or price <= 0:  # valida preço positivo
        return (None, "INVALID_PRICE", "Preço deve ser maior que zero")  # retorna erro
    if cost_price is not None and cost_price < 0:  # valida preço de custo não negativo
        return (None, "INVALID_COST_PRICE", "Preço de custo não pode ser negativo")  # retorna erro
    if preparation_time_minutes is not None and preparation_time_minutes < 0:  # valida tempo não negativo
        return (None, "INVALID_PREP_TIME", "Tempo de preparo não pode ser negativo")  # retorna erro
    conn = None  # inicializa conexão
    try:  # tenta criar produto
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql_check = "SELECT ID FROM PRODUCTS WHERE UPPER(NAME) = UPPER(?) AND IS_ACTIVE = TRUE;"  # verifica duplicata
        cur.execute(sql_check, (name,))  # executa verificação
        if cur.fetchone():  # se produto existe
            return (None, "PRODUCT_NAME_EXISTS", "Já existe um produto com este nome")  # retorna erro
        sql = "INSERT INTO PRODUCTS (NAME, DESCRIPTION, PRICE, COST_PRICE, PREPARATION_TIME_MINUTES) VALUES (?, ?, ?, ?, ?) RETURNING ID;"  # SQL de inserção
        cur.execute(sql, (name, description, price, cost_price, preparation_time_minutes))  # executa inserção
        new_product_id = cur.fetchone()[0]  # obtém ID do produto criado
        conn.commit()  # confirma transação
        return ({"id": new_product_id, "name": name, "description": description, "price": price, "cost_price": cost_price, "preparation_time_minutes": preparation_time_minutes}, None, None)  # retorna sucesso
    except fdb.Error as e:  # captura erros
        print(f"Erro ao criar produto: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return (None, "DATABASE_ERROR", "Erro interno do servidor")  # retorna erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão


def get_all_products():  # busca todos os produtos ativos
    conn = None  # inicializa conexão
    try:  # tenta buscar produtos
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = "SELECT ID, NAME, DESCRIPTION, PRICE, COST_PRICE, PREPARATION_TIME_MINUTES FROM PRODUCTS WHERE IS_ACTIVE = TRUE ORDER BY NAME;"  # SQL de busca
        cur.execute(sql)  # executa query
        products = [{"id": row[0], "name": row[1], "description": row[2], "price": str(row[3]), "cost_price": str(row[4]) if row[4] else "0.00", "preparation_time_minutes": row[5] if row[5] else 0} for row in cur.fetchall()]  # monta lista de produtos
        return products  # retorna lista
    except fdb.Error as e:  # captura erros
        print(f"Erro ao buscar produtos: {e}")  # exibe erro
        return []  # retorna vazio em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão


def get_product_by_id(product_id):  # busca produto ativo por ID
    conn = None  # inicializa conexão
    try:  # tenta buscar produto
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = "SELECT ID, NAME, DESCRIPTION, PRICE, COST_PRICE, PREPARATION_TIME_MINUTES FROM PRODUCTS WHERE ID = ? AND IS_ACTIVE = TRUE;"  # SQL de busca
        cur.execute(sql, (product_id,))  # executa query
        row = cur.fetchone()  # obtém linha
        if row:  # se produto encontrado
            return {"id": row[0], "name": row[1], "description": row[2], "price": str(row[3]), "cost_price": str(row[4]) if row[4] else "0.00", "preparation_time_minutes": row[5] if row[5] else 0}  # retorna dados
        return None  # retorna None se não encontrado
    except fdb.Error as e:  # captura erros
        print(f"Erro ao buscar produto por ID: {e}")  # exibe erro
        return None  # retorna None em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão


def update_product(product_id, update_data):  # atualiza dados de um produto
    allowed_fields = ['name', 'description', 'price', 'cost_price', 'preparation_time_minutes', 'is_active']  # campos permitidos
    fields_to_update = {k: v for k, v in update_data.items() if k in allowed_fields}  # filtra campos válidos
    if not fields_to_update:  # se nenhum campo válido
        return (False, "NO_VALID_FIELDS", "Nenhum campo válido para atualização foi fornecido")  # retorna erro
    if 'name' in fields_to_update:  # valida nome se presente
        name = fields_to_update['name']  # extrai nome
        if not name or not name.strip():  # verifica se não vazio
            return (False, "INVALID_NAME", "Nome do produto é obrigatório")  # retorna erro
    if 'price' in fields_to_update:  # valida preço se presente
        price = fields_to_update['price']  # extrai preço
        if price is None or price <= 0:  # verifica se positivo
            return (False, "INVALID_PRICE", "Preço deve ser maior que zero")  # retorna erro
    if 'cost_price' in fields_to_update:  # valida preço de custo se presente
        cost_price = fields_to_update['cost_price']  # extrai preço de custo
        if cost_price is not None and cost_price < 0:  # verifica se não negativo
            return (False, "INVALID_COST_PRICE", "Preço de custo não pode ser negativo")  # retorna erro
    if 'preparation_time_minutes' in fields_to_update:  # valida tempo se presente
        prep_time = fields_to_update['preparation_time_minutes']  # extrai tempo
        if prep_time is not None and prep_time < 0:  # verifica se não negativo
            return (False, "INVALID_PREP_TIME", "Tempo de preparo não pode ser negativo")  # retorna erro
    conn = None  # inicializa conexão
    try:  # tenta atualizar
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql_check_exists = "SELECT 1 FROM PRODUCTS WHERE ID = ? AND IS_ACTIVE = TRUE;"  # verifica se produto existe
        cur.execute(sql_check_exists, (product_id,))  # executa verificação
        if not cur.fetchone():  # se produto não existe
            return (False, "PRODUCT_NOT_FOUND", "Produto não encontrado")  # retorna erro
        if 'name' in fields_to_update:  # se atualizando nome
            sql_check_name = "SELECT ID FROM PRODUCTS WHERE UPPER(NAME) = UPPER(?) AND ID <> ? AND IS_ACTIVE = TRUE;"  # verifica duplicata
            cur.execute(sql_check_name, (fields_to_update['name'], product_id))  # executa verificação
            if cur.fetchone():  # se nome duplicado
                return (False, "PRODUCT_NAME_EXISTS", "Já existe um produto com este nome")  # retorna erro
        set_parts = [f"{key} = ?" for key in fields_to_update]  # monta partes do SET
        values = list(fields_to_update.values())  # extrai valores
        values.append(product_id)  # adiciona ID para WHERE
        sql = f"UPDATE PRODUCTS SET {', '.join(set_parts)} WHERE ID = ? AND IS_ACTIVE = TRUE;"  # SQL de update
        cur.execute(sql, tuple(values))  # executa update
        conn.commit()  # confirma transação
        return (True, None, "Produto atualizado com sucesso")  # retorna sucesso
    except fdb.Error as e:  # captura erros
        print(f"Erro ao atualizar produto: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return (False, "DATABASE_ERROR", "Erro interno do servidor")  # retorna erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão


def deactivate_product(product_id):  # inativa produto (soft delete)
    conn = None  # inicializa conexão
    try:  # tenta inativar
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = "UPDATE PRODUCTS SET IS_ACTIVE = FALSE WHERE ID = ?;"  # SQL de inativação
        cur.execute(sql, (product_id,))  # executa update
        conn.commit()  # confirma transação
        return cur.rowcount > 0  # retorna True se atualizou
    except fdb.Error as e:  # captura erros
        print(f"Erro ao inativar produto: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return False  # retorna False em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def add_product_to_section(product_id, section_id):  # associa produto a seção
    conn = None  # inicializa conexão
    try:  # tenta associar
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = "INSERT INTO PRODUCT_SECTION_ITEMS (PRODUCT_ID, SECTION_ID) VALUES (?, ?);"  # SQL de inserção
        cur.execute(sql, (product_id, section_id))  # executa inserção
        conn.commit()  # confirma transação
        return True  # retorna sucesso
    except fdb.IntegrityError:  # se associação já existe
        return True  # ignora erro (não é problema)
    except fdb.Error as e:  # captura outros erros
        print(f"Erro ao associar produto à seção: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return False  # retorna False em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def remove_product_from_section(product_id, section_id):  # remove associação produto-seção
    conn = None  # inicializa conexão
    try:  # tenta remover
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = "DELETE FROM PRODUCT_SECTION_ITEMS WHERE PRODUCT_ID = ? AND SECTION_ID = ?;"  # SQL de remoção
        cur.execute(sql, (product_id, section_id))  # executa delete
        conn.commit()  # confirma transação
        return cur.rowcount > 0  # retorna True se removeu
    except fdb.Error as e:  # captura erros
        print(f"Erro ao remover associação: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return False  # retorna False em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def create_section(section_data, user_id):  # cria nova seção no cardápio
    name = section_data.get('name')  # extrai nome da seção
    display_order = section_data.get('display_order', 0)  # extrai ordem de exibição
    conn = None  # inicializa conexão
    try:  # tenta criar seção
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = "INSERT INTO PRODUCT_SECTIONS (NAME, DISPLAY_ORDER, CREATED_BY_USER_ID) VALUES (?, ?, ?) RETURNING ID;"  # SQL de inserção
        cur.execute(sql, (name, display_order, user_id))  # executa inserção
        new_section_id = cur.fetchone()[0]  # obtém ID da seção criada
        conn.commit()  # confirma transação
        return {"id": new_section_id, "name": name, "display_order": display_order}  # retorna dados da seção
    except fdb.Error as e:  # captura erros
        print(f"Erro ao criar seção: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return None  # retorna None em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão


def get_all_sections():  # busca todas as seções do cardápio
    conn = None  # inicializa conexão
    try:  # tenta buscar seções
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = "SELECT ID, NAME, DISPLAY_ORDER FROM PRODUCT_SECTIONS ORDER BY DISPLAY_ORDER, NAME;"  # SQL de busca
        cur.execute(sql)  # executa query
        sections = [{"id": row[0], "name": row[1], "display_order": row[2]} for row in cur.fetchall()]  # monta lista de seções
        return sections  # retorna lista
    except fdb.Error as e:  # captura erros
        print(f"Erro ao buscar seções: {e}")  # exibe erro
        return []  # retorna vazio em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão


def update_section(section_id, update_data):  # atualiza dados de uma seção
    allowed_fields = ['name', 'display_order']  # campos permitidos
    set_parts = [f"{key.upper()} = ?" for key in update_data if key in allowed_fields]  # monta partes do SET
    if not set_parts: return False  # retorna False se nenhum campo válido
    values = [value for key, value in update_data.items() if key in allowed_fields]  # extrai valores
    values.append(section_id)  # adiciona ID para WHERE
    conn = None  # inicializa conexão
    try:  # tenta atualizar
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = f"UPDATE PRODUCT_SECTIONS SET {', '.join(set_parts)} WHERE ID = ?;"  # SQL de update
        cur.execute(sql, tuple(values))  # executa update
        conn.commit()  # confirma transação
        return cur.rowcount > 0  # retorna True se atualizou
    except fdb.Error as e:  # captura erros
        print(f"Erro ao atualizar seção: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return False  # retorna False em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão


def delete_section(section_id):  # deleta seção (cascade remove associações)
    conn = None  # inicializa conexão
    try:  # tenta deletar
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = "DELETE FROM PRODUCT_SECTIONS WHERE ID = ?;"  # SQL de delete
        cur.execute(sql, (section_id,))  # executa delete
        conn.commit()  # confirma transação
        return cur.rowcount > 0  # retorna True se deletou
    except fdb.Error as e:  # captura erros
        print(f"Erro ao deletar seção: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return False  # retorna False em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão


def get_section_by_id(section_id):  # busca seção por ID com produtos
    conn = None  # inicializa conexão
    try:  # tenta buscar seção
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql_section = "SELECT ID, NAME, DISPLAY_ORDER FROM SECTIONS WHERE ID = ? AND IS_ACTIVE = TRUE;"  # busca dados da seção
        cur.execute(sql_section, (section_id,))  # executa query
        section_data = cur.fetchone()  # obtém dados da seção
        if not section_data:  # se seção não encontrada
            return None  # retorna None
        section = {  # monta dicionário da seção
            "id": section_data[0],
            "name": section_data[1],
            "display_order": section_data[2],
            "products": []
        }
        sql_products = """
            SELECT ID, NAME, DESCRIPTION, PRICE, IMAGE_URL
            FROM PRODUCTS 
            WHERE SECTION_ID = ? AND IS_ACTIVE = TRUE 
            ORDER BY NAME;
        """  # busca produtos da seção
        cur.execute(sql_products, (section_id,))  # executa query
        for row in cur.fetchall():  # itera produtos
            section["products"].append({  # adiciona produto à seção
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "price": row[3],
                "image_url": row[4]
            })
        return section  # retorna seção com produtos
    except fdb.Error as e:  # captura erros
        print(f"Erro ao buscar seção por ID: {e}")  # exibe erro
        return None  # retorna None em erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão


def get_menu_summary():  # retorna KPIs do cardápio
    conn = None  # inicializa conexão
    try:  # tenta buscar KPIs
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        cur.execute("SELECT COUNT(*) FROM PRODUCTS WHERE IS_ACTIVE = TRUE")  # conta itens ativos
        total_items = cur.fetchone()[0]  # extrai total de itens
        cur.execute("SELECT AVG(PRICE) FROM PRODUCTS WHERE IS_ACTIVE = TRUE AND PRICE > 0")  # calcula preço médio
        price_result = cur.fetchone()  # obtém resultado
        avg_price = float(price_result[0]) if price_result and price_result[0] else 0.0  # converte para float
        cur.execute("""
            SELECT AVG(PRICE - COST_PRICE) 
            FROM PRODUCTS 
            WHERE IS_ACTIVE = TRUE AND PRICE > 0 AND COST_PRICE > 0
        """)  # calcula margem média
        margin_result = cur.fetchone()  # obtém resultado
        avg_margin = float(margin_result[0]) if margin_result and margin_result[0] else 0.0  # converte para float
        cur.execute("""
            SELECT AVG(PREPARATION_TIME_MINUTES) 
            FROM PRODUCTS 
            WHERE IS_ACTIVE = TRUE AND PREPARATION_TIME_MINUTES > 0
        """)  # calcula tempo médio de preparo
        prep_result = cur.fetchone()  # obtém resultado
        avg_prep_time = float(prep_result[0]) if prep_result and prep_result[0] else 0.0  # converte para float
        return {  # retorna KPIs
            "total_items": total_items,
            "average_price": round(avg_price, 2),
            "average_margin": round(avg_margin, 2),
            "average_preparation_time": round(avg_prep_time, 1)
        }
    except fdb.Error as e:  # captura erros
        print(f"Erro ao buscar resumo do cardápio: {e}")  # exibe erro
        return {  # retorna estrutura padrão em erro
            "total_items": 0,
            "average_price": 0.0,
            "average_margin": 0.0,
            "average_preparation_time": 0.0
        }
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão