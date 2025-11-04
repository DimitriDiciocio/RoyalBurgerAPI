import fdb
import logging
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
                                        stock_unit, item_quantity=1):
    """
    Calcula a quantidade consumida convertida para a unidade do estoque.
    
    Realiza conversão automática de unidades antes do cálculo.
    Exemplo: se ingrediente está em kg no estoque mas é usado em g na receita,
    converte corretamente antes de deduzir.
    
    Fórmula: portions × base_portion_quantity × item_quantity (convertido para stock_unit)
    
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
    
    Returns:
        Decimal: Quantidade consumida na unidade do estoque
    """
    # Calcula quantidade total consumida na unidade da porção base
    # Exemplo: 2 porções × 100g por porção × 3 itens = 600g
    consumption_in_portion_unit = (
        Decimal(str(portions)) * 
        Decimal(str(base_portion_quantity)) * 
        Decimal(str(item_quantity))
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
        
        # Buscar regras de ingredientes por produto com informações de unidades
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
        
        # Mapear ingredientes necessários por produto
        product_ingredients = {}
        for row in cur.fetchall():
            pid, ing_id, portions, min_q, max_q, base_qty, base_unit, stock_unit = row
            if pid not in product_ingredients:
                product_ingredients[pid] = {}
            
            product_ingredients[pid][ing_id] = {
                'portions': float(portions or 0),
                'min_quantity': int(min_q or 0),
                'max_quantity': int(max_q or 0),
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
                    # Calcula consumo convertido para unidade do estoque
                    needed = calculate_consumption_in_stock_unit(
                        portions=rule['portions'],
                        base_portion_quantity=rule['base_portion_quantity'],
                        base_portion_unit=rule['base_portion_unit'],
                        stock_unit=rule['stock_unit'],
                        item_quantity=quantity
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
                        logger.warning(f"Ingredient IDs inválidos nos extras, pulando validação")
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
                    
                    try:
                        total_extra = calculate_consumption_in_stock_unit(
                            portions=extra_qty,
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
            
            # Adicionar base_modifications (apenas deltas positivos)
            if 'base_modifications' in item and item['base_modifications']:
                # Busca informações de unidades dos base_modifications em batch
                bm_ing_ids = {bm.get('ingredient_id') for bm in item['base_modifications'] 
                             if bm.get('delta', 0) > 0 and bm.get('ingredient_id')}
                bm_info = {}
                if bm_ing_ids:
                    try:
                        bm_ing_ids = {int(bid) for bid in bm_ing_ids}
                    except (ValueError, TypeError):
                        logger.warning(f"Ingredient IDs inválidos em base_modifications, pulando validação")
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
                    if delta > 0:  # Apenas deltas positivos consomem estoque
                        ing_id = bm.get('ingredient_id')
                        if not ing_id:
                            continue
                        
                        try:
                            ing_id = int(ing_id)
                        except (ValueError, TypeError):
                            logger.warning(f"Ingredient ID inválido em base_modification: {ing_id}")
                            continue
                        
                        info = bm_info.get(ing_id, {
                            'base_portion_quantity': 1,
                            'base_portion_unit': 'un',
                            'stock_unit': 'un'
                        })
                        
                        try:
                            # DELTA é em porções, então multiplica por base_portion_quantity
                            delta_consumption = (
                                Decimal(str(delta)) * 
                                Decimal(str(info['base_portion_quantity']))
                            )
                            total_bm = _convert_unit(
                                delta_consumption,
                                info['base_portion_unit'],
                                info['stock_unit']
                            ) * Decimal(str(quantity))
                            
                            if ing_id not in required_ingredients:
                                required_ingredients[ing_id] = Decimal('0')
                            required_ingredients[ing_id] += total_bm
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


def deduct_stock_for_order(order_id):
    """Deduz o estoque dos ingredientes baseado nos produtos do pedido"""
    conn = None
    try:
        # Validação de entrada
        if not isinstance(order_id, int) or order_id <= 0:
            return (False, "VALIDATION_ERROR", "order_id deve ser um inteiro positivo")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
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
        
        conn.commit()
        
        # Verifica se algum ingrediente ficou sem estoque
        _check_and_deactivate_products(updated_ingredients, cur)
        
        # Log das alterações (substituído print por logger)
        _log_stock_changes(order_id, updated_ingredients)
        
        return (True, None, f"Estoque deduzido para {len(updated_ingredients)} ingredientes")
        
    except fdb.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"Erro ao deduzir estoque para pedido {order_id}: {e}", exc_info=True)
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    except ValueError as e:
        if conn:
            conn.rollback()
        logger.error(f"Erro de validação ao deduzir estoque para pedido {order_id}: {e}")
        return (False, "VALIDATION_ERROR", str(e))
    finally:
        if conn:
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
        
        # Busca ingredientes do produto com informações de unidades
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
        product_ingredients = cur.fetchall()
        
        # Adiciona ingredientes base do produto
        for row in product_ingredients:
            ingredient_id = row[0]
            portions = row[1] or 0
            base_portion_quantity = row[2] or 1
            base_portion_unit = row[3] or 'un'
            stock_unit = row[4] or 'un'
            
            # Calcula consumo convertido para unidade do estoque
            try:
                total_needed = calculate_consumption_in_stock_unit(
                    portions=portions,
                    base_portion_quantity=base_portion_quantity,
                    base_portion_unit=base_portion_unit,
                    stock_unit=stock_unit,
                    item_quantity=quantity
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
    """Executa as deduções de estoque"""
    updated_ingredients = []
    
    if not ingredient_deductions:
        return updated_ingredients
    
    for ingredient_id, deduction_amount in ingredient_deductions.items():
        # Busca estoque atual e limite mínimo
        cur.execute("""
            SELECT CURRENT_STOCK, MIN_STOCK_THRESHOLD, STOCK_STATUS, NAME
            FROM INGREDIENTS 
            WHERE ID = ?
        """, (ingredient_id,))
        result = cur.fetchone()
        
        if not result:
            logger.warning(f"Ingrediente {ingredient_id} não encontrado ao deduzir estoque")
            continue
            
        current_stock, min_threshold, current_status, ingredient_name = result
        
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
        
        # Verifica se há estoque suficiente
        current_stock_decimal = Decimal(str(current_stock))
        if current_stock_decimal < deduction_decimal:
            raise ValueError(
                f"Estoque insuficiente para {ingredient_name}. "
                f"Disponível: {current_stock_decimal}, Necessário: {deduction_decimal}"
            )
        
        # Calcula novo estoque (ambos Decimal agora)
        # IMPORTANTE: Sempre SUBTRAI para DEDUZIR estoque
        new_stock = current_stock_decimal - deduction_decimal
        
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
    """Determina novo status baseado no estoque"""
    new_stock_decimal = Decimal(str(new_stock))
    min_threshold_decimal = Decimal(str(min_threshold))
    
    if new_stock_decimal <= 0:
        return 'out_of_stock'
    elif new_stock_decimal <= min_threshold_decimal and current_status == 'ok':
        return 'low'
    else:
        return current_status

def _check_and_deactivate_products(updated_ingredients, cur):
    """Verifica se algum ingrediente ficou sem estoque e desativa produtos"""
    for item in updated_ingredients:
        if item['new_status'] == 'out_of_stock':
            deactivated_products = _auto_deactivate_products_for_ingredient(item['ingredient_id'], cur)
            if deactivated_products:
                product_names = [p['name'] for p in deactivated_products]
                logger.info(
                    f"Produtos desativados automaticamente devido a estoque zerado de "
                    f"{item['ingredient_name']}: {product_names}"
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
    Confirma que um ingrediente está fora de estoque e desativa produtos dependentes.
    Retorna (sucesso, produtos_desativados, error_code, mensagem)
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
        
        # Busca produtos que usam este ingrediente
        cur.execute("""
            SELECT DISTINCT P.ID, P.NAME
            FROM PRODUCTS P
            JOIN PRODUCT_INGREDIENTS PI ON P.ID = PI.PRODUCT_ID
            WHERE PI.INGREDIENT_ID = ? AND P.IS_ACTIVE = TRUE
        """, (ingredient_id,))
        
        affected_products = cur.fetchall()
        deactivated_products = []
        
        # Desativa produtos dependentes
        for product_id, product_name in affected_products:
            cur.execute("UPDATE PRODUCTS SET IS_ACTIVE = FALSE WHERE ID = ?", (product_id,))
            deactivated_products.append({
                'id': product_id,
                'name': product_name
            })
        
        conn.commit()
        
        message = f"Ingrediente '{ingredient_name}' confirmado como fora de estoque"
        if deactivated_products:
            message += f". {len(deactivated_products)} produtos foram desativados do cardápio."
        
        return (True, deactivated_products, None, message)
        
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
    Desativa automaticamente produtos que dependem de um ingrediente que ficou sem estoque.
    Retorna lista de produtos desativados.
    """
    try:
        # Busca produtos ativos que usam este ingrediente
        cursor.execute("""
            SELECT DISTINCT P.ID, P.NAME
            FROM PRODUCTS P
            JOIN PRODUCT_INGREDIENTS PI ON P.ID = PI.PRODUCT_ID
            WHERE PI.INGREDIENT_ID = ? AND P.IS_ACTIVE = TRUE
        """, (ingredient_id,))
        
        affected_products = cursor.fetchall()
        deactivated_products = []
        
        # Desativa produtos dependentes
        for product_id, product_name in affected_products:
            cursor.execute("UPDATE PRODUCTS SET IS_ACTIVE = FALSE WHERE ID = ?", (product_id,))
            deactivated_products.append({
                'id': product_id,
                'name': product_name
            })
        
        return deactivated_products
        
    except Exception as e:
        logger.error(f"Erro ao desativar produtos automaticamente para ingrediente {ingredient_id}: {e}", exc_info=True)
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
