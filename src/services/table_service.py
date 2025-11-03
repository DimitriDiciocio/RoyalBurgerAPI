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


def create_table(name, x_position=0, y_position=0):
    """
    Cria uma nova mesa no restaurante.
    
    Args:
        name: Nome da mesa (ex: "Mesa 01", "Balcão 03")
        x_position: Posição X no layout (default: 0)
        y_position: Posição Y no layout (default: 0)
    
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
            INSERT INTO RESTAURANT_TABLES (NAME, STATUS, X_POSITION, Y_POSITION)
            VALUES (?, ?, ?, ?)
            RETURNING ID, NAME, STATUS, X_POSITION, Y_POSITION, CURRENT_ORDER_ID;
        """
        cur.execute(sql, (name, TABLE_STATUS_AVAILABLE, int(x_position), int(y_position)))
        row = cur.fetchone()
        conn.commit()
        
        table = {
            "id": row[0],
            "name": row[1],
            "status": row[2],
            "x_position": row[3],
            "y_position": row[4],
            "current_order_id": row[5]
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
            SELECT ID, NAME, STATUS, X_POSITION, Y_POSITION, CURRENT_ORDER_ID, CREATED_AT, UPDATED_AT
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
            "x_position": row[3],
            "y_position": row[4],
            "current_order_id": row[5],
            "created_at": row[6].strftime('%Y-%m-%d %H:%M:%S') if row[6] else None,
            "updated_at": row[7].strftime('%Y-%m-%d %H:%M:%S') if row[7] else None
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
            SELECT ID, NAME, STATUS, X_POSITION, Y_POSITION, CURRENT_ORDER_ID, CREATED_AT, UPDATED_AT
            FROM RESTAURANT_TABLES
            ORDER BY NAME
        """)
        tables = []
        for row in cur.fetchall():
            tables.append({
                "id": row[0],
                "name": row[1],
                "status": row[2],
                "x_position": row[3],
                "y_position": row[4],
                "current_order_id": row[5],
                "created_at": row[6].strftime('%Y-%m-%d %H:%M:%S') if row[6] else None,
                "updated_at": row[7].strftime('%Y-%m-%d %H:%M:%S') if row[7] else None
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
    Similar a get_all_tables(), mas otimizado para visualização em tempo real.
    
    Returns:
        Lista de dicionários com status das mesas
    """
    return get_all_tables()  # Por enquanto, mesma função


def update_table(table_id, name=None, status=None, x_position=None, y_position=None):
    """
    Atualiza dados de uma mesa.
    
    Args:
        table_id: ID da mesa
        name: Novo nome (opcional)
        status: Novo status (opcional) - deve ser um dos VALID_TABLE_STATUSES
        x_position: Nova posição X (opcional)
        y_position: Nova posição Y (opcional)
    
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
    
    if x_position is not None:
        try:
            fields_to_update['X_POSITION'] = int(x_position)
        except (ValueError, TypeError):
            return (False, "INVALID_X_POSITION", "X_POSITION deve ser um número inteiro")
    
    if y_position is not None:
        try:
            fields_to_update['Y_POSITION'] = int(y_position)
        except (ValueError, TypeError):
            return (False, "INVALID_Y_POSITION", "Y_POSITION deve ser um número inteiro")
    
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


def update_layout(layout_data):
    """
    Atualiza o layout de todas as mesas (posições X e Y).
    
    Args:
        layout_data: Lista de dicionários com {table_id, x, y}
    
    Returns:
        Tupla (success, error_code, message)
    """
    if not layout_data or not isinstance(layout_data, list):
        return (False, "INVALID_DATA", "layout_data deve ser uma lista")
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Valida todos os dados antes de fazer qualquer update
        table_ids = []
        for item in layout_data:
            if not isinstance(item, dict):
                return (False, "INVALID_ITEM", "Cada item deve ser um dicionário")
            
            table_id = item.get('table_id')
            x = item.get('x')
            y = item.get('y')
            
            if table_id is None:
                return (False, "MISSING_TABLE_ID", "table_id é obrigatório em cada item")
            if x is None or y is None:
                return (False, "MISSING_POSITION", "x e y são obrigatórios em cada item")
            
            try:
                table_id = int(table_id)
                x = int(x)
                y = int(y)
            except (ValueError, TypeError):
                return (False, "INVALID_TYPE", "table_id, x e y devem ser números inteiros")
            
            table_ids.append(table_id)
        
        # Verifica se todas as mesas existem
        if table_ids:
            placeholders = ', '.join(['?' for _ in table_ids])
            cur.execute(f"SELECT ID FROM RESTAURANT_TABLES WHERE ID IN ({placeholders})", tuple(table_ids))
            found_ids = {row[0] for row in cur.fetchall()}
            missing_ids = set(table_ids) - found_ids
            if missing_ids:
                return (False, "TABLE_NOT_FOUND", f"Mesas não encontradas: {', '.join(map(str, missing_ids))}")
        
        # Atualiza todas as posições
        for item in layout_data:
            table_id = int(item['table_id'])
            x = int(item['x'])
            y = int(item['y'])
            cur.execute("""
                UPDATE RESTAURANT_TABLES
                SET X_POSITION = ?, Y_POSITION = ?, UPDATED_AT = CURRENT_TIMESTAMP
                WHERE ID = ?
            """, (x, y, table_id))
        
        conn.commit()
        return (True, None, "Layout atualizado com sucesso")
    except fdb.Error as e:
        logger.error(f"Erro ao atualizar layout: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
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

