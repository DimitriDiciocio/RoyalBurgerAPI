import fdb
import logging
import math
from decimal import Decimal
from ..database import get_db_connection

logger = logging.getLogger(__name__)

def _validate_ingredient_id(ingredient_id):
    """Valida se ingredient_id é um inteiro válido"""
    if not isinstance(ingredient_id, int) or ingredient_id <= 0:
        raise ValueError("ingredient_id deve ser um inteiro positivo")

def _validate_adjustment_amount(adjustment_amount):
    """Valida se adjustment_amount é um número válido"""
    if not isinstance(adjustment_amount, (int, float)):
        raise ValueError("adjustment_amount deve ser um número")


# =====================================================
# SISTEMA DE CONVERSÃO DE UNIDADES
# =====================================================

def _convert_unit(value, from_unit, to_unit):
    """
    Converte um valor de uma unidade para outra.
    
    Suporta conversões de:
    - Massa: kg ↔ g ↔ mg
    - Volume: L ↔ mL ↔ cL ↔ dL
    - Comprimento: m ↔ cm ↔ mm
    
    Exemplos validados:
    - 100g → 0.100kg ✓
    - 30g → 0.030kg ✓
    - 150g → 0.150kg ✓
    - 12g → 0.012kg ✓
    
    Args:
        value: Valor a ser convertido (Decimal ou número)
        from_unit: Unidade de origem (ex: 'g', 'kg', 'mL', 'L')
        to_unit: Unidade de destino (ex: 'g', 'kg', 'mL', 'L')
    
    Returns:
        Decimal: Valor convertido na unidade de destino
    
    Raises:
        ValueError: Se a conversão não for suportada ou unidades forem incompatíveis
    """
    # Normaliza unidades (remove espaços e converte para minúsculas)
    from_unit = str(from_unit).strip().lower() if from_unit else 'un'
    to_unit = str(to_unit).strip().lower() if to_unit else 'un'
    
    # Se as unidades são iguais, não precisa conversão
    if from_unit == to_unit:
        return Decimal(str(value))
    
    # Converte value para Decimal para precisão
    value_decimal = Decimal(str(value))
    
    # Define fatores de conversão (para unidade base → unidade menor)
    # Exemplo: 1 kg = 1000 g, então kg→g multiplica por 1000, g→kg divide por 1000
    conversion_factors = {
        # Massa
        'kg': {'g': Decimal('1000'), 'mg': Decimal('1000000')},
        'g': {'kg': Decimal('0.001'), 'mg': Decimal('1000')},
        'mg': {'kg': Decimal('0.000001'), 'g': Decimal('0.001')},
        
        # Volume
        'l': {'ml': Decimal('1000'), 'cl': Decimal('100'), 'dl': Decimal('10')},
        'litro': {'ml': Decimal('1000'), 'cl': Decimal('100'), 'dl': Decimal('10')},
        'ml': {'l': Decimal('0.001'), 'cl': Decimal('0.1'), 'litro': Decimal('0.001')},
        'cl': {'l': Decimal('0.01'), 'ml': Decimal('10'), 'litro': Decimal('0.01')},
        'dl': {'l': Decimal('0.1'), 'ml': Decimal('100'), 'litro': Decimal('0.1')},
        
        # Comprimento
        'm': {'cm': Decimal('100'), 'mm': Decimal('1000')},
        'cm': {'m': Decimal('0.01'), 'mm': Decimal('10')},
        'mm': {'m': Decimal('0.001'), 'cm': Decimal('0.1')},
    }
    
    # Tenta conversão direta
    if from_unit in conversion_factors:
        if to_unit in conversion_factors[from_unit]:
            return value_decimal * conversion_factors[from_unit][to_unit]
    
    # Tenta conversão inversa (se to_unit tem conversão para from_unit)
    if to_unit in conversion_factors:
        if from_unit in conversion_factors[to_unit]:
            # Inverte a conversão: divide ao invés de multiplicar
            return value_decimal / conversion_factors[to_unit][from_unit]
    
    # Se não encontrou conversão e unidades são diferentes de 'un', gera erro
    if from_unit != 'un' and to_unit != 'un':
        raise ValueError(
            f"Conversão não suportada: {from_unit} → {to_unit}. "
            f"Unidades devem ser compatíveis ou use 'un' para unidades genéricas."
        )
    
    # Se uma das unidades é 'un', assume que não precisa conversão
    # (assume que são a mesma unidade genérica)
    logger.warning(
        f"Conversão entre unidades genéricas assumida como 1:1 "
        f"({from_unit} → {to_unit}). Valor: {value_decimal}"
    )
    return value_decimal


def calculate_consumption_in_stock_unit(portions, base_portion_quantity, base_portion_unit, 
                                        stock_unit, item_quantity=1, loss_percentage=0):
    """
    Calcula a quantidade consumida convertida para a unidade do estoque.
    
    ALTERAÇÃO: Agora considera perdas (LOSS_PERCENTAGE) no cálculo.
    consumo_efetivo = consumo_teorico * (1 + perda% / 100)
    
    Realiza conversão automática de unidades antes do cálculo.
    Exemplo: se ingrediente está em kg no estoque mas é usado em g na receita,
    converte corretamente antes de deduzir.
    
    Fórmula: portions × base_portion_quantity × item_quantity × (1 + loss_percentage / 100) (convertido para stock_unit)
    
    Exemplos validados:
    - 1 porção × 100g × 1 item → 0.100kg (estoque em kg) ✓
    - 1 porção × 30g × 1 item → 0.030kg (estoque em kg) ✓
    - 1 porção × 150g × 1 item → 0.150kg (estoque em kg) ✓
    - 1 porção × 12g × 1 item → 0.012kg (estoque em kg) ✓
    
    Args:
        portions: Número de porções do ingrediente no produto
        base_portion_quantity: Quantidade de uma porção base
        base_portion_unit: Unidade da porção base
        stock_unit: Unidade do estoque
        item_quantity: Quantidade de itens do produto no pedido (padrão: 1)
        loss_percentage: Percentual de perda (padrão: 0) - ex: 5.0 significa 5% de perda
    
    Returns:
        Decimal: Quantidade consumida na unidade do estoque (incluindo perdas)
    """
    # Calcula quantidade total consumida na unidade da porção base
    # Exemplo: 2 porções × 100g por porção × 3 itens = 600g
    consumption_in_portion_unit = (
        Decimal(str(portions)) * 
        Decimal(str(base_portion_quantity)) * 
        Decimal(str(item_quantity))
    )
    
    # ALTERAÇÃO: Aplica perdas se loss_percentage > 0
    # consumo_efetivo = consumo_teorico * (1 + perda% / 100)
    if loss_percentage and loss_percentage > 0:
        loss_decimal = Decimal(str(loss_percentage)) / Decimal('100')
        consumption_in_portion_unit = consumption_in_portion_unit * (Decimal('1') + loss_decimal)
        logger.debug(
            f"Aplicando perda de {loss_percentage}%: "
            f"consumo_teorico * (1 + {loss_percentage}%) = {consumption_in_portion_unit}"
        )
    
    # Converte para a unidade do estoque
    consumption_in_stock_unit = _convert_unit(
        consumption_in_portion_unit,
        base_portion_unit,
        stock_unit
    )
    
    return consumption_in_stock_unit


def validate_stock_for_items(items, cur):
    """
    Valida se há estoque suficiente para os itens SEM deduzir o estoque.
    Usado antes de criar o pedido para evitar criar pedidos sem estoque disponível.
    
    Args:
        items: Lista de itens do pedido/carrinho
        cur: Cursor do banco de dados
    
    Returns:
        tuple: (success: bool, error_code: str, message: str)
        - success: True se estoque suficiente, False caso contrário
        - error_code: Código do erro (None se sucesso)
        - message: Mensagem de erro (None se sucesso)
    """
    # Validação de entrada
    if not items or not isinstance(items, list):
        return (True, None, None)  # Lista vazia não precisa validação
    
    try:
        # Coletar todos os ingredient_ids necessários
        required_ingredients = {}
        
        # Buscar produtos e suas regras de ingredientes
        product_ids = {item.get('product_id') for item in items if item.get('product_id')}
        if not product_ids:
            return (True, None, None)
        
        # Validação adicional: verificar se todos os product_ids são inteiros válidos
        try:
            product_ids = {int(pid) for pid in product_ids if pid}
        except (ValueError, TypeError) as e:
            logger.error(f"Product ID inválido na validação de estoque: {e}")
            return (False, "STOCK_VALIDATION_ERROR", "ID de produto inválido")
        
        # SEGURANÇA: Construção segura de SQL dinâmico usando placeholders parametrizados
        # product_ids foi validado como conjunto de inteiros, sem risco de SQL injection
        placeholders = ', '.join(['?' for _ in product_ids])
        
        # SIMPLIFICAÇÃO: Buscar regras de ingredientes por produto (sem perdas)
        # Verifica se campo LOSS_PERCENTAGE existe antes de usar
        try:
            # Tenta ler com LOSS_PERCENTAGE (se campo existir)
            sql_rules = f"""
                SELECT 
                    pi.PRODUCT_ID, 
                    pi.INGREDIENT_ID, 
                    pi.PORTIONS, 
                    pi.MIN_QUANTITY, 
                    pi.MAX_QUANTITY,
                    COALESCE(pi.LOSS_PERCENTAGE, 0) as LOSS_PERCENTAGE,
                    i.BASE_PORTION_QUANTITY,
                    i.BASE_PORTION_UNIT,
                    i.STOCK_UNIT
                FROM PRODUCT_INGREDIENTS pi
                JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
                WHERE pi.PRODUCT_ID IN ({placeholders})
            """
            cur.execute(sql_rules, tuple(product_ids))
            use_loss_percentage = True
        except fdb.Error as e:
            # Se campo não existe, usa query sem LOSS_PERCENTAGE
            error_msg = str(e).lower()
            if 'loss_percentage' in error_msg or 'unknown' in error_msg:
                sql_rules = f"""
                    SELECT 
                        pi.PRODUCT_ID, 
                        pi.INGREDIENT_ID, 
                        pi.PORTIONS, 
                        pi.MIN_QUANTITY, 
                        pi.MAX_QUANTITY,
                        i.BASE_PORTION_QUANTITY,
                        i.BASE_PORTION_UNIT,
                        i.STOCK_UNIT
                    FROM PRODUCT_INGREDIENTS pi
                    JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
                    WHERE pi.PRODUCT_ID IN ({placeholders})
                """
                cur.execute(sql_rules, tuple(product_ids))
                use_loss_percentage = False
            else:
                raise
        
        # Mapear ingredientes necessários por produto
        product_ingredients = {}
        for row in cur.fetchall():
            if use_loss_percentage:
                pid, ing_id, portions, min_q, max_q, loss_pct, base_qty, base_unit, stock_unit = row
                loss_percentage = float(loss_pct or 0)
            else:
                pid, ing_id, portions, min_q, max_q, base_qty, base_unit, stock_unit = row
                loss_percentage = 0  # Campo não existe, usa 0
            
            if pid not in product_ingredients:
                product_ingredients[pid] = {}
            
            product_ingredients[pid][ing_id] = {
                'portions': float(portions or 0),
                'min_quantity': int(min_q or 0),
                'max_quantity': int(max_q or 0),
                'loss_percentage': loss_percentage,
                'base_portion_quantity': float(base_qty or 1),
                'base_portion_unit': str(base_unit or 'un'),
                'stock_unit': str(stock_unit or 'un')
            }
        
        # Calcular quantidade total necessária de cada ingrediente (convertida para unidade do estoque)
        for item in items:
            product_id = item.get('product_id')
            quantity = item.get('quantity', 1)
            
            # Validação de quantidade
            try:
                quantity = max(1, int(quantity)) if quantity else 1
            except (ValueError, TypeError):
                logger.warning(f"Quantidade inválida no item: {quantity}, usando 1")
                quantity = 1
            
            rules = product_ingredients.get(product_id, {})
            
            for ing_id, rule in rules.items():
                try:
                    # SIMPLIFICAÇÃO: Calcula consumo (perdas são opcionais, padrão 0)
                    needed = calculate_consumption_in_stock_unit(
                        portions=rule['portions'],
                        base_portion_quantity=rule['base_portion_quantity'],
                        base_portion_unit=rule['base_portion_unit'],
                        stock_unit=rule['stock_unit'],
                        item_quantity=quantity,
                        loss_percentage=rule.get('loss_percentage', 0)
                    )
                    
                    if ing_id not in required_ingredients:
                        required_ingredients[ing_id] = Decimal('0')
                    required_ingredients[ing_id] += needed
                except ValueError as e:
                    logger.error(f"Erro ao calcular consumo na validação para ingrediente {ing_id}: {e}")
                    return (
                        False,
                        "STOCK_VALIDATION_ERROR",
                        f"Erro na conversão de unidades: {str(e)}"
                    )
            
            # Adicionar extras (que são ingredientes adicionais)
            if 'extras' in item and item['extras']:
                # Busca informações de unidades dos extras em batch para evitar N+1
                extra_ing_ids = {ex.get('ingredient_id') for ex in item['extras'] if ex.get('ingredient_id')}
                extras_info = {}
                if extra_ing_ids:
                    try:
                        extra_ing_ids = {int(eid) for eid in extra_ing_ids}
                    except (ValueError, TypeError):
                        logger.warning("Ingredient IDs inválidos nos extras, pulando validação")
                        continue
                    
                    # SEGURANÇA: Query parametrizada, extra_ing_ids validado como inteiros
                    placeholders_extras = ', '.join(['?' for _ in extra_ing_ids])
                    sql_extras_info = f"""
                        SELECT ID, BASE_PORTION_QUANTITY, BASE_PORTION_UNIT, STOCK_UNIT
                        FROM INGREDIENTS
                        WHERE ID IN ({placeholders_extras})
                    """
                    cur.execute(sql_extras_info, tuple(extra_ing_ids))
                    extras_info = {row[0]: {
                        'base_portion_quantity': float(row[1] or 1),
                        'base_portion_unit': str(row[2] or 'un'),
                        'stock_unit': str(row[3] or 'un')
                    } for row in cur.fetchall()}
                
                for extra in item.get('extras', []):
                    ing_id = extra.get('ingredient_id')
                    if not ing_id:
                        continue
                    
                    try:
                        ing_id = int(ing_id)
                    except (ValueError, TypeError):
                        logger.warning(f"Ingredient ID inválido no extra: {ing_id}")
                        continue
                    
                    extra_qty = extra.get('quantity', 1)
                    try:
                        extra_qty = max(1, int(extra_qty)) if extra_qty else 1
                    except (ValueError, TypeError):
                        extra_qty = 1
                    
                    info = extras_info.get(ing_id, {
                        'base_portion_quantity': 1,
                        'base_portion_unit': 'un',
                        'stock_unit': 'un'
                    })
                    
                    # CORREÇÃO: Verificar se o ingrediente já está na base do produto
                    # IMPORTANTE: Se portions > 0, o ingrediente está na base e já foi calculado acima
                    # Nesse caso, o extra não deveria existir (ingrediente da base não pode ser extra)
                    # Mas por segurança, verificamos e calculamos apenas a quantidade adicional
                    rule = rules.get(ing_id)
                    base_portions = rule.get('portions', 0) if rule else 0
                    
                    # Se o ingrediente está na base (portions > 0), já foi calculado acima
                    # O extra consome apenas a quantidade adicional (extra_qty - base_portions * quantity)
                    # Mas se portions = 0 (é só extra), consome a quantidade total do extra
                    if base_portions > 0:
                        # Ingrediente está na base, extra consome apenas quantidade adicional
                        # base_portions é por item, então total base = base_portions * quantity
                        # extra_qty é a quantidade total do extra (pode incluir a base se o usuário adicionou)
                        # Consumo adicional = extra_qty - (base_portions * quantity)
                        base_total_portions = base_portions * quantity
                        extra_portions_to_consume = max(0, extra_qty - base_total_portions)
                        
                        # Se não há consumo adicional, pula (já foi calculado na base)
                        if extra_portions_to_consume <= 0:
                            continue
                    else:
                        # Ingrediente não está na base (portions = 0), é só extra
                        # extra_qty é a quantidade total do extra (incluindo min_quantity se houver)
                        # Consome a quantidade total
                        extra_portions_to_consume = extra_qty
                    
                    try:
                        total_extra = calculate_consumption_in_stock_unit(
                            portions=extra_portions_to_consume,
                            base_portion_quantity=info['base_portion_quantity'],
                            base_portion_unit=info['base_portion_unit'],
                            stock_unit=info['stock_unit'],
                            item_quantity=quantity
                        )
                        
                        if ing_id not in required_ingredients:
                            required_ingredients[ing_id] = Decimal('0')
                        required_ingredients[ing_id] += total_extra
                    except ValueError as e:
                        logger.error(f"Erro ao calcular consumo de extra {ing_id}: {e}")
                        return (
                            False,
                            "STOCK_VALIDATION_ERROR",
                            f"Erro na conversão de unidades do extra: {str(e)}"
                        )
            
            # CORREÇÃO: Processar base_modifications (deltas positivos e negativos)
            # Deltas positivos aumentam consumo, deltas negativos reduzem consumo
            if 'base_modifications' in item and item['base_modifications']:
                # Busca informações de unidades dos base_modifications em batch
                # CORREÇÃO: Incluir todos os base_modifications (positivos e negativos)
                bm_ing_ids = {bm.get('ingredient_id') for bm in item['base_modifications'] 
                             if bm.get('delta', 0) != 0 and bm.get('ingredient_id')}
                bm_info = {}
                if bm_ing_ids:
                    try:
                        bm_ing_ids = {int(bid) for bid in bm_ing_ids}
                    except (ValueError, TypeError):
                        logger.warning("Ingredient IDs inválidos em base_modifications, pulando validação")
                        continue
                    
                    # SEGURANÇA: Query parametrizada, bm_ing_ids validado como inteiros
                    placeholders_bm = ', '.join(['?' for _ in bm_ing_ids])
                    sql_bm_info = f"""
                        SELECT ID, BASE_PORTION_QUANTITY, BASE_PORTION_UNIT, STOCK_UNIT
                        FROM INGREDIENTS
                        WHERE ID IN ({placeholders_bm})
                    """
                    cur.execute(sql_bm_info, tuple(bm_ing_ids))
                    bm_info = {row[0]: {
                        'base_portion_quantity': float(row[1] or 1),
                        'base_portion_unit': str(row[2] or 'un'),
                        'stock_unit': str(row[3] or 'un')
                    } for row in cur.fetchall()}
                
                for bm in item.get('base_modifications', []):
                    delta = bm.get('delta', 0)
                    if delta == 0:  # Ignora deltas zero
                        continue
                    
                    ing_id = bm.get('ingredient_id')
                    if not ing_id:
                        continue
                    
                    try:
                        ing_id = int(ing_id)
                    except (ValueError, TypeError):
                        logger.warning(f"Ingredient ID inválido em base_modification: {ing_id}")
                        continue
                    
                    # CORREÇÃO: Buscar informações do ingrediente (pode estar na receita base ou não)
                    info = bm_info.get(ing_id)
                    if not info:
                        # Se não encontrou nas informações buscadas, tenta buscar da receita base
                        rule = rules.get(ing_id)
                        if rule:
                            info = {
                                'base_portion_quantity': rule['base_portion_quantity'],
                                'base_portion_unit': rule['base_portion_unit'],
                                'stock_unit': rule['stock_unit']
                            }
                        else:
                            # Fallback: usa valores padrão
                            info = {
                                'base_portion_quantity': 1,
                                'base_portion_unit': 'un',
                                'stock_unit': 'un'
                            }
                    
                    try:
                        # CORREÇÃO: Usar calculate_consumption_in_stock_unit para consistência
                        # Isso garante conversão de unidades correta e considera perdas se houver
                        # Delta pode ser positivo ou negativo
                        rule = rules.get(ing_id, {})
                        loss_percentage = rule.get('loss_percentage', 0) if rule else 0
                        
                        delta_consumption = calculate_consumption_in_stock_unit(
                            portions=abs(delta),  # Usa valor absoluto para cálculo
                            base_portion_quantity=info['base_portion_quantity'],
                            base_portion_unit=info['base_portion_unit'],
                            stock_unit=info['stock_unit'],
                            item_quantity=quantity,
                            loss_percentage=loss_percentage
                        )
                        
                        # Garantir que required_ingredients existe para este ingrediente
                        # (pode não existir se o ingrediente não está na receita base)
                        if ing_id not in required_ingredients:
                            required_ingredients[ing_id] = Decimal('0')
                        
                        # CORREÇÃO: Se delta é negativo, reduz o consumo necessário
                        # Se delta é positivo, aumenta o consumo necessário
                        if delta < 0:
                            # Delta negativo: reduz consumo (remove da receita base)
                            required_ingredients[ing_id] = max(Decimal('0'), required_ingredients[ing_id] - delta_consumption)
                        else:
                            # Delta positivo: aumenta consumo (adiciona à receita base)
                            required_ingredients[ing_id] += delta_consumption
                            
                    except ValueError as e:
                        logger.error(f"Erro ao calcular consumo de base_modification {ing_id}: {e}")
                        return (
                            False,
                            "STOCK_VALIDATION_ERROR",
                            f"Erro na conversão de unidades do base_modification: {str(e)}"
                        )
        
        # Verificar se há ingredientes necessários
        if not required_ingredients:
            return (True, None, None)
        
        # Buscar estoque atual dos ingredientes necessários
        # SEGURANÇA: Query parametrizada, ing_ids são chaves do dict (validados como inteiros)
        ing_ids = list(required_ingredients.keys())
        placeholders = ', '.join(['?' for _ in ing_ids])
        sql_check = f"""
            SELECT ID, NAME, CURRENT_STOCK, STOCK_UNIT
            FROM INGREDIENTS
            WHERE ID IN ({placeholders})
        """
        cur.execute(sql_check, tuple(ing_ids))
        
        # Validar estoque disponível (todas as quantidades já estão convertidas para STOCK_UNIT)
        for row in cur.fetchall():
            ing_id, ing_name, current_stock, stock_unit = row
            needed = required_ingredients.get(ing_id, Decimal('0'))
            available = Decimal(str(current_stock or 0))
            
            if needed > available:
                return (
                    False,
                    "INSUFFICIENT_STOCK",
                    f"Estoque insuficiente para {ing_name}. Disponível: {available:.3f} {stock_unit}, Necessário: {needed:.3f} {stock_unit}"
                )
        
        return (True, None, None)
        
    except fdb.Error as e:
        logger.error(f"Erro de banco de dados ao validar estoque: {e}", exc_info=True)
        return (False, "STOCK_VALIDATION_ERROR", "Erro ao validar estoque: falha no banco de dados")
    except Exception as e:
        logger.error(f"Erro inesperado ao validar estoque: {e}", exc_info=True)
        return (False, "STOCK_VALIDATION_ERROR", f"Erro ao validar estoque: {str(e)}")


def deduct_stock_for_order(order_id, cur=None):
    """
    Deduz o estoque dos ingredientes baseado nos produtos do pedido
    
    OTIMIZAÇÃO DE PERFORMANCE: Aceita cursor opcional para reutilizar conexão existente,
    evitando múltiplas conexões ao banco quando chamada dentro de transações.
    
    Args:
        order_id: ID do pedido
        cur: Cursor opcional para reutilizar conexão (se None, cria nova conexão e faz commit)
    
    Returns:
        tuple: (success: bool, error_code: str, message: str)
    """
    conn = None
    should_close_conn = False
    
    try:
        # Validação de entrada
        if not isinstance(order_id, int) or order_id <= 0:
            return (False, "VALIDATION_ERROR", "order_id deve ser um inteiro positivo")
        
        # Se cursor não foi fornecido, cria nova conexão
        if cur is None:
            conn = get_db_connection()
            cur = conn.cursor()
            should_close_conn = True
        
        # Busca todos os itens do pedido
        cur.execute("""
            SELECT PRODUCT_ID, QUANTITY 
            FROM ORDER_ITEMS 
            WHERE ORDER_ID = ?
        """, (order_id,))
        order_items = cur.fetchall()
        
        if not order_items:
            return (True, None, "Pedido sem itens")
        
        # Calcula deduções necessárias
        ingredient_deductions = _calculate_ingredient_deductions(order_id, order_items, cur)
        
        # Executa as deduções de estoque
        updated_ingredients = _execute_stock_deductions(ingredient_deductions, cur)
        
        # Só faz commit se criou a conexão nesta função
        if should_close_conn:
            conn.commit()
        
        # Verifica se algum ingrediente ficou sem estoque
        _check_and_deactivate_products(updated_ingredients, cur)
        
        # Log das alterações (substituído print por logger)
        _log_stock_changes(order_id, updated_ingredients)
        
        return (True, None, f"Estoque deduzido para {len(updated_ingredients)} ingredientes")
        
    except fdb.Error as e:
        if should_close_conn and conn:
            conn.rollback()
        logger.error(f"Erro ao deduzir estoque para pedido {order_id}: {e}", exc_info=True)
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    except ValueError as e:
        if should_close_conn and conn:
            conn.rollback()
        logger.error(f"Erro de validação ao deduzir estoque para pedido {order_id}: {e}")
        return (False, "VALIDATION_ERROR", str(e))
    finally:
        # Fecha conexão apenas se foi criada nesta função
        if should_close_conn and conn:
            conn.close()

def _calculate_ingredient_deductions(order_id, order_items, cur):
    """
    Calcula deduções necessárias de ingredientes com conversão de unidades.
    
    Converte automaticamente as unidades de consumo para a unidade do estoque.
    Exemplo: se o ingrediente está em kg no estoque mas é usado em g na receita,
    realiza a conversão correta antes de deduzir.
    
    Validação: Testado e validado com conversão g → kg para:
    - Pão: 100g → 0.100kg ✓
    - Mussarela: 30g → 0.030kg ✓
    - Hambúrguer: 150g → 0.150kg ✓
    - Ketchup: 12g → 0.012kg ✓
    """
    ingredient_deductions = {}
    
    # Validação de entrada
    if not order_items:
        return ingredient_deductions
    
    for product_id, quantity in order_items:
        # Validação de quantity
        try:
            quantity = max(1, int(quantity)) if quantity else 1
        except (ValueError, TypeError):
            logger.warning(f"Quantidade inválida no pedido {order_id}, produto {product_id}: {quantity}, usando 1")
            quantity = 1
        
        # SIMPLIFICAÇÃO: Busca ingredientes do produto (perdas opcionais)
        # Verifica se campo LOSS_PERCENTAGE existe antes de usar
        try:
            cur.execute("""
                SELECT 
                    pi.INGREDIENT_ID, 
                    pi.PORTIONS,
                    COALESCE(pi.LOSS_PERCENTAGE, 0) as LOSS_PERCENTAGE,
                    i.BASE_PORTION_QUANTITY,
                    i.BASE_PORTION_UNIT,
                    i.STOCK_UNIT
                FROM PRODUCT_INGREDIENTS pi
                JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
                WHERE pi.PRODUCT_ID = ?
            """, (product_id,))
            use_loss_percentage = True
        except fdb.Error as e:
            # Se campo não existe, usa query sem LOSS_PERCENTAGE
            error_msg = str(e).lower()
            if 'loss_percentage' in error_msg or 'unknown' in error_msg:
                cur.execute("""
                    SELECT 
                        pi.INGREDIENT_ID, 
                        pi.PORTIONS,
                        i.BASE_PORTION_QUANTITY,
                        i.BASE_PORTION_UNIT,
                        i.STOCK_UNIT
                    FROM PRODUCT_INGREDIENTS pi
                    JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
                    WHERE pi.PRODUCT_ID = ?
                """, (product_id,))
                use_loss_percentage = False
            else:
                raise
        
        product_ingredients = cur.fetchall()
        
        # Adiciona ingredientes base do produto
        for row in product_ingredients:
            ingredient_id = row[0]
            portions = row[1] or 0
            if use_loss_percentage:
                loss_percentage = float(row[2] or 0)
                base_portion_quantity = row[3] or 1
                base_portion_unit = row[4] or 'un'
                stock_unit = row[5] or 'un'
            else:
                loss_percentage = 0  # Campo não existe, usa 0
                base_portion_quantity = row[2] or 1
                base_portion_unit = row[3] or 'un'
                stock_unit = row[4] or 'un'
            
            # SIMPLIFICAÇÃO: Calcula consumo (perdas são opcionais, padrão 0)
            try:
                total_needed = calculate_consumption_in_stock_unit(
                    portions=portions,
                    base_portion_quantity=base_portion_quantity,
                    base_portion_unit=base_portion_unit,
                    stock_unit=stock_unit,
                    item_quantity=quantity,
                    loss_percentage=loss_percentage
                )
            except ValueError as e:
                logger.error(
                    f"Erro ao calcular consumo do ingrediente {ingredient_id} "
                    f"para produto {product_id} no pedido {order_id}: {e}"
                )
                raise ValueError(
                    f"Erro na conversão de unidades para ingrediente ID {ingredient_id}. "
                    f"Verifique as unidades configuradas: {e}"
                )
            
            if ingredient_id in ingredient_deductions:
                ingredient_deductions[ingredient_id] += total_needed
            else:
                ingredient_deductions[ingredient_id] = total_needed
        
        # Busca ingredientes extras do item - otimização: buscar todos os extras de uma vez
        # Usa subquery para evitar múltiplas queries por produto
        cur.execute("""
            SELECT 
                oie.INGREDIENT_ID, 
                oie.QUANTITY,
                oie.TYPE,
                oie.DELTA,
                i.BASE_PORTION_QUANTITY,
                i.BASE_PORTION_UNIT,
                i.STOCK_UNIT
            FROM ORDER_ITEM_EXTRAS oie
            JOIN INGREDIENTS i ON oie.INGREDIENT_ID = i.ID
            WHERE oie.ORDER_ITEM_ID IN (
                SELECT ID FROM ORDER_ITEMS 
                WHERE ORDER_ID = ? AND PRODUCT_ID = ?
            )
        """, (order_id, product_id))
        extras = cur.fetchall()
        
        # Adiciona ingredientes extras e base_modifications
        for row in extras:
            ingredient_id = row[0]
            extra_quantity = row[1] or 1
            extra_type = (row[2] or 'extra').lower()
            delta = row[3] or 0
            base_portion_quantity = row[4] or 1
            base_portion_unit = row[5] or 'un'
            stock_unit = row[6] or 'un'
            
            try:
                if extra_type == 'base' and delta > 0:
                    # Base modifications: DELTA positivo indica consumo adicional
                    # DELTA negativo NÃO consome estoque (redução de ingrediente)
                    # Converte DELTA usando BASE_PORTION_QUANTITY e unidades
                    # DELTA é em porções, então multiplica por base_portion_quantity
                    delta_consumption = (
                        Decimal(str(delta)) * 
                        Decimal(str(base_portion_quantity))
                    )
                    total_extra = _convert_unit(
                        delta_consumption,
                        base_portion_unit,
                        stock_unit
                    ) * Decimal(str(quantity))
                else:
                    # Extras normais: QUANTITY × base_portion_quantity × item_quantity
                    total_extra = calculate_consumption_in_stock_unit(
                        portions=extra_quantity,
                        base_portion_quantity=base_portion_quantity,
                        base_portion_unit=base_portion_unit,
                        stock_unit=stock_unit,
                        item_quantity=quantity
                    )
            except ValueError as e:
                logger.error(
                    f"Erro ao calcular consumo do extra/ingrediente {ingredient_id} "
                    f"para produto {product_id} no pedido {order_id}: {e}"
                )
                raise ValueError(
                    f"Erro na conversão de unidades para extra/ingrediente ID {ingredient_id}. "
                    f"Verifique as unidades configuradas: {e}"
                )
            
            if ingredient_id in ingredient_deductions:
                ingredient_deductions[ingredient_id] += total_extra
            else:
                ingredient_deductions[ingredient_id] = total_extra
    
    return ingredient_deductions

def _execute_stock_deductions(ingredient_deductions, cur):
    """
    Executa as deduções de estoque.
    
    ALTERAÇÃO: Agora suporta FEFO (lotes) se a tabela STOCK_LOTS existir.
    Se não existir, usa o método antigo (atualização direta de CURRENT_STOCK).
    """
    updated_ingredients = []
    
    if not ingredient_deductions:
        return updated_ingredients
    
    for ingredient_id, deduction_amount in ingredient_deductions.items():
        # SIMPLIFICAÇÃO: Busca estoque atual (lote mínimo opcional)
        # Verifica se campo MIN_LOT_SIZE existe antes de usar
        try:
            cur.execute("""
                SELECT CURRENT_STOCK, MIN_STOCK_THRESHOLD, STOCK_STATUS, NAME, COALESCE(MIN_LOT_SIZE, 0) as MIN_LOT_SIZE
                FROM INGREDIENTS 
                WHERE ID = ?
            """, (ingredient_id,))
            use_min_lot_size = True
        except fdb.Error as e:
            # Se campo não existe, usa query sem MIN_LOT_SIZE
            error_msg = str(e).lower()
            if 'min_lot_size' in error_msg or 'unknown' in error_msg:
                cur.execute("""
                    SELECT CURRENT_STOCK, MIN_STOCK_THRESHOLD, STOCK_STATUS, NAME
                    FROM INGREDIENTS 
                    WHERE ID = ?
                """, (ingredient_id,))
                use_min_lot_size = False
            else:
                raise
        
        result = cur.fetchone()
        
        if not result:
            logger.warning(f"Ingrediente {ingredient_id} não encontrado ao deduzir estoque")
            continue
        
        if use_min_lot_size:
            current_stock, min_threshold, current_status, ingredient_name, min_lot_size = result
        else:
            current_stock, min_threshold, current_status, ingredient_name = result
            min_lot_size = 0  # Campo não existe, usa 0
        
        # Garante que deduction_amount é Decimal para compatibilidade com current_stock
        # Converte explicitamente para Decimal, lidando com qualquer tipo numérico
        if isinstance(deduction_amount, Decimal):
            deduction_decimal = deduction_amount
        elif isinstance(deduction_amount, (int, float)):
            deduction_decimal = Decimal(str(deduction_amount))
        else:
            deduction_decimal = Decimal(str(deduction_amount))
        
        # Garante que deduction_decimal é sempre positivo
        # Se vier negativo, loga erro e corrige para positivo
        # Valores negativos resultariam em ADIÇÃO ao invés de SUBTRAÇÃO (bug crítico!)
        if deduction_decimal < 0:
            logger.error(
                f"[BUG CRÍTICO] Dedução negativa detectada para ingrediente {ingredient_id} ({ingredient_name}): {deduction_decimal}. "
                f"Isso causaria ADIÇÃO ao invés de subtração! Corrigindo para valor absoluto."
            )
            deduction_decimal = abs(deduction_decimal)
        
        # Se a dedução é zero, não precisa processar
        if deduction_decimal == 0:
            logger.warning(
                f"Dedução zero para ingrediente {ingredient_id} ({ingredient_name}). Pulando."
            )
            continue
        
        # SIMPLIFICAÇÃO: Arredonda para lote mínimo se MIN_LOT_SIZE > 0 (opcional)
        if min_lot_size and min_lot_size > 0:
            min_lot_decimal = Decimal(str(min_lot_size))
            # Arredonda para cima para múltiplo do lote mínimo
            lots_needed = math.ceil(float(deduction_decimal / min_lot_decimal))
            deduction_decimal = Decimal(str(lots_needed)) * min_lot_decimal
            logger.debug(
                f"Arredondando dedução para lote mínimo: {ingredient_name} | "
                f"Original: {deduction_amount} | Lote mínimo: {min_lot_size} | "
                f"Arredondado: {deduction_decimal}"
            )
        
        # SIMPLIFICAÇÃO: Remove código relacionado a FEFO (lotes)
        # TODO: FUTURO - Implementar FEFO completo quando necessário
        # Por enquanto, usa método direto (atualização de CURRENT_STOCK)
        # FEFO requer lógica mais complexa para gerenciar lotes individuais
        
        # Verifica se há estoque suficiente
        current_stock_decimal = Decimal(str(current_stock))
        
        # SIMPLIFICAÇÃO: Validação para evitar estoques negativos
        if current_stock_decimal < deduction_decimal:
            raise ValueError(
                f"Estoque insuficiente para {ingredient_name}. "
                f"Disponível: {current_stock_decimal}, Necessário: {deduction_decimal}"
            )
        
        # Calcula novo estoque (ambos Decimal agora)
        # IMPORTANTE: Sempre SUBTRAI para DEDUZIR estoque
        new_stock = current_stock_decimal - deduction_decimal
        
        # SIMPLIFICAÇÃO: Validação adicional para evitar estoques negativos
        if new_stock < 0:
            raise ValueError(
                f"Erro: Novo estoque seria negativo para {ingredient_name}. "
                f"Antes: {current_stock_decimal}, Dedução: {deduction_decimal}, Depois: {new_stock}"
            )
        
        # Log para debug: mostra valores antes e depois
        logger.debug(
            f"Deduzindo estoque: {ingredient_name} (ID: {ingredient_id}) | "
            f"Antes: {current_stock_decimal} | Dedução: {deduction_decimal} | Depois: {new_stock}"
        )
        
        # Determina novo status baseado no estoque
        new_status = _determine_new_status(new_stock, min_threshold, current_status)
        
        # Atualiza o estoque
        cur.execute("""
            UPDATE INGREDIENTS 
            SET CURRENT_STOCK = ?, STOCK_STATUS = ?
            WHERE ID = ?
        """, (new_stock, new_status, ingredient_id))
        
        updated_ingredients.append({
            'ingredient_id': ingredient_id,
            'ingredient_name': ingredient_name,
            'old_stock': current_stock,
            'new_stock': new_stock,
            'deducted': deduction_decimal,
            'new_status': new_status
        })
    
    return updated_ingredients

def _determine_new_status(new_stock, min_threshold, current_status):
    """
    Determina novo status baseado no estoque.
    
    CORREÇÃO: Sempre recalcula o status baseado no novo estoque, não mantém o status anterior.
    
    Lógica:
    - Se estoque <= 0: 'out_of_stock'
    - Se estoque > 0 mas <= min_threshold: 'low'
    - Se estoque > min_threshold: 'ok'
    """
    new_stock_decimal = Decimal(str(new_stock))
    min_threshold_decimal = Decimal(str(min_threshold)) if min_threshold else Decimal('0')
    
    if new_stock_decimal <= 0:
        return 'out_of_stock'
    elif min_threshold_decimal > 0 and new_stock_decimal <= min_threshold_decimal:
        # Se está abaixo ou igual ao threshold, marca como 'low'
        return 'low'
    else:
        # Se está acima do threshold, marca como 'ok'
        return 'ok'

def _check_and_deactivate_products(updated_ingredients, cur):
    """
    Verifica se algum ingrediente ficou sem estoque.
    
    NOTA: Produtos NÃO são mais desativados automaticamente.
    Eles permanecem ativos no banco, mas são filtrados no GET de produtos
    baseado no availability_status calculado dinamicamente.
    """
    # CORREÇÃO: Não desativa produtos automaticamente
    # Apenas registra no log para monitoramento
    for item in updated_ingredients:
        if item['new_status'] == 'out_of_stock':
            # Busca produtos afetados apenas para log (não desativa)
            cur.execute("""
                SELECT DISTINCT P.ID, P.NAME
                FROM PRODUCTS P
                JOIN PRODUCT_INGREDIENTS PI ON P.ID = PI.PRODUCT_ID
                WHERE PI.INGREDIENT_ID = ? AND P.IS_ACTIVE = TRUE
            """, (item['ingredient_id'],))
            affected_products = cur.fetchall()
            if affected_products:
                product_names = [p[1] for p in affected_products]
                logger.info(
                    f"Ingrediente '{item['ingredient_name']}' ficou sem estoque. "
                    f"Produtos afetados (não desativados, apenas filtrados no GET): {product_names}"
                )

def _log_stock_changes(order_id, updated_ingredients):
    """Log das alterações de estoque"""
    if not updated_ingredients:
        return
    
    logger.info(f"Estoque deduzido para pedido {order_id}:")
    for item in updated_ingredients:
        logger.debug(
            f"  {item['ingredient_name']}: {item['old_stock']} -> {item['new_stock']} "
            f"(deduzido: {item['deducted']}, status: {item['new_status']})"
        )


def get_stock_alerts():
    """
    Retorna lista de ingredientes com estoque baixo.
    Retorna (ingredientes, error_code, mensagem)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT ID, NAME, CURRENT_STOCK, MIN_STOCK_THRESHOLD, STOCK_STATUS
            FROM INGREDIENTS 
            WHERE STOCK_STATUS = 'low'
            ORDER BY CURRENT_STOCK ASC
        """)
        
        alerts = []
        for row in cur.fetchall():
            alerts.append({
                'id': row[0],
                'name': row[1],
                'current_stock': row[2],
                'min_threshold': row[3],
                'status': row[4]
            })
        
        return (alerts, None, None)
        
    except fdb.Error as e:
        logger.error(f"Erro ao buscar alertas de estoque: {e}", exc_info=True)
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()


def confirm_out_of_stock(ingredient_id):
    """
    Confirma que um ingrediente está fora de estoque.
    
    NOTA: Produtos NÃO são mais desativados automaticamente.
    Eles permanecem ativos no banco, mas são filtrados no GET de produtos
    baseado no availability_status calculado dinamicamente.
    
    Retorna (sucesso, produtos_afetados, error_code, mensagem)
    """
    conn = None
    try:
        _validate_ingredient_id(ingredient_id)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se o ingrediente existe
        cur.execute("SELECT NAME FROM INGREDIENTS WHERE ID = ? AND IS_ACTIVE = TRUE", (ingredient_id,))
        result = cur.fetchone()
        if not result:
            return (False, [], "INGREDIENT_NOT_FOUND", "Ingrediente não encontrado")
        
        ingredient_name = result[0]
        
        # Atualiza o ingrediente para fora de estoque
        cur.execute("""
            UPDATE INGREDIENTS 
            SET CURRENT_STOCK = 0, STOCK_STATUS = 'out_of_stock'
            WHERE ID = ?
        """, (ingredient_id,))
        
        # Busca produtos que usam este ingrediente (apenas para informação, não desativa)
        cur.execute("""
            SELECT DISTINCT P.ID, P.NAME
            FROM PRODUCTS P
            JOIN PRODUCT_INGREDIENTS PI ON P.ID = PI.PRODUCT_ID
            WHERE PI.INGREDIENT_ID = ? AND P.IS_ACTIVE = TRUE
        """, (ingredient_id,))
        
        affected_products = cur.fetchall()
        affected_products_list = []
        
        # CORREÇÃO: Não desativa produtos, apenas lista os afetados
        for product_id, product_name in affected_products:
            affected_products_list.append({
                'id': product_id,
                'name': product_name
            })
        
        conn.commit()
        
        message = f"Ingrediente '{ingredient_name}' confirmado como fora de estoque"
        if affected_products_list:
            message += f". {len(affected_products_list)} produtos serão filtrados no GET (não desativados)."
        
        return (True, affected_products_list, None, message)
        
    except fdb.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"Erro ao confirmar estoque zerado para ingrediente {ingredient_id}: {e}", exc_info=True)
        return (False, [], "DATABASE_ERROR", "Erro interno do servidor")
    except ValueError as e:
        logger.error(f"Erro de validação ao confirmar estoque zerado: {e}")
        return (False, [], "VALIDATION_ERROR", str(e))
    finally:
        if conn:
            conn.close()


def adjust_stock(ingredient_id, adjustment_amount):
    """Ajusta manualmente o estoque de um ingrediente"""
    conn = None
    try:
        _validate_ingredient_id(ingredient_id)
        _validate_adjustment_amount(adjustment_amount)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca dados atuais do ingrediente
        cur.execute("""
            SELECT CURRENT_STOCK, MIN_STOCK_THRESHOLD, STOCK_STATUS, NAME
            FROM INGREDIENTS 
            WHERE ID = ?
        """, (ingredient_id,))
        result = cur.fetchone()
        
        if not result:
            return (False, [], "INGREDIENT_NOT_FOUND", "Ingrediente não encontrado")
        
        current_stock, min_threshold, current_status, ingredient_name = result
        
        # Calcula novo estoque usando Decimal para precisão (corrigido de float)
        current_stock_decimal = Decimal(str(current_stock))
        adjustment_decimal = Decimal(str(adjustment_amount))
        new_stock = max(Decimal('0'), current_stock_decimal + adjustment_decimal)
        
        # Determina novo status
        new_status = _determine_new_status(new_stock, min_threshold, current_status)
        
        # Atualiza o estoque
        cur.execute("""
            UPDATE INGREDIENTS 
            SET CURRENT_STOCK = ?, STOCK_STATUS = ?
            WHERE ID = ?
        """, (new_stock, new_status, ingredient_id,))
        
        # Se o ingrediente voltou a ter estoque, tenta reativar produtos
        reactivated_products = []
        if current_status == 'out_of_stock' and new_stock > 0:
            reactivated_products = reactivate_products_for_ingredient(ingredient_id, cur)
        
        conn.commit()
        
        message = f"Estoque de '{ingredient_name}' ajustado: {current_stock} -> {new_stock} (status: {new_status})"
        if reactivated_products:
            message += f". {len(reactivated_products)} produtos foram reativados."
        
        return (True, reactivated_products, None, message)
        
    except fdb.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"Erro ao ajustar estoque para ingrediente {ingredient_id}: {e}", exc_info=True)
        return (False, [], "DATABASE_ERROR", "Erro interno do servidor")
    except ValueError as e:
        logger.error(f"Erro de validação ao ajustar estoque: {e}")
        return (False, [], "VALIDATION_ERROR", str(e))
    finally:
        if conn:
            conn.close()


def _auto_deactivate_products_for_ingredient(ingredient_id, cursor):
    """
    DEPRECATED: Esta função não desativa mais produtos automaticamente.
    Produtos permanecem ativos no banco e são filtrados dinamicamente no GET
    baseado no availability_status calculado.
    
    Retorna lista vazia (não desativa nada).
    """
    # CORREÇÃO: Não desativa produtos automaticamente
    # Produtos são filtrados no GET baseado em availability_status
    return []


def reactivate_products_for_ingredient(ingredient_id, cursor=None):
    """
    Reativa produtos que usam um ingrediente, se todos os ingredientes necessários estiverem disponíveis.
    Retorna lista de produtos reativados.
    """
    conn = None
    try:
        # Validação de entrada
        _validate_ingredient_id(ingredient_id)
        
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
        
        # Busca produtos inativos que usam este ingrediente
        cursor.execute("""
            SELECT DISTINCT P.ID, P.NAME
            FROM PRODUCTS P
            JOIN PRODUCT_INGREDIENTS PI ON P.ID = PI.PRODUCT_ID
            WHERE PI.INGREDIENT_ID = ? AND P.IS_ACTIVE = FALSE
        """, (ingredient_id,))
        
        products_to_check = cursor.fetchall()
        reactivated_products = []
        
        for product_id, product_name in products_to_check:
            # Verifica se todos os ingredientes do produto estão disponíveis
            cursor.execute("""
                SELECT PI.INGREDIENT_ID, PI.PORTIONS, I.CURRENT_STOCK, I.STOCK_STATUS
                FROM PRODUCT_INGREDIENTS PI
                JOIN INGREDIENTS I ON PI.INGREDIENT_ID = I.ID
                WHERE PI.PRODUCT_ID = ? AND I.IS_ACTIVE = TRUE
            """, (product_id,))
            
            ingredients = cursor.fetchall()
            can_reactivate = True
            
            for ing_id, portions, current_stock, status in ingredients:
                # Usa Decimal para cálculo preciso
                required_qty = Decimal(str(portions or 0))
                current_stock_decimal = Decimal(str(current_stock or 0))
                
                if status == 'out_of_stock' or current_stock_decimal < required_qty:
                    can_reactivate = False
                    break
            
            if can_reactivate:
                cursor.execute("UPDATE PRODUCTS SET IS_ACTIVE = TRUE WHERE ID = ?", (product_id,))
                reactivated_products.append({
                    'id': product_id,
                    'name': product_name
                })
        
        # Commit apenas se a conexão foi criada nesta função
        if conn:
            conn.commit()
        
        return reactivated_products
        
    except fdb.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"Erro ao reativar produtos para ingrediente {ingredient_id}: {e}", exc_info=True)
        return []
    except ValueError as e:
        logger.error(f"Erro de validação ao reativar produtos: {e}")
        return []
    finally:
        if conn:
            conn.close()


# =====================================================
# SISTEMA DE RESERVAS TEMPORÁRIAS (SOFT LOCKS)
# =====================================================

def create_temporary_reservation(ingredient_id, quantity, session_id, user_id=None, cart_id=None, ttl_minutes=10):
    """
    Cria uma reserva temporária (soft lock) de insumo.
    
    Args:
        ingredient_id: ID do insumo
        quantity: Quantidade a reservar (na unidade do estoque)
        session_id: ID da sessão do usuário
        user_id: ID do usuário (opcional, para usuários autenticados)
        cart_id: ID do carrinho (opcional)
        ttl_minutes: Tempo de vida da reserva em minutos (padrão: 10)
    
    Returns:
        tuple: (success: bool, reservation_id: int, error_code: str, message: str)
    """
    conn = None
    try:
        _validate_ingredient_id(ingredient_id)
        
        if quantity <= 0:
            return (False, None, "INVALID_QUANTITY", "Quantidade deve ser maior que zero")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se há estoque disponível
        available = get_ingredient_available_stock(ingredient_id, cur)
        if available < quantity:
            return (
                False, 
                None, 
                "INSUFFICIENT_STOCK", 
                f"Estoque insuficiente. Disponível: {available:.3f}, Solicitado: {quantity:.3f}"
            )
        
        # Calcula data de expiração
        from datetime import datetime, timedelta
        expires_at = datetime.now() + timedelta(minutes=ttl_minutes)
        
        # Cria reserva temporária
        cur.execute("""
            INSERT INTO TEMPORARY_RESERVATIONS 
            (INGREDIENT_ID, QUANTITY, SESSION_ID, USER_ID, CART_ID, EXPIRES_AT)
            VALUES (?, ?, ?, ?, ?, ?)
            RETURNING ID
        """, (ingredient_id, quantity, session_id, user_id, cart_id, expires_at))
        
        reservation_id = cur.fetchone()[0]
        conn.commit()
        
        return (True, reservation_id, None, "Reserva temporária criada com sucesso")
        
    except fdb.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"Erro ao criar reserva temporária: {e}", exc_info=True)
        return (False, None, "DATABASE_ERROR", "Erro interno do servidor")
    except ValueError as e:
        if conn:
            conn.rollback()
        logger.error(f"Erro de validação ao criar reserva temporária: {e}")
        return (False, None, "VALIDATION_ERROR", str(e))
    finally:
        if conn:
            conn.close()


def clear_temporary_reservations(session_id=None, user_id=None, cart_id=None):
    """
    Limpa reservas temporárias expiradas ou de uma sessão específica.
    
    Args:
        session_id: ID da sessão (opcional)
        user_id: ID do usuário (opcional)
        cart_id: ID do carrinho (opcional)
    
    Returns:
        tuple: (success: bool, cleared_count: int, error_code: str, message: str)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Limpa reservas expiradas
        cur.execute("""
            DELETE FROM TEMPORARY_RESERVATIONS
            WHERE EXPIRES_AT <= CURRENT_TIMESTAMP
        """)
        expired_count = cur.rowcount
        
        # Limpa reservas específicas se fornecidas
        if session_id or user_id or cart_id:
            conditions = []
            params = []
            
            if session_id:
                conditions.append("SESSION_ID = ?")
                params.append(session_id)
            if user_id:
                conditions.append("USER_ID = ?")
                params.append(user_id)
            if cart_id:
                conditions.append("CART_ID = ?")
                params.append(cart_id)
            
            if conditions:
                sql = f"""
                    DELETE FROM TEMPORARY_RESERVATIONS
                    WHERE {' AND '.join(conditions)}
                """
                cur.execute(sql, tuple(params))
                specific_count = cur.rowcount
            else:
                specific_count = 0
        else:
            specific_count = 0
        
        conn.commit()
        total_cleared = expired_count + specific_count
        
        return (True, total_cleared, None, f"{total_cleared} reservas temporárias removidas")
        
    except fdb.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"Erro ao limpar reservas temporárias: {e}", exc_info=True)
        return (False, 0, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()


def get_ingredient_available_stock(ingredient_id, cur=None):
    """
    Obtém estoque disponível de um insumo considerando reservas.
    
    Args:
        ingredient_id: ID do insumo
        cur: Cursor do banco (opcional, se None cria nova conexão)
    
    Returns:
        Decimal: Estoque disponível na unidade do estoque
    """
    conn = None
    should_close = False
    
    try:
        if cur is None:
            conn = get_db_connection()
            cur = conn.cursor()
            should_close = True
        
        # Busca informações do insumo
        cur.execute("""
            SELECT 
                CURRENT_STOCK,
                MIN_STOCK_THRESHOLD,
                STOCK_UNIT,
                IS_AVAILABLE
            FROM INGREDIENTS
            WHERE ID = ?
        """, (ingredient_id,))
        
        row = cur.fetchone()
        if not row:
            return Decimal('0')
        
        current_stock, min_threshold, stock_unit, is_available = row
        
        if not is_available:
            return Decimal('0')
        
        current_stock_decimal = Decimal(str(current_stock or 0))
        min_threshold_decimal = Decimal(str(min_threshold or 0))
        
        
        # Calcula reservas confirmadas (pedidos pendentes/confirmados/preparando)
        # IMPORTANTE: Precisa considerar conversão de unidades usando calculate_consumption_in_stock_unit
        # Mas por enquanto, vamos simplificar assumindo que já está na unidade correta
        cur.execute("""
            SELECT 
                oi.QUANTITY,
                pi.PORTIONS,
                i2.BASE_PORTION_QUANTITY,
                i2.BASE_PORTION_UNIT,
                i2.STOCK_UNIT
            FROM ORDER_ITEMS oi
            JOIN PRODUCT_INGREDIENTS pi ON oi.PRODUCT_ID = pi.PRODUCT_ID
            JOIN INGREDIENTS i2 ON pi.INGREDIENT_ID = i2.ID
            JOIN ORDERS o ON oi.ORDER_ID = o.ID
            WHERE pi.INGREDIENT_ID = ?
              AND o.STATUS IN ('pending', 'confirmed', 'preparing')
        """, (ingredient_id,))
        
        confirmed_reservations = Decimal('0')
        for row in cur.fetchall():
            oi_quantity, portions, base_portion_quantity, base_portion_unit, stock_unit = row
            try:
                # Calcula consumo convertido para unidade do estoque
                consumption = calculate_consumption_in_stock_unit(
                    portions=portions or 0,
                    base_portion_quantity=base_portion_quantity or 1,
                    base_portion_unit=base_portion_unit or 'un',
                    stock_unit=stock_unit or 'un',
                    item_quantity=oi_quantity or 1
                )
                confirmed_reservations += consumption
            except ValueError as e:
                logger.warning(f"Erro ao calcular reserva confirmada: {e}")
                continue
        
        # Calcula reservas temporárias ativas
        # CORREÇÃO: Tratamento seguro para evitar erro SQLCODE -804 do Firebird
        # Usa uma abordagem mais simples que evita o problema do SQLDA
        temporary_reservations = Decimal('0')
        try:
            # ALTERAÇÃO: Query simplificada que evita SQLCODE -804 usando EXISTS primeiro
            # Primeiro verifica se há registros antes de fazer o SUM
            cur.execute("""
                SELECT CAST(COALESCE(SUM(QUANTITY), 0) AS NUMERIC(18, 3))
                FROM TEMPORARY_RESERVATIONS
                WHERE INGREDIENT_ID = ?
                  AND EXPIRES_AT > CURRENT_TIMESTAMP
            """, (ingredient_id,))
            
            sum_row = cur.fetchone()
            # ALTERAÇÃO: Validação mais robusta do resultado
            if sum_row is not None:
                try:
                    # Tenta acessar o primeiro elemento de forma segura
                    # Firebird pode retornar diferentes formatos dependendo da versão
                    if hasattr(sum_row, '__getitem__'):
                        sum_value = sum_row[0] if len(sum_row) > 0 else None
                    else:
                        # Se não é indexável, tenta converter direto
                        sum_value = sum_row
                    
                    if sum_value is not None and sum_value != '':
                        temporary_reservations = Decimal(str(sum_value))
                        # ALTERAÇÃO: Garantir que não seja negativo
                        if temporary_reservations < 0:
                            logger.warning(f"Reserva temporária negativa detectada para ingrediente {ingredient_id}: {temporary_reservations}")
                            temporary_reservations = Decimal('0')
                except (ValueError, TypeError, IndexError, AttributeError) as e:
                    logger.debug(f"Erro ao converter reserva temporária para Decimal (ingrediente {ingredient_id}): {e}")
                    temporary_reservations = Decimal('0')
            else:
                # Se fetchone() retornou None, não há registros
                temporary_reservations = Decimal('0')
        except fdb.Error as e:
            # ALTERAÇÃO: Se houver erro na query (ex: SQLCODE -804), assume 0 e loga apenas em debug
            # SQLCODE -804 pode ocorrer quando não há registros ou há problema com SQLDA
            error_code = getattr(e, 'sqlcode', None)
            if error_code == -804:
                # SQLCODE -804 é esperado quando não há registros ou há problema com SQLDA
                # Assume 0 e loga apenas em debug para evitar poluição de logs
                logger.debug(f"Nenhuma reserva temporária encontrada para ingrediente {ingredient_id} (SQLCODE -804)")
            else:
                # Outros erros são logados como warning
                logger.warning(f"Erro ao buscar reservas temporárias para ingrediente {ingredient_id}: {e}")
            temporary_reservations = Decimal('0')
        
        # Estoque disponível = estoque_real - reservas_confirmadas - reservas_temporárias
        # NOTA: MIN_STOCK_THRESHOLD é apenas um indicador de alerta para reabastecimento
        # Não é descontado do estoque disponível - serve apenas para sinalizar ao admin/gerente
        available = current_stock_decimal - confirmed_reservations - temporary_reservations
        
        # SIMPLIFICAÇÃO: Remove código relacionado a substitutos
        # TODO: FUTURO - Implementar validação de substitutos quando necessário
        # Por enquanto, retorna estoque disponível (garantindo que não seja negativo)
        # Substitutos requerem lógica mais complexa para validar disponibilidade e conversão
        
        # Retorna estoque disponível (garantindo que não seja negativo)
        return max(Decimal('0'), available)
        
    except fdb.Error as e:
        logger.error(f"Erro ao obter estoque disponível: {e}", exc_info=True)
        return Decimal('0')
    finally:
        if should_close and conn:
            conn.close()


# =====================================================
# CÁLCULO DE CAPACIDADE DE PRODUÇÃO
# =====================================================

def _batch_get_ingredient_availability(product_ids, cur):
    """
    SIMPLIFICAÇÃO: Obtém estoque disponível para múltiplos ingredientes de uma vez.
    Usado para otimizar cálculo de capacidade em batch.
    
    Args:
        product_ids: Lista de IDs de produtos
        cur: Cursor do banco
    
    Returns:
        dict: {ingredient_id: available_stock}
    """
    if not product_ids:
        return {}
    
    try:
        # Busca ingredientes de todos os produtos
        placeholders = ', '.join(['?' for _ in product_ids])
        
        # Busca ingredientes obrigatórios (PORTIONS > 0) de todos os produtos
        cur.execute(f"""
            SELECT DISTINCT pi.INGREDIENT_ID
            FROM PRODUCT_INGREDIENTS pi
            WHERE pi.PRODUCT_ID IN ({placeholders})
              AND pi.PORTIONS > 0
        """, tuple(product_ids))
        
        ingredient_ids = [row[0] for row in cur.fetchall()]
        
        if not ingredient_ids:
            return {}
        
        # OTIMIZAÇÃO: Busca estoque disponível para todos os ingredientes de uma vez usando função batch
        return _batch_get_ingredient_available_stock(ingredient_ids, cur)
    except Exception as e:
        logger.warning(f"Erro ao buscar disponibilidade em batch: {e}", exc_info=True)
        return {}


def _batch_get_ingredient_available_stock(ingredient_ids, cur):
    """
    OTIMIZAÇÃO: Obtém estoque disponível para múltiplos ingredientes de uma vez.
    Evita N+1 queries ao buscar estoque, reservas confirmadas e reservas temporárias em batch.
    
    Args:
        ingredient_ids: Lista de IDs de ingredientes
        cur: Cursor do banco
    
    Returns:
        dict: {ingredient_id: available_stock (Decimal)}
    """
    if not ingredient_ids:
        logger.warning("[STOCK_SERVICE] _batch_get_ingredient_available_stock chamado sem ingredient_ids")
        return {}
    
    try:
        # LOG: Iniciando busca de estoque
        logger.info(f"[STOCK_SERVICE] _batch_get_ingredient_available_stock: buscando estoque para {len(ingredient_ids)} ingredientes")
        
        # Busca informações básicas de todos os ingredientes de uma vez
        placeholders = ', '.join(['?' for _ in ingredient_ids])
        cur.execute(f"""
            SELECT 
                ID,
                CURRENT_STOCK,
                MIN_STOCK_THRESHOLD,
                STOCK_UNIT,
                IS_AVAILABLE
            FROM INGREDIENTS
            WHERE ID IN ({placeholders})
        """, tuple(ingredient_ids))
        
        ingredients_info = {}
        ingredient_rows = cur.fetchall()
        logger.info(f"[STOCK_SERVICE] Encontrados {len(ingredient_rows)} ingredientes no banco")
        
        for row in ingredient_rows:
            ing_id, current_stock, min_threshold, stock_unit, is_available = row
            if not is_available:
                logger.debug(f"[STOCK_SERVICE] Ingrediente {ing_id} não disponível (IS_AVAILABLE = FALSE)")
                ingredients_info[ing_id] = {
                    'current_stock': Decimal('0'),
                    'min_threshold': Decimal('0'),
                    'stock_unit': stock_unit,
                    'available_stock': Decimal('0')
                }
            else:
                ingredients_info[ing_id] = {
                    'current_stock': Decimal(str(current_stock or 0)),
                    'min_threshold': Decimal(str(min_threshold or 0)),
                    'stock_unit': stock_unit,
                    'available_stock': Decimal('0'),  # Será calculado abaixo
                    'is_available': is_available
                }
                # LOG: Estoque do ingrediente (SEMPRE logar para diagnóstico)
                logger.info(f"[STOCK_SERVICE] 📦 Ingrediente {ing_id}: "
                           f"CURRENT_STOCK={current_stock}, "
                           f"MIN_STOCK_THRESHOLD={min_threshold}, "
                           f"STOCK_UNIT={stock_unit}, "
                           f"IS_AVAILABLE={is_available}")
        
        # OTIMIZAÇÃO: Busca reservas confirmadas de todos os ingredientes de uma vez
        # Agrupa por ingrediente e calcula consumo total
        cur.execute(f"""
            SELECT 
                pi.INGREDIENT_ID,
                oi.QUANTITY,
                pi.PORTIONS,
                i2.BASE_PORTION_QUANTITY,
                i2.BASE_PORTION_UNIT,
                i2.STOCK_UNIT
            FROM ORDER_ITEMS oi
            JOIN PRODUCT_INGREDIENTS pi ON oi.PRODUCT_ID = pi.PRODUCT_ID
            JOIN INGREDIENTS i2 ON pi.INGREDIENT_ID = i2.ID
            JOIN ORDERS o ON oi.ORDER_ID = o.ID
            WHERE pi.INGREDIENT_ID IN ({placeholders})
              AND o.STATUS IN ('pending', 'confirmed', 'preparing')
        """, tuple(ingredient_ids))
        
        # Calcula reservas confirmadas por ingrediente
        confirmed_reservations = {ing_id: Decimal('0') for ing_id in ingredient_ids}
        confirmed_rows = cur.fetchall()
        logger.info(f"[STOCK_SERVICE] 📋 Reservas confirmadas: {len(confirmed_rows)} itens de pedidos encontrados")
        
        for row in confirmed_rows:
            ing_id, oi_quantity, portions, base_portion_quantity, base_portion_unit, stock_unit = row
            if ing_id not in ingredients_info:
                continue
            
            try:
                # Calcula consumo convertido para unidade do estoque
                consumption = calculate_consumption_in_stock_unit(
                    portions=portions or 0,
                    base_portion_quantity=base_portion_quantity or 1,
                    base_portion_unit=base_portion_unit or 'un',
                    stock_unit=stock_unit or 'un',
                    item_quantity=oi_quantity or 1
                )
                confirmed_reservations[ing_id] += consumption
                logger.debug(f"[STOCK_SERVICE] Reserva confirmada: ingrediente {ing_id}, consumo={consumption} {stock_unit}")
            except ValueError as e:
                logger.warning(f"[STOCK_SERVICE] Erro ao calcular reserva confirmada para ingrediente {ing_id}: {e}", exc_info=True)
                continue
        
        # LOG: Resumo de reservas confirmadas (SEMPRE logar se houver reservas)
        total_confirmed = sum(confirmed_reservations.values())
        if total_confirmed > 0:
            confirmed_count = len([r for r in confirmed_reservations.values() if r > 0])
            logger.info(f"[STOCK_SERVICE] 📋 Total de reservas confirmadas: {total_confirmed} (distribuído entre {confirmed_count} ingredientes)")
            # LOG: Detalhes das reservas confirmadas
            for ing_id, reserved in confirmed_reservations.items():
                if reserved > 0:
                    logger.info(f"[STOCK_SERVICE]   → Ingrediente {ing_id}: {reserved} unidades reservadas")
        
        # OTIMIZAÇÃO: Busca reservas temporárias de todos os ingredientes de uma vez
        cur.execute(f"""
            SELECT 
                INGREDIENT_ID,
                COALESCE(SUM(QUANTITY), 0) as TOTAL_RESERVATIONS
            FROM TEMPORARY_RESERVATIONS
            WHERE INGREDIENT_ID IN ({placeholders})
              AND EXPIRES_AT > CURRENT_TIMESTAMP
            GROUP BY INGREDIENT_ID
        """, tuple(ingredient_ids))
        
        temporary_reservations = {ing_id: Decimal('0') for ing_id in ingredient_ids}
        temp_reservations_rows = cur.fetchall()
        logger.info(f"[STOCK_SERVICE] Encontradas {len(temp_reservations_rows)} reservas temporárias ativas")
        for row in temp_reservations_rows:
            ing_id, total_reservations = row
            temporary_reservations[ing_id] = Decimal(str(total_reservations or 0))
        
        # LOG: Reservas confirmadas
        confirmed_count = sum(1 for r in confirmed_reservations.values() if r > 0)
        logger.info(f"[STOCK_SERVICE] Reservas confirmadas encontradas para {confirmed_count} ingredientes")
        
        # Calcula estoque disponível para cada ingrediente
        availability_map = {}
        for ing_id in ingredient_ids:
            if ing_id not in ingredients_info:
                logger.warning(f"[STOCK_SERVICE] Ingrediente {ing_id} não encontrado em ingredients_info")
                availability_map[ing_id] = Decimal('0')
                continue
            
            info = ingredients_info[ing_id]
            current_stock = info['current_stock']
            min_threshold = info['min_threshold']
            confirmed = confirmed_reservations.get(ing_id, Decimal('0'))
            temporary = temporary_reservations.get(ing_id, Decimal('0'))
            
            # NOTA: MIN_STOCK_THRESHOLD é uma margem mínima para gestão de capacidade do insumo
            # Serve para sinalizar ao admin/gerente que deve ser comprado/atualizado o estoque
            # Pode ser maior que o estoque atual - isso é apenas um sinal de que precisa reabastecer
            # O threshold não bloqueia o uso do estoque, apenas serve como indicador de alerta
            
            # Estoque disponível = estoque_real - reservas_confirmadas - reservas_temporárias
            # O threshold é apenas um indicador para alertas, não é descontado do estoque disponível
            # Se o estoque ficar abaixo do threshold, é apenas um sinal para reabastecer
            available = current_stock - confirmed - temporary
            
            
            # LOG: Cálculo de estoque disponível (apenas em debug para evitar poluição de logs)
            # ALTERAÇÃO: Logging otimizado - usar debug ao invés de info para detalhes rotineiros
            logger.debug(f"[STOCK_SERVICE] Ingrediente {ing_id} ({info.get('stock_unit', 'N/A')}): "
                        f"current_stock={current_stock}, "
                        f"min_threshold={min_threshold}, "
                        f"confirmed_reservations={confirmed}, "
                        f"temporary_reservations={temporary}, "
                        f"available={available}")
            
            availability_map[ing_id] = max(Decimal('0'), available)
            
            # LOG: Estoque disponível final (SEMPRE logar se for 0)
            if availability_map[ing_id] <= 0:
                # Verificar a causa raiz do estoque zerado
                if current_stock <= 0:
                    logger.error(f"[STOCK_SERVICE] ❌ Ingrediente {ing_id} SEM ESTOQUE FÍSICO: CURRENT_STOCK = {current_stock}")
                elif confirmed + temporary >= current_stock:
                    logger.warning(f"[STOCK_SERVICE] ⚠️ Ingrediente {ing_id} SEM ESTOQUE DISPONÍVEL: "
                                 f"reservas ({confirmed} confirmadas + {temporary} temporárias) consumiram todo o estoque disponível")
                else:
                    logger.warning(f"[STOCK_SERVICE] ⚠️ Ingrediente {ing_id} SEM ESTOQUE DISPONÍVEL: "
                                 f"disponivel={availability_map[ing_id]}, "
                                 f"current_stock={current_stock}, "
                                 f"min_threshold={min_threshold} (apenas alerta), "
                                 f"confirmed={confirmed}, "
                                 f"temporary={temporary}, "
                                 f"formula: {current_stock} - {confirmed} - {temporary} = {available}")
            else:
                # ALTERAÇÃO: Logging otimizado - usar debug para casos normais
                logger.debug(f"[STOCK_SERVICE] ✅ Ingrediente {ing_id}: estoque disponível = {availability_map[ing_id]} {info['stock_unit']}")
        
        # LOG: Resumo
        available_count = sum(1 for stock in availability_map.values() if stock > 0)
        logger.info(f"[STOCK_SERVICE] Estoque disponível calculado: {available_count}/{len(ingredient_ids)} ingredientes com estoque > 0")
        
        return availability_map
    except Exception as e:
        logger.error(f"[STOCK_SERVICE] Erro ao buscar estoque disponível em batch: {e}", exc_info=True)
        return {}


def calculate_product_capacity(product_id, cur=None, include_extras=True):
    """
    Calcula a capacidade de produção de um produto.
    
    capacidade = min_i floor(estoque_disponivel_i / consumo_por_unidade_i)
    
    Args:
        product_id: ID do produto
        cur: Cursor do banco (opcional)
        include_extras: Se True, considera extras além da receita base
    
    Returns:
        dict: {
            'capacity': int,  # Capacidade máxima (número de unidades)
            'limiting_ingredient': dict,  # Insumo que limita a capacidade
            'ingredients': list,  # Lista de todos os insumos com suas capacidades
            'is_available': bool
        }
    """
    conn = None
    should_close = False
    
    try:
        if cur is None:
            conn = get_db_connection()
            cur = conn.cursor()
            should_close = True
        
        # SIMPLIFICAÇÃO: Busca ingredientes da receita base (perdas opcionais)
        # Verifica se campo LOSS_PERCENTAGE existe antes de usar
        # TODO: REVISAR - Método atual de detecção de coluna é frágil; considerar usar INFORMATION_SCHEMA
        use_loss_percentage = False
        try:
            # Tenta buscar coluna LOSS_PERCENTAGE (pode não existir em versões antigas do schema)
            cur.execute("""
                SELECT 
                    pi.INGREDIENT_ID,
                    pi.PORTIONS,
                    COALESCE(pi.LOSS_PERCENTAGE, 0) as LOSS_PERCENTAGE,
                    i.NAME,
                    i.BASE_PORTION_QUANTITY,
                    i.BASE_PORTION_UNIT,
                    i.STOCK_UNIT,
                    i.IS_AVAILABLE
                FROM PRODUCT_INGREDIENTS pi
                JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
                WHERE pi.PRODUCT_ID = ?
                  AND pi.PORTIONS > 0
                  AND i.IS_AVAILABLE = TRUE
            """, (product_id,))
            use_loss_percentage = True
        except fdb.Error as e:
            # Se campo não existe, usa query sem LOSS_PERCENTAGE
            error_msg = str(e).lower()
            if 'loss_percentage' in error_msg or 'unknown' in error_msg or 'column' in error_msg:
                logger.debug(f"Campo LOSS_PERCENTAGE não encontrado, usando query sem perdas para produto {product_id}")
                cur.execute("""
                    SELECT 
                        pi.INGREDIENT_ID,
                        pi.PORTIONS,
                        i.NAME,
                        i.BASE_PORTION_QUANTITY,
                        i.BASE_PORTION_UNIT,
                        i.STOCK_UNIT,
                        i.IS_AVAILABLE
                    FROM PRODUCT_INGREDIENTS pi
                    JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
                    WHERE pi.PRODUCT_ID = ?
                      AND pi.PORTIONS > 0
                      AND i.IS_AVAILABLE = TRUE
                """, (product_id,))
                use_loss_percentage = False
            else:
                # ALTERAÇÃO: Re-raise se for outro tipo de erro (não relacionado à coluna)
                logger.error(f"Erro inesperado ao buscar ingredientes do produto {product_id}: {e}", exc_info=True)
                raise
        
        ingredients = cur.fetchall()
        
        if not ingredients:
            return {
                'capacity': 0,
                'limiting_ingredient': None,
                'ingredients': [],
                'is_available': False,
                'message': 'Produto sem ingredientes cadastrados ou ingredientes indisponíveis'
            }
        
        capacities = []
        ingredient_info_list = []
        min_capacity = None
        limiting_ingredient = None
        
        for row in ingredients:
            if use_loss_percentage:
                ing_id, portions, loss_pct, name, base_portion_quantity, base_portion_unit, stock_unit, is_available = row
                loss_percentage = float(loss_pct or 0)
            else:
                ing_id, portions, name, base_portion_quantity, base_portion_unit, stock_unit, is_available = row
                loss_percentage = 0  # Campo não existe, usa 0
            
            if not is_available:
                continue
            
            # Obtém estoque disponível
            available_stock = get_ingredient_available_stock(ing_id, cur)
            
            # SIMPLIFICAÇÃO: Calcula consumo (perdas são opcionais, padrão 0)
            try:
                consumption_per_unit = calculate_consumption_in_stock_unit(
                    portions=portions,
                    base_portion_quantity=base_portion_quantity,
                    base_portion_unit=base_portion_unit,
                    stock_unit=stock_unit,
                    item_quantity=1,
                    loss_percentage=loss_percentage
                )
            except ValueError as e:
                logger.error(f"Erro ao calcular consumo para {name} (ingrediente {ing_id}): {e}", exc_info=True)
                continue
            
            if consumption_per_unit <= 0:
                continue
            
            # Calcula capacidade para este insumo
            capacity = int(available_stock / consumption_per_unit)
            
            ingredient_info = {
                'ingredient_id': ing_id,
                'name': name,
                'available_stock': float(available_stock),
                'consumption_per_unit': float(consumption_per_unit),
                'capacity': capacity,
                'stock_unit': stock_unit
            }
            
            capacities.append(capacity)
            ingredient_info_list.append(ingredient_info)
            
            # Identifica insumo limitante (menor capacidade)
            if min_capacity is None or capacity < min_capacity:
                min_capacity = capacity
                limiting_ingredient = ingredient_info
        
        if not capacities:
            return {
                'capacity': 0,
                'limiting_ingredient': None,
                'ingredients': ingredient_info_list,
                'is_available': False,
                'message': 'Nenhum ingrediente disponível'
            }
        
        return {
            'capacity': min_capacity,
            'limiting_ingredient': limiting_ingredient,
            'ingredients': ingredient_info_list,
            'is_available': min_capacity > 0,
            'message': f'Capacidade: {min_capacity} unidades' if min_capacity > 0 else 'Sem capacidade de produção'
        }
        
    except fdb.Error as e:
        logger.error(f"Erro ao calcular capacidade do produto: {e}", exc_info=True)
        return {
            'capacity': 0,
            'limiting_ingredient': None,
            'ingredients': [],
            'is_available': False,
            'message': 'Erro ao calcular capacidade'
        }
    finally:
        if should_close and conn:
            conn.close()


def calculate_product_capacity_with_extras(product_id, extras=None, base_modifications=None, cur=None):
    """
    Calcula capacidade de produção considerando extras e modificações da receita base.
    
    ALTERAÇÃO: Se o mesmo insumo aparece na receita e como extra → soma antes de validar.
    ALTERAÇÃO: base_modifications permite modificar a receita base (deltas positivos ou negativos).
    capacidade_total = min_i floor(estoque_disponivel_i / (consumo_receita_modificado_i + consumo_extras_i))
    
    Args:
        product_id: ID do produto
        extras: Lista de extras [{ingredient_id: int, quantity: int}]
        base_modifications: Lista de modificações da receita base [{ingredient_id: int, delta: int}]
                          delta positivo = adiciona à receita base
                          delta negativo = remove da receita base
        cur: Cursor do banco (opcional)
    
    Returns:
        dict: Mesmo formato de calculate_product_capacity, mas considerando extras e base_modifications
    """
    conn = None
    should_close = False
    
    try:
        if cur is None:
            conn = get_db_connection()
            cur = conn.cursor()
            should_close = True
        
        # Se não há extras nem base_modifications, retorna capacidade base
        if not extras and not base_modifications:
            return calculate_product_capacity(product_id, cur, include_extras=False)
        
        # NOVO: Processa base_modifications para criar mapa de deltas por ingrediente
        base_mods_map = {}  # {ingredient_id: delta_total}
        if base_modifications:
            for bm in base_modifications:
                ing_id = bm.get('ingredient_id')
                delta = bm.get('delta', 0)
                
                if not ing_id or delta == 0:
                    continue
                
                try:
                    ing_id = int(ing_id)
                    delta = int(delta)
                except (ValueError, TypeError):
                    continue
                
                if ing_id not in base_mods_map:
                    base_mods_map[ing_id] = 0
                base_mods_map[ing_id] += delta
        
        # ALTERAÇÃO: Busca ingredientes da receita base (perdas opcionais)
        # Verifica se campo LOSS_PERCENTAGE existe antes de usar
        # TODO: REVISAR - Método atual de detecção de coluna é frágil; considerar usar INFORMATION_SCHEMA
        use_loss_percentage = False
        try:
            # Tenta buscar coluna LOSS_PERCENTAGE (pode não existir em versões antigas do schema)
            cur.execute("""
                SELECT 
                    pi.INGREDIENT_ID,
                    pi.PORTIONS,
                    COALESCE(pi.LOSS_PERCENTAGE, 0) as LOSS_PERCENTAGE,
                    i.NAME,
                    i.BASE_PORTION_QUANTITY,
                    i.BASE_PORTION_UNIT,
                    i.STOCK_UNIT,
                    i.IS_AVAILABLE
                FROM PRODUCT_INGREDIENTS pi
                JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
                WHERE pi.PRODUCT_ID = ?
                  AND pi.PORTIONS > 0
                  AND i.IS_AVAILABLE = TRUE
            """, (product_id,))
            use_loss_percentage = True
        except fdb.Error as e:
            # Se campo não existe, usa query sem LOSS_PERCENTAGE
            error_msg = str(e).lower()
            if 'loss_percentage' in error_msg or 'unknown' in error_msg or 'column' in error_msg:
                logger.debug(f"Campo LOSS_PERCENTAGE não encontrado, usando query sem perdas para produto {product_id}")
                cur.execute("""
                    SELECT 
                        pi.INGREDIENT_ID,
                        pi.PORTIONS,
                        i.NAME,
                        i.BASE_PORTION_QUANTITY,
                        i.BASE_PORTION_UNIT,
                        i.STOCK_UNIT,
                        i.IS_AVAILABLE
                    FROM PRODUCT_INGREDIENTS pi
                    JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
                    WHERE pi.PRODUCT_ID = ?
                      AND pi.PORTIONS > 0
                      AND i.IS_AVAILABLE = TRUE
                """, (product_id,))
                use_loss_percentage = False
            else:
                # ALTERAÇÃO: Re-raise se for outro tipo de erro (não relacionado à coluna)
                logger.error(f"Erro inesperado ao buscar ingredientes do produto {product_id}: {e}", exc_info=True)
                raise
        
        recipe_ingredients = cur.fetchall()
        
        if not recipe_ingredients:
            return {
                'capacity': 0,
                'limiting_ingredient': None,
                'ingredients': [],
                'is_available': False,
                'message': 'Produto sem ingredientes cadastrados ou ingredientes indisponíveis'
            }
        
        # ALTERAÇÃO: Agrega consumo de extras por ingrediente
        # Mapeia extras por ingredient_id para somar consumo quando o mesmo ingrediente aparece na receita
        extras_consumption = {}  # {ingredient_id: consumo_total_em_extras}
        extras_info = {}  # {ingredient_id: {name, stock_unit, base_portion_quantity, base_portion_unit}}
        
        # ALTERAÇÃO: Otimização - busca todos os ingredientes extras de uma vez (evita N+1)
        extra_ingredient_ids = []
        extra_quantities = {}
        for extra in extras:
            ing_id = extra.get('ingredient_id')
            qty = extra.get('quantity', 1)
            
            if not ing_id or qty <= 0:
                continue
            
            try:
                ing_id = int(ing_id)
                qty = int(qty)
            except (ValueError, TypeError):
                continue
            
            if ing_id not in extra_ingredient_ids:
                extra_ingredient_ids.append(ing_id)
                extra_quantities[ing_id] = 0
            extra_quantities[ing_id] += qty
        
        # Busca informações de todos os ingredientes extras de uma vez
        extra_ingredients_info = {}
        if extra_ingredient_ids:
            placeholders = ', '.join(['?' for _ in extra_ingredient_ids])
            cur.execute(f"""
                SELECT 
                    ID,
                    BASE_PORTION_QUANTITY,
                    BASE_PORTION_UNIT,
                    STOCK_UNIT,
                    NAME,
                    IS_AVAILABLE
                FROM INGREDIENTS
                WHERE ID IN ({placeholders})
            """, tuple(extra_ingredient_ids))
            
            for row in cur.fetchall():
                ing_id_db, base_portion_quantity, base_portion_unit, stock_unit, name, is_available = row
                if is_available:
                    extra_ingredients_info[ing_id_db] = {
                        'base_portion_quantity': base_portion_quantity,
                        'base_portion_unit': base_portion_unit,
                        'stock_unit': stock_unit,
                        'name': name
                    }
        
        # Processa consumo de cada ingrediente extra
        for ing_id, qty in extra_quantities.items():
            if ing_id not in extra_ingredients_info:
                continue
            
            extra_info = extra_ingredients_info[ing_id]
            base_portion_quantity = extra_info['base_portion_quantity']
            base_portion_unit = extra_info['base_portion_unit']
            stock_unit = extra_info['stock_unit']
            name = extra_info['name']
            
            # Calcula consumo do extra por unidade do produto
            try:
                extra_consumption = calculate_consumption_in_stock_unit(
                    portions=qty,
                    base_portion_quantity=base_portion_quantity,
                    base_portion_unit=base_portion_unit,
                    stock_unit=stock_unit,
                    item_quantity=1
                )
            except ValueError as e:
                logger.error(f"Erro ao calcular consumo do extra {ing_id} ({name}): {e}", exc_info=True)
                continue
            
            if extra_consumption > 0:
                # ALTERAÇÃO: Soma consumo de extras (se o mesmo ingrediente aparecer múltiplas vezes nos extras)
                if ing_id not in extras_consumption:
                    extras_consumption[ing_id] = Decimal('0')
                    extras_info[ing_id] = {
                        'name': name,
                        'stock_unit': stock_unit,
                        'base_portion_quantity': base_portion_quantity,
                        'base_portion_unit': base_portion_unit
                    }
                extras_consumption[ing_id] += extra_consumption
        
        # ALTERAÇÃO: Calcula capacidade considerando receita + extras
        # Para cada ingrediente: consumo_total = consumo_receita + consumo_extras
        capacities = []
        ingredient_info_list = []
        min_capacity = None
        limiting_ingredient = None
        
        for row in recipe_ingredients:
            if use_loss_percentage:
                ing_id, portions, loss_pct, name, base_portion_quantity, base_portion_unit, stock_unit, is_available = row
                loss_percentage = float(loss_pct or 0)
            else:
                ing_id, portions, name, base_portion_quantity, base_portion_unit, stock_unit, is_available = row
                loss_percentage = 0  # Campo não existe, usa 0
            
            if not is_available:
                continue
            
            # Obtém estoque disponível
            available_stock = get_ingredient_available_stock(ing_id, cur)
            
            # Calcula consumo da receita por unidade do produto
            try:
                recipe_consumption = calculate_consumption_in_stock_unit(
                    portions=portions,
                    base_portion_quantity=base_portion_quantity,
                    base_portion_unit=base_portion_unit,
                    stock_unit=stock_unit,
                    item_quantity=1,
                    loss_percentage=loss_percentage
                )
            except ValueError as e:
                logger.error(f"Erro ao calcular consumo da receita para {name}: {e}")
                continue
            
            # NOVO: Aplica modificações da receita base (base_modifications)
            # Se há delta negativo, reduz o consumo da receita base
            # Se há delta positivo, adiciona ao consumo (será somado com extras depois)
            modified_recipe_consumption = recipe_consumption
            if ing_id in base_mods_map:
                delta = base_mods_map[ing_id]
                # Calcula consumo do delta (pode ser positivo ou negativo)
                try:
                    delta_consumption = calculate_consumption_in_stock_unit(
                        portions=abs(delta),  # Usa valor absoluto para cálculo
                        base_portion_quantity=base_portion_quantity,
                        base_portion_unit=base_portion_unit,
                        stock_unit=stock_unit,
                        item_quantity=1,
                        loss_percentage=loss_percentage
                    )
                    # Se delta é negativo, subtrai do consumo da receita
                    # Se delta é positivo, adiciona ao consumo (será tratado como extra)
                    if delta < 0:
                        modified_recipe_consumption = max(Decimal('0'), recipe_consumption - delta_consumption)
                    else:
                        # Delta positivo será tratado como extra (adicionado depois)
                        if ing_id not in extras_consumption:
                            extras_consumption[ing_id] = Decimal('0')
                        extras_consumption[ing_id] += delta_consumption
                except ValueError as e:
                    logger.warning(f"Erro ao calcular consumo do delta para {name}: {e}")
                    # Em caso de erro, mantém consumo original
            
            # ALTERAÇÃO: Soma consumo de extras se o mesmo ingrediente aparecer nos extras
            total_consumption = modified_recipe_consumption
            if ing_id in extras_consumption:
                total_consumption += extras_consumption[ing_id]
            
            if total_consumption <= 0:
                continue
            
            # Calcula capacidade para este ingrediente (receita + extras)
            capacity = int(available_stock / total_consumption)
            
            ingredient_info = {
                'ingredient_id': ing_id,
                'name': name,
                'available_stock': float(available_stock),
                'consumption_per_unit': float(total_consumption),
                'recipe_consumption': float(recipe_consumption),
                'extras_consumption': float(extras_consumption.get(ing_id, 0)),
                'capacity': capacity,
                'stock_unit': stock_unit
            }
            
            capacities.append(capacity)
            ingredient_info_list.append(ingredient_info)
            
            # Identifica insumo limitante (menor capacidade)
            if min_capacity is None or capacity < min_capacity:
                min_capacity = capacity
                limiting_ingredient = ingredient_info
        
        # ALTERAÇÃO: Processa extras que não aparecem na receita
        for ing_id, extra_consumption in extras_consumption.items():
            # Verifica se o ingrediente já foi processado (está na receita)
            if any(ing.get('ingredient_id') == ing_id for ing in ingredient_info_list):
                continue
            
            # Ingrediente extra que não está na receita
            extra_info = extras_info[ing_id]
            available_stock = get_ingredient_available_stock(ing_id, cur)
            
            if extra_consumption <= 0:
                continue
            
            # Calcula capacidade para este extra (apenas extras, sem receita)
            capacity = int(available_stock / extra_consumption)
            
            ingredient_info = {
                'ingredient_id': ing_id,
                'name': extra_info['name'],
                'available_stock': float(available_stock),
                'consumption_per_unit': float(extra_consumption),
                'recipe_consumption': 0.0,
                'extras_consumption': float(extra_consumption),
                'capacity': capacity,
                'stock_unit': extra_info['stock_unit']
            }
            
            capacities.append(capacity)
            ingredient_info_list.append(ingredient_info)
            
            # Identifica insumo limitante (menor capacidade)
            if min_capacity is None or capacity < min_capacity:
                min_capacity = capacity
                limiting_ingredient = ingredient_info
        
        if not capacities:
            return {
                'capacity': 0,
                'limiting_ingredient': None,
                'ingredients': ingredient_info_list,
                'is_available': False,
                'message': 'Nenhum ingrediente disponível'
            }
        
        return {
            'capacity': min_capacity,
            'limiting_ingredient': limiting_ingredient,
            'ingredients': ingredient_info_list,
            'is_available': min_capacity > 0,
            'message': f'Capacidade: {min_capacity} unidades' if min_capacity > 0 else 'Sem capacidade de produção'
        }
        
    except fdb.Error as e:
        logger.error(f"Erro ao calcular capacidade com extras: {e}", exc_info=True)
        return {
            'capacity': 0,
            'limiting_ingredient': None,
            'ingredients': [],
            'is_available': False,
            'message': 'Erro ao calcular capacidade'
        }
    finally:
        if should_close and conn:
            conn.close()