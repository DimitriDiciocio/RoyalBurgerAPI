# src/services/address_service.py

import fdb
from ..database import get_db_connection


def create_address(user_id, address_data):
    """Cria um novo endereço para um usuário específico."""
    fields = ['city', 'neighborhood', 'street', 'number', 'complement', 'reference_point']
    values = [address_data.get(field) for field in fields]
    values.insert(0, user_id)  # Adiciona o user_id no início

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = """
            INSERT INTO ADDRESSES (USER_ID, CITY, NEIGHBORHOOD, STREET, "NUMBER", COMPLEMENT, REFERENCE_POINT)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING ID;
        """
        # "NUMBER" está entre aspas pois é uma palavra reservada em alguns contextos SQL
        cur.execute(sql, tuple(values))
        new_address_id = cur.fetchone()[0]
        conn.commit()

        address_data['id'] = new_address_id
        address_data['user_id'] = user_id
        return address_data
    except fdb.Error as e:
        print(f"Erro ao criar endereço: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: conn.close()


def get_addresses_by_user_id(user_id):
    """Busca todos os endereços de um usuário."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = 'SELECT ID, CITY, NEIGHBORHOOD, STREET, "NUMBER", COMPLEMENT, REFERENCE_POINT FROM ADDRESSES WHERE USER_ID = ?;'
        cur.execute(sql, (user_id,))

        addresses = []
        for row in cur.fetchall():
            addresses.append({
                "id": row[0], "city": row[1], "neighborhood": row[2],
                "street": row[3], "number": row[4], "complement": row[5],
                "reference_point": row[6]
            })
        return addresses
    except fdb.Error as e:
        print(f"Erro ao buscar endereços: {e}")
        return []
    finally:
        if conn: conn.close()


def get_address_by_id(address_id):
    """Busca um único endereço pelo seu ID."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = 'SELECT ID, USER_ID, CITY, NEIGHBORHOOD, STREET, "NUMBER", COMPLEMENT, REFERENCE_POINT FROM ADDRESSES WHERE ID = ?;'
        cur.execute(sql, (address_id,))
        row = cur.fetchone()
        if row:
            return {
                "id": row[0], "user_id": row[1], "city": row[2], "neighborhood": row[3],
                "street": row[4], "number": row[5], "complement": row[6],
                "reference_point": row[7]
            }
        return None
    except fdb.Error as e:
        print(f"Erro ao buscar endereço por ID: {e}")
        return None
    finally:
        if conn: conn.close()


def update_address(address_id, update_data):
    """Atualiza dados de um endereço."""
    allowed_fields = ['city', 'neighborhood', 'street', 'number', 'complement', 'reference_point']

    # NUMBER precisa de tratamento especial por causa das aspas
    set_parts = [f'"{key.upper()}" = ?' if key == 'number' else f"{key.upper()} = ?" for key in update_data if
                 key in allowed_fields]

    if not set_parts: return False

    values = [value for key, value in update_data.items() if key in allowed_fields]
    values.append(address_id)

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = f"UPDATE ADDRESSES SET {', '.join(set_parts)} WHERE ID = ?;"
        cur.execute(sql, tuple(values))
        conn.commit()
        return cur.rowcount > 0
    except fdb.Error as e:
        print(f"Erro ao atualizar endereço: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()


def delete_address(address_id):
    """Deleta um endereço permanentemente (hard delete)."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = "DELETE FROM ADDRESSES WHERE ID = ?;"
        cur.execute(sql, (address_id,))
        conn.commit()
        return cur.rowcount > 0
    except fdb.Error as e:
        print(f"Erro ao deletar endereço: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()