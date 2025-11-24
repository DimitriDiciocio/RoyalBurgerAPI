"""
Serviço de Impostos Recorrentes
Gerencia impostos que se repetem mensalmente
"""

import fdb
import logging
from datetime import datetime, date
from ..database import get_db_connection
from . import financial_movement_service

logger = logging.getLogger(__name__)

def create_recurring_tax(tax_data, created_by_user_id):
    """
    Cria um imposto recorrente
    
    Args:
        tax_data: dict com:
            - name: str
            - description: str
            - category: str
            - subcategory: str
            - value: float
            - payment_day: int (1-31)
            - sender_receiver: str
            - notes: str
        created_by_user_id: int
    
    Returns:
        (success: bool, error_code: str, result: dict)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Validações
        required_fields = ['name', 'category', 'value', 'payment_day']
        for field in required_fields:
            if not tax_data.get(field):
                return (False, f"INVALID_{field.upper()}", f"Campo {field} é obrigatório")
        
        payment_day = int(tax_data['payment_day'])
        if payment_day < 1 or payment_day > 31:
            return (False, "INVALID_PAYMENT_DAY", "Dia de pagamento deve ser entre 1 e 31")
        
        value = float(tax_data['value'])
        if value <= 0:
            return (False, "INVALID_VALUE", "Valor deve ser maior que zero")
        
        # Inserir
        sql = """
            INSERT INTO RECURRING_TAXES (
                NAME, DESCRIPTION, CATEGORY, SUBCATEGORY,
                "VALUE", PAYMENT_DAY, SENDER_RECEIVER, NOTES, CREATED_BY
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING ID, CREATED_AT
        """
        
        # ALTERAÇÃO FDB4: Tratar NOTES (BLOB) - Firebird 4 não aceita None em BLOB
        notes_value = tax_data.get('notes')
        if notes_value is None:
            notes_value = ''  # String vazia ao invés de None para BLOB
        
        cur.execute(sql, (
            tax_data['name'],
            tax_data.get('description'),
            tax_data['category'],
            tax_data.get('subcategory'),
            value,
            payment_day,
            tax_data.get('sender_receiver'),
            notes_value,  # ALTERAÇÃO FDB4: String vazia ao invés de None
            created_by_user_id
        ))
        
        row = cur.fetchone()
        tax_id = row[0]
        created_at = row[1]
        
        conn.commit()
        
        return (True, None, {
            "id": tax_id,
            "name": tax_data['name'],
            "description": tax_data.get('description'),
            "category": tax_data['category'],
            "subcategory": tax_data.get('subcategory'),
            "value": value,
            "payment_day": payment_day,
            "sender_receiver": tax_data.get('sender_receiver'),
            "notes": tax_data.get('notes'),
            "created_at": created_at.isoformat() if created_at else None
        })
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logger para código de produção
        logger.error(f"Erro ao criar imposto recorrente: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()


def generate_monthly_taxes(year=None, month=None):
    """
    Gera movimentações financeiras para impostos recorrentes do mês
    
    Args:
        year: int (default: ano atual)
        month: int (default: mês atual)
    
    Returns:
        (success: bool, count: int, errors: list)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        if not year:
            year = datetime.now().year
        if not month:
            month = datetime.now().month
        
        # Buscar impostos recorrentes ativos
        cur.execute("""
            SELECT ID, NAME, DESCRIPTION, CATEGORY, SUBCATEGORY,
                   "VALUE", PAYMENT_DAY, SENDER_RECEIVER, NOTES
            FROM RECURRING_TAXES
            WHERE IS_ACTIVE = TRUE
        """)
        
        taxes = cur.fetchall()
        generated_count = 0
        errors = []
        
        for tax in taxes:
            tax_id, name, description, category, subcategory, value, payment_day, sender_receiver, notes = tax
            
            # Verificar se já foi gerado para este mês
            cur.execute("""
                SELECT COUNT(*)
                FROM FINANCIAL_MOVEMENTS
                WHERE TYPE = 'TAX'
                AND RELATED_ENTITY_TYPE = 'recurring_tax'
                AND RELATED_ENTITY_ID = ?
                AND EXTRACT(YEAR FROM CREATED_AT) = ?
                AND EXTRACT(MONTH FROM CREATED_AT) = ?
            """, (tax_id, year, month))
            
            already_generated = cur.fetchone()[0] > 0
            
            if already_generated:
                continue  # Já foi gerado este mês
            
            # Criar data de pagamento (dia do mês especificado)
            try:
                # Usar o último dia do mês se o dia especificado não existir (ex: 31 em fevereiro)
                from calendar import monthrange
                last_day = monthrange(year, month)[1]
                day_to_use = min(payment_day, last_day)
                payment_date = date(year, month, day_to_use)
            except (ValueError, TypeError) as e:
                # Fallback para dia 28 se houver erro
                try:
                    payment_date = date(year, month, 28)
                except:
                    payment_date = date(year, month, 1)  # Último fallback
            
            # Criar movimentação financeira (inicialmente como Pending)
            movement_data = {
                'type': 'TAX',
                'value': float(value),
                'category': category or 'Tributos',
                'subcategory': subcategory or name,
                'description': description or f'{name} - {month:02d}/{year}',
                'movement_date': None,  # Pendente até ser pago
                'payment_status': 'Pending',
                'sender_receiver': sender_receiver,
                'related_entity_type': 'recurring_tax',
                'related_entity_id': tax_id,
                'notes': notes
            }
            
            success, error_code, result = financial_movement_service.create_financial_movement(
                movement_data, None  # Sistema gera automaticamente
            )
            
            if success:
                generated_count += 1
            else:
                errors.append(f"Erro ao gerar imposto {name}: {result}")
        
        return (True, generated_count, errors)
        
    except Exception as e:
        # ALTERAÇÃO: Substituído print() por logger para código de produção
        logger.error(f"Erro ao gerar impostos mensais: {e}", exc_info=True)
        return (False, 0, [str(e)])
    finally:
        if conn:
            conn.close()


def get_recurring_taxes(active_only=True):
    """
    Lista impostos recorrentes
    
    Args:
        active_only: Se True, retorna apenas ativos
    
    Returns:
        list de impostos
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # ALTERAÇÃO FDB4: Usar CAST para BLOB NOTES (compatibilidade Firebird 4)
        sql = "SELECT ID, NAME, DESCRIPTION, CATEGORY, SUBCATEGORY, \"VALUE\", PAYMENT_DAY, IS_ACTIVE, SENDER_RECEIVER, CAST(COALESCE(NOTES, '') AS VARCHAR(1000)) as NOTES FROM RECURRING_TAXES"
        
        if active_only:
            sql += " WHERE IS_ACTIVE = TRUE"
        
        sql += " ORDER BY PAYMENT_DAY, NAME"
        
        cur.execute(sql)
        
        taxes = []
        for row in cur.fetchall():
            taxes.append({
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "category": row[3],
                "subcategory": row[4],
                "value": float(row[5]),
                "payment_day": row[6],
                "is_active": row[7],
                "sender_receiver": row[8],
                "notes": row[9]
            })
        
        return taxes
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logger para código de produção
        logger.error(f"Erro ao buscar impostos recorrentes: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


def update_recurring_tax(tax_id, tax_data, updated_by_user_id=None):
    """
    Atualiza um imposto recorrente
    
    Args:
        tax_id: ID do imposto
        tax_data: dict com campos a atualizar
        updated_by_user_id: ID do usuário que atualizou
    
    Returns:
        (success: bool, error_code: str, result: dict)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verificar se existe
        cur.execute("SELECT ID FROM RECURRING_TAXES WHERE ID = ?", (tax_id,))
        if not cur.fetchone():
            return (False, "NOT_FOUND", "Imposto recorrente não encontrado")
        
        # Construir query de atualização dinamicamente
        updates = []
        params = []
        
        if 'name' in tax_data:
            updates.append("NAME = ?")
            params.append(tax_data['name'])
        
        if 'description' in tax_data:
            updates.append("DESCRIPTION = ?")
            params.append(tax_data['description'])
        
        if 'category' in tax_data:
            updates.append("CATEGORY = ?")
            params.append(tax_data['category'])
        
        if 'subcategory' in tax_data:
            updates.append("SUBCATEGORY = ?")
            params.append(tax_data['subcategory'])
        
        if 'value' in tax_data:
            value = float(tax_data['value'])
            if value <= 0:
                return (False, "INVALID_VALUE", "Valor deve ser maior que zero")
            updates.append("\"VALUE\" = ?")
            params.append(value)
        
        if 'payment_day' in tax_data:
            payment_day = int(tax_data['payment_day'])
            if payment_day < 1 or payment_day > 31:
                return (False, "INVALID_PAYMENT_DAY", "Dia de pagamento deve ser entre 1 e 31")
            updates.append("PAYMENT_DAY = ?")
            params.append(payment_day)
        
        if 'is_active' in tax_data:
            updates.append("IS_ACTIVE = ?")
            params.append(bool(tax_data['is_active']))
        
        if 'sender_receiver' in tax_data:
            updates.append("SENDER_RECEIVER = ?")
            params.append(tax_data['sender_receiver'])
        
        if 'notes' in tax_data:
            # ALTERAÇÃO FDB4: Tratar NOTES (BLOB) - Firebird 4 não aceita None em BLOB
            notes_value = tax_data['notes']
            if notes_value is None:
                notes_value = ''  # String vazia ao invés de None para BLOB
            updates.append("NOTES = ?")
            params.append(notes_value)
        
        if not updates:
            return (False, "NO_UPDATES", "Nenhum campo para atualizar")
        
        updates.append("UPDATED_AT = CURRENT_TIMESTAMP")
        params.append(tax_id)
        
        sql = f"UPDATE RECURRING_TAXES SET {', '.join(updates)} WHERE ID = ? RETURNING ID, NAME, \"VALUE\", PAYMENT_DAY, IS_ACTIVE"
        
        cur.execute(sql, params)
        row = cur.fetchone()
        
        if not row:
            return (False, "NOT_FOUND", "Imposto recorrente não encontrado")
        
        conn.commit()
        
        return (True, None, {
            "id": row[0],
            "name": row[1],
            "value": float(row[2]),
            "payment_day": row[3],
            "is_active": row[4]
        })
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logger para código de produção
        logger.error(f"Erro ao atualizar imposto recorrente {tax_id}: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()


def delete_recurring_tax(tax_id):
    """
    Desativa um imposto recorrente (soft delete)
    
    Args:
        tax_id: ID do imposto
    
    Returns:
        (success: bool, error_code: str, message: str)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verificar se existe
        cur.execute("SELECT ID FROM RECURRING_TAXES WHERE ID = ?", (tax_id,))
        if not cur.fetchone():
            return (False, "NOT_FOUND", "Imposto recorrente não encontrado")
        
        # Desativar (soft delete)
        cur.execute("""
            UPDATE RECURRING_TAXES 
            SET IS_ACTIVE = FALSE, UPDATED_AT = CURRENT_TIMESTAMP
            WHERE ID = ?
        """, (tax_id,))
        
        conn.commit()
        
        return (True, None, "Imposto recorrente desativado com sucesso")
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logger para código de produção
        logger.error(f"Erro ao desativar imposto recorrente {tax_id}: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()

