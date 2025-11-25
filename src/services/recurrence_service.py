"""
Serviço de Regras de Recorrência
Gerencia despesas e impostos recorrentes (mensais, semanais, anuais)
"""

import fdb
import logging
from datetime import datetime, date, timedelta
from calendar import monthrange
from ..database import get_db_connection
from . import financial_movement_service

logger = logging.getLogger(__name__)

def create_recurrence_rule(rule_data, created_by_user_id):
    """
    Cria uma regra de recorrência
    
    Args:
        rule_data: dict com:
            - name: str
            - description: str (opcional)
            - type: 'EXPENSE' ou 'TAX'
            - category: str
            - subcategory: str (opcional)
            - value: float
            - recurrence_type: 'MONTHLY', 'WEEKLY', 'YEARLY'
            - recurrence_day: int (dia do mês: 1-31, dia da semana: 1-7, dia do ano: 1-365)
            - sender_receiver: str (opcional)
            - notes: str (opcional)
        created_by_user_id: ID do usuário
    
    Returns:
        (success: bool, error_code: str, result: dict)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Validações
        required_fields = ['name', 'type', 'category', 'value', 'recurrence_type', 'recurrence_day']
        for field in required_fields:
            if not rule_data.get(field):
                return (False, f"INVALID_{field.upper()}", f"Campo {field} é obrigatório")
        
        # Validar tipo
        if rule_data['type'] not in ['EXPENSE', 'TAX']:
            return (False, "INVALID_TYPE", "Tipo deve ser 'EXPENSE' ou 'TAX'")
        
        # Validar tipo de recorrência
        recurrence_type = rule_data['recurrence_type']
        if recurrence_type not in ['MONTHLY', 'WEEKLY', 'YEARLY']:
            return (False, "INVALID_RECURRENCE_TYPE", "Tipo de recorrência deve ser 'MONTHLY', 'WEEKLY' ou 'YEARLY'")
        
        # Validar dia de recorrência
        recurrence_day = int(rule_data['recurrence_day'])
        if recurrence_type == 'MONTHLY':
            if recurrence_day < 1 or recurrence_day > 31:
                return (False, "INVALID_RECURRENCE_DAY", "Para recorrência mensal, dia deve ser entre 1 e 31")
        elif recurrence_type == 'WEEKLY':
            if recurrence_day < 1 or recurrence_day > 7:
                return (False, "INVALID_RECURRENCE_DAY", "Para recorrência semanal, dia deve ser entre 1 (segunda) e 7 (domingo)")
        elif recurrence_type == 'YEARLY':
            if recurrence_day < 1 or recurrence_day > 365:
                return (False, "INVALID_RECURRENCE_DAY", "Para recorrência anual, dia deve ser entre 1 e 365")
        
        # Validar valor
        value = float(rule_data['value'])
        if value <= 0:
            return (False, "INVALID_VALUE", "Valor deve ser maior que zero")
        
        # Inserir
        sql = """
            INSERT INTO RECURRENCE_RULES (
                NAME, DESCRIPTION, TYPE, CATEGORY, SUBCATEGORY,
                "VALUE", RECURRENCE_TYPE, RECURRENCE_DAY,
                SENDER_RECEIVER, NOTES, CREATED_BY
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING ID, CREATED_AT
        """
        
        # ALTERAÇÃO FDB4: Tratar NOTES (BLOB) - Firebird 4 não aceita None em BLOB
        notes_value = rule_data.get('notes')
        if notes_value is None:
            notes_value = ''  # String vazia ao invés de None para BLOB
        
        cur.execute(sql, (
            rule_data['name'],
            rule_data.get('description'),
            rule_data['type'],
            rule_data['category'],
            rule_data.get('subcategory'),
            value,
            recurrence_type,
            recurrence_day,
            rule_data.get('sender_receiver'),
            notes_value,  # ALTERAÇÃO FDB4: String vazia ao invés de None
            created_by_user_id
        ))
        
        row = cur.fetchone()
        rule_id = row[0]
        created_at = row[1]
        
        conn.commit()
        
        return (True, None, {
            "id": rule_id,
            "name": rule_data['name'],
            "description": rule_data.get('description'),
            "type": rule_data['type'],
            "category": rule_data['category'],
            "subcategory": rule_data.get('subcategory'),
            "value": value,
            "recurrence_type": recurrence_type,
            "recurrence_day": recurrence_day,
            "sender_receiver": rule_data.get('sender_receiver'),
            "notes": rule_data.get('notes'),
            "is_active": True,
            "created_at": created_at.isoformat() if created_at else None
        })
        
    except fdb.Error as e:
        logger.error(f"Erro ao criar regra de recorrência: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()


def get_recurrence_rules(active_only=True):
    """
    Lista regras de recorrência
    
    Args:
        active_only: Se True, retorna apenas ativas
    
    Returns:
        list de regras
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # ALTERAÇÃO FDB4: Usar CAST para BLOB NOTES (compatibilidade Firebird 4)
        sql = """
            SELECT ID, NAME, DESCRIPTION, TYPE, CATEGORY, SUBCATEGORY,
                   "VALUE", RECURRENCE_TYPE, RECURRENCE_DAY, IS_ACTIVE,
                   SENDER_RECEIVER, CAST(COALESCE(NOTES, '') AS VARCHAR(1000)) as NOTES,
                   CREATED_AT, UPDATED_AT
            FROM RECURRENCE_RULES
        """
        
        if active_only:
            sql += " WHERE IS_ACTIVE = TRUE"
        
        sql += " ORDER BY RECURRENCE_TYPE, RECURRENCE_DAY, NAME"
        
        cur.execute(sql)
        
        rules = []
        for row in cur.fetchall():
            rules.append({
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "type": row[3],
                "category": row[4],
                "subcategory": row[5],
                "value": float(row[6]),
                "recurrence_type": row[7],
                "recurrence_day": row[8],
                "is_active": row[9],
                "sender_receiver": row[10],
                "notes": row[11],
                "created_at": row[12].isoformat() if row[12] else None,
                "updated_at": row[13].isoformat() if row[13] else None
            })
        
        return rules
        
    except fdb.Error as e:
        logger.error(f"Erro ao buscar regras de recorrência: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


def update_recurrence_rule(rule_id, rule_data, updated_by_user_id=None):
    """
    Atualiza uma regra de recorrência
    
    Args:
        rule_id: ID da regra
        rule_data: dict com campos a atualizar
        updated_by_user_id: ID do usuário que atualizou
    
    Returns:
        (success: bool, error_code: str, result: dict)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verificar se existe
        cur.execute("SELECT ID FROM RECURRENCE_RULES WHERE ID = ?", (rule_id,))
        if not cur.fetchone():
            return (False, "NOT_FOUND", "Regra de recorrência não encontrada")
        
        # Construir query de atualização dinamicamente
        updates = []
        params = []
        
        if 'name' in rule_data:
            updates.append("NAME = ?")
            params.append(rule_data['name'])
        
        if 'description' in rule_data:
            updates.append("DESCRIPTION = ?")
            params.append(rule_data['description'])
        
        if 'type' in rule_data:
            if rule_data['type'] not in ['EXPENSE', 'TAX']:
                return (False, "INVALID_TYPE", "Tipo deve ser 'EXPENSE' ou 'TAX'")
            updates.append("TYPE = ?")
            params.append(rule_data['type'])
        
        if 'category' in rule_data:
            updates.append("CATEGORY = ?")
            params.append(rule_data['category'])
        
        if 'subcategory' in rule_data:
            updates.append("SUBCATEGORY = ?")
            params.append(rule_data['subcategory'])
        
        if 'value' in rule_data:
            value = float(rule_data['value'])
            if value <= 0:
                return (False, "INVALID_VALUE", "Valor deve ser maior que zero")
            updates.append("\"VALUE\" = ?")
            params.append(value)
        
        if 'recurrence_type' in rule_data:
            if rule_data['recurrence_type'] not in ['MONTHLY', 'WEEKLY', 'YEARLY']:
                return (False, "INVALID_RECURRENCE_TYPE", "Tipo de recorrência deve ser 'MONTHLY', 'WEEKLY' ou 'YEARLY'")
            updates.append("RECURRENCE_TYPE = ?")
            params.append(rule_data['recurrence_type'])
        
        if 'recurrence_day' in rule_data:
            recurrence_day = int(rule_data['recurrence_day'])
            # Validar baseado no tipo de recorrência
            recurrence_type = rule_data.get('recurrence_type')
            if not recurrence_type:
                # Buscar tipo atual
                cur.execute("SELECT RECURRENCE_TYPE FROM RECURRENCE_RULES WHERE ID = ?", (rule_id,))
                result = cur.fetchone()
                recurrence_type = result[0] if result else None
            
            if recurrence_type == 'MONTHLY' and (recurrence_day < 1 or recurrence_day > 31):
                return (False, "INVALID_RECURRENCE_DAY", "Para recorrência mensal, dia deve ser entre 1 e 31")
            elif recurrence_type == 'WEEKLY' and (recurrence_day < 1 or recurrence_day > 7):
                return (False, "INVALID_RECURRENCE_DAY", "Para recorrência semanal, dia deve ser entre 1 e 7")
            elif recurrence_type == 'YEARLY' and (recurrence_day < 1 or recurrence_day > 365):
                return (False, "INVALID_RECURRENCE_DAY", "Para recorrência anual, dia deve ser entre 1 e 365")
            
            updates.append("RECURRENCE_DAY = ?")
            params.append(recurrence_day)
        
        if 'is_active' in rule_data:
            updates.append("IS_ACTIVE = ?")
            params.append(bool(rule_data['is_active']))
        
        if 'sender_receiver' in rule_data:
            updates.append("SENDER_RECEIVER = ?")
            params.append(rule_data['sender_receiver'])
        
        if 'notes' in rule_data:
            # ALTERAÇÃO FDB4: Tratar NOTES (BLOB) - Firebird 4 não aceita None em BLOB
            notes_value = rule_data['notes']
            if notes_value is None:
                notes_value = ''  # String vazia ao invés de None para BLOB
            updates.append("NOTES = ?")
            params.append(notes_value)
        
        if not updates:
            return (False, "NO_UPDATES", "Nenhum campo para atualizar")
        
        updates.append("UPDATED_AT = CURRENT_TIMESTAMP")
        params.append(rule_id)
        
        sql = f"UPDATE RECURRENCE_RULES SET {', '.join(updates)} WHERE ID = ? RETURNING ID, NAME, TYPE, \"VALUE\", IS_ACTIVE"
        
        cur.execute(sql, params)
        row = cur.fetchone()
        
        if not row:
            return (False, "NOT_FOUND", "Regra de recorrência não encontrada")
        
        conn.commit()
        
        return (True, None, {
            "id": row[0],
            "name": row[1],
            "type": row[2],
            "value": float(row[3]),
            "is_active": row[4]
        })
        
    except fdb.Error as e:
        logger.error(f"Erro ao atualizar regra de recorrência: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()


def delete_recurrence_rule(rule_id):
    """
    Desativa uma regra de recorrência (soft delete)
    
    Args:
        rule_id: ID da regra
    
    Returns:
        (success: bool, error_code: str, message: str)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verificar se existe
        cur.execute("SELECT ID FROM RECURRENCE_RULES WHERE ID = ?", (rule_id,))
        if not cur.fetchone():
            return (False, "NOT_FOUND", "Regra de recorrência não encontrada")
        
        # Desativar (soft delete)
        cur.execute("""
            UPDATE RECURRENCE_RULES 
            SET IS_ACTIVE = FALSE, UPDATED_AT = CURRENT_TIMESTAMP
            WHERE ID = ?
        """, (rule_id,))
        
        conn.commit()
        
        return (True, None, "Regra de recorrência desativada com sucesso")
        
    except fdb.Error as e:
        logger.error(f"Erro ao desativar regra de recorrência: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()


def generate_recurring_movements(year=None, month=None, week=None):
    """
    Gera movimentações financeiras baseadas em regras de recorrência
    
    Args:
        year: int (default: ano atual)
        month: int (default: mês atual, usado para MONTHLY e YEARLY)
        week: int (default: semana atual, usado para WEEKLY)
    
    Returns:
        (success: bool, count: int, errors: list)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        now = datetime.now()
        if not year:
            year = now.year
        if not month:
            month = now.month
        if not week:
            # Calcular semana do ano
            week = now.isocalendar()[1]
        
        # Buscar regras de recorrência ativas
        cur.execute("""
            SELECT ID, NAME, DESCRIPTION, TYPE, CATEGORY, SUBCATEGORY,
                   "VALUE", RECURRENCE_TYPE, RECURRENCE_DAY, SENDER_RECEIVER, NOTES
            FROM RECURRENCE_RULES
            WHERE IS_ACTIVE = TRUE
        """)
        
        rules = cur.fetchall()
        generated_count = 0
        errors = []
        
        for rule in rules:
            rule_id, name, description, rule_type, category, subcategory, value, recurrence_type, recurrence_day, sender_receiver, notes = rule
            
            # Verificar se deve gerar baseado no tipo de recorrência
            should_generate = False
            payment_date = None
            
            if recurrence_type == 'MONTHLY':
                # Verificar se já foi gerado para este mês
                # ALTERAÇÃO: Corrigir nome da coluna de TYPE para MOVEMENT_TYPE
                cur.execute("""
                    SELECT COUNT(*)
                    FROM FINANCIAL_MOVEMENTS
                    WHERE MOVEMENT_TYPE = ?
                    AND RELATED_ENTITY_TYPE = 'recurrence_rule'
                    AND RELATED_ENTITY_ID = ?
                    AND EXTRACT(YEAR FROM CREATED_AT) = ?
                    AND EXTRACT(MONTH FROM CREATED_AT) = ?
                """, (rule_type, rule_id, year, month))
                
                already_generated = cur.fetchone()[0] > 0
                
                if not already_generated:
                    should_generate = True
                    # Criar data de pagamento (dia do mês especificado)
                    try:
                        last_day = monthrange(year, month)[1]
                        day_to_use = min(recurrence_day, last_day)
                        payment_date = date(year, month, day_to_use)
                    except (ValueError, TypeError):
                        try:
                            payment_date = date(year, month, 28)
                        except:
                            payment_date = date(year, month, 1)
            
            elif recurrence_type == 'WEEKLY':
                # Verificar se já foi gerado para esta semana
                # ALTERAÇÃO: Corrigir nome da coluna de TYPE para MOVEMENT_TYPE
                cur.execute("""
                    SELECT COUNT(*)
                    FROM FINANCIAL_MOVEMENTS
                    WHERE MOVEMENT_TYPE = ?
                    AND RELATED_ENTITY_TYPE = 'recurrence_rule'
                    AND RELATED_ENTITY_ID = ?
                    AND EXTRACT(YEAR FROM CREATED_AT) = ?
                    AND EXTRACT(WEEK FROM CREATED_AT) = ?
                """, (rule_type, rule_id, year, week))
                
                already_generated = cur.fetchone()[0] > 0
                
                if not already_generated:
                    should_generate = True
                    # Calcular data baseada no dia da semana (1=segunda, 7=domingo)
                    # Encontrar o primeiro dia da semana do ano especificado
                    # ISO week: semana 1 é a primeira semana com quinta-feira
                    jan_1 = date(year, 1, 1)
                    # Ajustar para segunda-feira da semana 1
                    days_offset = (jan_1.weekday() - 0) % 7  # 0 = segunda-feira
                    first_monday = jan_1 - timedelta(days=days_offset)
                    # Calcular início da semana especificada
                    week_start = first_monday + timedelta(weeks=week - 1)
                    # Adicionar dias até o dia da semana especificado (recurrence_day - 1, pois 1=segunda)
                    payment_date = week_start + timedelta(days=recurrence_day - 1)
            
            elif recurrence_type == 'YEARLY':
                # Verificar se já foi gerado para este ano
                # ALTERAÇÃO: Corrigir nome da coluna de TYPE para MOVEMENT_TYPE
                cur.execute("""
                    SELECT COUNT(*)
                    FROM FINANCIAL_MOVEMENTS
                    WHERE MOVEMENT_TYPE = ?
                    AND RELATED_ENTITY_TYPE = 'recurrence_rule'
                    AND RELATED_ENTITY_ID = ?
                    AND EXTRACT(YEAR FROM CREATED_AT) = ?
                """, (rule_type, rule_id, year))
                
                already_generated = cur.fetchone()[0] > 0
                
                if not already_generated:
                    should_generate = True
                    # Criar data baseada no dia do ano (1-365)
                    try:
                        payment_date = date(year, 1, 1) + timedelta(days=recurrence_day - 1)
                    except:
                        payment_date = date(year, 12, 31)
            
            if not should_generate:
                continue  # Já foi gerado ou não deve gerar agora
            
            # Criar movimentação financeira (inicialmente como Pending)
            movement_data = {
                'type': rule_type,
                'value': float(value),
                'category': category or ('Tributos' if rule_type == 'TAX' else 'Custos Fixos'),
                'subcategory': subcategory or name,
                'description': description or f'{name} - {recurrence_type}',
                'movement_date': payment_date,  # FASE 4: Usar data esperada
                'payment_status': 'Pending',
                'sender_receiver': sender_receiver,
                'related_entity_type': 'recurrence_rule',
                'related_entity_id': rule_id,
                'notes': notes
            }
            
            success, error_code, result = financial_movement_service.create_financial_movement(
                movement_data, None  # Sistema gera automaticamente
            )
            
            if success:
                generated_count += 1
            else:
                errors.append(f"Erro ao gerar regra {name}: {result}")
        
        return (True, generated_count, errors)
        
    except Exception as e:
        logger.error(f"Erro ao gerar movimentações recorrentes: {e}", exc_info=True)
        return (False, 0, [str(e)])
    finally:
        if conn:
            conn.close()

