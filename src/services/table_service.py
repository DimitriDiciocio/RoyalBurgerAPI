import fdb
import logging
from ..database import get_db_connection

logger = logging.getLogger(__name__)

# =============================
# Serviço de Gestão de Mesas do Restaurante
# Tabela: RESTAURANT_TABLES
# =============================

# Status válidos para mesas
TABLE_STATUS_AVAILABLE = 'available'
TABLE_STATUS_OCCUPIED = 'occupied'
TABLE_STATUS_CLEANING = 'cleaning'
TABLE_STATUS_RESERVED = 'reserved'

VALID_TABLE_STATUSES = [
    TABLE_STATUS_AVAILABLE,
    TABLE_STATUS_OCCUPIED,
    TABLE_STATUS_CLEANING,
    TABLE_STATUS_RESERVED
]


def create_table(name):
    """
    Cria uma nova mesa no restaurante.
    
    Args:
        name: Nome da mesa (ex: "Mesa 01", "Balcão 03")
    
    Returns:
        Tupla (table_dict, error_code, message)
    """
    name = (name or '').strip()
    if not name:
        return (None, "INVALID_NAME", "Nome da mesa é obrigatório")

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Verifica se já existe uma mesa com o mesmo nome
        cur.execute("SELECT ID FROM RESTAURANT_TABLES WHERE UPPER(TRIM(NAME)) = UPPER(TRIM(?))", (name,))
        if cur.fetchone():
            return (None, "TABLE_NAME_EXISTS", "Já existe uma mesa com este nome")

        sql = """
            INSERT INTO RESTAURANT_TABLES (NAME, STATUS)
            VALUES (?, ?)
            RETURNING ID, NAME, STATUS, CURRENT_ORDER_ID;
        """
        cur.execute(sql, (name, TABLE_STATUS_AVAILABLE))
        row = cur.fetchone()
        conn.commit()
        
        table = {
            "id": row[0],
            "name": row[1],
            "status": row[2],
            "current_order_id": row[3]
        }
        return (table, None, None)
    except fdb.Error as e:
        logger.error(f"Erro ao criar mesa: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()


def get_table_by_id(table_id):
    """
    Busca uma mesa por ID.
    
    Returns:
        dict com dados da mesa ou None se não encontrada
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT ID, NAME, STATUS, CURRENT_ORDER_ID, CREATED_AT, UPDATED_AT
            FROM RESTAURANT_TABLES
            WHERE ID = ?
        """, (table_id,))
        row = cur.fetchone()
        if not row:
            return None
        
        return {
            "id": row[0],
            "name": row[1],
            "status": row[2],
            "current_order_id": row[3],
            "created_at": row[4].strftime('%Y-%m-%d %H:%M:%S') if row[4] else None,
            "updated_at": row[5].strftime('%Y-%m-%d %H:%M:%S') if row[5] else None
        }
    except fdb.Error as e:
        logger.error(f"Erro ao buscar mesa por ID: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def get_all_tables():
    """
    Lista todas as mesas do restaurante.
    
    Returns:
        Lista de dicionários com dados das mesas
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT ID, NAME, STATUS, CURRENT_ORDER_ID, CREATED_AT, UPDATED_AT
            FROM RESTAURANT_TABLES
            ORDER BY NAME
        """)
        tables = []
        for row in cur.fetchall():
            tables.append({
                "id": row[0],
                "name": row[1],
                "status": row[2],
                "current_order_id": row[3],
                "created_at": row[4].strftime('%Y-%m-%d %H:%M:%S') if row[4] else None,
                "updated_at": row[5].strftime('%Y-%m-%d %H:%M:%S') if row[5] else None
            })
        return tables
    except fdb.Error as e:
        logger.error(f"Erro ao listar mesas: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


def get_tables_status():
    """
    Retorna o status de todas as mesas (usado pelo painel do atendente).
    Retorna apenas os campos essenciais: ID, NAME, STATUS, CURRENT_ORDER_ID.
    
    Returns:
        Lista de dicionários com status das mesas
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT ID, NAME, STATUS, CURRENT_ORDER_ID
            FROM RESTAURANT_TABLES
            ORDER BY NAME
        """)
        tables = []
        for row in cur.fetchall():
            tables.append({
                "id": row[0],
                "name": row[1],
                "status": row[2],
                "current_order_id": row[3]
            })
        return tables
    except fdb.Error as e:
        logger.error(f"Erro ao buscar status das mesas: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


def update_table(table_id, name=None, status=None):
    """
    Atualiza dados de uma mesa.
    
    Args:
        table_id: ID da mesa
        name: Novo nome (opcional)
        status: Novo status (opcional) - deve ser um dos VALID_TABLE_STATUSES
    
    Returns:
        Tupla (success, error_code, message)
    """
    fields_to_update = {}
    
    if name is not None:
        name = (name or '').strip()
        if not name:
            return (False, "INVALID_NAME", "Nome da mesa é obrigatório")
        fields_to_update['NAME'] = name
    
    if status is not None:
        if status not in VALID_TABLE_STATUSES:
            return (False, "INVALID_STATUS", f"Status deve ser um dos: {', '.join(VALID_TABLE_STATUSES)}")
        fields_to_update['STATUS'] = status
    
    if not fields_to_update:
        return (False, "NO_VALID_FIELDS", "Nenhum campo válido para atualização foi fornecido")

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Verifica existência
        cur.execute("SELECT 1 FROM RESTAURANT_TABLES WHERE ID = ?", (table_id,))
        if not cur.fetchone():
            return (False, "TABLE_NOT_FOUND", "Mesa não encontrada")

        # Verifica nome único se for alterar nome
        if 'NAME' in fields_to_update:
            cur.execute("SELECT 1 FROM RESTAURANT_TABLES WHERE UPPER(NAME) = UPPER(?) AND ID <> ?", 
                       (fields_to_update['NAME'], table_id))
            if cur.fetchone():
                return (False, "TABLE_NAME_EXISTS", "Já existe uma mesa com este nome")

        set_parts = [f"{k} = ?" for k in fields_to_update.keys()]
        values = list(fields_to_update.values())
        values.append(table_id)

        sql = f"UPDATE RESTAURANT_TABLES SET {', '.join(set_parts)}, UPDATED_AT = CURRENT_TIMESTAMP WHERE ID = ?;"
        cur.execute(sql, tuple(values))
        conn.commit()
        return (True, None, "Mesa atualizada com sucesso")
    except fdb.Error as e:
        logger.error(f"Erro ao atualizar mesa: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()


def delete_table(table_id):
    """
    Remove uma mesa do restaurante.
    Não permite deletar mesa que está ocupada.
    
    Returns:
        True se deletada com sucesso, False caso contrário
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se a mesa está ocupada
        cur.execute("SELECT STATUS, CURRENT_ORDER_ID FROM RESTAURANT_TABLES WHERE ID = ?", (table_id,))
        row = cur.fetchone()
        if not row:
            return False
        
        if row[0] == TABLE_STATUS_OCCUPIED or row[1] is not None:
            return False  # Não permite deletar mesa ocupada
        
        cur.execute("DELETE FROM RESTAURANT_TABLES WHERE ID = ?", (table_id,))
        affected = cur.rowcount
        conn.commit()
        return affected > 0
    except fdb.Error as e:
        logger.error(f"Erro ao deletar mesa: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


def set_table_occupied(table_id, order_id):
    """
    Marca uma mesa como ocupada e vincula a um pedido.
    Usado internamente quando um atendente abre uma mesa.
    
    Returns:
        True se atualizado com sucesso, False caso contrário
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE RESTAURANT_TABLES
            SET STATUS = ?, CURRENT_ORDER_ID = ?, UPDATED_AT = CURRENT_TIMESTAMP
            WHERE ID = ?
        """, (TABLE_STATUS_OCCUPIED, order_id, table_id))
        affected = cur.rowcount
        conn.commit()
        return affected > 0
    except fdb.Error as e:
        logger.error(f"Erro ao marcar mesa como ocupada: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


def set_table_available(table_id):
    """
    Marca uma mesa como disponível e remove o vínculo com o pedido.
    Usado internamente quando um pedido é fechado.
    
    Returns:
        True se atualizado com sucesso, False caso contrário
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE RESTAURANT_TABLES
            SET STATUS = ?, CURRENT_ORDER_ID = NULL, UPDATED_AT = CURRENT_TIMESTAMP
            WHERE ID = ?
        """, (TABLE_STATUS_AVAILABLE, table_id))
        affected = cur.rowcount
        conn.commit()
        return affected > 0
    except fdb.Error as e:
        logger.error(f"Erro ao marcar mesa como disponível: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


def is_table_available(table_id):
    """
    Verifica se uma mesa está disponível.
    
    Returns:
        True se disponível, False caso contrário
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT STATUS FROM RESTAURANT_TABLES WHERE ID = ?", (table_id,))
        row = cur.fetchone()
        if not row:
            return False
        return row[0] == TABLE_STATUS_AVAILABLE
    except fdb.Error as e:
        logger.error(f"Erro ao verificar disponibilidade da mesa: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()

