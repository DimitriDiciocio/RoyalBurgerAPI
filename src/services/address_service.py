import fdb  
from ..database import get_db_connection  

def create_address(user_id, address_data):  
    # Ordem deve refletir as colunas do INSERT abaixo
    street = address_data.get('street')  
    number = address_data.get('number')  
    complement = address_data.get('complement')  
    neighborhood = address_data.get('neighborhood')  
    city = address_data.get('city')  
    state = address_data.get('state')  
    zip_code = address_data.get('zip_code')  
    values = [user_id, street, number, complement, neighborhood, city, state, zip_code]  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        sql = """
            INSERT INTO ADDRESSES (USER_ID, STREET, "NUMBER", COMPLEMENT, NEIGHBORHOOD, CITY, STATE, ZIP_CODE)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING ID;
        """  
        cur.execute(sql, tuple(values))  
        new_address_id = cur.fetchone()[0]  
        # Define o novo endereço como padrão e desmarca os demais do usuário
        cur.execute("UPDATE ADDRESSES SET IS_DEFAULT = FALSE WHERE USER_ID = ? AND ID <> ?;", (user_id, new_address_id))
        cur.execute("UPDATE ADDRESSES SET IS_DEFAULT = TRUE WHERE ID = ?;", (new_address_id,))
        conn.commit()  
        address_data['id'] = new_address_id  
        address_data['user_id'] = user_id  
        address_data['is_active'] = True  
        address_data['is_default'] = True  
        return address_data  
    except fdb.Error as e:  
        print(f"Erro ao criar endereço: {e}")  
        if conn: conn.rollback()  
        return None  
    finally:  
        if conn: conn.close()  

def get_addresses_by_user_id(user_id):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        sql = 'SELECT ID, STREET, "NUMBER", COMPLEMENT, NEIGHBORHOOD, CITY, STATE, ZIP_CODE, IS_ACTIVE, IS_DEFAULT FROM ADDRESSES WHERE USER_ID = ? AND IS_ACTIVE = TRUE;'  
        cur.execute(sql, (user_id,))  
        addresses = []  
        for row in cur.fetchall():  
            addresses.append({  
                "id": row[0],
                "street": row[1],
                "number": row[2],
                "complement": row[3],
                "neighborhood": row[4],
                "city": row[5],
                "state": row[6],
                "zip_code": row[7],
                "is_active": bool(row[8]) if row[8] is not None else True,
                "is_default": bool(row[9]) if row[9] is not None else False,
            })
        return addresses  
    except fdb.Error as e:  
        print(f"Erro ao buscar endereços: {e}")  
        return []  
    finally:  
        if conn: conn.close()  

def get_address_by_id(address_id):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        sql = 'SELECT ID, USER_ID, STREET, "NUMBER", COMPLEMENT, NEIGHBORHOOD, CITY, STATE, ZIP_CODE, IS_ACTIVE, IS_DEFAULT FROM ADDRESSES WHERE ID = ?;'  
        cur.execute(sql, (address_id,))  
        row = cur.fetchone()  
        if row:  
            return {  
                "id": row[0],
                "user_id": row[1],
                "street": row[2],
                "number": row[3],
                "complement": row[4],
                "neighborhood": row[5],
                "city": row[6],
                "state": row[7],
                "zip_code": row[8],
                "is_active": bool(row[9]) if row[9] is not None else True,
                "is_default": bool(row[10]) if row[10] is not None else False,
            }
        return None  
    except fdb.Error as e:  
        print(f"Erro ao buscar endereço por ID: {e}")  
        return None  
    finally:  
        if conn: conn.close()  

def update_address(address_id, update_data):  
    allowed_fields = ['street', 'number', 'complement', 'neighborhood', 'city', 'state', 'zip_code']  
    column_name_for_key = lambda key: '"NUMBER"' if key == 'number' else key.upper()  
    # Normalização de valores em branco para None
    normalized_update = {}
    for key, value in update_data.items():
        if key in ['zip_code', 'complement'] and isinstance(value, str) and value.strip() == "":
            normalized_update[key] = None
        else:
            normalized_update[key] = value
    # Se não há campos permitidos, nada a fazer
    if not any(k in allowed_fields for k in normalized_update.keys()):
        return False, None  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        # Busca valores atuais para comparação e status
        cur.execute('SELECT STREET, "NUMBER", COMPLEMENT, NEIGHBORHOOD, CITY, STATE, ZIP_CODE, IS_ACTIVE FROM ADDRESSES WHERE ID = ?;', (address_id,))
        row = cur.fetchone()
        if not row:
            return False, None
        if row[7] is False:
            # Não permitir atualização de endereço inativo
            return False, None
        current = {
            'street': row[0],
            'number': row[1],
            'complement': row[2],
            'neighborhood': row[3],
            'city': row[4],
            'state': row[5],
            'zip_code': row[6],
        }
        # Compara apenas os campos enviados
        unchanged = True
        for key, value in normalized_update.items():
            if key in allowed_fields:
                if current.get(key) != value:
                    unchanged = False
                    break
        if unchanged:
            return True, False
        # Monta UPDATE apenas para campos fornecidos
        set_parts = [f"{column_name_for_key(key)} = ?" for key in normalized_update if key in allowed_fields]
        values = [normalized_update[key] for key in normalized_update if key in allowed_fields]
        values.append(address_id)
        sql = f"UPDATE ADDRESSES SET {', '.join(set_parts)} WHERE ID = ? AND IS_ACTIVE = TRUE;"  
        cur.execute(sql, tuple(values))  
        conn.commit()  
        return True, True  
    except fdb.Error as e:  
        print(f"Erro ao atualizar endereço: {e}")  
        if conn: conn.rollback()  
        return False, None  
    finally:  
        if conn: conn.close()  

def delete_address(address_id):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        sql = "UPDATE ADDRESSES SET IS_ACTIVE = FALSE WHERE ID = ? AND IS_ACTIVE = TRUE;"  
        cur.execute(sql, (address_id,))  
        affected = cur.rowcount  
        conn.commit()  
        if affected and affected > 0:
            return True
        # Se já estava inativo ou não existe, considere sucesso idempotente
        cur = conn.cursor()
        cur.execute('SELECT IS_ACTIVE FROM ADDRESSES WHERE ID = ?;', (address_id,))
        row = cur.fetchone()
        if not row:
            return True
        return row[0] is False  
    except fdb.Error as e:  
        print(f"Erro ao deletar endereço: {e}")  
        if conn: conn.rollback()  
        return False  
    finally:  
        if conn: conn.close()

def set_default_address(user_id, address_id):
    """
    Define um endereço como padrão para o usuário.
    Desmarca todos os outros endereços do usuário como não padrão.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se o endereço pertence ao usuário e está ativo
        cur.execute('SELECT ID FROM ADDRESSES WHERE ID = ? AND USER_ID = ? AND IS_ACTIVE = TRUE;', (address_id, user_id))
        if not cur.fetchone():
            return False, "Endereço não encontrado ou não pertence ao usuário"
        
        # Desmarca todos os endereços do usuário como não padrão
        cur.execute("UPDATE ADDRESSES SET IS_DEFAULT = FALSE WHERE USER_ID = ?;", (user_id,))
        
        # Define o endereço especificado como padrão
        cur.execute("UPDATE ADDRESSES SET IS_DEFAULT = TRUE WHERE ID = ? AND USER_ID = ?;", (address_id, user_id))
        
        conn.commit()
        return True, "Endereço definido como padrão com sucesso"
        
    except fdb.Error as e:
        print(f"Erro ao definir endereço padrão: {e}")
        if conn: conn.rollback()
        return False, "Erro interno do servidor"
    finally:
        if conn: conn.close()  
