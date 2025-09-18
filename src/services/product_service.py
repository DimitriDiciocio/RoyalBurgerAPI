# src/services/product_service.py

import fdb
from ..database import get_db_connection


def create_product(product_data):
    """Cria um novo produto no banco de dados."""
    name = product_data.get('name')
    description = product_data.get('description')
    price = product_data.get('price')

    # Validações básicas
    if not name or not name.strip():
        return (None, "INVALID_NAME", "Nome do produto é obrigatório")
    
    if price is None or price <= 0:
        return (None, "INVALID_PRICE", "Preço deve ser maior que zero")

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se já existe um produto com o mesmo nome
        sql_check = "SELECT ID FROM PRODUCTS WHERE UPPER(NAME) = UPPER(?) AND IS_ACTIVE = TRUE;"
        cur.execute(sql_check, (name,))
        if cur.fetchone():
            return (None, "PRODUCT_NAME_EXISTS", "Já existe um produto com este nome")
        
        sql = "INSERT INTO PRODUCTS (NAME, DESCRIPTION, PRICE) VALUES (?, ?, ?) RETURNING ID;"
        cur.execute(sql, (name, description, price))
        new_product_id = cur.fetchone()[0]
        conn.commit()
        return ({"id": new_product_id, "name": name, "description": description, "price": price}, None, None)
    except fdb.Error as e:
        print(f"Erro ao criar produto: {e}")
        if conn: conn.rollback()
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def get_all_products():
    """Busca todos os produtos ativos."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = "SELECT ID, NAME, DESCRIPTION, PRICE FROM PRODUCTS WHERE IS_ACTIVE = TRUE ORDER BY NAME;"
        cur.execute(sql)
        products = [{"id": row[0], "name": row[1], "description": row[2], "price": str(row[3])} for row in
                    cur.fetchall()]
        return products
    except fdb.Error as e:
        print(f"Erro ao buscar produtos: {e}")
        return []
    finally:
        if conn: conn.close()


def get_product_by_id(product_id):
    """Busca um único produto ativo pelo ID."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = "SELECT ID, NAME, DESCRIPTION, PRICE FROM PRODUCTS WHERE ID = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql, (product_id,))
        row = cur.fetchone()
        if row:
            return {"id": row[0], "name": row[1], "description": row[2], "price": str(row[3])}
        return None
    except fdb.Error as e:
        print(f"Erro ao buscar produto por ID: {e}")
        return None
    finally:
        if conn: conn.close()


def update_product(product_id, update_data):
    """Atualiza dados de um produto."""
    allowed_fields = ['name', 'description', 'price']
    fields_to_update = {k: v for k, v in update_data.items() if k in allowed_fields}
    
    if not fields_to_update:
        return (False, "NO_VALID_FIELDS", "Nenhum campo válido para atualização foi fornecido")

    # Validações específicas
    if 'name' in fields_to_update:
        name = fields_to_update['name']
        if not name or not name.strip():
            return (False, "INVALID_NAME", "Nome do produto é obrigatório")
    
    if 'price' in fields_to_update:
        price = fields_to_update['price']
        if price is None or price <= 0:
            return (False, "INVALID_PRICE", "Preço deve ser maior que zero")

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se o produto existe
        sql_check_exists = "SELECT 1 FROM PRODUCTS WHERE ID = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql_check_exists, (product_id,))
        if not cur.fetchone():
            return (False, "PRODUCT_NOT_FOUND", "Produto não encontrado")
        
        # Se está atualizando o nome, verifica se não há duplicata
        if 'name' in fields_to_update:
            sql_check_name = "SELECT ID FROM PRODUCTS WHERE UPPER(NAME) = UPPER(?) AND ID <> ? AND IS_ACTIVE = TRUE;"
            cur.execute(sql_check_name, (fields_to_update['name'], product_id))
            if cur.fetchone():
                return (False, "PRODUCT_NAME_EXISTS", "Já existe um produto com este nome")

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
    """Inativa um produto (Soft Delete)."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = "UPDATE PRODUCTS SET IS_ACTIVE = FALSE WHERE ID = ?;"
        cur.execute(sql, (product_id,))
        conn.commit()
        return cur.rowcount > 0
    except fdb.Error as e:
        print(f"Erro ao inativar produto: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

def add_product_to_section(product_id, section_id):
    """Associa um produto a uma seção."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = "INSERT INTO PRODUCT_SECTION_ITEMS (PRODUCT_ID, SECTION_ID) VALUES (?, ?);"
        cur.execute(sql, (product_id, section_id))
        conn.commit()
        return True
    except fdb.IntegrityError:
        # Ignora o erro se a associação já existir, não é um problema.
        return True
    except fdb.Error as e:
        print(f"Erro ao associar produto à seção: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

def remove_product_from_section(product_id, section_id):
    """Remove a associação de um produto de uma seção."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = "DELETE FROM PRODUCT_SECTION_ITEMS WHERE PRODUCT_ID = ? AND SECTION_ID = ?;"
        cur.execute(sql, (product_id, section_id))
        conn.commit()
        return cur.rowcount > 0
    except fdb.Error as e:
        print(f"Erro ao remover associação: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

# --- Funções de CRUD para Seções (Product Sections) ---

def create_section(section_data, user_id):
    """Cria uma nova seção no cardápio."""
    name = section_data.get('name')
    display_order = section_data.get('display_order', 0)

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = "INSERT INTO PRODUCT_SECTIONS (NAME, DISPLAY_ORDER, CREATED_BY_USER_ID) VALUES (?, ?, ?) RETURNING ID;"
        cur.execute(sql, (name, display_order, user_id))
        new_section_id = cur.fetchone()[0]
        conn.commit()
        return {"id": new_section_id, "name": name, "display_order": display_order}
    except fdb.Error as e:
        print(f"Erro ao criar seção: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: conn.close()


def get_all_sections():
    """Busca todas as seções do cardápio, ordenadas pela ordem de exibição."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = "SELECT ID, NAME, DISPLAY_ORDER FROM PRODUCT_SECTIONS ORDER BY DISPLAY_ORDER, NAME;"
        cur.execute(sql)
        sections = [{"id": row[0], "name": row[1], "display_order": row[2]} for row in cur.fetchall()]
        return sections
    except fdb.Error as e:
        print(f"Erro ao buscar seções: {e}")
        return []
    finally:
        if conn: conn.close()


def update_section(section_id, update_data):
    """Atualiza os dados de uma seção."""
    allowed_fields = ['name', 'display_order']
    set_parts = [f"{key.upper()} = ?" for key in update_data if key in allowed_fields]
    if not set_parts: return False

    values = [value for key, value in update_data.items() if key in allowed_fields]
    values.append(section_id)

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = f"UPDATE PRODUCT_SECTIONS SET {', '.join(set_parts)} WHERE ID = ?;"
        cur.execute(sql, tuple(values))
        conn.commit()
        return cur.rowcount > 0
    except fdb.Error as e:
        print(f"Erro ao atualizar seção: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()


def delete_section(section_id):
    """Deleta uma seção. O 'ON DELETE CASCADE' cuidará da tabela de associação."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = "DELETE FROM PRODUCT_SECTIONS WHERE ID = ?;"
        cur.execute(sql, (section_id,))
        conn.commit()
        return cur.rowcount > 0
    except fdb.Error as e:
        print(f"Erro ao deletar seção: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()


def get_section_by_id(section_id):
    """Busca uma única seção pelo seu ID, incluindo seus produtos."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Busca os dados da seção
        sql_section = "SELECT ID, NAME, DISPLAY_ORDER FROM SECTIONS WHERE ID = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql_section, (section_id,))
        section_data = cur.fetchone()

        if not section_data:
            return None  # Retorna None se a seção não for encontrada

        section = {
            "id": section_data[0],
            "name": section_data[1],
            "display_order": section_data[2],
            "products": []
        }

        # Busca os produtos associados a essa seção
        sql_products = """
            SELECT ID, NAME, DESCRIPTION, PRICE, IMAGE_URL
            FROM PRODUCTS 
            WHERE SECTION_ID = ? AND IS_ACTIVE = TRUE 
            ORDER BY NAME;
        """
        cur.execute(sql_products, (section_id,))
        for row in cur.fetchall():
            section["products"].append({
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "price": row[3],
                "image_url": row[4]
            })

        return section
    except fdb.Error as e:
        print(f"Erro ao buscar seção por ID: {e}")
        return None
    finally:
        if conn: conn.close()