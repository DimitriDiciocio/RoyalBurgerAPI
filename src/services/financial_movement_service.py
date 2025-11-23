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
import hashlib
import json
from datetime import datetime, date, timedelta
from decimal import Decimal
from ..database import get_db_connection
from ..utils.cache_manager import get_cache_manager
from .stock_service import _convert_unit

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


def _invalidate_financial_movements_cache():
    """
    ALTERAÇÃO: Invalida cache de movimentações financeiras e resumo do fluxo de caixa
    """
    try:
        cache = get_cache_manager()
        # ALTERAÇÃO: Limpar todas as chaves de cache de movimentações
        cache.clear_pattern('financial_movements:*')
        # ALTERAÇÃO: Limpar também cache do resumo do fluxo de caixa
        cache.clear_pattern('cash_flow_summary:*')
        logger.debug("Cache de movimentações financeiras e resumo do fluxo de caixa invalidado")
    except Exception as e:
        logger.warning(f"Erro ao invalidar cache de movimentações: {e}")


def _calculate_cost_per_base_portion(price, stock_unit, base_portion_quantity, base_portion_unit):
    """
    Calcula o custo por porção base de um insumo, convertendo corretamente as unidades.
    
    Etapa 1: Converte o preço da unidade de compra (stock_unit) para unidade base (g ou ml)
    Etapa 2: Calcula o custo da porção base multiplicando pelo base_portion_quantity
    
    Exemplos:
    - PRICE = R$ 25,00 por kg, BASE_PORTION_QUANTITY = 30g
      → preço_por_g = R$ 25,00 / 1000 = R$ 0,025 por g
      → custo_por_porcao = R$ 0,025 × 30 = R$ 0,75
    
    - PRICE = R$ 12,00 por L, BASE_PORTION_QUANTITY = 100ml
      → preço_por_ml = R$ 12,00 / 1000 = R$ 0,012 por ml
      → custo_por_porcao = R$ 0,012 × 100 = R$ 1,20
    
    Args:
        price: Preço do insumo na unidade de compra (STOCK_UNIT)
        stock_unit: Unidade de compra do insumo (ex: 'kg', 'g', 'L', 'ml')
        base_portion_quantity: Quantidade da porção base (ex: 30, 100)
        base_portion_unit: Unidade da porção base (ex: 'g', 'ml')
    
    Returns:
        float: Custo por porção base em reais
    """
    try:
        # Se preço é zero, retorna zero
        if not price or price <= 0:
            return 0.0
        
        # Normalizar unidades
        stock_unit = str(stock_unit or 'un').strip().lower()
        base_portion_unit = str(base_portion_unit or 'un').strip().lower()
        base_portion_quantity = float(base_portion_quantity or 1.0)
        
        # Se unidades são iguais ou são 'un', não precisa conversão
        if stock_unit == base_portion_unit or stock_unit == 'un' or base_portion_unit == 'un':
            # Se unidades são iguais, custo por porção = preço × quantidade
            return float(price) * base_portion_quantity
        
        # Converter preço para unidade base (g ou ml)
        # Primeiro, converte 1 unidade de stock_unit para base_portion_unit
        try:
            # Converte 1 unidade de stock_unit para base_portion_unit
            # Exemplo: 1 kg → 1000 g, então 1 g = 1/1000 kg
            conversion_factor = _convert_unit(
                Decimal('1'), 
                from_unit=stock_unit, 
                to_unit=base_portion_unit
            )
            
            # Preço por unidade base = preço / fator_conversao
            # Exemplo: R$ 25,00 por kg → R$ 25,00 / 1000 = R$ 0,025 por g
            price_per_base_unit = float(price) / float(conversion_factor)
            
            # Custo por porção base = preço por unidade base × quantidade da porção
            # Exemplo: R$ 0,025 por g × 30 g = R$ 0,75
            cost_per_base_portion = price_per_base_unit * base_portion_quantity
            
            return cost_per_base_portion
            
        except (ValueError, Exception) as e:
            # Se conversão falhar, logar e usar cálculo direto como fallback
            logger.warning(
                f"Erro ao converter unidades para cálculo de CMV: "
                f"stock_unit={stock_unit}, base_portion_unit={base_portion_unit}, "
                f"erro={e}. Usando cálculo direto como fallback."
            )
            # Fallback: assume que são unidades compatíveis e calcula diretamente
            return float(price) * base_portion_quantity
            
    except Exception as e:
        logger.error(f"Erro ao calcular custo por porção base: {e}")
        return 0.0


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
        
        # ALTERAÇÃO: Log dos dados recebidos para debug
        logger.info(f"create_financial_movement recebeu: {movement_data}")
        
        # Validações
        # ALTERAÇÃO: category agora é opcional (pode ser None ou string vazia)
        required_fields = ['type', 'value', 'description']
        for field in required_fields:
            if not movement_data.get(field):
                return (False, f"INVALID_{field.upper()}", f"Campo {field} é obrigatório")
        
        # ALTERAÇÃO: Validar category separadamente (pode ser None ou vazio)
        category = movement_data.get('category')
        if category is not None and category != '' and not isinstance(category, str):
            return (False, "INVALID_CATEGORY", "Categoria deve ser uma string ou null")
        
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
        
        # ALTERAÇÃO: Converter movement_date para datetime se for string
        # Aceita formatos: DD-MM-YYYY (brasileiro) ou YYYY-MM-DD (ISO) ou ISO com timezone
        if movement_date and isinstance(movement_date, str):
            try:
                # Remover espaços e pegar apenas a parte da data (antes de 'T' se houver)
                date_str = movement_date.strip().split('T')[0].split(' ')[0]
                
                # Detectar formato pelo primeiro segmento
                first_part = date_str.split('-')[0] if '-' in date_str else ''
                
                if len(first_part) == 4:
                    # Formato ISO (YYYY-MM-DD)
                    movement_date = datetime.strptime(date_str, '%Y-%m-%d')
                elif len(first_part) == 2:
                    # Formato brasileiro (DD-MM-YYYY)
                    movement_date = datetime.strptime(date_str, '%d-%m-%Y')
                elif 'T' in movement_date:
                    # ISO com timezone (YYYY-MM-DDTHH:MM:SS)
                    movement_date = datetime.fromisoformat(movement_date.replace('Z', '+00:00'))
                else:
                    # Tentar parse genérico
                    movement_date = datetime.fromisoformat(movement_date.replace('Z', '+00:00'))
            except (ValueError, AttributeError) as e:
                logger.error(f"Erro ao converter data: {movement_date}, erro: {e}")
                return (False, "INVALID_DATE", f"Formato de data inválido: {movement_date}. Use DD-MM-YYYY ou YYYY-MM-DD")
        
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
        
        # ALTERAÇÃO: Tratar category que pode ser None ou string vazia
        category_value = category if category and category.strip() else None
        
        cur.execute(sql, (
            movement_data['type'],
            value,
            category_value,  # ALTERAÇÃO: Pode ser None
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
        
        # ALTERAÇÃO: Invalidar cache após criar movimentação
        _invalidate_financial_movements_cache()
        
        # ALTERAÇÃO: Publicar evento de movimentação criada para atualização em tempo real
        try:
            from ..utils.event_publisher import publish_event
            publish_event('financial_movement.created', {
                'movement_id': movement_id,
                'type': movement_data['type'],
                'value': float(value),
                'payment_status': payment_status,
                'related_entity_type': movement_data.get('related_entity_type'),
                'related_entity_id': movement_data.get('related_entity_id')
            })
        except Exception as e:
            logger.warning(f"Erro ao publicar evento de movimentação criada: {e}")
        
        return (True, None, {
            "id": movement_id,
            "type": movement_data['type'],
            "value": value,
            "category": category_value,  # ALTERAÇÃO: Usar category_value que pode ser None
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
        # ALTERAÇÃO: Log detalhado do erro do banco de dados
        logger.error(f"Erro do banco de dados ao criar movimentação financeira: {e}", exc_info=True)
        if should_close_conn and conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", f"Erro no banco de dados: {str(e)}")
    except Exception as e:
        # ALTERAÇÃO: Capturar outras exceções não tratadas
        logger.error(f"Erro inesperado ao criar movimentação financeira: {e}", exc_info=True)
        if should_close_conn and conn:
            conn.rollback()
        return (False, "INTERNAL_ERROR", f"Erro interno: {str(e)}")
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
        
        # ALTERAÇÃO: Buscar dados do pedido para calcular CMV
        # CORREÇÃO: Separar queries para evitar problemas SQLDA no Firebird
        # Primeiro, buscar itens do pedido com seus IDs
        cur.execute("""
            SELECT 
                oi.ID,
                oi.PRODUCT_ID,
                oi.QUANTITY,
                p.COST_PRICE
            FROM ORDER_ITEMS oi
            JOIN PRODUCTS p ON oi.PRODUCT_ID = p.ID
            WHERE oi.ORDER_ID = ?
        """, (order_id,))
        
        order_items = cur.fetchall()
        if not order_items:
            return (False, None, None, None, "Pedido não encontrado ou sem itens")
        
        # ALTERAÇÃO: Calcular CMV (Custo de Mercadoria Vendida) incluindo extras
        # CORREÇÃO: Usar conversão de unidades para calcular custo correto por porção base
        # CORREÇÃO PERFORMANCE: Buscar todos os extras de uma vez para evitar N+1 queries
        item_ids = [item[0] for item in order_items]
        extras_map = {}  # item_id -> extras_cost
        
        if item_ids:
            try:
                # ALTERAÇÃO: Buscar todos os extras com informações de unidade e porção base
                placeholders = ','.join(['?' for _ in item_ids])
                cur.execute(f"""
                    SELECT 
                        oie.ORDER_ITEM_ID,
                        oie.TYPE,
                        oie.QUANTITY,
                        oie.DELTA,
                        COALESCE(i.PRICE, 0) as PRICE,
                        COALESCE(i.STOCK_UNIT, 'un') as STOCK_UNIT,
                        COALESCE(i.BASE_PORTION_QUANTITY, 1.0) as BASE_PORTION_QUANTITY,
                        COALESCE(i.BASE_PORTION_UNIT, 'un') as BASE_PORTION_UNIT
                    FROM ORDER_ITEM_EXTRAS oie
                    LEFT JOIN INGREDIENTS i ON oie.INGREDIENT_ID = i.ID
                    WHERE oie.ORDER_ITEM_ID IN ({placeholders})
                """, item_ids)
                
                extras_rows = cur.fetchall()
                for row in extras_rows:
                    item_id, extra_type, quantity, delta, price, stock_unit, base_portion_quantity, base_portion_unit = row
                    if item_id not in extras_map:
                        extras_map[item_id] = 0.0
                    
                    # ALTERAÇÃO: Calcular custo por porção base com conversão de unidades
                    cost_per_base_portion = _calculate_cost_per_base_portion(
                        price=float(price or 0),
                        stock_unit=str(stock_unit or 'un'),
                        base_portion_quantity=float(base_portion_quantity or 1.0),
                        base_portion_unit=str(base_portion_unit or 'un')
                    )
                    
                    # Calcular custo do extra ou modificação
                    if extra_type == 'extra' and quantity:
                        extras_map[item_id] += float(quantity or 0) * cost_per_base_portion
                    elif extra_type == 'base' and delta and delta > 0:
                        extras_map[item_id] += float(delta) * cost_per_base_portion
            except Exception as e:
                # ALTERAÇÃO: Se houver erro, logar e continuar sem extras
                logger.warning(f"Erro ao calcular custo de extras para pedido {order_id}: {e}")
        
        total_cmv = 0.0
        for item in order_items:
            item_id, product_id, quantity, product_cost = item
            
            # Custo do produto
            product_cost_float = float(product_cost or 0)
            if product_cost_float <= 0:
                # Se não tem COST_PRICE, calcular pelos ingredientes
                cur.execute("""
                    SELECT COALESCE(SUM(pi.PORTIONS * ing.PRICE), 0)
                    FROM PRODUCT_INGREDIENTS pi
                    JOIN INGREDIENTS ing ON pi.INGREDIENT_ID = ing.ID
                    WHERE pi.PRODUCT_ID = ?
                """, (product_id,))
                cost_result = cur.fetchone()
                product_cost_float = float(cost_result[0] or 0) if cost_result and cost_result[0] is not None else 0.0
            
            # ALTERAÇÃO: Obter custo de extras do mapa (já calculado acima)
            extras_cost = extras_map.get(item_id, 0.0)
            
            # Custo total do item = (custo produto × quantidade) + custo extras
            total_cmv += (product_cost_float * quantity) + extras_cost
        
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
            except (ValueError, AttributeError) as e:
                # ALTERAÇÃO: Especificar exceções ao invés de bare except
                logger.warning(f"Erro ao parsear payment_date: {e}. Usando data atual.")
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
    Busca movimentações financeiras com filtros e paginação
    ALTERAÇÃO: Adicionado suporte a paginação e cache em memória para melhorar performance
    
    Args:
        filters: dict com:
            - start_date: datetime/str
            - end_date: datetime/str
            - type: 'REVENUE', 'EXPENSE', 'CMV', 'TAX'
            - category: str
            - payment_status: 'Pending', 'Paid'
            - related_entity_type: str
            - related_entity_id: int
            - page: int (opcional, default: 1) - Número da página
            - page_size: int (opcional, default: 100) - Itens por página
    
    Returns:
        dict com:
            - items: list de movimentações
            - total: int - Total de registros
            - page: int - Página atual
            - page_size: int - Itens por página
            - total_pages: int - Total de páginas
    """
    # ALTERAÇÃO: Implementar cache em memória para queries frequentes
    cache = get_cache_manager()
    
    # Construir chave de cache baseada nos filtros
    filters_normalized = filters or {}
    # Normalizar filtros para criar chave consistente
    cache_key_parts = ['financial_movements']
    if filters_normalized:
        # Ordenar filtros para garantir chave consistente
        sorted_filters = sorted(filters_normalized.items())
        filters_str = json.dumps(sorted_filters, default=str, sort_keys=True)
        filters_hash = hashlib.md5(filters_str.encode()).hexdigest()
        cache_key_parts.append(filters_hash)
    cache_key = ':'.join(cache_key_parts)
    
    # ALTERAÇÃO: Tentar obter do cache (TTL de 60 segundos para dados financeiros)
    # Cache mais curto para garantir dados atualizados
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        logger.debug(f"Cache hit para movimentações financeiras: {cache_key}")
        return cached_result
    
    logger.debug(f"Cache miss para movimentações financeiras: {cache_key}")
    
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
                    except (ValueError, AttributeError):
                        # ALTERAÇÃO: Especificar exceções ao invés de bare except
                        # Se não conseguir parsear, manter como string e deixar o SQL tratar
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
                    except (ValueError, AttributeError):
                        # ALTERAÇÃO: Especificar exceções ao invés de bare except
                        # Se não conseguir parsear, manter como string e deixar o SQL tratar
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
                # ALTERAÇÃO: Comparar diretamente com BOOLEAN (Firebird aceita TRUE/FALSE diretamente)
                conditions.append("fm.RECONCILED = ?")
                params.append(bool(filters['reconciled']))
        
        # ALTERAÇÃO: Adicionar paginação
        page = filters.get('page', 1) if filters else 1
        page_size = filters.get('page_size', 100) if filters else 100
        
        # Validar e limitar page_size (máximo 1000 para evitar sobrecarga)
        try:
            page = int(page)
            page_size = int(page_size)
            if page < 1:
                page = 1
            if page_size < 1:
                page_size = 100
            if page_size > 1000:
                page_size = 1000
        except (ValueError, TypeError):
            page = 1
            page_size = 100
        
        # Calcular offset
        offset = (page - 1) * page_size
        
        # ALTERAÇÃO: Contar total de registros antes de aplicar paginação
        count_sql = "SELECT COUNT(*) FROM FINANCIAL_MOVEMENTS fm"
        if conditions:
            count_sql += " WHERE " + " AND ".join(conditions)
        
        cur.execute(count_sql, params)
        total_count = cur.fetchone()[0] or 0
        
        # ALTERAÇÃO: No Firebird, FIRST/SKIP deve vir logo após SELECT, não depois de ORDER BY
        # Reconstruir a query com FIRST/SKIP no lugar correto
        fields_clause = """
                fm.ID, fm.TYPE, fm."VALUE", fm.CATEGORY, fm.SUBCATEGORY,
                fm.DESCRIPTION, fm.MOVEMENT_DATE, fm.PAYMENT_STATUS,
                fm.PAYMENT_METHOD, fm.SENDER_RECEIVER,
                fm.RELATED_ENTITY_TYPE, fm.RELATED_ENTITY_ID,
                fm.NOTES, fm.CREATED_AT, fm.UPDATED_AT,
                fm.PAYMENT_GATEWAY_ID, fm.TRANSACTION_ID, fm.BANK_ACCOUNT,
                fm.RECONCILED, fm.RECONCILED_AT,
                u.FULL_NAME as created_by_name
        """
        
        # ALTERAÇÃO: Adicionar FIRST/SKIP logo após SELECT (sintaxe correta do Firebird)
        # CORREÇÃO SEGURANÇA: page_size e offset são validados e convertidos para int acima
        # Firebird não suporta parametrização de FIRST/SKIP, então f-string é necessário
        # Garantir que são inteiros para evitar SQL injection
        page_size = int(page_size)
        offset = int(offset)
        if offset > 0:
            select_clause = f"SELECT FIRST {page_size} SKIP {offset}"
        else:
            select_clause = f"SELECT FIRST {page_size}"
        
        from_clause = """
            FROM FINANCIAL_MOVEMENTS fm
            LEFT JOIN USERS u ON fm.CREATED_BY = u.ID
        """
        
        # Construir query completa
        base_sql = select_clause + fields_clause + from_clause
        
        # Aplicar condições
        if conditions:
            base_sql += " WHERE " + " AND ".join(conditions)
        
        # Adicionar ORDER BY
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
        
        # ALTERAÇÃO: Calcular total de páginas
        total_pages = (total_count + page_size - 1) // page_size if page_size > 0 else 0
        
        # ALTERAÇÃO: Retornar objeto com paginação
        result = {
            "items": movements,
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
        
        # ALTERAÇÃO: Cachear resultado (TTL de 60 segundos)
        cache.set(cache_key, result, ttl=60)
        
        return result
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logger para código de produção
        logger.error(f"Erro ao buscar movimentações financeiras: {e}", exc_info=True)
        # ALTERAÇÃO: Retornar estrutura de paginação mesmo em caso de erro
        return {
            "items": [],
            "total": 0,
            "page": 1,
            "page_size": 100,
            "total_pages": 0
        }
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
            # ALTERAÇÃO: Tratar category que pode ser None ou string vazia
            category_value = movement_data['category']
            if category_value is not None and category_value != '':
                category_value = category_value.strip() if isinstance(category_value, str) else category_value
                if not category_value:
                    category_value = None
            else:
                category_value = None
            update_fields.append("CATEGORY = ?")
            params.append(category_value)
        
        if 'subcategory' in movement_data:
            update_fields.append("SUBCATEGORY = ?")
            params.append(movement_data['subcategory'])
        
        if 'description' in movement_data:
            update_fields.append("DESCRIPTION = ?")
            params.append(movement_data['description'])
        
        if 'movement_date' in movement_data:
            movement_date = movement_data['movement_date']
            # ALTERAÇÃO: Aceitar formatos: DD-MM-YYYY (brasileiro) ou YYYY-MM-DD (ISO) ou ISO com timezone
            if isinstance(movement_date, str):
                try:
                    # Remover espaços e pegar apenas a parte da data (antes de 'T' se houver)
                    date_str = movement_date.strip().split('T')[0].split(' ')[0]
                    
                    # Detectar formato pelo primeiro segmento
                    first_part = date_str.split('-')[0] if '-' in date_str else ''
                    
                    if len(first_part) == 4:
                        # Formato ISO (YYYY-MM-DD)
                        movement_date = datetime.strptime(date_str, '%Y-%m-%d')
                    elif len(first_part) == 2:
                        # Formato brasileiro (DD-MM-YYYY)
                        movement_date = datetime.strptime(date_str, '%d-%m-%Y')
                    elif 'T' in movement_date:
                        # ISO com timezone (YYYY-MM-DDTHH:MM:SS)
                        movement_date = datetime.fromisoformat(movement_date.replace('Z', '+00:00'))
                    else:
                        # Tentar parse genérico
                        movement_date = datetime.fromisoformat(movement_date.replace('Z', '+00:00'))
                except (ValueError, AttributeError) as e:
                    logger.error(f"Erro ao converter data na atualização: {movement_date}, erro: {e}")
                    return (False, "INVALID_DATE", f"Formato de data inválido: {movement_date}. Use DD-MM-YYYY ou YYYY-MM-DD")
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
        
        # ALTERAÇÃO: Adicionar UPDATED_AT (UPDATED_BY não existe na tabela)
        update_fields.append("UPDATED_AT = CURRENT_TIMESTAMP")
        
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
        
        # ALTERAÇÃO: Invalidar cache após atualizar movimentação
        _invalidate_financial_movements_cache()
        
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
    ALTERAÇÃO: Adicionado cache em memória para melhorar performance
    
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
    # ALTERAÇÃO: Implementar cache em memória para queries frequentes de resumo
    cache = get_cache_manager()
    
    # Construir chave de cache baseada nos parâmetros
    cache_key = f"cash_flow_summary:{period}:{include_pending}"
    
    # ALTERAÇÃO: Tentar obter do cache (TTL de 60 segundos para dados financeiros)
    # Cache mais curto para garantir dados atualizados
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        logger.debug(f"Cache hit para resumo do fluxo de caixa: {cache_key}")
        return cached_result
    
    logger.debug(f"Cache miss para resumo do fluxo de caixa: {cache_key}")
    
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
        # ALTERAÇÃO: Usar alias de tabela e CAST explícito para evitar erro -804 e -104
        # Firebird precisa de alias e tipo explícito para funções agregadas
        sql = f"""
            SELECT 
                fm.TYPE,
                CAST(COALESCE(SUM(fm."VALUE"), 0) AS DECIMAL(15,2)) AS TOTAL
            FROM FINANCIAL_MOVEMENTS fm
            WHERE fm.PAYMENT_STATUS = 'Paid'
            AND fm.MOVEMENT_DATE IS NOT NULL
            AND ({date_filter})
            GROUP BY fm.TYPE
        """
        
        # ALTERAÇÃO: Tratamento robusto para evitar erro -804 (SQLDA inconsistente)
        try:
            cur.execute(sql)
            # ALTERAÇÃO: Verificar se a query foi executada antes de fazer fetchall()
            results = cur.fetchall()
        except fdb.Error as db_err:
            logger.error(
                f"Erro ao executar query de resumo do fluxo de caixa: {db_err}. "
                f"SQL: {sql}"
            )
            # ALTERAÇÃO: Retornar valores zerados em caso de erro
            results = []
        
        totals = {
            TYPE_REVENUE: 0.0,
            TYPE_EXPENSE: 0.0,
            TYPE_CMV: 0.0,
            TYPE_TAX: 0.0
        }
        
        # ALTERAÇÃO: Tratamento robusto para processar resultados
        for row in results:
            try:
                # ALTERAÇÃO: Validar que a linha tem pelo menos 2 colunas
                if row is not None and len(row) >= 2:
                    movement_type = row[0]
                    total_value = row[1]
                    
                    # ALTERAÇÃO: Validar tipos antes de converter
                    if movement_type and total_value is not None:
                        try:
                            total_float = float(total_value)
                            if movement_type in totals:
                                totals[movement_type] = total_float
                            else:
                                logger.warning(
                                    f"Tipo de movimentação desconhecido no resumo: {movement_type}"
                                )
                        except (ValueError, TypeError) as e:
                            logger.warning(
                                f"Erro ao converter total para float: {total_value}. "
                                f"Erro: {e}. Linha: {row}"
                            )
                    else:
                        logger.warning(f"Valores None na linha do resumo: {row}")
                else:
                    logger.warning(f"Linha inválida no resumo (menos de 2 colunas): {row}")
            except Exception as e:
                logger.error(
                    f"Erro ao processar linha do resumo do fluxo de caixa: {e}. "
                    f"Linha: {row}"
                )
                # ALTERAÇÃO: Continuar processamento mesmo se uma linha falhar
                continue
        
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
            
            # ALTERAÇÃO: Usar alias de tabela e CAST explícito para evitar erro -804 e -104
            try:
                cur.execute(f"""
                    SELECT 
                        fm.TYPE,
                        CAST(COALESCE(SUM(fm."VALUE"), 0) AS DECIMAL(15,2)) AS TOTAL
                    FROM FINANCIAL_MOVEMENTS fm
                    WHERE fm.PAYMENT_STATUS = 'Pending'
                    AND ({pending_filter})
                    GROUP BY fm.TYPE
                """)
                
                pending_results = cur.fetchall()
            except fdb.Error as db_err:
                logger.error(
                    f"Erro ao executar query de pendentes no resumo do fluxo de caixa: {db_err}"
                )
                pending_results = []
            
            pending_amount = 0.0
            # ALTERAÇÃO: Tratamento robusto para processar resultados de pendentes
            for row in pending_results:
                try:
                    if row is not None and len(row) >= 2:
                        movement_type = row[0]
                        total_value = row[1]
                        
                        if movement_type and total_value is not None:
                            try:
                                total_float = float(total_value)
                                if movement_type in [TYPE_EXPENSE, TYPE_TAX]:
                                    pending_amount += total_float
                            except (ValueError, TypeError) as e:
                                logger.warning(
                                    f"Erro ao converter total pendente para float: {total_value}. "
                                    f"Erro: {e}. Linha: {row}"
                                )
                except Exception as e:
                    logger.error(
                        f"Erro ao processar linha de pendentes: {e}. Linha: {row}"
                    )
                    continue
            
            result["pending_amount"] = pending_amount
        
        # ALTERAÇÃO: Cachear resultado (TTL de 60 segundos)
        cache.set(cache_key, result, ttl=60)
        
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
    Se a movimentação estiver vinculada a uma compra (purchase_invoice),
    também atualiza o status da compra para manter consistência.
    
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
                except (ValueError, AttributeError) as e:
                    # ALTERAÇÃO: Especificar exceções ao invés de bare except
                    logger.warning(f"Erro ao parsear movement_date: {e}. Usando data atual.")
                    movement_date = datetime.now()
            elif isinstance(movement_date, date) and not isinstance(movement_date, datetime):
                movement_date = datetime.combine(movement_date, datetime.min.time())
        else:
            # Se marcando como Pending, limpar movement_date
            movement_date = None
        
        # ALTERAÇÃO: Buscar informações da movimentação para verificar se está vinculada a uma compra
        cur.execute("""
            SELECT RELATED_ENTITY_TYPE, RELATED_ENTITY_ID
            FROM FINANCIAL_MOVEMENTS
            WHERE ID = ?
        """, (movement_id,))
        movement_info = cur.fetchone()
        
        related_entity_type = None
        related_entity_id = None
        if movement_info:
            related_entity_type = movement_info[0]
            related_entity_id = movement_info[1]
        
        # ALTERAÇÃO: Atualizar movimentação financeira
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
        
        # ALTERAÇÃO: Se a movimentação está vinculada a uma compra, sincronizar o status
        purchase_updated = False
        if related_entity_type and related_entity_id:
            # Verificar se é uma compra (purchase_invoice ou variações)
            normalized_entity_type = (related_entity_type or '').lower()
            if normalized_entity_type in ['purchase_invoice', 'purchaseinvoice', 'purchase', 'compra', 'invoice']:
                try:
                    # Verificar se a compra existe e buscar payment_date em uma única query
                    cur.execute("""
                        SELECT ID, PAYMENT_STATUS, PAYMENT_DATE FROM PURCHASE_INVOICES WHERE ID = ?
                    """, (related_entity_id,))
                    purchase_row = cur.fetchone()
                    
                    if not purchase_row:
                        logger.warning(f"Compra {related_entity_id} não encontrada para sincronização com movimentação {movement_id}")
                    else:
                        # Atualizar status da compra
                        update_purchase_sql = """
                            UPDATE PURCHASE_INVOICES
                            SET PAYMENT_STATUS = ?,
                                UPDATED_AT = CURRENT_TIMESTAMP
                        """
                        update_purchase_params = [payment_status]
                        
                        # Se marcando como Paid, atualizar payment_date se não existir
                        if payment_status == STATUS_PAID:
                            current_payment_date = purchase_row[2]  # PAYMENT_DATE é o terceiro campo
                            if not current_payment_date:
                                # Não tem payment_date, adicionar
                                update_purchase_sql += ", PAYMENT_DATE = ?"
                                update_purchase_params.append(movement_date if movement_date else datetime.now())
                        
                        update_purchase_sql += " WHERE ID = ?"
                        update_purchase_params.append(related_entity_id)
                        
                        cur.execute(update_purchase_sql, update_purchase_params)
                        
                        # Verificar se a compra foi atualizada
                        if cur.rowcount > 0:
                            purchase_updated = True
                            logger.info(f"Status da compra {related_entity_id} sincronizado com movimentação {movement_id}: {payment_status}")
                        else:
                            logger.warning(f"Falha ao atualizar compra {related_entity_id} (nenhuma linha afetada)")
                            
                except fdb.Error as e:
                    logger.error(f"Erro de banco ao sincronizar status da compra {related_entity_id}: {e}", exc_info=True)
                    # Fazer rollback para manter consistência
                    conn.rollback()
                    return (False, "SYNC_ERROR", f"Erro ao sincronizar status da compra: {str(e)}")
                except Exception as e:
                    logger.error(f"Erro inesperado ao sincronizar status da compra {related_entity_id}: {e}", exc_info=True)
                    # Fazer rollback para manter consistência
                    conn.rollback()
                    return (False, "SYNC_ERROR", f"Erro ao sincronizar status da compra: {str(e)}")
        
        # Commit da transação (ambas as atualizações ou nenhuma)
        conn.commit()
        
        # ALTERAÇÃO: Invalidar cache após atualizar status
        _invalidate_financial_movements_cache()
        
        # ALTERAÇÃO: Publicar evento de status de pagamento atualizado
        try:
            from ..utils.event_publisher import publish_event
            publish_event('financial_movement.payment_status_updated', {
                'movement_id': movement_id,
                'payment_status': payment_status,
                'related_entity_type': related_entity_type,
                'related_entity_id': related_entity_id,
                'purchase_updated': purchase_updated
            })
        except Exception as e:
            logger.warning(f"Erro ao publicar evento de status atualizado: {e}")
        
        result = {
            "id": row[0],
            "type": row[1],
            "value": float(row[2]),
            "description": row[3],
            "payment_status": payment_status,
            "movement_date": movement_date.isoformat() if movement_date else None
        }
        
        # ALTERAÇÃO: Incluir informação sobre sincronização da compra
        if purchase_updated:
            result["purchase_synced"] = True
            result["purchase_id"] = related_entity_id
        
        return (True, None, result)
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logger para código de produção
        logger.error(f"Erro ao atualizar status de pagamento da movimentação {movement_id}: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()


def delete_financial_movement(movement_id, deleted_by_user_id=None):
    """
    ALTERAÇÃO: Exclui uma movimentação financeira
    ALTERAÇÃO: Se a movimentação estiver relacionada a uma compra, também exclui a compra
    
    Args:
        movement_id: ID da movimentação
        deleted_by_user_id: ID do usuário que está excluindo (opcional, necessário para exclusão de compra)
    
    Returns:
        (success: bool, error_code: str, result: dict/str)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verificar se existe e obter informações sobre entidade relacionada
        cur.execute("""
            SELECT ID, RELATED_ENTITY_TYPE, RELATED_ENTITY_ID 
            FROM FINANCIAL_MOVEMENTS 
            WHERE ID = ?
        """, (movement_id,))
        row = cur.fetchone()
        if not row:
            return (False, "NOT_FOUND", "Movimentação não encontrada")
        
        related_entity_type = row[1] if len(row) > 1 else None
        related_entity_id = row[2] if len(row) > 2 else None
        
        # ALTERAÇÃO: Se a movimentação está relacionada a uma compra, excluir a compra também
        if related_entity_type and related_entity_id:
            # Normalizar tipo de entidade
            normalized_type = (related_entity_type or '').lower().strip()
            purchase_types = ['purchase_invoice', 'purchaseinvoice', 'purchase', 'compra', 'invoice']
            
            if normalized_type in purchase_types or 'purchase' in normalized_type:
                # É uma compra - excluir a compra primeiro (que vai excluir a movimentação também)
                try:
                    from . import purchase_service
                    # Se deleted_by_user_id não foi fornecido, tentar obter do contexto atual
                    if deleted_by_user_id is None:
                        # TODO: REVISAR obter user_id do contexto JWT se disponível
                        # Por enquanto, usar None e deixar o purchase_service validar
                        deleted_by_user_id = None
                    
                    # ALTERAÇÃO: Fechar conexão atual antes de chamar purchase_service
                    # para evitar conflitos de transação
                    if conn:
                        conn.close()
                        conn = None
                    
                    # Excluir a compra (isso vai excluir a movimentação financeira automaticamente)
                    success, error_code, result = purchase_service.delete_purchase_invoice(
                        related_entity_id, 
                        deleted_by_user_id
                    )
                    
                    if success:
                        logger.info(
                            f"Movimentação {movement_id} e compra relacionada {related_entity_id} "
                            f"excluídas com sucesso"
                        )
                        # ALTERAÇÃO: Invalidar cache após excluir movimentação
                        _invalidate_financial_movements_cache()
                        return (
                            True, 
                            None, 
                            "Movimentação e compra relacionada excluídas com sucesso"
                        )
                    else:
                        # ALTERAÇÃO: Se falhou ao excluir a compra, não excluir apenas a movimentação
                        # Retornar erro para manter integridade referencial
                        logger.warning(
                            f"Falha ao excluir compra {related_entity_id} relacionada à movimentação {movement_id}: "
                            f"{error_code} - {result}"
                        )
                        return (False, error_code, f"Erro ao excluir compra relacionada: {result}")
                        
                except ImportError:
                    logger.error("Não foi possível importar purchase_service para exclusão em cascata")
                    # ALTERAÇÃO: Se não conseguir importar, não excluir apenas a movimentação
                    # para manter integridade referencial
                    return (False, "IMPORT_ERROR", "Não é possível excluir movimentação relacionada a compra sem o serviço de compras")
                except Exception as e:
                    logger.error(
                        f"Erro ao excluir compra relacionada à movimentação {movement_id}: {e}",
                        exc_info=True
                    )
                    # ALTERAÇÃO: Se houver erro, não excluir apenas a movimentação
                    # para manter integridade referencial
                    return (False, "CASCADE_DELETE_ERROR", f"Erro ao excluir compra relacionada: {str(e)}")
        
        # ALTERAÇÃO: Se não é uma compra, excluir apenas a movimentação
        # Se conn foi fechada acima, recriar
        if not conn:
            conn = get_db_connection()
            cur = conn.cursor()
        
        cur.execute("DELETE FROM FINANCIAL_MOVEMENTS WHERE ID = ?", (movement_id,))
        conn.commit()
        
        logger.info(f"Movimentação {movement_id} excluída com sucesso")
        
        # ALTERAÇÃO: Invalidar cache após excluir movimentação
        _invalidate_financial_movements_cache()
        
        return (True, None, "Movimentação excluída com sucesso")
        
    except fdb.Error as e:
        logger.error(f"Erro ao excluir movimentação {movement_id}: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", f"Erro no banco de dados: {str(e)}")
    except Exception as e:
        logger.error(f"Erro inesperado ao excluir movimentação {movement_id}: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "INTERNAL_ERROR", f"Erro interno: {str(e)}")
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
                except (ValueError, AttributeError):
                    # ALTERAÇÃO: Especificar exceções ao invés de bare except
                    # Se não conseguir parsear, manter como string e deixar o SQL tratar
                    pass
            if isinstance(start_date, date) and not isinstance(start_date, datetime):
                start_date = datetime.combine(start_date, datetime.min.time())
            conditions.append("fm.MOVEMENT_DATE >= ?")
            params.append(start_date)
        
        if end_date:
            if isinstance(end_date, str):
                try:
                    end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    # ALTERAÇÃO: Especificar exceções ao invés de bare except
                    # Se não conseguir parsear, manter como string e deixar o SQL tratar
                    pass
            if isinstance(end_date, date) and not isinstance(end_date, datetime):
                end_date = datetime.combine(end_date, datetime.min.time())
            end_date = end_date + timedelta(days=1)
            conditions.append("fm.MOVEMENT_DATE < ?")
            params.append(end_date)
        
        if reconciled is not None:
            # ALTERAÇÃO: Comparar diretamente com BOOLEAN (Firebird aceita TRUE/FALSE diretamente)
            conditions.append("fm.RECONCILED = ?")
            params.append(bool(reconciled))
        
        if payment_gateway_id:
            conditions.append("fm.PAYMENT_GATEWAY_ID = ?")
            params.append(payment_gateway_id)
        
        # Adicionar filtro para apenas movimentações pagas (relevantes para conciliação)
        conditions.append("fm.PAYMENT_STATUS = 'Paid'")
        
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        
        # ALTERAÇÃO: Buscar estatísticas com CAST para garantir compatibilidade de tipos
        # ALTERAÇÃO: Usar CASE WHEN para converter BOOLEAN para comparação numérica (Firebird não permite CAST direto de BOOLEAN)
        stats_sql = """
            SELECT 
                CAST(COUNT(*) AS INTEGER) as total,
                CAST(SUM(CASE WHEN fm.RECONCILED = TRUE THEN 1 ELSE 0 END) AS INTEGER) as reconciled_count,
                CAST(SUM(CASE WHEN fm.RECONCILED IS NULL OR fm.RECONCILED = FALSE THEN 1 ELSE 0 END) AS INTEGER) as unreconciled_count,
                CAST(SUM(CASE WHEN fm.RECONCILED = TRUE THEN CAST(fm."VALUE" AS DECIMAL(15,2)) ELSE 0 END) AS DECIMAL(15,2)) as reconciled_amount,
                CAST(SUM(CASE WHEN fm.RECONCILED IS NULL OR fm.RECONCILED = FALSE THEN CAST(fm."VALUE" AS DECIMAL(15,2)) ELSE 0 END) AS DECIMAL(15,2)) as unreconciled_amount
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

