"""
Serviço de Compras e Entrada de Estoque
Gerencia compras de ingredientes e registro automático de despesas
"""

import fdb
import logging
import json
from datetime import datetime
from decimal import Decimal
from ..database import get_db_connection
from . import financial_movement_service

logger = logging.getLogger(__name__)


def _check_purchase_permission(invoice_id, user_id, user_role, action='edit', cur=None):
    """
    Verifica permissões granulares para operações em notas fiscais
    
    ALTERAÇÃO: Função para verificar permissões granulares
    
    Regras:
    - DELETE: Apenas admin pode excluir
    - UPDATE: Admin e manager podem editar; usuário que criou pode editar
    - CREATE: Admin e manager podem criar
    
    Args:
        invoice_id: ID da nota fiscal
        user_id: ID do usuário atual
        user_role: Role do usuário ('admin', 'manager', etc)
        action: 'edit' ou 'delete'
        cur: cursor do banco (opcional)
    
    Returns:
        (allowed: bool, error_code: str, message: str)
    """
    conn = None
    try:
        if cur is None:
            conn = get_db_connection()
            cur = conn.cursor()
            should_close = True
        else:
            should_close = False
        
        # DELETE: Apenas admin
        if action == 'delete':
            if user_role != 'admin':
                if should_close and conn:
                    conn.close()
                return (False, "PERMISSION_DENIED", "Apenas administradores podem excluir notas fiscais")
        
        # UPDATE: Verificar se é admin/manager ou criador
        if action == 'edit':
            if user_role not in ['admin', 'manager']:
                # Verificar se o usuário criou a nota fiscal
                cur.execute("SELECT CREATED_BY FROM PURCHASE_INVOICES WHERE ID = ?", (invoice_id,))
                invoice_row = cur.fetchone()
                if invoice_row and invoice_row[0] != user_id:
                    if should_close and conn:
                        conn.close()
                    return (False, "PERMISSION_DENIED", "Você não tem permissão para editar esta nota fiscal")
        
        if should_close and conn:
            conn.close()
        
        return (True, None, None)
        
    except Exception as e:
        logger.error(f"Erro ao verificar permissões: {e}", exc_info=True)
        if should_close and conn:
            conn.close()
        return (False, "PERMISSION_CHECK_ERROR", f"Erro ao verificar permissões: {str(e)}")

def create_purchase_invoice(invoice_data, created_by_user_id, cur=None):
    """
    Cria uma nota fiscal de compra e registra automaticamente:
    1. Entrada de estoque dos ingredientes
    2. Despesa financeira (EXPENSE)
    
    Args:
        invoice_data: dict com:
            - invoice_number: str
            - supplier_name: str
            - total_amount: float
            - purchase_date: datetime (opcional)
            - payment_status: 'Pending' ou 'Paid' (default: 'Pending')
            - payment_method: str (opcional)
            - payment_date: datetime (opcional, obrigatório se Paid)
            - items: list de dicts com:
                - ingredient_id: int
                - quantity: float
                - unit_price: float
            - notes: str (opcional)
        created_by_user_id: ID do usuário
        cur: Cursor opcional para transação existente
    
    Returns:
        (success: bool, error_code: str, result: dict)
    """
    conn = None
    should_close_conn = False
    
    try:
        if cur is None:
            conn = get_db_connection()
            cur = conn.cursor()
            should_close_conn = True
        
        # Validar dados
        required_fields = ['invoice_number', 'supplier_name', 'total_amount', 'items']
        for field in required_fields:
            if not invoice_data.get(field):
                return (False, f"INVALID_{field.upper()}", f"Campo {field} é obrigatório")
        
        if not invoice_data['items'] or len(invoice_data['items']) == 0:
            return (False, "INVALID_ITEMS", "A nota fiscal deve ter pelo menos um item")
        
        # Validar status e data de pagamento
        payment_status = invoice_data.get('payment_status', 'Pending')
        if payment_status not in ['Pending', 'Paid']:
            return (False, "INVALID_STATUS", "Status deve ser 'Pending' ou 'Paid'")
        
        payment_date = invoice_data.get('payment_date')
        if payment_status == 'Paid' and not payment_date:
            payment_date = datetime.now()
        elif payment_date and isinstance(payment_date, str):
            try:
                payment_date = datetime.fromisoformat(payment_date.replace('Z', '+00:00'))
            except:
                payment_date = datetime.now()
        elif payment_date and isinstance(payment_date, datetime):
            pass  # Já é datetime
        else:
            payment_date = None
        
        purchase_date = invoice_data.get('purchase_date', datetime.now())
        if isinstance(purchase_date, str):
            try:
                purchase_date = datetime.fromisoformat(purchase_date.replace('Z', '+00:00'))
            except:
                purchase_date = datetime.now()
        elif not isinstance(purchase_date, datetime):
            purchase_date = datetime.now()
        
        # Validar itens
        for item in invoice_data['items']:
            if not item.get('ingredient_id'):
                return (False, "INVALID_ITEM", "Cada item deve ter ingredient_id")
            if not item.get('quantity') or float(item.get('quantity', 0)) <= 0:
                return (False, "INVALID_ITEM", "Cada item deve ter quantity > 0")
            if not item.get('unit_price') or float(item.get('unit_price', 0)) <= 0:
                return (False, "INVALID_ITEM", "Cada item deve ter unit_price > 0")
        
        # 1. Inserir nota fiscal
        # ALTERAÇÃO: Firebird pode ter problemas com campos None em BLOB, construir SQL dinamicamente
        logger.info("=== INÍCIO CREATE PURCHASE INVOICE ===")
        logger.info(f"Dados recebidos: {invoice_data}")
        logger.info(f"User ID: {created_by_user_id}")
        logger.info(f"Purchase date: {purchase_date} (tipo: {type(purchase_date)})")
        logger.info(f"Payment date: {payment_date} (tipo: {type(payment_date)})")
        logger.info(f"Payment status: {payment_status}")
        
        try:
            cur.execute("SELECT MAX(ID) FROM PURCHASE_INVOICES")
            max_id_before = cur.fetchone()[0] or 0
            logger.info(f"MAX(ID) antes do INSERT: {max_id_before}")
        except Exception as e:
            logger.error(f"Erro ao buscar MAX(ID): {e}", exc_info=True)
            max_id_before = 0
        
        # ALTERAÇÃO: Preparar valores e construir SQL dinamicamente para evitar problemas com None
        # 1. TOTAL_AMOUNT: Converter float para Decimal
        total_amount = Decimal(str(invoice_data['total_amount']))
        
        # 2. ALTERAÇÃO: Usar SQL fixo com todos os campos (mesmo que alguns sejam None)
        # Firebird aceita None em campos nullable quando passado explicitamente
        invoice_sql = """
            INSERT INTO PURCHASE_INVOICES (
                INVOICE_NUMBER, SUPPLIER_NAME, TOTAL_AMOUNT,
                PURCHASE_DATE, PAYMENT_STATUS, PAYMENT_METHOD,
                PAYMENT_DATE, NOTES, CREATED_BY
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        # ALTERAÇÃO: Converter datetime para naive (sem timezone) - Firebird pode não aceitar timezone-aware
        if purchase_date and purchase_date.tzinfo is not None:
            purchase_date = purchase_date.replace(tzinfo=None)
        if payment_date and payment_date.tzinfo is not None:
            payment_date = payment_date.replace(tzinfo=None)
        
        # ALTERAÇÃO: Usar string vazia ao invés de None para BLOB (Firebird pode não aceitar None em BLOB)
        notes_value = invoice_data.get('notes')
        if notes_value is None:
            notes_value = ''  # String vazia ao invés de None para BLOB
        
        # Preparar valores na ordem exata do SQL
        invoice_values = (
            str(invoice_data['invoice_number']),
            str(invoice_data['supplier_name']),
            total_amount,
            purchase_date,
            str(payment_status),
            invoice_data.get('payment_method'),  # Pode ser None
            payment_date,  # Pode ser None
            notes_value,  # ALTERAÇÃO: String vazia ao invés de None para BLOB
            int(created_by_user_id)
        )
        
        logger.info(f"SQL: {invoice_sql}")
        logger.info(f"Valores: {invoice_values}")
        for i, (field_name, val) in enumerate(zip(
            ['INVOICE_NUMBER', 'SUPPLIER_NAME', 'TOTAL_AMOUNT', 'PURCHASE_DATE', 
             'PAYMENT_STATUS', 'PAYMENT_METHOD', 'PAYMENT_DATE', 'NOTES', 'CREATED_BY'],
            invoice_values
        )):
            logger.info(f"Campo {i} ({field_name}): {repr(val)} (tipo: {type(val).__name__})")
        
        try:
            logger.info("Tentando executar INSERT...")
            cur.execute(invoice_sql, invoice_values)
            logger.info("INSERT executado com sucesso")
        except fdb.Error as e:
            logger.error(f"ERRO FDB ao executar INSERT: {e}", exc_info=True)
            logger.error(f"SQLCODE: {e.args[1] if len(e.args) > 1 else 'N/A'}")
            logger.error(f"SQL completo: {invoice_sql}")
            logger.error(f"Valores completos: {invoice_values}")
            # ALTERAÇÃO: Tentar identificar qual campo específico está causando problema
            logger.error("Testando campos individualmente...")
            # Testar se o problema é com datetime
            try:
                test_sql = "SELECT CAST(? AS TIMESTAMP) FROM RDB$DATABASE"
                cur.execute(test_sql, (purchase_date,))
                logger.info("Teste TIMESTAMP com purchase_date: OK")
            except Exception as test_e:
                logger.error(f"Teste TIMESTAMP com purchase_date FALHOU: {test_e}")
            raise
        except Exception as e:
            logger.error(f"ERRO GERAL ao executar INSERT: {e}", exc_info=True)
            logger.error(f"Tipo de erro: {type(e).__name__}")
            raise
        
        # ALTERAÇÃO: Buscar ID gerado - Firebird não suporta RETURNING da mesma forma
        
        # Agora buscar o ID recém-criado (será max_id_before + 1 se for identity)
        # Mas para garantir, buscar pelo invoice_number que acabamos de inserir
        cur.execute("""
            SELECT ID, CREATED_AT 
            FROM PURCHASE_INVOICES 
            WHERE INVOICE_NUMBER = ? 
            AND CREATED_BY = ?
            AND ID > ?
            ORDER BY ID DESC
            ROWS 1
        """, (invoice_data['invoice_number'], created_by_user_id, max_id_before))
        
        invoice_row = cur.fetchone()
        if not invoice_row:
            # Fallback: buscar apenas pelo invoice_number (menos seguro mas funciona)
            cur.execute("""
                SELECT ID, CREATED_AT 
                FROM PURCHASE_INVOICES 
                WHERE INVOICE_NUMBER = ?
                ORDER BY CREATED_AT DESC
                ROWS 1
            """, (invoice_data['invoice_number'],))
            invoice_row = cur.fetchone()
        
        if not invoice_row:
            if should_close_conn:
                conn.rollback()
            return (False, "DATABASE_ERROR", "Erro ao criar nota fiscal - não foi possível recuperar ID")
        
        invoice_id = invoice_row[0]
        created_at = invoice_row[1]
        
        # 2. Inserir itens e dar entrada no estoque
        for item in invoice_data['items']:
            ingredient_id = int(item['ingredient_id'])
            # ALTERAÇÃO: Converter para Decimal (Firebird DECIMAL precisa de Decimal)
            quantity = Decimal(str(item['quantity']))
            unit_price = Decimal(str(item['unit_price']))
            total_price = quantity * unit_price
            
            # Verificar se ingrediente existe
            cur.execute("SELECT ID FROM INGREDIENTS WHERE ID = ?", (ingredient_id,))
            if not cur.fetchone():
                if should_close_conn:
                    conn.rollback()
                return (False, "INGREDIENT_NOT_FOUND", f"Ingrediente ID {ingredient_id} não encontrado")
            
            # Inserir item da nota fiscal
            item_sql = """
                INSERT INTO PURCHASE_INVOICE_ITEMS (
                    PURCHASE_INVOICE_ID, INGREDIENT_ID,
                    QUANTITY, UNIT_PRICE, TOTAL_PRICE
                )
                VALUES (?, ?, ?, ?, ?)
            """
            cur.execute(item_sql, (invoice_id, ingredient_id, quantity, unit_price, total_price))
            
            # Dar entrada no estoque
            # ALTERAÇÃO: Corrigido nome do campo (CURRENT_STOCK ao invés de STOCK_QUANTITY)
            cur.execute("""
                UPDATE INGREDIENTS
                SET CURRENT_STOCK = CURRENT_STOCK + ?
                WHERE ID = ?
            """, (quantity, ingredient_id))
            
            # Verificar se a atualização foi bem-sucedida
            if cur.rowcount == 0:
                if should_close_conn:
                    conn.rollback()
                return (False, "STOCK_UPDATE_ERROR", f"Erro ao atualizar estoque do ingrediente ID {ingredient_id}")
        
        # 3. Registrar despesa financeira automaticamente
        expense_data = {
            'type': 'EXPENSE',
            'value': float(invoice_data['total_amount']),
            'category': financial_movement_service.CATEGORY_STOCK_PURCHASES,
            'subcategory': 'Ingredientes',
            'description': f'Compra - NF {invoice_data["invoice_number"]} - {invoice_data["supplier_name"]}',
            'movement_date': payment_date if payment_status == 'Paid' else None,
            'payment_status': payment_status,
            'payment_method': invoice_data.get('payment_method'),
            'sender_receiver': invoice_data['supplier_name'],
            'related_entity_type': 'purchase_invoice',
            'related_entity_id': invoice_id,
            'notes': invoice_data.get('notes')
        }
        
        expense_success, expense_error_code, expense_result = financial_movement_service.create_financial_movement(
            expense_data, created_by_user_id, cur=cur
        )
        
        if not expense_success:
            if should_close_conn:
                conn.rollback()
            return (False, expense_error_code, f"Erro ao registrar despesa: {expense_result}")
        
        expense_id = expense_result['id']
        
        if should_close_conn:
            conn.commit()
            # ALTERAÇÃO: Registrar auditoria de criação
            _log_audit_entry(
                invoice_id=invoice_id,
                action_type='CREATE',
                changed_by=created_by_user_id,
                new_values=invoice_data,
                notes=f'Nota fiscal criada - NF {invoice_data["invoice_number"]}'
            )
        
        return (True, None, {
            "invoice_id": invoice_id,
            "expense_id": expense_id,
            "created_at": created_at.isoformat() if created_at else None
        })
        
    except fdb.Error as e:
        logger.error(f"Erro ao criar nota fiscal de compra: {e}", exc_info=True)
        if should_close_conn and conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", f"Erro no banco de dados: {str(e)}")
    except Exception as e:
        logger.error(f"Erro ao criar nota fiscal de compra: {e}", exc_info=True)
        if should_close_conn and conn:
            conn.rollback()
        return (False, "INTERNAL_ERROR", "Erro interno do servidor")
    finally:
        if should_close_conn and conn:
            conn.close()


def get_purchase_invoices(filters=None):
    """
    Busca notas fiscais de compra com filtros
    
    Args:
        filters: dict com:
            - start_date: datetime/str
            - end_date: datetime/str
            - supplier_name: str
            - payment_status: 'Pending' ou 'Paid'
    
    Returns:
        list de notas fiscais
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        base_sql = """
            SELECT 
                pi.ID, pi.INVOICE_NUMBER, pi.SUPPLIER_NAME, pi.TOTAL_AMOUNT,
                pi.PURCHASE_DATE, pi.PAYMENT_STATUS, pi.PAYMENT_METHOD,
                pi.PAYMENT_DATE, pi.NOTES, pi.CREATED_AT, pi.UPDATED_AT,
                u.FULL_NAME as created_by_name
            FROM PURCHASE_INVOICES pi
            LEFT JOIN USERS u ON pi.CREATED_BY = u.ID
        """
        
        conditions = []
        params = []
        
        if filters:
            if filters.get('start_date'):
                start_date = filters['start_date']
                if isinstance(start_date, str):
                    try:
                        start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    except:
                        pass
                conditions.append("pi.PURCHASE_DATE >= ?")
                params.append(start_date)
            
            if filters.get('end_date'):
                end_date = filters['end_date']
                if isinstance(end_date, str):
                    try:
                        end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    except:
                        pass
                from datetime import timedelta
                end_date = end_date + timedelta(days=1)
                conditions.append("pi.PURCHASE_DATE < ?")
                params.append(end_date)
            
            if filters.get('supplier_name'):
                conditions.append("UPPER(pi.SUPPLIER_NAME) LIKE UPPER(?)")
                params.append(f"%{filters['supplier_name']}%")
            
            if filters.get('payment_status'):
                conditions.append("pi.PAYMENT_STATUS = ?")
                params.append(filters['payment_status'])
        
        if conditions:
            base_sql += " WHERE " + " AND ".join(conditions)
        
        base_sql += " ORDER BY pi.PURCHASE_DATE DESC, pi.CREATED_AT DESC"
        
        cur.execute(base_sql, params)
        
        invoices = []
        for row in cur.fetchall():
            invoices.append({
                "id": row[0],
                "invoice_number": row[1],
                "supplier_name": row[2],
                "total_amount": float(row[3]),
                "purchase_date": row[4].isoformat() if row[4] else None,
                "payment_status": row[5],
                "payment_method": row[6],
                "payment_date": row[7].isoformat() if row[7] else None,
                "notes": row[8],
                "created_at": row[9].isoformat() if row[9] else None,
                "updated_at": row[10].isoformat() if row[10] else None,
                "created_by_name": row[11]
            })
        
        return invoices
        
    except fdb.Error as e:
        logger.error(f"Erro ao buscar notas fiscais: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


def get_purchase_invoice_by_id(invoice_id):
    """
    Busca uma nota fiscal de compra por ID com seus itens
    
    Args:
        invoice_id: ID da nota fiscal
    
    Returns:
        dict com dados da nota fiscal e itens, ou None se não encontrada
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Buscar nota fiscal
        cur.execute("""
            SELECT 
                pi.ID, pi.INVOICE_NUMBER, pi.SUPPLIER_NAME, pi.TOTAL_AMOUNT,
                pi.PURCHASE_DATE, pi.PAYMENT_STATUS, pi.PAYMENT_METHOD,
                pi.PAYMENT_DATE, pi.NOTES, pi.CREATED_AT, pi.UPDATED_AT,
                u.FULL_NAME as created_by_name
            FROM PURCHASE_INVOICES pi
            LEFT JOIN USERS u ON pi.CREATED_BY = u.ID
            WHERE pi.ID = ?
        """, (invoice_id,))
        
        row = cur.fetchone()
        if not row:
            return None
        
        invoice = {
            "id": row[0],
            "invoice_number": row[1],
            "supplier_name": row[2],
            "total_amount": float(row[3]),
            "purchase_date": row[4].isoformat() if row[4] else None,
            "payment_status": row[5],
            "payment_method": row[6],
            "payment_date": row[7].isoformat() if row[7] else None,
            "notes": row[8],
            "created_at": row[9].isoformat() if row[9] else None,
            "updated_at": row[10].isoformat() if row[10] else None,
            "created_by_name": row[11],
            "items": []
        }
        
        # Buscar itens
        cur.execute("""
            SELECT 
                pii.ID, pii.INGREDIENT_ID, i.NAME as ingredient_name,
                pii.QUANTITY, pii.UNIT_PRICE, pii.TOTAL_PRICE
            FROM PURCHASE_INVOICE_ITEMS pii
            JOIN INGREDIENTS i ON pii.INGREDIENT_ID = i.ID
            WHERE pii.PURCHASE_INVOICE_ID = ?
            ORDER BY pii.ID
        """, (invoice_id,))
        
        for item_row in cur.fetchall():
            invoice["items"].append({
                "id": item_row[0],
                "ingredient_id": item_row[1],
                "ingredient_name": item_row[2],
                "quantity": float(item_row[3]),
                "unit_price": float(item_row[4]),
                "total_price": float(item_row[5])
            })
        
        return invoice
        
    except fdb.Error as e:
        logger.error(f"Erro ao buscar nota fiscal: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def update_purchase_invoice(invoice_id, invoice_data, updated_by_user_id):
    """
    Atualiza uma nota fiscal de compra
    
    ALTERAÇÃO: Novo método para UPDATE
    Por enquanto, permite atualizar apenas campos simples (status, notas, etc)
    Atualização de itens requer recálculo de estoque e será implementada futuramente
    
    Args:
        invoice_id: ID da nota fiscal
        invoice_data: dict com campos a atualizar
        updated_by_user_id: ID do usuário que está atualizando
    
    Returns:
        (success: bool, error_code: str, result: dict)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # ALTERAÇÃO: Verificar permissões granulares
        # Buscar role do usuário
        cur.execute("SELECT ROLE FROM USERS WHERE ID = ?", (updated_by_user_id,))
        user_row = cur.fetchone()
        if not user_row:
            return (False, "USER_NOT_FOUND", "Usuário não encontrado")
        user_role = user_row[0]
        
        # Verificar permissão de edição
        allowed, error_code, message = _check_purchase_permission(invoice_id, updated_by_user_id, user_role, action='edit', cur=cur)
        if not allowed:
            return (False, error_code, message)
        
        # Verificar se nota fiscal existe e buscar valores antigos para auditoria
        cur.execute("""
            SELECT ID, INVOICE_NUMBER, SUPPLIER_NAME, TOTAL_AMOUNT, PURCHASE_DATE,
                   PAYMENT_STATUS, PAYMENT_METHOD, PAYMENT_DATE, NOTES
            FROM PURCHASE_INVOICES WHERE ID = ?
        """, (invoice_id,))
        invoice_row = cur.fetchone()
        if not invoice_row:
            return (False, "NOT_FOUND", "Nota fiscal não encontrada")
        
        # ALTERAÇÃO: Preparar valores antigos para auditoria
        old_values = {
            'invoice_number': invoice_row[1],
            'supplier_name': invoice_row[2],
            'total_amount': float(invoice_row[3]) if invoice_row[3] else 0,
            'purchase_date': invoice_row[4].isoformat() if invoice_row[4] else None,
            'payment_status': invoice_row[5],
            'payment_method': invoice_row[6],
            'payment_date': invoice_row[7].isoformat() if invoice_row[7] else None,
            'notes': invoice_row[8]
        }
        
        # Buscar itens antigos se houver atualização de itens
        old_items = None
        if 'items' in invoice_data and invoice_data['items']:
            cur.execute("""
                SELECT INGREDIENT_ID, QUANTITY, UNIT_PRICE, TOTAL_PRICE
                FROM PURCHASE_INVOICE_ITEMS
                WHERE PURCHASE_INVOICE_ID = ?
            """, (invoice_id,))
            old_items_data = cur.fetchall()
            old_items = [
                {
                    'ingredient_id': item[0],
                    'quantity': float(item[1]),
                    'unit_price': float(item[2]),
                    'total_price': float(item[3])
                }
                for item in old_items_data
            ]
            old_values['items'] = old_items
        
        # ALTERAÇÃO: Permitir atualização de campos simples e itens
        update_fields = []
        update_values = []
        
        # Verificar se há atualização de itens
        if 'items' in invoice_data and invoice_data['items']:
            # ALTERAÇÃO: Implementar atualização completa de itens com recálculo de estoque
            success, error_code, result = _update_invoice_items_with_stock_recalc(invoice_id, invoice_data['items'], cur)
            if not success:
                if conn:
                    conn.rollback()
                return (False, error_code, result)
            
            # Recalcular total_amount baseado nos novos itens
            cur.execute("""
                SELECT SUM(TOTAL_PRICE) 
                FROM PURCHASE_INVOICE_ITEMS 
                WHERE PURCHASE_INVOICE_ID = ?
            """, (invoice_id,))
            total_row = cur.fetchone()
            new_total = float(total_row[0]) if total_row and total_row[0] else 0
            update_fields.append("TOTAL_AMOUNT = ?")
            update_values.append(new_total)
            
            # Atualizar movimento financeiro com novo valor
            cur.execute("""
                SELECT ID FROM FINANCIAL_MOVEMENTS
                WHERE RELATED_ENTITY_TYPE = 'purchase_invoice'
                AND RELATED_ENTITY_ID = ?
            """, (invoice_id,))
            movement_row = cur.fetchone()
            if movement_row:
                movement_id = movement_row[0]
                cur.execute("""
                    UPDATE FINANCIAL_MOVEMENTS
                    SET VALUE = ?, UPDATED_AT = ?
                    WHERE ID = ?
                """, (new_total, datetime.now(), movement_id))
        
        if 'payment_status' in invoice_data:
            payment_status = invoice_data['payment_status']
            if payment_status not in ['Pending', 'Paid']:
                return (False, "INVALID_STATUS", "Status deve ser 'Pending' ou 'Paid'")
            update_fields.append("PAYMENT_STATUS = ?")
            update_values.append(payment_status)
            
            # Se mudou para Paid, definir payment_date se não existir
            if payment_status == 'Paid':
                cur.execute("SELECT PAYMENT_DATE FROM PURCHASE_INVOICES WHERE ID = ?", (invoice_id,))
                current_payment_date = cur.fetchone()[0]
                if not current_payment_date:
                    payment_date = invoice_data.get('payment_date', datetime.now())
                    if isinstance(payment_date, str):
                        try:
                            payment_date = datetime.fromisoformat(payment_date.replace('Z', '+00:00'))
                        except:
                            payment_date = datetime.now()
                    update_fields.append("PAYMENT_DATE = ?")
                    update_values.append(payment_date)
        
        if 'payment_method' in invoice_data:
            update_fields.append("PAYMENT_METHOD = ?")
            update_values.append(invoice_data['payment_method'])
        
        if 'notes' in invoice_data:
            update_fields.append("NOTES = ?")
            update_values.append(invoice_data['notes'])
        
        if not update_fields and 'items' not in invoice_data:
            return (False, "NO_CHANGES", "Nenhum campo para atualizar")
        
        # Adicionar updated_at (sempre que houver atualização)
        update_fields.append("UPDATED_AT = ?")
        update_values.append(datetime.now())
        
        # Adicionar invoice_id para WHERE
        update_values.append(invoice_id)
        
        # Executar UPDATE
        update_sql = f"""
            UPDATE PURCHASE_INVOICES
            SET {', '.join(update_fields)}
            WHERE ID = ?
        """
        
        cur.execute(update_sql, update_values)
        
        # Atualizar movimento financeiro relacionado se status mudou
        if 'payment_status' in invoice_data:
            cur.execute("""
                SELECT ID FROM FINANCIAL_MOVEMENTS
                WHERE RELATED_ENTITY_TYPE = 'purchase_invoice'
                AND RELATED_ENTITY_ID = ?
            """, (invoice_id,))
            movement_row = cur.fetchone()
            
            if movement_row:
                movement_id = movement_row[0]
                cur.execute("""
                    UPDATE FINANCIAL_MOVEMENTS
                    SET PAYMENT_STATUS = ?, UPDATED_AT = ?
                    WHERE ID = ?
                """, (invoice_data['payment_status'], datetime.now(), movement_id))
        
        conn.commit()
        
        # ALTERAÇÃO: Registrar auditoria de atualização
        changed_fields = []
        if 'items' in invoice_data:
            changed_fields.append('items')
        if 'payment_status' in invoice_data:
            changed_fields.append('payment_status')
        if 'payment_method' in invoice_data:
            changed_fields.append('payment_method')
        if 'notes' in invoice_data:
            changed_fields.append('notes')
        
        new_values = {k: v for k, v in invoice_data.items() if k in changed_fields}
        if 'items' in invoice_data:
            new_values['items'] = invoice_data['items']
        
        _log_audit_entry(
            invoice_id=invoice_id,
            action_type='UPDATE',
            changed_by=updated_by_user_id,
            old_values=old_values,
            new_values=new_values,
            changed_fields=changed_fields,
            notes=f'Nota fiscal atualizada - campos: {", ".join(changed_fields)}',
            cur=cur
        )
        
        # Buscar nota fiscal atualizada
        updated_invoice = get_purchase_invoice_by_id(invoice_id)
        
        return (True, None, updated_invoice)
        
    except fdb.Error as e:
        logger.error(f"Erro ao atualizar nota fiscal: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", f"Erro no banco de dados: {str(e)}")
    except Exception as e:
        logger.error(f"Erro ao atualizar nota fiscal: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "INTERNAL_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()


def _log_audit_entry(invoice_id, action_type, changed_by, old_values=None, new_values=None, changed_fields=None, notes=None, cur=None):
    """
    Registra entrada de auditoria para nota fiscal
    
    ALTERAÇÃO: Função para registrar histórico de alterações
    
    Args:
        invoice_id: ID da nota fiscal
        action_type: 'CREATE', 'UPDATE', 'DELETE'
        changed_by: ID do usuário que fez a alteração
        old_values: dict com valores antigos (opcional)
        new_values: dict com valores novos (opcional)
        changed_fields: lista de campos alterados (opcional)
        notes: observações (opcional)
        cur: cursor do banco (opcional, cria novo se não fornecido)
    
    Returns:
        bool: True se registrado com sucesso
    """
    try:
        if cur is None:
            conn = get_db_connection()
            cur = conn.cursor()
            should_commit = True
        else:
            should_commit = False
        
        old_values_json = json.dumps(old_values, default=str) if old_values else None
        new_values_json = json.dumps(new_values, default=str) if new_values else None
        changed_fields_str = ', '.join(changed_fields) if changed_fields else None
        
        cur.execute("""
            INSERT INTO PURCHASE_INVOICES_AUDIT (
                PURCHASE_INVOICE_ID, ACTION_TYPE, CHANGED_BY,
                OLD_VALUES, NEW_VALUES, CHANGED_FIELDS, NOTES
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (invoice_id, action_type, changed_by, old_values_json, new_values_json, changed_fields_str, notes))
        
        if should_commit:
            conn.commit()
            conn.close()
        
        return True
    except Exception as e:
        logger.error(f"Erro ao registrar auditoria: {e}", exc_info=True)
        return False


def _update_invoice_items_with_stock_recalc(invoice_id, new_items, cur):
    """
    Atualiza itens da nota fiscal com recálculo de estoque
    
    ALTERAÇÃO: Função auxiliar para atualização de itens
    Reverte estoque dos itens antigos e aplica estoque dos novos itens
    
    Args:
        invoice_id: ID da nota fiscal
        new_items: Lista de novos itens
        cur: Cursor do banco de dados
    
    Returns:
        (success: bool, error_code: str, result: dict)
    """
    try:
        # 1. Buscar itens atuais
        cur.execute("""
            SELECT ID, INGREDIENT_ID, QUANTITY
            FROM PURCHASE_INVOICE_ITEMS
            WHERE PURCHASE_INVOICE_ID = ?
        """, (invoice_id,))
        old_items = cur.fetchall()
        
        # 2. Reverter estoque dos itens antigos
        for old_item in old_items:
            old_item_id = old_item[0]
            old_ingredient_id = old_item[1]
            old_quantity = float(old_item[2])
            
            # Reverter estoque
            cur.execute("""
                UPDATE INGREDIENTS
                SET CURRENT_STOCK = CURRENT_STOCK - ?
                WHERE ID = ?
            """, (old_quantity, old_ingredient_id))
            
            if cur.rowcount == 0:
                return (False, "STOCK_REVERSAL_ERROR", f"Erro ao reverter estoque do ingrediente ID {old_ingredient_id}")
        
        # 3. Excluir itens antigos
        cur.execute("DELETE FROM PURCHASE_INVOICE_ITEMS WHERE PURCHASE_INVOICE_ID = ?", (invoice_id,))
        
        # 4. Validar novos itens
        for item in new_items:
            if not item.get('ingredient_id'):
                return (False, "INVALID_ITEM", "Cada item deve ter ingredient_id")
            if not item.get('quantity') or float(item.get('quantity', 0)) <= 0:
                return (False, "INVALID_ITEM", "Cada item deve ter quantity > 0")
            if not item.get('unit_price') or float(item.get('unit_price', 0)) <= 0:
                return (False, "INVALID_ITEM", "Cada item deve ter unit_price > 0")
        
        # 5. Inserir novos itens e aplicar estoque
        for item in new_items:
            ingredient_id = int(item['ingredient_id'])
            quantity = float(item['quantity'])
            unit_price = float(item['unit_price'])
            total_price = quantity * unit_price
            
            # Verificar se ingrediente existe
            cur.execute("SELECT ID FROM INGREDIENTS WHERE ID = ?", (ingredient_id,))
            if not cur.fetchone():
                return (False, "INGREDIENT_NOT_FOUND", f"Ingrediente ID {ingredient_id} não encontrado")
            
            # Inserir novo item
            item_sql = """
                INSERT INTO PURCHASE_INVOICE_ITEMS (
                    PURCHASE_INVOICE_ID, INGREDIENT_ID,
                    QUANTITY, UNIT_PRICE, TOTAL_PRICE
                )
                VALUES (?, ?, ?, ?, ?)
            """
            cur.execute(item_sql, (invoice_id, ingredient_id, quantity, unit_price, total_price))
            
            # Aplicar entrada no estoque
            cur.execute("""
                UPDATE INGREDIENTS
                SET CURRENT_STOCK = CURRENT_STOCK + ?
                WHERE ID = ?
            """, (quantity, ingredient_id))
            
            if cur.rowcount == 0:
                return (False, "STOCK_UPDATE_ERROR", f"Erro ao atualizar estoque do ingrediente ID {ingredient_id}")
        
        return (True, None, {"message": "Itens atualizados com sucesso"})
        
    except Exception as e:
        logger.error(f"Erro ao atualizar itens da nota fiscal: {e}", exc_info=True)
        return (False, "INTERNAL_ERROR", f"Erro ao atualizar itens: {str(e)}")


def delete_purchase_invoice(invoice_id, deleted_by_user_id):
    """
    Exclui uma nota fiscal de compra
    
    ALTERAÇÃO: Novo método para DELETE
    Reverte entrada de estoque e remove movimento financeiro
    
    Args:
        invoice_id: ID da nota fiscal
        deleted_by_user_id: ID do usuário que está excluindo
    
    Returns:
        (success: bool, error_code: str, result: dict)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # ALTERAÇÃO: Verificar permissões granulares
        # Buscar role do usuário
        cur.execute("SELECT ROLE FROM USERS WHERE ID = ?", (deleted_by_user_id,))
        user_row = cur.fetchone()
        if not user_row:
            return (False, "USER_NOT_FOUND", "Usuário não encontrado")
        user_role = user_row[0]
        
        # Verificar permissão de exclusão
        allowed, error_code, message = _check_purchase_permission(invoice_id, deleted_by_user_id, user_role, action='delete', cur=cur)
        if not allowed:
            return (False, error_code, message)
        
        # Verificar se nota fiscal existe e buscar dados para auditoria
        cur.execute("""
            SELECT ID, INVOICE_NUMBER, SUPPLIER_NAME, TOTAL_AMOUNT, PURCHASE_DATE,
                   PAYMENT_STATUS, PAYMENT_METHOD, PAYMENT_DATE, NOTES
            FROM PURCHASE_INVOICES WHERE ID = ?
        """, (invoice_id,))
        invoice_row = cur.fetchone()
        if not invoice_row:
            return (False, "NOT_FOUND", "Nota fiscal não encontrada")
        
        # ALTERAÇÃO: Preparar valores para auditoria antes de excluir
        old_values = {
            'invoice_number': invoice_row[1],
            'supplier_name': invoice_row[2],
            'total_amount': float(invoice_row[3]) if invoice_row[3] else 0,
            'purchase_date': invoice_row[4].isoformat() if invoice_row[4] else None,
            'payment_status': invoice_row[5],
            'payment_method': invoice_row[6],
            'payment_date': invoice_row[7].isoformat() if invoice_row[7] else None,
            'notes': invoice_row[8]
        }
        
        # 1. Buscar itens da nota fiscal
        cur.execute("""
            SELECT INGREDIENT_ID, QUANTITY
            FROM PURCHASE_INVOICE_ITEMS
            WHERE PURCHASE_INVOICE_ID = ?
        """, (invoice_id,))
        
        items = cur.fetchall()
        
        # ALTERAÇÃO: Validar estoque antes de reverter
        stock_validation_errors = []
        for item in items:
            ingredient_id = item[0]
            quantity = float(item[1])
            
            # Verificar estoque atual e nome do ingrediente
            cur.execute("SELECT CURRENT_STOCK, NAME FROM INGREDIENTS WHERE ID = ?", (ingredient_id,))
            stock_row = cur.fetchone()
            if stock_row:
                current_stock = float(stock_row[0])
                ingredient_name = stock_row[1] if stock_row[1] else f"Ingrediente ID {ingredient_id}"
                # Se estoque atual é menor que quantidade a reverter, pode causar estoque negativo
                if current_stock < quantity:
                    stock_validation_errors.append({
                        'ingredient_id': ingredient_id,
                        'ingredient_name': ingredient_name,
                        'current_stock': current_stock,
                        'required_reversal': quantity,
                        'shortage': quantity - current_stock
                    })
        
        # Se houver erros de validação, retornar com detalhes
        if stock_validation_errors:
            error_details = "; ".join([
                f"{err['ingredient_name']}: estoque atual ({err['current_stock']}) < quantidade a reverter ({err['required_reversal']})"
                for err in stock_validation_errors
            ])
            return (False, "INSUFFICIENT_STOCK", 
                   f"Não é possível excluir: estoque insuficiente para reverter. {error_details}")
        
        # 2. Reverter entrada de estoque para cada item
        for item in items:
            ingredient_id = item[0]
            quantity = float(item[1])
            
            # Reverter estoque (subtrair a quantidade que foi adicionada)
            cur.execute("""
                UPDATE INGREDIENTS
                SET CURRENT_STOCK = CURRENT_STOCK - ?
                WHERE ID = ?
            """, (quantity, ingredient_id))
            
            # Verificar se a atualização foi bem-sucedida
            if cur.rowcount == 0:
                conn.rollback()
                return (False, "STOCK_REVERSAL_ERROR", f"Erro ao reverter estoque do ingrediente ID {ingredient_id}")
        
        # 3. Buscar e excluir movimento financeiro relacionado
        cur.execute("""
            SELECT ID FROM FINANCIAL_MOVEMENTS
            WHERE RELATED_ENTITY_TYPE = 'purchase_invoice'
            AND RELATED_ENTITY_ID = ?
        """, (invoice_id,))
        
        movement_row = cur.fetchone()
        if movement_row:
            movement_id = movement_row[0]
            cur.execute("DELETE FROM FINANCIAL_MOVEMENTS WHERE ID = ?", (movement_id,))
        
        # 4. Excluir itens da nota fiscal
        cur.execute("DELETE FROM PURCHASE_INVOICE_ITEMS WHERE PURCHASE_INVOICE_ID = ?", (invoice_id,))
        
        # 5. Excluir nota fiscal
        cur.execute("DELETE FROM PURCHASE_INVOICES WHERE ID = ?", (invoice_id,))
        
        if cur.rowcount == 0:
            conn.rollback()
            return (False, "DELETE_ERROR", "Erro ao excluir nota fiscal")
        
        # ALTERAÇÃO: Registrar auditoria de exclusão antes do commit
        _log_audit_entry(
            invoice_id=invoice_id,
            action_type='DELETE',
            changed_by=deleted_by_user_id,
            old_values=old_values,
            notes=f'Nota fiscal excluída - NF {old_values["invoice_number"]}',
            cur=cur
        )
        
        conn.commit()
        
        return (True, None, {"message": "Nota fiscal excluída com sucesso", "invoice_id": invoice_id})
        
    except fdb.Error as e:
        logger.error(f"Erro ao excluir nota fiscal: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", f"Erro no banco de dados: {str(e)}")
    except Exception as e:
        logger.error(f"Erro ao excluir nota fiscal: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "INTERNAL_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()

