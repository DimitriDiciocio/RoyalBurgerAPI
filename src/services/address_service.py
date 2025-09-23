import fdb  # importa driver do Firebird
from ..database import get_db_connection  # importa função de conexão com banco

def create_address(user_id, address_data):  # função para criar endereço
    fields = ['city', 'neighborhood', 'street', 'number', 'complement', 'reference_point']  # campos permitidos
    values = [address_data.get(field) for field in fields]  # extrai valores dos campos
    values.insert(0, user_id)  # adiciona user_id no início da lista
    conn = None  # inicializa conexão
    try:  # tenta criar endereço
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = """
            INSERT INTO ADDRESSES (USER_ID, CITY, NEIGHBORHOOD, STREET, "NUMBER", COMPLEMENT, REFERENCE_POINT)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING ID;
        """  # query de inserção com retorno do ID
        cur.execute(sql, tuple(values))  # executa query
        new_address_id = cur.fetchone()[0]  # obtém ID do endereço criado
        conn.commit()  # confirma transação
        address_data['id'] = new_address_id  # adiciona ID aos dados
        address_data['user_id'] = user_id  # adiciona user_id aos dados
        return address_data  # retorna dados do endereço
    except fdb.Error as e:  # captura erros do banco
        print(f"Erro ao criar endereço: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return None  # retorna None em caso de erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def get_addresses_by_user_id(user_id):  # função para buscar endereços por usuário
    conn = None  # inicializa conexão
    try:  # tenta buscar endereços
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = 'SELECT ID, CITY, NEIGHBORHOOD, STREET, "NUMBER", COMPLEMENT, REFERENCE_POINT FROM ADDRESSES WHERE USER_ID = ?;'  # query de busca
        cur.execute(sql, (user_id,))  # executa query
        addresses = []  # lista de endereços
        for row in cur.fetchall():  # itera resultados
            addresses.append({  # monta dicionário do endereço
                "id": row[0], "city": row[1], "neighborhood": row[2],
                "street": row[3], "number": row[4], "complement": row[5],
                "reference_point": row[6]
            })
        return addresses  # retorna lista de endereços
    except fdb.Error as e:  # captura erros
        print(f"Erro ao buscar endereços: {e}")  # exibe erro
        return []  # retorna lista vazia em caso de erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def get_address_by_id(address_id):  # função para buscar endereço por ID
    conn = None  # inicializa conexão
    try:  # tenta buscar endereço
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = 'SELECT ID, USER_ID, CITY, NEIGHBORHOOD, STREET, "NUMBER", COMPLEMENT, REFERENCE_POINT FROM ADDRESSES WHERE ID = ?;'  # query de busca
        cur.execute(sql, (address_id,))  # executa query
        row = cur.fetchone()  # obtém resultado
        if row:  # se encontrou endereço
            return {  # retorna dicionário do endereço
                "id": row[0], "user_id": row[1], "city": row[2], "neighborhood": row[3],
                "street": row[4], "number": row[5], "complement": row[6],
                "reference_point": row[7]
            }
        return None  # retorna None se não encontrado
    except fdb.Error as e:  # captura erros
        print(f"Erro ao buscar endereço por ID: {e}")  # exibe erro
        return None  # retorna None em caso de erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def update_address(address_id, update_data):  # função para atualizar endereço
    allowed_fields = ['city', 'neighborhood', 'street', 'number', 'complement', 'reference_point']  # campos permitidos
    set_parts = [f'"{key.upper()}" = ?' if key == 'number' else f"{key.upper()} = ?" for key in update_data if key in allowed_fields]  # monta partes do SET
    if not set_parts: return False  # retorna falso se não há campos válidos
    values = [value for key, value in update_data.items() if key in allowed_fields]  # extrai valores
    values.append(address_id)  # adiciona ID do endereço
    conn = None  # inicializa conexão
    try:  # tenta atualizar
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = f"UPDATE ADDRESSES SET {', '.join(set_parts)} WHERE ID = ?;"  # query de atualização
        cur.execute(sql, tuple(values))  # executa query
        conn.commit()  # confirma transação
        return cur.rowcount > 0  # retorna True se atualizou
    except fdb.Error as e:  # captura erros
        print(f"Erro ao atualizar endereço: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return False  # retorna falso em caso de erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def delete_address(address_id):  # função para deletar endereço
    conn = None  # inicializa conexão
    try:  # tenta deletar
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = "DELETE FROM ADDRESSES WHERE ID = ?;"  # query de deleção
        cur.execute(sql, (address_id,))  # executa query
        conn.commit()  # confirma transação
        return cur.rowcount > 0  # retorna True se deletou
    except fdb.Error as e:  # captura erros
        print(f"Erro ao deletar endereço: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
        return False  # retorna falso em caso de erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão