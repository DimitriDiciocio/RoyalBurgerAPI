"""
Serviço de Movimentações Financeiras
Gerencia o novo sistema de fluxo de caixa com suporte a:
- Receitas e CMV automáticos de pedidos
- Despesas e impostos
- Contas a pagar (Pending)
- Relatórios financeiros
"""

import fdb
import logging
from datetime import datetime, date, timedelta
from ..database import get_db_connection

logger = logging.getLogger(__name__)

# Constantes
TYPE_REVENUE = 'REVENUE'
TYPE_EXPENSE = 'EXPENSE'
TYPE_CMV = 'CMV'
TYPE_TAX = 'TAX'

STATUS_PENDING = 'Pending'
STATUS_PAID = 'Paid'

# Categorias padrão
CATEGORY_SALES = 'Vendas'
CATEGORY_VARIABLE_COSTS = 'Custos Variáveis'
CATEGORY_FIXED_COSTS = 'Custos Fixos'
CATEGORY_TAXES = 'Tributos'
CATEGORY_STOCK_PURCHASES = 'Compras de Estoque'

def create_financial_movement(movement_data, created_by_user_id, cur=None):
    """
    Cria uma nova movimentação financeira
    
    Args:
        movement_data: dict com campos:
            - type: 'REVENUE', 'EXPENSE', 'CMV', 'TAX'
            - value: float (valor > 0)
            - category: str (categoria)
            - subcategory: str (opcional)
            - description: str
            - movement_date: datetime (opcional, None = pendente)
            - payment_status: 'Pending' ou 'Paid' (default: 'Pending')
            - payment_method: str (opcional)
            - sender_receiver: str (opcional)
            - related_entity_type: str (opcional, ex: 'order')
            - related_entity_id: int (opcional)
            - notes: str (opcional)
            - payment_gateway_id: str (opcional) - FASE 6: ID do gateway de pagamento
            - transaction_id: str (opcional) - FASE 6: ID da transação no gateway
            - bank_account: str (opcional) - FASE 6: Conta bancária
        created_by_user_id: ID do usuário que criou
        cur: Cursor opcional para reutilizar transação existente
    
    Returns:
        (success: bool, error_code: str, result: dict)
    """
    conn = None
    should_close_conn = False
    try:
        # ALTERAÇÃO: Se cursor não foi fornecido, cria nova conexão
        if cur is None:
            conn = get_db_connection()
            cur = conn.cursor()
            should_close_conn = True
        
        # Validações
        required_fields = ['type', 'value', 'category', 'description']
        for field in required_fields:
            if not movement_data.get(field):
                return (False, f"INVALID_{field.upper()}", f"Campo {field} é obrigatório")
        
        # Validar tipo
        valid_types = [TYPE_REVENUE, TYPE_EXPENSE, TYPE_CMV, TYPE_TAX]
        if movement_data['type'] not in valid_types:
            return (False, "INVALID_TYPE", f"Tipo deve ser um de: {', '.join(valid_types)}")
        
        # Validar valor
        try:
            value = float(movement_data['value'])
            if value <= 0:
                return (False, "INVALID_VALUE", "Valor deve ser maior que zero")
        except (ValueError, TypeError):
            return (False, "INVALID_VALUE", "Valor deve ser um número válido")
        
        # Validar status
        payment_status = movement_data.get('payment_status', STATUS_PENDING)
        if payment_status not in [STATUS_PENDING, STATUS_PAID]:
            return (False, "INVALID_STATUS", "Status deve ser 'Pending' ou 'Paid'")
        
        # ALTERAÇÃO FASE 4: Permitir movement_date mesmo para Pending (data esperada)
        # Se status é Paid, movement_date é obrigatório (usa data atual se não fornecida)
        # Se status é Pending, movement_date pode ser NULL ou uma data futura (data esperada de pagamento)
        movement_date = movement_data.get('movement_date')
        if payment_status == STATUS_PAID and not movement_date:
            movement_date = datetime.now()  # Obrigatório para Paid, usar data atual se não fornecida
        # Se Pending, movement_date pode ser NULL ou uma data futura (data esperada)
        
        # Converter movement_date para datetime se for string
        if movement_date and isinstance(movement_date, str):
            try:
                movement_date = datetime.fromisoformat(movement_date.replace('Z', '+00:00'))
            except:
                return (False, "INVALID_DATE", "Formato de data inválido")
        
        # ALTERAÇÃO FASE 6: Incluir campos de gateway e conciliação
        # Inserir movimentação
        sql = """
            INSERT INTO FINANCIAL_MOVEMENTS (
                TYPE, "VALUE", CATEGORY, SUBCATEGORY, DESCRIPTION,
                MOVEMENT_DATE, PAYMENT_STATUS, PAYMENT_METHOD,
                SENDER_RECEIVER, RELATED_ENTITY_TYPE, RELATED_ENTITY_ID,
                NOTES, CREATED_BY,
                PAYMENT_GATEWAY_ID, TRANSACTION_ID, BANK_ACCOUNT
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING ID, CREATED_AT, UPDATED_AT
        """
        
        cur.execute(sql, (
            movement_data['type'],
            value,
            movement_data['category'],
            movement_data.get('subcategory'),
            movement_data['description'],
            movement_date,
            payment_status,
            movement_data.get('payment_method'),
            movement_data.get('sender_receiver'),
            movement_data.get('related_entity_type'),
            movement_data.get('related_entity_id'),
            movement_data.get('notes'),
            created_by_user_id,
            movement_data.get('payment_gateway_id'),  # FASE 6
            movement_data.get('transaction_id'),  # FASE 6
            movement_data.get('bank_account')  # FASE 6
        ))
        
        row = cur.fetchone()
        movement_id = row[0]
        created_at = row[1]
        updated_at = row[2]
        
        # ALTERAÇÃO: Só faz commit se criou a conexão nesta função
        if should_close_conn:
            conn.commit()
        
        return (True, None, {
            "id": movement_id,
            "type": movement_data['type'],
            "value": value,
            "category": movement_data['category'],
            "subcategory": movement_data.get('subcategory'),
            "description": movement_data['description'],
            "movement_date": movement_date.isoformat() if movement_date else None,
            "payment_status": payment_status,
            "payment_method": movement_data.get('payment_method'),
            "sender_receiver": movement_data.get('sender_receiver'),
            "related_entity_type": movement_data.get('related_entity_type'),
            "related_entity_id": movement_data.get('related_entity_id'),
            "notes": movement_data.get('notes'),
            "payment_gateway_id": movement_data.get('payment_gateway_id'),  # FASE 6
            "transaction_id": movement_data.get('transaction_id'),  # FASE 6
            "bank_account": movement_data.get('bank_account'),  # FASE 6
            "reconciled": False,  # FASE 6 - sempre False ao criar
            "reconciled_at": None,  # FASE 6
            "created_at": created_at.isoformat() if created_at else None,
            "updated_at": updated_at.isoformat() if updated_at else None
        })
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logger para código de produção
        logger.error(f"Erro ao criar movimentação financeira: {e}", exc_info=True)
        if should_close_conn and conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if should_close_conn and conn:
            conn.close()


def register_order_revenue_and_cmv(order_id, order_total, payment_method, payment_date=None, created_by_user_id=None, cur=None):
    """
    Registra automaticamente RECEITA, CMV e TAXAS DE PAGAMENTO de um pedido finalizado
    
    Args:
        order_id: ID do pedido
        order_total: Valor total do pedido (já com descontos aplicados)
        payment_method: Método de pagamento ('credit', 'debit', 'pix', 'money', 'ifood', 'uber_eats')
        payment_date: Data do pagamento (default: agora)
        created_by_user_id: ID do usuário (opcional)
        cur: Cursor opcional para reutilizar transação existente
    
    Returns:
        (success: bool, revenue_id: int, cmv_id: int, payment_fee_id: int, error: str)
        - revenue_id: ID da movimentação de receita
        - cmv_id: ID da movimentação de CMV (None se não houver custo)
        - payment_fee_id: ID da movimentação de taxa de pagamento (None se não houver taxa)
    """
    conn = None
    should_close_conn = False
    try:
        # ALTERAÇÃO: Se cursor não foi fornecido, cria nova conexão
        if cur is None:
            conn = get_db_connection()
            cur = conn.cursor()
            should_close_conn = True
        
        # Buscar dados do pedido para calcular CMV
        # CORREÇÃO: Incluir extras no cálculo do CMV - Query otimizada
        cur.execute("""
            SELECT 
                oi.PRODUCT_ID,
                oi.QUANTITY,
                -- Custo do produto (usa COST_PRICE se disponível, senão calcula pelos ingredientes)
                COALESCE(
                    p.COST_PRICE,
                    (SELECT SUM(pi.PORTIONS * ing.PRICE)
                     FROM PRODUCT_INGREDIENTS pi
                     JOIN INGREDIENTS ing ON pi.INGREDIENT_ID = ing.ID
                     WHERE pi.PRODUCT_ID = oi.PRODUCT_ID)
                ) as product_cost,
                -- Custo dos extras
                -- NOTA: INGREDIENTS não tem COST_PRICE, usa PRICE como custo
                COALESCE(SUM(
                    CASE 
                        WHEN oie.TYPE = 'extra' THEN oie.QUANTITY * COALESCE(i.PRICE, 0)
                        WHEN oie.TYPE = 'base' AND oie.DELTA > 0 THEN oie.DELTA * COALESCE(i.PRICE, 0)
                        ELSE 0
                    END
                ), 0) as extras_cost
            FROM ORDER_ITEMS oi
            JOIN PRODUCTS p ON oi.PRODUCT_ID = p.ID
            LEFT JOIN ORDER_ITEM_EXTRAS oie ON oi.ID = oie.ORDER_ITEM_ID
            LEFT JOIN INGREDIENTS i ON oie.INGREDIENT_ID = i.ID
            WHERE oi.ORDER_ID = ?
            GROUP BY oi.PRODUCT_ID, oi.QUANTITY, p.COST_PRICE
        """, (order_id,))
        
        order_items = cur.fetchall()
        if not order_items:
            return (False, None, None, "Pedido não encontrado ou sem itens")
        
        # Calcular CMV (Custo de Mercadoria Vendida) incluindo extras
        total_cmv = 0.0
        for item in order_items:
            product_id, quantity, product_cost, extras_cost = item
            
            # Custo do produto
            product_cost_float = float(product_cost or 0)
            if product_cost_float <= 0:
                # Se não tem COST_PRICE, calcular pelos ingredientes
                cur.execute("""
                    SELECT SUM(pi.PORTIONS * ing.PRICE)
                    FROM PRODUCT_INGREDIENTS pi
                    JOIN INGREDIENTS ing ON pi.INGREDIENT_ID = ing.ID
                    WHERE pi.PRODUCT_ID = ?
                """, (product_id,))
                cost_result = cur.fetchone()
                product_cost_float = float(cost_result[0] or 0) if cost_result else 0.0
            
            # Custo total do item = (custo produto × quantidade) + custo extras
            total_cmv += (product_cost_float * quantity) + float(extras_cost or 0)
        
        # Mapear método de pagamento para subcategoria
        payment_subcategory_map = {
            'credit': 'Cartão de Crédito',
            'debit': 'Cartão de Débito',
            'pix': 'PIX',
            'money': 'Dinheiro',
            'cash': 'Dinheiro'
        }
        subcategory = payment_subcategory_map.get(payment_method.lower() if payment_method else '', payment_method or 'Outros')
        
        # Data do movimento (pagamento)
        if not payment_date:
            payment_date = datetime.now()
        elif isinstance(payment_date, str):
            try:
                payment_date = datetime.fromisoformat(payment_date.replace('Z', '+00:00'))
            except:
                payment_date = datetime.now()
        elif isinstance(payment_date, date) and not isinstance(payment_date, datetime):
            payment_date = datetime.combine(payment_date, datetime.min.time())
        
        # Registrar RECEITA diretamente no banco (sem chamar create_financial_movement para evitar overhead)
        revenue_sql = """
            INSERT INTO FINANCIAL_MOVEMENTS (
                TYPE, "VALUE", CATEGORY, SUBCATEGORY, DESCRIPTION,
                MOVEMENT_DATE, PAYMENT_STATUS, PAYMENT_METHOD,
                RELATED_ENTITY_TYPE, RELATED_ENTITY_ID, CREATED_BY
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING ID
        """
        
        cur.execute(revenue_sql, (
            TYPE_REVENUE,
            float(order_total),
            CATEGORY_SALES,
            subcategory,
            f'Venda - Pedido #{order_id}',
            payment_date,
            STATUS_PAID,
            payment_method,
            'order',
            order_id,
            created_by_user_id
        ))
        
        revenue_row = cur.fetchone()
        revenue_id = revenue_row[0] if revenue_row else None
        
        # Registrar CMV (apenas se houver custo)
        cmv_id = None
        if total_cmv > 0:
            cmv_sql = """
                INSERT INTO FINANCIAL_MOVEMENTS (
                    TYPE, "VALUE", CATEGORY, SUBCATEGORY, DESCRIPTION,
                    MOVEMENT_DATE, PAYMENT_STATUS,
                    RELATED_ENTITY_TYPE, RELATED_ENTITY_ID, CREATED_BY
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING ID
            """
            
            cur.execute(cmv_sql, (
                TYPE_CMV,
                total_cmv,
                CATEGORY_VARIABLE_COSTS,
                'Ingredientes Consumidos',
                f'CMV - Pedido #{order_id}',
                payment_date,
                STATUS_PAID,
                'order',
                order_id,
                created_by_user_id
            ))
            
            cmv_row = cur.fetchone()
            cmv_id = cmv_row[0] if cmv_row else None
        
        # ALTERAÇÃO FASE 3: Calcular e registrar taxa de pagamento
        payment_fee_id = None
        if payment_method:
            payment_method_lower = payment_method.lower() if payment_method else ''
            
            # Buscar taxas de APP_SETTINGS
            # Mapear método de pagamento para campo de taxa
            tax_field_map = {
                'credit': 'taxa_cartao_credito',
                'debit': 'taxa_cartao_debito',
                'pix': 'taxa_pix',
                'ifood': 'taxa_ifood',
                'uber_eats': 'taxa_uber_eats',
                'uber': 'taxa_uber_eats'
            }
            
            tax_field = tax_field_map.get(payment_method_lower)
            
            if tax_field:
                # Buscar configurações (usar cache se disponível)
                # ALTERAÇÃO: Buscar taxas de APP_SETTINGS usando cursor se disponível, senão usar cache
                if cur:
                    # Buscar diretamente do banco usando cursor existente
                    cur.execute("""
                        SELECT TAXA_CARTAO_CREDITO, TAXA_CARTAO_DEBITO, TAXA_PIX, TAXA_IFOOD, TAXA_UBER_EATS
                        FROM APP_SETTINGS
                        WHERE ID = (SELECT MAX(ID) FROM APP_SETTINGS)
                    """)
                    tax_row = cur.fetchone()
                    if tax_row:
                        tax_values = {
                            'taxa_cartao_credito': float(tax_row[0]) if tax_row[0] else 0.0,
                            'taxa_cartao_debito': float(tax_row[1]) if tax_row[1] else 0.0,
                            'taxa_pix': float(tax_row[2]) if tax_row[2] else 0.0,
                            'taxa_ifood': float(tax_row[3]) if tax_row[3] else 0.0,
                            'taxa_uber_eats': float(tax_row[4]) if tax_row[4] else 0.0
                        }
                        tax_percentage = tax_values.get(tax_field, 0.0)
                    else:
                        tax_percentage = 0.0
                else:
                    # Usar cache se não houver cursor
                    from . import settings_service
                    settings = settings_service.get_all_settings(use_cache=True)
                    tax_percentage = settings.get(tax_field, 0.0) if settings else 0.0
                
                # Calcular valor da taxa
                if tax_percentage and float(tax_percentage) > 0:
                    fee_amount = (float(order_total) * float(tax_percentage)) / 100.0
                    
                    # Registrar despesa de taxa diretamente no banco
                    fee_sql = """
                        INSERT INTO FINANCIAL_MOVEMENTS (
                            TYPE, "VALUE", CATEGORY, SUBCATEGORY, DESCRIPTION,
                            MOVEMENT_DATE, PAYMENT_STATUS, PAYMENT_METHOD,
                            RELATED_ENTITY_TYPE, RELATED_ENTITY_ID, CREATED_BY
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        RETURNING ID
                    """
                    
                    cur.execute(fee_sql, (
                        TYPE_EXPENSE,
                        fee_amount,
                        CATEGORY_VARIABLE_COSTS,
                        'Taxas de Pagamento',
                        f'Taxa {payment_method} - Pedido #{order_id}',
                        payment_date,
                        STATUS_PAID,  # Taxa é deduzida automaticamente
                        payment_method,
                        'order',
                        order_id,
                        created_by_user_id
                    ))
                    
                    fee_row = cur.fetchone()
                    payment_fee_id = fee_row[0] if fee_row else None
        
        # ALTERAÇÃO: Só faz commit se criou a conexão nesta função
        if should_close_conn:
            conn.commit()
        
        return (True, revenue_id, cmv_id, payment_fee_id, None)
        
    except Exception as e:
        # ALTERAÇÃO: Substituído print() por logger para código de produção
        logger.error(f"Erro ao registrar receita e CMV do pedido {order_id}: {e}", exc_info=True)
        if should_close_conn and conn:
            conn.rollback()
        return (False, None, None, None, str(e))
    finally:
        if should_close_conn and conn:
            conn.close()


def get_financial_movements(filters=None):
    """
    Busca movimentações financeiras com filtros
    
    Args:
        filters: dict com:
            - start_date: datetime/str
            - end_date: datetime/str
            - type: 'REVENUE', 'EXPENSE', 'CMV', 'TAX'
            - category: str
            - payment_status: 'Pending', 'Paid'
            - related_entity_type: str
            - related_entity_id: int
    
    Returns:
        list de movimentações
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # ALTERAÇÃO FASE 6: Incluir campos de gateway e conciliação
        base_sql = """
            SELECT 
                fm.ID, fm.TYPE, fm."VALUE", fm.CATEGORY, fm.SUBCATEGORY,
                fm.DESCRIPTION, fm.MOVEMENT_DATE, fm.PAYMENT_STATUS,
                fm.PAYMENT_METHOD, fm.SENDER_RECEIVER,
                fm.RELATED_ENTITY_TYPE, fm.RELATED_ENTITY_ID,
                fm.NOTES, fm.CREATED_AT, fm.UPDATED_AT,
                fm.PAYMENT_GATEWAY_ID, fm.TRANSACTION_ID, fm.BANK_ACCOUNT,
                fm.RECONCILED, fm.RECONCILED_AT,
                u.FULL_NAME as created_by_name
            FROM FINANCIAL_MOVEMENTS fm
            LEFT JOIN USERS u ON fm.CREATED_BY = u.ID
        """
        
        conditions = []
        params = []
        
        if filters:
            # Filtro por data de movimento (para fluxo de caixa real)
            if filters.get('start_date'):
                start_date = filters['start_date']
                if isinstance(start_date, str):
                    try:
                        start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    except:
                        pass
                if isinstance(start_date, date) and not isinstance(start_date, datetime):
                    start_date = datetime.combine(start_date, datetime.min.time())
                conditions.append("fm.MOVEMENT_DATE >= ?")
                params.append(start_date)
            
            if filters.get('end_date'):
                end_date = filters['end_date']
                if isinstance(end_date, str):
                    try:
                        end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    except:
                        pass
                if isinstance(end_date, date) and not isinstance(end_date, datetime):
                    end_date = datetime.combine(end_date, datetime.min.time())
                # Adiciona 1 dia para incluir o dia final
                end_date = end_date + timedelta(days=1)
                conditions.append("fm.MOVEMENT_DATE < ?")
                params.append(end_date)
            
            # Filtro por tipo
            if filters.get('type'):
                conditions.append("fm.TYPE = ?")
                params.append(filters['type'])
            
            # Filtro por categoria
            if filters.get('category'):
                conditions.append("fm.CATEGORY = ?")
                params.append(filters['category'])
            
            # Filtro por status de pagamento
            if filters.get('payment_status'):
                conditions.append("fm.PAYMENT_STATUS = ?")
                params.append(filters['payment_status'])
            
            # Filtro por entidade relacionada
            if filters.get('related_entity_type'):
                conditions.append("fm.RELATED_ENTITY_TYPE = ?")
                params.append(filters['related_entity_type'])
            
            if filters.get('related_entity_id'):
                conditions.append("fm.RELATED_ENTITY_ID = ?")
                params.append(filters['related_entity_id'])
            
            # FASE 6: Filtros de gateway e conciliação
            if filters.get('payment_gateway_id'):
                conditions.append("fm.PAYMENT_GATEWAY_ID = ?")
                params.append(filters['payment_gateway_id'])
            
            if filters.get('transaction_id'):
                conditions.append("fm.TRANSACTION_ID = ?")
                params.append(filters['transaction_id'])
            
            if filters.get('bank_account'):
                conditions.append("fm.BANK_ACCOUNT = ?")
                params.append(filters['bank_account'])
            
            if filters.get('reconciled') is not None:
                conditions.append("fm.RECONCILED = ?")
                params.append(bool(filters['reconciled']))
        
        if conditions:
            base_sql += " WHERE " + " AND ".join(conditions)
        
        base_sql += " ORDER BY fm.MOVEMENT_DATE DESC NULLS LAST, fm.CREATED_AT DESC"
        
        cur.execute(base_sql, params)
        
        movements = []
        for row in cur.fetchall():
            movements.append({
                "id": row[0],
                "type": row[1],
                "value": float(row[2]),
                "category": row[3],
                "subcategory": row[4],
                "description": row[5],
                "movement_date": row[6].isoformat() if row[6] else None,
                "payment_status": row[7],
                "payment_method": row[8],
                "sender_receiver": row[9],
                "related_entity_type": row[10],
                "related_entity_id": row[11],
                "notes": row[12],
                "created_at": row[13].isoformat() if row[13] else None,
                "updated_at": row[14].isoformat() if row[14] else None,
                "payment_gateway_id": row[15],  # FASE 6
                "transaction_id": row[16],  # FASE 6
                "bank_account": row[17],  # FASE 6
                "reconciled": bool(row[18]) if row[18] is not None else False,  # FASE 6
                "reconciled_at": row[19].isoformat() if row[19] else None,  # FASE 6
                "created_by_name": row[20]
            })
        
        return movements
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logger para código de produção
        logger.error(f"Erro ao buscar movimentações financeiras: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


def get_financial_movement_by_id(movement_id):
    """
    Busca uma movimentação financeira por ID
    
    Args:
        movement_id: int - ID da movimentação
    
    Returns:
        dict com os dados da movimentação ou None se não encontrada
    """
    # ALTERAÇÃO: Nova função adicionada para integração com frontend
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT 
                fm.ID, fm.TYPE, fm."VALUE", fm.CATEGORY, fm.SUBCATEGORY,
                fm.DESCRIPTION, fm.MOVEMENT_DATE, fm.PAYMENT_STATUS,
                fm.PAYMENT_METHOD, fm.SENDER_RECEIVER,
                fm.RELATED_ENTITY_TYPE, fm.RELATED_ENTITY_ID,
                fm.NOTES, fm.CREATED_AT, fm.UPDATED_AT,
                fm.PAYMENT_GATEWAY_ID, fm.TRANSACTION_ID, fm.BANK_ACCOUNT,
                fm.RECONCILED, fm.RECONCILED_AT,
                u.FULL_NAME as created_by_name
            FROM FINANCIAL_MOVEMENTS fm
            LEFT JOIN USERS u ON fm.CREATED_BY = u.ID
            WHERE fm.ID = ?
        """
        
        cur.execute(sql, (movement_id,))
        row = cur.fetchone()
        
        if not row:
            return None
        
        # ALTERAÇÃO: Formatar resultado no mesmo padrão da lista
        movement = {
            'id': row[0],
            'type': row[1],
            'value': float(row[2]) if row[2] else 0.0,
            'category': row[3],
            'subcategory': row[4],
            'description': row[5],
            'movement_date': row[6].isoformat() if row[6] else None,
            'payment_status': row[7],
            'payment_method': row[8],
            'sender_receiver': row[9],
            'related_entity_type': row[10],
            'related_entity_id': row[11],
            'notes': row[12],
            'created_at': row[13].isoformat() if row[13] else None,
            'updated_at': row[14].isoformat() if row[14] else None,
            'payment_gateway_id': row[15],
            'transaction_id': row[16],
            'bank_account': row[17],
            'reconciled': bool(row[18]) if row[18] is not None else False,
            'reconciled_at': row[19].isoformat() if row[19] else None,
            'created_by_name': row[20]
        }
        
        return movement
        
    except fdb.Error as e:
        logger.error(f"Erro ao buscar movimentação financeira {movement_id}: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def update_financial_movement(movement_id, movement_data, updated_by_user_id=None):
    """
    Atualiza uma movimentação financeira (campos gerais)
    
    Args:
        movement_id: int - ID da movimentação
        movement_data: dict com campos a atualizar:
            - type: 'REVENUE', 'EXPENSE', 'CMV', 'TAX' (opcional)
            - value: float (opcional)
            - category: str (opcional)
            - subcategory: str (opcional)
            - description: str (opcional)
            - movement_date: datetime/str (opcional)
            - payment_status: 'Pending' ou 'Paid' (opcional)
            - payment_method: str (opcional)
            - sender_receiver: str (opcional)
            - notes: str (opcional)
        updated_by_user_id: ID do usuário que está atualizando
    
    Returns:
        (success: bool, error_code: str, result: dict/str)
    """
    # ALTERAÇÃO: Nova função adicionada para integração com frontend
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verificar se movimentação existe
        cur.execute("SELECT ID FROM FINANCIAL_MOVEMENTS WHERE ID = ?", (movement_id,))
        if not cur.fetchone():
            return (False, "NOT_FOUND", "Movimentação não encontrada")
        
        # Construir campos a atualizar
        update_fields = []
        params = []
        
        if 'type' in movement_data:
            valid_types = [TYPE_REVENUE, TYPE_EXPENSE, TYPE_CMV, TYPE_TAX]
            if movement_data['type'] not in valid_types:
                return (False, "INVALID_TYPE", f"Tipo deve ser um de: {', '.join(valid_types)}")
            update_fields.append("TYPE = ?")
            params.append(movement_data['type'])
        
        if 'value' in movement_data:
            try:
                value = float(movement_data['value'])
                if value <= 0:
                    return (False, "INVALID_VALUE", "Valor deve ser maior que zero")
                update_fields.append('"VALUE" = ?')
                params.append(value)
            except (ValueError, TypeError):
                return (False, "INVALID_VALUE", "Valor deve ser um número válido")
        
        if 'category' in movement_data:
            update_fields.append("CATEGORY = ?")
            params.append(movement_data['category'])
        
        if 'subcategory' in movement_data:
            update_fields.append("SUBCATEGORY = ?")
            params.append(movement_data['subcategory'])
        
        if 'description' in movement_data:
            update_fields.append("DESCRIPTION = ?")
            params.append(movement_data['description'])
        
        if 'movement_date' in movement_data:
            movement_date = movement_data['movement_date']
            if isinstance(movement_date, str):
                try:
                    movement_date = datetime.fromisoformat(movement_date.replace('Z', '+00:00'))
                except:
                    return (False, "INVALID_DATE", "Data inválida")
            update_fields.append("MOVEMENT_DATE = ?")
            params.append(movement_date)
        
        if 'payment_status' in movement_data:
            if movement_data['payment_status'] not in [STATUS_PENDING, STATUS_PAID]:
                return (False, "INVALID_STATUS", "Status deve ser 'Pending' ou 'Paid'")
            update_fields.append("PAYMENT_STATUS = ?")
            params.append(movement_data['payment_status'])
        
        if 'payment_method' in movement_data:
            update_fields.append("PAYMENT_METHOD = ?")
            params.append(movement_data['payment_method'])
        
        if 'sender_receiver' in movement_data:
            update_fields.append("SENDER_RECEIVER = ?")
            params.append(movement_data['sender_receiver'])
        
        if 'notes' in movement_data:
            update_fields.append("NOTES = ?")
            params.append(movement_data['notes'])
        
        # Se não há campos para atualizar
        if not update_fields:
            return (False, "NO_UPDATES", "Nenhum campo para atualizar")
        
        # Adicionar UPDATED_AT
        update_fields.append("UPDATED_AT = CURRENT_TIMESTAMP")
        
        if updated_by_user_id:
            update_fields.append("UPDATED_BY = ?")
            params.append(updated_by_user_id)
        
        # Executar atualização
        sql = f"""
            UPDATE FINANCIAL_MOVEMENTS
            SET {', '.join(update_fields)}
            WHERE ID = ?
        """
        params.append(movement_id)
        
        cur.execute(sql, params)
        conn.commit()
        
        # Buscar movimentação atualizada
        updated_movement = get_financial_movement_by_id(movement_id)
        
        return (True, None, updated_movement)
        
    except fdb.Error as e:
        logger.error(f"Erro ao atualizar movimentação financeira {movement_id}: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", str(e))
    finally:
        if conn:
            conn.close()


def get_cash_flow_summary(period='this_month', include_pending=False):
    """
    Calcula resumo do fluxo de caixa
    
    Args:
        period: 'this_month', 'last_month', 'last_30_days', 'custom'
        include_pending: Se True, inclui movimentações pendentes
    
    Returns:
        dict com:
            - total_revenue: float
            - total_expense: float
            - total_cmv: float
            - total_tax: float
            - gross_profit: float (revenue - cmv)
            - net_profit: float (revenue - cmv - expense - tax)
            - cash_flow: float (entradas - saídas)
            - pending_amount: float (se include_pending)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Determinar período
        if period == 'this_month':
            date_filter = """
                EXTRACT(MONTH FROM MOVEMENT_DATE) = EXTRACT(MONTH FROM CURRENT_DATE)
                AND EXTRACT(YEAR FROM MOVEMENT_DATE) = EXTRACT(YEAR FROM CURRENT_DATE)
            """
        elif period == 'last_month':
            date_filter = """
                EXTRACT(MONTH FROM MOVEMENT_DATE) = EXTRACT(MONTH FROM CURRENT_DATE) - 1
                AND EXTRACT(YEAR FROM MOVEMENT_DATE) = EXTRACT(YEAR FROM CURRENT_DATE)
            """
        elif period == 'last_30_days':
            date_filter = "MOVEMENT_DATE >= CURRENT_DATE - INTERVAL '30 days'"
        else:
            date_filter = "1=1"  # Todos os registros
        
        # Query para movimentações pagas (fluxo de caixa real)
        sql = f"""
            SELECT 
                TYPE,
                SUM("VALUE") as total
            FROM FINANCIAL_MOVEMENTS
            WHERE PAYMENT_STATUS = 'Paid'
            AND MOVEMENT_DATE IS NOT NULL
            AND ({date_filter})
            GROUP BY TYPE
        """
        
        cur.execute(sql)
        results = cur.fetchall()
        
        totals = {
            TYPE_REVENUE: 0.0,
            TYPE_EXPENSE: 0.0,
            TYPE_CMV: 0.0,
            TYPE_TAX: 0.0
        }
        
        for row in results:
            movement_type, total = row
            totals[movement_type] = float(total or 0)
        
        # Calcular métricas
        total_revenue = totals[TYPE_REVENUE]
        total_expense = totals[TYPE_EXPENSE]
        total_cmv = totals[TYPE_CMV]
        total_tax = totals[TYPE_TAX]
        
        gross_profit = total_revenue - total_cmv
        net_profit = total_revenue - total_cmv - total_expense - total_tax
        cash_flow = total_revenue - total_expense - total_cmv - total_tax
        
        result = {
            "total_revenue": total_revenue,
            "total_expense": total_expense,
            "total_cmv": total_cmv,
            "total_tax": total_tax,
            "gross_profit": gross_profit,
            "net_profit": net_profit,
            "cash_flow": cash_flow,
            "period": period
        }
        
        # ALTERAÇÃO FASE 4: Incluir pendentes usando MOVEMENT_DATE esperado se disponível
        # Para pendentes, usar MOVEMENT_DATE (data esperada) se disponível, senão CREATED_AT
        if include_pending:
            # Criar filtro de data para pendentes usando data esperada
            pending_date_filter = """
                CASE 
                    WHEN MOVEMENT_DATE IS NOT NULL THEN MOVEMENT_DATE
                    ELSE CREATED_AT
                END
            """
            
            # Ajustar date_filter para usar a data esperada
            if period == 'this_month':
                pending_filter = f"""
                    EXTRACT(MONTH FROM ({pending_date_filter})) = EXTRACT(MONTH FROM CURRENT_DATE)
                    AND EXTRACT(YEAR FROM ({pending_date_filter})) = EXTRACT(YEAR FROM CURRENT_DATE)
                """
            elif period == 'last_month':
                pending_filter = f"""
                    EXTRACT(MONTH FROM ({pending_date_filter})) = EXTRACT(MONTH FROM CURRENT_DATE) - 1
                    AND EXTRACT(YEAR FROM ({pending_date_filter})) = EXTRACT(YEAR FROM CURRENT_DATE)
                """
            elif period == 'last_30_days':
                pending_filter = f"{pending_date_filter} >= CURRENT_DATE - INTERVAL '30 days'"
            else:
                pending_filter = "1=1"  # Todos os pendentes
            
            cur.execute(f"""
                SELECT 
                    TYPE,
                    SUM("VALUE") as total
                FROM FINANCIAL_MOVEMENTS
                WHERE PAYMENT_STATUS = 'Pending'
                AND ({pending_filter})
                GROUP BY TYPE
            """)
            
            pending_results = cur.fetchall()
            pending_amount = 0.0
            for row in pending_results:
                movement_type, total = row
                if movement_type in [TYPE_EXPENSE, TYPE_TAX]:
                    pending_amount += float(total or 0)
            
            result["pending_amount"] = pending_amount
        
        return result
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logger para código de produção
        logger.error(f"Erro ao calcular resumo do fluxo de caixa: {e}", exc_info=True)
        return {
            "total_revenue": 0.0,
            "total_expense": 0.0,
            "total_cmv": 0.0,
            "total_tax": 0.0,
            "gross_profit": 0.0,
            "net_profit": 0.0,
            "cash_flow": 0.0,
            "period": period
        }
    finally:
        if conn:
            conn.close()


def update_payment_status(movement_id, payment_status, movement_date=None, updated_by_user_id=None):
    """
    Atualiza status de pagamento de uma movimentação
    
    Args:
        movement_id: ID da movimentação
        payment_status: 'Pending' ou 'Paid'
        movement_date: Data do movimento (obrigatório se status = 'Paid')
        updated_by_user_id: ID do usuário que atualizou
    
    Returns:
        (success: bool, error_code: str, result: dict)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Validar status
        if payment_status not in [STATUS_PENDING, STATUS_PAID]:
            return (False, "INVALID_STATUS", "Status deve ser 'Pending' ou 'Paid'")
        
        # Se marcando como Paid, movement_date é obrigatório
        if payment_status == STATUS_PAID:
            if not movement_date:
                movement_date = datetime.now()
            elif isinstance(movement_date, str):
                try:
                    movement_date = datetime.fromisoformat(movement_date.replace('Z', '+00:00'))
                except:
                    movement_date = datetime.now()
            elif isinstance(movement_date, date) and not isinstance(movement_date, datetime):
                movement_date = datetime.combine(movement_date, datetime.min.time())
        else:
            # Se marcando como Pending, limpar movement_date
            movement_date = None
        
        # Atualizar
        sql = """
            UPDATE FINANCIAL_MOVEMENTS
            SET PAYMENT_STATUS = ?,
                MOVEMENT_DATE = ?,
                UPDATED_AT = CURRENT_TIMESTAMP
            WHERE ID = ?
            RETURNING ID, TYPE, "VALUE", DESCRIPTION
        """
        
        cur.execute(sql, (payment_status, movement_date, movement_id))
        row = cur.fetchone()
        
        if not row:
            return (False, "NOT_FOUND", "Movimentação não encontrada")
        
        conn.commit()
        
        return (True, None, {
            "id": row[0],
            "type": row[1],
            "value": float(row[2]),
            "description": row[3],
            "payment_status": payment_status,
            "movement_date": movement_date.isoformat() if movement_date else None
        })
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logger para código de produção
        logger.error(f"Erro ao atualizar status de pagamento da movimentação {movement_id}: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()


def reconcile_financial_movement(movement_id, reconciled=True, updated_by_user_id=None):
    """
    Marca uma movimentação financeira como reconciliada ou não
    
    Args:
        movement_id: ID da movimentação
        reconciled: True para marcar como reconciliada, False para desmarcar
        updated_by_user_id: ID do usuário que atualizou (opcional)
    
    Returns:
        (success: bool, error_code: str, result: dict)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verificar se existe
        cur.execute("SELECT ID FROM FINANCIAL_MOVEMENTS WHERE ID = ?", (movement_id,))
        if not cur.fetchone():
            return (False, "NOT_FOUND", "Movimentação não encontrada")
        
        # Atualizar status de conciliação
        reconciled_at = datetime.now() if reconciled else None
        
        sql = """
            UPDATE FINANCIAL_MOVEMENTS
            SET RECONCILED = ?,
                RECONCILED_AT = ?,
                UPDATED_AT = CURRENT_TIMESTAMP
            WHERE ID = ?
            RETURNING ID, TYPE, "VALUE", DESCRIPTION, RECONCILED, RECONCILED_AT
        """
        
        cur.execute(sql, (reconciled, reconciled_at, movement_id))
        row = cur.fetchone()
        
        if not row:
            return (False, "NOT_FOUND", "Movimentação não encontrada")
        
        conn.commit()
        
        return (True, None, {
            "id": row[0],
            "type": row[1],
            "value": float(row[2]),
            "description": row[3],
            "reconciled": bool(row[4]) if row[4] is not None else False,
            "reconciled_at": row[5].isoformat() if row[5] else None
        })
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logger para código de produção
        logger.error(f"Erro ao reconciliar movimentação {movement_id}: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()


def update_financial_movement_gateway_info(movement_id, gateway_data, updated_by_user_id=None):
    """
    Atualiza informações de gateway de uma movimentação financeira
    
    Args:
        movement_id: ID da movimentação
        gateway_data: dict com:
            - payment_gateway_id: str (opcional)
            - transaction_id: str (opcional)
            - bank_account: str (opcional)
        updated_by_user_id: ID do usuário que atualizou (opcional)
    
    Returns:
        (success: bool, error_code: str, result: dict)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verificar se existe
        cur.execute("SELECT ID FROM FINANCIAL_MOVEMENTS WHERE ID = ?", (movement_id,))
        if not cur.fetchone():
            return (False, "NOT_FOUND", "Movimentação não encontrada")
        
        # Construir query de atualização dinamicamente
        updates = []
        params = []
        
        if 'payment_gateway_id' in gateway_data:
            updates.append("PAYMENT_GATEWAY_ID = ?")
            params.append(gateway_data['payment_gateway_id'])
        
        if 'transaction_id' in gateway_data:
            updates.append("TRANSACTION_ID = ?")
            params.append(gateway_data['transaction_id'])
        
        if 'bank_account' in gateway_data:
            updates.append("BANK_ACCOUNT = ?")
            params.append(gateway_data['bank_account'])
        
        if not updates:
            return (False, "NO_UPDATES", "Nenhum campo para atualizar")
        
        updates.append("UPDATED_AT = CURRENT_TIMESTAMP")
        params.append(movement_id)
        
        sql = f"""
            UPDATE FINANCIAL_MOVEMENTS
            SET {', '.join(updates)}
            WHERE ID = ?
            RETURNING ID, PAYMENT_GATEWAY_ID, TRANSACTION_ID, BANK_ACCOUNT
        """
        
        cur.execute(sql, params)
        row = cur.fetchone()
        
        if not row:
            return (False, "NOT_FOUND", "Movimentação não encontrada")
        
        conn.commit()
        
        return (True, None, {
            "id": row[0],
            "payment_gateway_id": row[1],
            "transaction_id": row[2],
            "bank_account": row[3]
        })
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logger para código de produção
        logger.error(f"Erro ao atualizar informações de gateway da movimentação {movement_id}: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()


def get_reconciliation_report(start_date=None, end_date=None, reconciled=None, payment_gateway_id=None):
    """
    Gera relatório de conciliação bancária
    
    Args:
        start_date: datetime/str (opcional)
        end_date: datetime/str (opcional)
        reconciled: bool (opcional) - True para reconciliadas, False para não reconciliadas, None para todas
        payment_gateway_id: str (opcional) - Filtrar por gateway
    
    Returns:
        dict com:
            - total_movements: int
            - reconciled_count: int
            - unreconciled_count: int
            - reconciled_amount: float
            - unreconciled_amount: float
            - movements: list de movimentações
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Construir filtros
        conditions = []
        params = []
        
        if start_date:
            if isinstance(start_date, str):
                try:
                    start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                except:
                    pass
            if isinstance(start_date, date) and not isinstance(start_date, datetime):
                start_date = datetime.combine(start_date, datetime.min.time())
            conditions.append("fm.MOVEMENT_DATE >= ?")
            params.append(start_date)
        
        if end_date:
            if isinstance(end_date, str):
                try:
                    end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                except:
                    pass
            if isinstance(end_date, date) and not isinstance(end_date, datetime):
                end_date = datetime.combine(end_date, datetime.min.time())
            end_date = end_date + timedelta(days=1)
            conditions.append("fm.MOVEMENT_DATE < ?")
            params.append(end_date)
        
        if reconciled is not None:
            conditions.append("fm.RECONCILED = ?")
            params.append(bool(reconciled))
        
        if payment_gateway_id:
            conditions.append("fm.PAYMENT_GATEWAY_ID = ?")
            params.append(payment_gateway_id)
        
        # Adicionar filtro para apenas movimentações pagas (relevantes para conciliação)
        conditions.append("fm.PAYMENT_STATUS = 'Paid'")
        
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        
        # ALTERAÇÃO: Buscar estatísticas com CAST para garantir compatibilidade de tipos
        stats_sql = """
            SELECT 
                CAST(COUNT(*) AS INTEGER) as total,
                CAST(SUM(CASE WHEN fm.RECONCILED = 1 THEN 1 ELSE 0 END) AS INTEGER) as reconciled_count,
                CAST(SUM(CASE WHEN fm.RECONCILED IS NULL OR fm.RECONCILED = 0 THEN 1 ELSE 0 END) AS INTEGER) as unreconciled_count,
                CAST(SUM(CASE WHEN fm.RECONCILED = 1 THEN CAST(fm."VALUE" AS DECIMAL(15,2)) ELSE 0 END) AS DECIMAL(15,2)) as reconciled_amount,
                CAST(SUM(CASE WHEN fm.RECONCILED IS NULL OR fm.RECONCILED = 0 THEN CAST(fm."VALUE" AS DECIMAL(15,2)) ELSE 0 END) AS DECIMAL(15,2)) as unreconciled_amount
            FROM FINANCIAL_MOVEMENTS fm
        """ + where_clause
        
        cur.execute(stats_sql, params)
        stats_row = cur.fetchone()
        
        # ALTERAÇÃO: Garantir que valores nunca sejam None
        total_movements = int(stats_row[0]) if stats_row[0] is not None else 0
        reconciled_count = int(stats_row[1]) if stats_row[1] is not None else 0
        unreconciled_count = int(stats_row[2]) if stats_row[2] is not None else 0
        reconciled_amount = float(stats_row[3]) if stats_row[3] is not None else 0.0
        unreconciled_amount = float(stats_row[4]) if stats_row[4] is not None else 0.0
        
        # Buscar movimentações
        movements_sql = """
            SELECT 
                fm.ID, fm.TYPE, fm."VALUE", fm.DESCRIPTION, fm.MOVEMENT_DATE,
                fm.PAYMENT_STATUS, fm.PAYMENT_METHOD, fm.PAYMENT_GATEWAY_ID,
                fm.TRANSACTION_ID, fm.BANK_ACCOUNT, fm.RECONCILED, fm.RECONCILED_AT
            FROM FINANCIAL_MOVEMENTS fm
        """ + where_clause + """
            ORDER BY fm.MOVEMENT_DATE DESC NULLS LAST, fm.CREATED_AT DESC
        """
        
        cur.execute(movements_sql, params)
        
        movements = []
        for row in cur.fetchall():
            movements.append({
                "id": row[0],
                "type": row[1],
                "value": float(row[2]),
                "description": row[3],
                "movement_date": row[4].isoformat() if row[4] else None,
                "payment_status": row[5],
                "payment_method": row[6],
                "payment_gateway_id": row[7],
                "transaction_id": row[8],
                "bank_account": row[9],
                "reconciled": bool(row[10]) if row[10] is not None else False,
                "reconciled_at": row[11].isoformat() if row[11] else None
            })
        
        return {
            "total_movements": total_movements,
            "reconciled_count": reconciled_count,
            "unreconciled_count": unreconciled_count,
            "reconciled_amount": reconciled_amount,
            "unreconciled_amount": unreconciled_amount,
            "movements": movements
        }
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logger para código de produção
        logger.error(f"Erro ao gerar relatório de conciliação: {e}", exc_info=True)
        return {
            "total_movements": 0,
            "reconciled_count": 0,
            "unreconciled_count": 0,
            "reconciled_amount": 0.0,
            "unreconciled_amount": 0.0,
            "movements": []
        }
    finally:
        if conn:
            conn.close()

