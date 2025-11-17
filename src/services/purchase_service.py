"""
Serviço de Compras e Entrada de Estoque
Gerencia compras de ingredientes e registro automático de despesas
"""

import fdb
import logging
from datetime import datetime
from ..database import get_db_connection
from . import financial_movement_service

logger = logging.getLogger(__name__)

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
        invoice_sql = """
            INSERT INTO PURCHASE_INVOICES (
                INVOICE_NUMBER, SUPPLIER_NAME, TOTAL_AMOUNT,
                PURCHASE_DATE, PAYMENT_STATUS, PAYMENT_METHOD,
                PAYMENT_DATE, NOTES, CREATED_BY
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING ID, CREATED_AT
        """
        
        cur.execute(invoice_sql, (
            invoice_data['invoice_number'],
            invoice_data['supplier_name'],
            float(invoice_data['total_amount']),
            purchase_date,
            payment_status,
            invoice_data.get('payment_method'),
            payment_date,
            invoice_data.get('notes'),
            created_by_user_id
        ))
        
        invoice_row = cur.fetchone()
        if not invoice_row:
            return (False, "DATABASE_ERROR", "Erro ao criar nota fiscal")
        
        invoice_id = invoice_row[0]
        created_at = invoice_row[1]
        
        # 2. Inserir itens e dar entrada no estoque
        for item in invoice_data['items']:
            ingredient_id = int(item['ingredient_id'])
            quantity = float(item['quantity'])
            unit_price = float(item['unit_price'])
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

