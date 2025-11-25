from ..database import get_db_connection
from . import stock_service, promotion_service
import fdb
import logging
from decimal import Decimal
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def _validate_cart_id(cart_id):
    """Valida se cart_id é um inteiro válido e converte se necessário"""
    # Converte para inteiro se for string
    if isinstance(cart_id, str):
        try:
            cart_id = int(cart_id)
        except (ValueError, TypeError):
            raise ValueError("cart_id deve ser um número inteiro válido")
    
    # Valida se é inteiro positivo
    if not isinstance(cart_id, int) or cart_id <= 0:
        raise ValueError("cart_id deve ser um inteiro positivo")
    
    return cart_id

def _apply_promotion_to_price(product_price, promotion):
    """
    Aplica desconto de promoção ao preço do produto
    
    Args:
        product_price: Preço original do produto
        promotion: Dicionário com dados da promoção (pode ser None)
    
    Returns:
        Tuple (preco_final, valor_desconto, tem_promocao)
    """
    if not promotion:
        return (float(product_price), 0.0, False)
    
    try:
        price = float(product_price)
        discount_percentage = promotion.get('discount_percentage')
        discount_value = promotion.get('discount_value')
        
        # Aplica desconto percentual ou em valor fixo
        if discount_percentage and discount_percentage > 0:
            discount = (price * discount_percentage) / 100.0
            final_price = price - discount
        elif discount_value and discount_value > 0:
            discount = float(discount_value)
            final_price = price - discount
        else:
            return (price, 0.0, False)
        
        # Garante que o preço final não seja negativo
        final_price = max(0.0, final_price)
        return (final_price, discount, True)
    except (ValueError, TypeError, AttributeError):
        return (float(product_price), 0.0, False)

def _calculate_cart_totals(items):
    """Calcula totais do carrinho de forma centralizada"""
    total_items = sum(item["quantity"] for item in items)
    subtotal = sum(item["item_subtotal"] for item in items)
    
    # Retorna apenas subtotal - taxas e descontos são aplicados no pedido
    return {
        "total_items": total_items,
        "subtotal": subtotal,
        "total": subtotal,
        "is_empty": len(items) == 0
    }

def get_or_create_cart(user_id):
    """
    Busca o carrinho ativo do usuário ou cria um novo se não existir
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca carrinho ativo do usuário
        sql = "SELECT ID, USER_ID, CREATED_AT, UPDATED_AT FROM CARTS WHERE USER_ID = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql, (user_id,))
        row = cur.fetchone()
        
        if row:
            return {
                "id": row[0],
                "user_id": row[1],
                "created_at": row[2],
                "updated_at": row[3]
            }
        
        # Se não existe, cria um novo carrinho
        sql = "INSERT INTO CARTS (USER_ID, IS_ACTIVE) VALUES (?, TRUE) RETURNING ID;"
        cur.execute(sql, (user_id,))
        cart_id = cur.fetchone()[0]
        conn.commit()
        
        # Retorna o carrinho criado (sem query adicional desnecessária)
        return {
            "id": cart_id,
            "user_id": user_id,
            "created_at": None,  # Será preenchido em próximo acesso se necessário
            "updated_at": None
        }
        
    except fdb.Error as e:
        logger.error(f"Erro ao buscar/criar carrinho: {e}", exc_info=True)
        if conn: conn.rollback()
        return None
    finally:
        if conn: conn.close()


def get_cart_items(cart_id):
    """
    Busca todos os itens do carrinho com seus extras
    """
    conn = None
    try:
        cart_id = _validate_cart_id(cart_id)
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca itens do carrinho
        sql = """
            SELECT 
                ci.ID,
                ci.PRODUCT_ID,
                ci.QUANTITY,
                CAST(ci.NOTES AS VARCHAR(1000)) as NOTES,
                p.NAME as PRODUCT_NAME,
                p.PRICE as PRODUCT_PRICE,
                p.DESCRIPTION as PRODUCT_DESCRIPTION,
                p.IMAGE_URL as PRODUCT_IMAGE_URL,
                p.PREPARATION_TIME_MINUTES as PRODUCT_PREPARATION_TIME
            FROM CART_ITEMS ci
            JOIN PRODUCTS p ON ci.PRODUCT_ID = p.ID
            WHERE ci.CART_ID = ?
            ORDER BY ci.CREATED_AT;
        """
        cur.execute(sql, (cart_id,))
        item_rows = cur.fetchall()
        
        if not item_rows:
            return []
        
        # OTIMIZAÇÃO: Buscar todos os extras de uma vez (evita N+1 queries)
        item_ids = [row[0] for row in item_rows]
        placeholders = ', '.join(['?' for _ in item_ids])
        extras_sql = f"""
            SELECT 
                cie.CART_ITEM_ID,
                cie.ID,
                cie.INGREDIENT_ID,
                cie.QUANTITY,
                COALESCE(cie.DELTA, cie.QUANTITY) as DELTA,
                COALESCE(cie.UNIT_PRICE, COALESCE(i.ADDITIONAL_PRICE, i.PRICE)) as UNIT_PRICE,
                cie.TYPE,
                i.NAME as INGREDIENT_NAME
            FROM CART_ITEM_EXTRAS cie
            JOIN INGREDIENTS i ON cie.INGREDIENT_ID = i.ID
            WHERE cie.CART_ITEM_ID IN ({placeholders})
            ORDER BY cie.CART_ITEM_ID, cie.TYPE, i.NAME;
        """
        cur.execute(extras_sql, tuple(item_ids))
        extras_rows = cur.fetchall()
        
        # Agrupar extras por cart_item_id
        extras_by_item = {}
        for extra_row in extras_rows:
            cart_item_id = extra_row[0]
            if cart_item_id not in extras_by_item:
                extras_by_item[cart_item_id] = []
            extras_by_item[cart_item_id].append(extra_row)
        
        items = []
        for row in item_rows:
            item_id = row[0]
            product_id = row[1]
            quantity = row[2]
            notes = row[3]
            product_name = row[4]
            product_price = float(row[5]) if row[5] else 0.0
            product_description = row[6]
            product_image_url = row[7]
            product_preparation_time = int(row[8]) if row[8] else 0
            
            # Processar extras do item (já buscados em batch)
            extras = []
            extras_total = 0.0
            base_modifications = []
            base_mods_total = 0.0
            
            for extra_row in extras_by_item.get(item_id, []):
                # extra_row: [CART_ITEM_ID, ID, INGREDIENT_ID, QUANTITY, DELTA, UNIT_PRICE, TYPE, INGREDIENT_NAME]
                row_id = extra_row[1]
                ingredient_id = extra_row[2]
                extra_quantity = int(extra_row[3] or 0)  # QUANTITY é a quantidade total de extras
                delta = int(extra_row[4] or 0)  # DELTA pode ser diferente para base_modifications
                unit_price = float(extra_row[5] or 0.0)
                row_type = (extra_row[6] or 'extra').lower()
                ingredient_name = extra_row[7]

                if row_type == 'extra':
                    # CORREÇÃO: Para extras, QUANTITY é a quantidade TOTAL (não por unidade do produto)
                    # O frontend envia quantity × quantidade_produto, então já é o total
                    extras.append({
                        "id": row_id,
                        "ingredient_id": ingredient_id,
                        "quantity": extra_quantity,  # Quantidade total de extras
                        "ingredient_name": ingredient_name,
                        "ingredient_price": unit_price
                    })
                    if extra_quantity > 0:
                        # CORREÇÃO: extras_total já é o total, não precisa multiplicar pela quantidade do produto
                        extras_total += unit_price * extra_quantity
                else:  # base
                    base_modifications.append({
                        "ingredient_id": ingredient_id,
                        "delta": delta,
                        "ingredient_name": ingredient_name,
                        "ingredient_price": unit_price  # Incluir preço para exibição no mobile
                    })
                    if delta > 0:
                        base_mods_total += unit_price * delta
            
            # ALTERAÇÃO: Buscar promoção ativa para o produto
            promotion = promotion_service.get_promotion_by_product_id(product_id, include_expired=False)
            
            # ALTERAÇÃO: Aplicar desconto de promoção ao preço base do produto
            product_price_with_promotion, discount_per_unit, has_promotion = _apply_promotion_to_price(product_price, promotion)
            
            # Calcula subtotal do item
            # CORREÇÃO: extras_total já é o total de todos os extras (não por unidade)
            # Então: (preço_base_com_promocao × quantidade_produto) + extras_total + (base_mods_total × quantidade_produto)
            # base_mods_total é por unidade, então precisa multiplicar pela quantidade
            # ALTERAÇÃO: Usar preço com promoção aplicada
            item_subtotal = (product_price_with_promotion * quantity) + extras_total + (base_mods_total * quantity)
            
            item = {
                "id": item_id,
                "product_id": product_id,
                "quantity": quantity,
                "notes": notes or "",
                "product": {
                    "id": product_id,
                    "name": product_name,
                    "price": product_price,  # Preço original (sem desconto)
                    "description": product_description,
                    "image_url": product_image_url,
                    "preparation_time_minutes": product_preparation_time
                },
                "extras": extras,
                "base_modifications": base_modifications,
                "base_mods_total": base_mods_total,
                "extras_total": extras_total,
                "item_subtotal": item_subtotal,  # ALTERAÇÃO: Já inclui desconto de promoção
                # ALTERAÇÃO: Adicionar informações de promoção para o frontend
                "promotion": promotion if has_promotion else None
            }
            items.append(item)
        
        return items
        
    except fdb.Error as e:
        logger.error(f"Erro ao buscar itens do carrinho: {e}", exc_info=True)
        return []
    except ValueError as e:
        logger.warning(f"Erro de validação ao buscar itens do carrinho: {e}")
        return []
    finally:
        if conn: conn.close()


def get_active_cart_by_user_id(user_id):
    """
    Retorna o carrinho ativo do usuário (apenas metadados) ou None
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT ID FROM CARTS WHERE USER_ID = ? AND IS_ACTIVE = TRUE;", (user_id,))
        row = cur.fetchone()
        if row:
            return {"id": row[0]}
        return None
    except fdb.Error as e:
        logger.error(f"Erro ao buscar carrinho ativo do usuário: {e}", exc_info=True)
        return None
    finally:
        if conn: conn.close()


def get_guest_cart_by_id(cart_id):
    """
    Retorna o carrinho convidado (USER_ID IS NULL) se existir e estiver ativo
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT ID FROM CARTS WHERE ID = ? AND USER_ID IS NULL AND IS_ACTIVE = TRUE;", (cart_id,))
        row = cur.fetchone()
        if row:
            return {"id": row[0]}
        return None
    except fdb.Error as e:
        logger.error(f"Erro ao buscar carrinho convidado: {e}", exc_info=True)
        return None
    finally:
        if conn: conn.close()


def create_guest_cart():
    """
    Cria um novo carrinho convidado (USER_ID = NULL) ou reutiliza existente
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se já existe um carrinho de convidado ativo
        cur.execute("SELECT ID FROM CARTS WHERE USER_ID IS NULL AND IS_ACTIVE = TRUE;")
        existing_cart = cur.fetchone()
        
        if existing_cart:
            # Reutiliza carrinho existente
            return {"id": existing_cart[0]}
        
        # Se não existe, cria novo carrinho
        # Usa uma abordagem que evita conflito de constraint
        try:
            cur.execute("INSERT INTO CARTS (USER_ID, IS_ACTIVE) VALUES (NULL, TRUE) RETURNING ID;")
            cart_id = cur.fetchone()[0]
            conn.commit()
            return {"id": cart_id}
        except fdb.Error as constraint_error:
            # Se falhou por constraint, tenta buscar novamente (pode ter sido criado por outra thread)
            if constraint_error.args[1] == -803:  # Violation of PRIMARY or UNIQUE KEY constraint
                cur.execute("SELECT ID FROM CARTS WHERE USER_ID IS NULL AND IS_ACTIVE = TRUE;")
                existing_cart = cur.fetchone()
                if existing_cart:
                    return {"id": existing_cart[0]}
                else:
                    raise constraint_error
            else:
                raise constraint_error
        
    except fdb.Error as e:
        logger.error(f"Erro ao criar carrinho convidado: {e}", exc_info=True)
        if conn: conn.rollback()
        return None
    finally:
        if conn: conn.close()


def get_cart_summary(user_id):
    """
    Retorna o resumo completo do carrinho do usuário
    """
    try:
        cart = get_or_create_cart(user_id)
        if not cart:
            return None
        
        items = get_cart_items(cart["id"])
        if items is None:
            return None

        # Validação de disponibilidade
        availability_alerts = _check_availability_alerts(items)
        
        # Calcula totais usando função centralizada
        summary = _calculate_cart_totals(items)
        summary["availability_alerts"] = availability_alerts
        
        return {
            "cart": cart,
            "items": items,
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"Erro ao calcular resumo do carrinho: {e}", exc_info=True)
        return None

def _check_availability_alerts(items):
    """Verifica alertas de disponibilidade de forma centralizada"""
    if not items:
        return []
    
    availability_alerts = []
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # OTIMIZAÇÃO: Coletar todos os product_ids e ingredient_ids de uma vez
        product_ids = [item["product_id"] for item in items]
        extra_ingredient_ids = set()
        for item in items:
            for extra in item.get("extras", []):
                extra_ingredient_ids.add(extra["ingredient_id"])
        
        # OTIMIZAÇÃO: Query única para ingredientes base de todos os produtos
        base_availability = {}
        if product_ids:
            placeholders = ', '.join(['?' for _ in product_ids])
            base_query = f"""
                SELECT pi.PRODUCT_ID, i.ID, i.IS_AVAILABLE
                FROM PRODUCT_INGREDIENTS pi
                JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
                WHERE pi.PRODUCT_ID IN ({placeholders})
            """
            cur.execute(base_query, tuple(product_ids))
            for row in cur.fetchall():
                product_id, ing_id, is_av = row
                base_availability[(product_id, ing_id)] = is_av
        
        # OTIMIZAÇÃO: Query única para extras
        extra_availability = {}
        if extra_ingredient_ids:
            placeholders = ', '.join(['?' for _ in extra_ingredient_ids])
            extra_query = f"""
                SELECT ID, IS_AVAILABLE
                FROM INGREDIENTS
                WHERE ID IN ({placeholders})
            """
            cur.execute(extra_query, tuple(extra_ingredient_ids))
            for row in cur.fetchall():
                extra_availability[row[0]] = row[1]
        
        # OTIMIZAÇÃO: Processar resultados em memória
        for item in items:
            product_id = item["product_id"]
            
            # Verificar ingredientes base do produto
            for (prod_id, ing_id), is_av in base_availability.items():
                if prod_id == product_id and not is_av:
                    availability_alerts.append({
                        "product_id": product_id,
                        "ingredient_id": ing_id,
                        "issue": "ingredient_unavailable"
                    })
            
            # Verificar extras
            for extra in item.get("extras", []):
                ing_id = extra["ingredient_id"]
                if not extra_availability.get(ing_id, True):
                    availability_alerts.append({
                        "product_id": product_id,
                        "ingredient_id": ing_id,
                        "issue": "extra_unavailable"
                    })
    except Exception as e:
        logger.error(f"Erro ao verificar disponibilidade: {e}", exc_info=True)
    finally:
        if conn: conn.close()
    
    return availability_alerts


def add_item_to_cart(user_id, product_id, quantity, extras=None, notes=None, base_modifications=None):
    """
    Adiciona um item ao carrinho do usuário
    """
    conn = None
    try:
        # Validações de limites de segurança
        if quantity <= 0 or quantity > 999:
            return (False, "INVALID_QUANTITY", "Quantidade deve estar entre 1 e 999")
        
        if extras and len(extras) > 50:
            return (False, "TOO_MANY_EXTRAS", "Número máximo de extras por item: 50")
        
        if base_modifications and len(base_modifications) > 50:
            return (False, "TOO_MANY_MODIFICATIONS", "Número máximo de modificações: 50")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca ou cria carrinho
        cart = get_or_create_cart(user_id)
        if not cart:
            return (False, "CART_ERROR", "Erro ao acessar carrinho")
        
        cart_id = cart["id"]
        
        # Valida limite de itens no carrinho
        cur.execute("SELECT COUNT(*) FROM CART_ITEMS WHERE CART_ID = ?;", (cart_id,))
        item_count = cur.fetchone()[0]
        if item_count >= 100:
            return (False, "CART_FULL", "Carrinho cheio. Máximo de 100 itens diferentes")
        
        # Verifica se produto existe e está ativo
        sql = "SELECT ID, NAME, PRICE FROM PRODUCTS WHERE ID = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql, (product_id,))
        product = cur.fetchone()
        if not product:
            return (False, "PRODUCT_NOT_FOUND", "Produto não encontrado ou inativo")
        
        # OTIMIZAÇÃO DE PERFORMANCE: Busca regras do produto uma única vez
        # e valida estoque do produto antes de validar extras
        rules = _get_product_rules(cur, product_id)
        
        # Verifica estoque suficiente para o produto
        # ALTERAÇÃO: Passa cart_id para excluir reservas temporárias do próprio carrinho
        stock_check = _check_product_stock_availability(cur, product_id, quantity, cart_id=cart_id)
        if not stock_check[0]:
            return (False, "INSUFFICIENT_STOCK", stock_check[1])
        
        # OTIMIZAÇÃO DE PERFORMANCE: Inicializa variáveis para reutilização
        ingredient_names = {}
        ingredient_availability = {}
        
        # OTIMIZAÇÃO DE PERFORMANCE: Valida extras em batch ao invés de loop individual
        # Verifica e valida extras conforme regras do produto (PORTIONS=0, min/max)
        if extras:
            # Coleta todos os IDs de ingredientes primeiro
            extra_ingredient_ids = [extra.get("ingredient_id") for extra in extras if extra.get("ingredient_id")]
            
            # Busca disponibilidade de todos os ingredientes de uma vez (1 query ao invés de N)
            ingredient_availability = _batch_get_ingredient_availability(extra_ingredient_ids, quantity, cur)
            
            # Busca nomes de ingredientes de uma vez para mensagens de erro
            if extra_ingredient_ids:
                placeholders = ', '.join(['?' for _ in extra_ingredient_ids])
                cur.execute(f"SELECT ID, NAME FROM INGREDIENTS WHERE ID IN ({placeholders})", tuple(extra_ingredient_ids))
                for row in cur.fetchall():
                    ingredient_names[row[0]] = row[1]
            
            # Valida cada extra usando dados já carregados em batch
            for extra in extras:
                ing_id = extra.get("ingredient_id")
                qty = int(extra.get("quantity", 1))
                rule = rules.get(ing_id)
                
                # CORREÇÃO: Se o ingrediente não está nas regras do produto, verifica se ele existe e está disponível
                # Permite adicionar ingredientes que não estão cadastrados como extras do produto
                # (desde que não sejam da receita base)
                if not rule:
                    # Verifica se o ingrediente existe e está disponível
                    if ing_id not in ingredient_names:
                        return (False, "EXTRA_NOT_ALLOWED", f"Ingrediente ID {ing_id} não encontrado")
                    # Se não está nas regras, assume que pode ser adicionado como extra (portions=0)
                    # Usa valores padrão: min=0, max=None (sem limite de regra)
                    min_q = 0
                    max_q_rule = None
                else:
                    # Se está nas regras, verifica se não é da receita base
                    if float(rule["portions"]) != 0.0:
                        return (False, "EXTRA_NOT_ALLOWED", "Um dos extras selecionados já faz parte da receita base")
                    min_q = int(rule["min_quantity"] or 0)
                    max_q_rule = int(rule["max_quantity"]) if rule["max_quantity"] else None
                
                # Obtém disponibilidade do cache em memória (já carregado em batch)
                max_available_info = ingredient_availability.get(ing_id)
                if not max_available_info:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Ingrediente '{ing_name}' não encontrado ou indisponível")
                
                max_q_available = max_available_info['max_available']
                
                # Aplica limite da regra se existir
                if max_q_rule is not None and max_q_rule > 0:
                    max_q_available = min(max_q_rule, max_q_available)
                    # Atualiza limited_by se necessário
                    if max_q_available == max_q_rule and max_available_info['max_available'] > max_q_rule:
                        max_available_info['limited_by'] = 'rule'
                
                # Valida quantidade mínima
                if qty < min_q:
                    return (False, "EXTRA_OUT_OF_RANGE", 
                           f"Quantidade de extra abaixo do mínimo permitido [{min_q}]")
                
                # IMPORTANTE: qty é a quantidade TOTAL (incluindo min_quantity)
                # max_q_available é a quantidade máxima de EXTRAS disponíveis (sem incluir min_quantity)
                # Então a quantidade total máxima permitida é: min_q + max_q_available
                max_total_qty = min_q + max_q_available
                
                # Valida quantidade máxima (considerando estoque)
                # Se max_q_available > 0, há estoque para extras adicionais
                if max_q_available > 0 and qty > max_total_qty:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "EXTRA_OUT_OF_RANGE", 
                           f"Quantidade de extra excede o disponível. "
                           f"Máximo permitido: {max_total_qty} (mínimo: {min_q} + extras: {max_q_available}) "
                           f"(limitado por {'regra' if max_available_info['limited_by'] == 'rule' else 'estoque'})")
                
                # Verifica se ingrediente está disponível
                # Se max_q_available é 0, não há estoque para extras adicionais (mas pode ter min_q > 0)
                # Se não tem stock_info, ingrediente não está disponível
                if not max_available_info['stock_info']:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Ingrediente '{ing_name}' não disponível ou sem estoque")
                
                # Se max_q_available é 0 e qty > min_q, não há estoque suficiente
                if max_q_available == 0 and qty > min_q:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Ingrediente '{ing_name}' não tem estoque suficiente para a quantidade solicitada. "
                           f"Máximo permitido: {min_q}")
                
                # Verifica estoque suficiente para a quantidade solicitada com conversão de unidades
                stock_info = max_available_info['stock_info']
                base_portion_quantity = stock_info['base_portion_quantity']
                base_portion_unit = stock_info['base_portion_unit']
                stock_unit = stock_info['stock_unit']
                current_stock = stock_info['current_stock']
                
                # Calcula consumo convertido para unidade do estoque
                try:
                    required_quantity = stock_service.calculate_consumption_in_stock_unit(
                        portions=qty,
                        base_portion_quantity=float(base_portion_quantity),
                        base_portion_unit=str(base_portion_unit),
                        stock_unit=str(stock_unit),
                        item_quantity=quantity
                    )
                except ValueError as e:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Erro na conversão de unidades para '{ing_name}': {str(e)}")
                
                # Compara com estoque disponível
                if current_stock < required_quantity:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Estoque insuficiente para extra '{ing_name}'. "
                           f"Necessário: {required_quantity:.3f} {stock_unit}, "
                           f"Disponível: {current_stock:.3f} {stock_unit}")
        
        # OTIMIZAÇÃO DE PERFORMANCE: Verifica item existente antes de validar estoque novamente
        # Isso evita validações duplicadas de estoque
        existing_item_id = find_identical_cart_item(cart_id, product_id, extras or [], notes or "", base_modifications or [])
        
        if existing_item_id:
            # NOVA VALIDAÇÃO: Busca quantidade atual do item antes de incrementar
            cur.execute("SELECT QUANTITY FROM CART_ITEMS WHERE ID = ?", (existing_item_id,))
            existing_row = cur.fetchone()
            if existing_row:
                existing_quantity = existing_row[0]
                new_total_quantity = existing_quantity + quantity
                
                # OTIMIZAÇÃO: Valida estoque apenas para a quantidade adicional (não recalcula tudo)
                # Isso evita validar novamente o que já estava no carrinho
                # ALTERAÇÃO: Passa cart_id para excluir reservas temporárias do próprio carrinho
                stock_check_additional = _check_product_stock_availability(cur, product_id, quantity, cart_id=cart_id)  # Apenas quantidade adicional
                if not stock_check_additional[0]:
                    return (False, "INSUFFICIENT_STOCK", stock_check_additional[1])
                
                # OTIMIZAÇÃO: Valida estoque para extras com a nova quantidade total em batch
                # Reutiliza ingredient_availability se já foi carregado, senão busca novamente
                if extras:
                    # Recoleta IDs se necessário (pode não estar definido no escopo atual)
                    extra_ingredient_ids = [extra.get("ingredient_id") for extra in extras if extra.get("ingredient_id")]
                    if extra_ingredient_ids:
                        # Revalida disponibilidade com a nova quantidade total
                        # ALTERAÇÃO: Passa cart_id para excluir reservas temporárias do próprio carrinho
                        ingredient_availability_total = _batch_get_ingredient_availability(extra_ingredient_ids, new_total_quantity, cur, cart_id=cart_id)
                        
                        # Reutiliza ingredient_names se já foi carregado
                        for extra in extras:
                            ing_id = extra.get("ingredient_id")
                            qty = int(extra.get("quantity", 1))
                            rule = rules.get(ing_id)
                            max_q_rule = int(rule["max_quantity"]) if rule and rule.get("max_quantity") else None
                            
                            # Obtém disponibilidade do cache em memória
                            max_available_info = ingredient_availability_total.get(ing_id)
                            if not max_available_info or not max_available_info.get('stock_info'):
                                ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                                return (False, "INSUFFICIENT_STOCK", 
                                       f"Ingrediente '{ing_name}' não disponível ou sem estoque")
                            
                            # Aplica limite da regra
                            max_q_available = max_available_info['max_available']
                            if max_q_rule is not None and max_q_rule > 0:
                                max_q_available = min(max_q_rule, max_q_available)
                            
                            stock_info = max_available_info['stock_info']
                            base_portion_quantity = stock_info['base_portion_quantity']
                            base_portion_unit = stock_info['base_portion_unit']
                            stock_unit = stock_info['stock_unit']
                            current_stock = stock_info['current_stock']
                            
                            # CORREÇÃO: qty é o total de extras, dividir pela quantidade do produto para obter porções por unidade
                            # Porque calculate_consumption_in_stock_unit espera porções por unidade
                            portions_por_unidade = qty / new_total_quantity if new_total_quantity > 0 else qty
                            
                            # Calcula consumo para a NOVA quantidade total
                            try:
                                required_quantity_total = stock_service.calculate_consumption_in_stock_unit(
                                    portions=portions_por_unidade,
                                    base_portion_quantity=float(base_portion_quantity),
                                    base_portion_unit=str(base_portion_unit),
                                    stock_unit=str(stock_unit),
                                    item_quantity=new_total_quantity  # ← Usa quantidade total
                                )
                            except ValueError as e:
                                ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                                return (False, "INSUFFICIENT_STOCK", 
                                       f"Erro na conversão de unidades para extra '{ing_name}': {str(e)}")
                            
                            # Compara com estoque disponível
                            if current_stock < required_quantity_total:
                                ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                                return (False, "INSUFFICIENT_STOCK", 
                                       f"Estoque insuficiente para extra '{ing_name}'. "
                                       f"Necessário: {required_quantity_total:.3f} {stock_unit}, "
                                       f"Disponível: {current_stock:.3f} {stock_unit}")
            
            # Incrementa quantidade do item existente
            sql = "UPDATE CART_ITEMS SET QUANTITY = QUANTITY + ? WHERE ID = ?;"
            cur.execute(sql, (quantity, existing_item_id))
            
            # NOVA INTEGRAÇÃO: Recria reservas temporárias para todo o carrinho
            # (porque a quantidade foi atualizada, precisa recalcular todas as reservas)
            # Busca user_id do carrinho
            cur.execute("SELECT USER_ID FROM CARTS WHERE ID = ?", (cart_id,))
            cart_user_row = cur.fetchone()
            cart_user_id = cart_user_row[0] if cart_user_row else user_id
            
            success, error_code, message = _recreate_temporary_reservations_for_cart(
                cart_id=cart_id,
                user_id=cart_user_id,
                cur=cur
            )
            
            if not success:
                conn.rollback()
                return (False, error_code, message)
        else:
            # Cria novo item
            sql = "INSERT INTO CART_ITEMS (CART_ID, PRODUCT_ID, QUANTITY, NOTES) VALUES (?, ?, ?, ?) RETURNING ID;"
            cur.execute(sql, (cart_id, product_id, quantity, notes))
            new_item_id = cur.fetchone()[0]
            
            # OTIMIZAÇÃO: Busca preços de ingredientes em batch ao invés de queries individuais
            # Adiciona extras se fornecidos (TYPE='extra')
            # IMPORTANTE: Inserir extras e base_modifications ANTES de criar reservas temporárias
            if extras:
                logger.info(f"[add_item_to_cart] Processando {len(extras)} extras para item {new_item_id}")
                # Coleta IDs de ingredientes e busca preços de uma vez
                extra_ingredient_ids = [ex.get("ingredient_id") for ex in extras if ex.get("ingredient_id")]
                ingredient_prices = {}
                if extra_ingredient_ids:
                    placeholders = ', '.join(['?' for _ in extra_ingredient_ids])
                    cur.execute(
                        f"SELECT ID, COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID IN ({placeholders}) AND IS_AVAILABLE = TRUE;",
                        tuple(extra_ingredient_ids)
                    )
                    for row in cur.fetchall():
                        ingredient_prices[row[0]] = float(row[1] or 0.0)
                
                # Insere extras usando preços já carregados
                extras_inserted = 0
                for extra in extras:
                    ingredient_id = extra.get("ingredient_id")
                    extra_quantity = int(extra.get("quantity", 1))
                    
                    # IMPORTANTE: Valida quantidade antes de inserir
                    if extra_quantity <= 0:
                        logger.warning(f"[add_item_to_cart] Extra com quantidade inválida: ingredient_id={ingredient_id}, qty={extra_quantity}, extra_data={extra}")
                        continue
                    
                    # CORREÇÃO: Busca preço mesmo se não estava no batch inicial (para ingredientes não cadastrados como extras)
                    unit_price = ingredient_prices.get(ingredient_id, 0.0)
                    if unit_price == 0.0:
                        # Tenta buscar preço diretamente do banco
                        cur.execute(
                            "SELECT COALESCE(ADDITIONAL_PRICE, PRICE, 0) FROM INGREDIENTS WHERE ID = ? AND IS_AVAILABLE = TRUE",
                            (ingredient_id,)
                        )
                        price_row = cur.fetchone()
                        if price_row:
                            unit_price = float(price_row[0] or 0.0)
                            ingredient_prices[ingredient_id] = unit_price  # Adiciona ao cache
                    
                    if unit_price > 0:  # Só insere se ingrediente existe e tem preço
                        sql_extra = (
                            "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) "
                            "VALUES (?, ?, ?, 'extra', ?, ?);"
                        )
                        cur.execute(sql_extra, (new_item_id, ingredient_id, extra_quantity, extra_quantity, unit_price))
                        extras_inserted += 1
                        logger.info(f"[add_item_to_cart] Extra inserido: item_id={new_item_id}, ingredient_id={ingredient_id}, quantity={extra_quantity}, price={unit_price}")
                    else:
                        logger.warning(f"[add_item_to_cart] Extra não inserido - preço zero ou ingrediente não encontrado: ingredient_id={ingredient_id}, unit_price={unit_price}, quantity={extra_quantity}")
                
                logger.info(f"[add_item_to_cart] Total de extras inseridos: {extras_inserted} de {len(extras)}")

            # Adiciona modificações de base (TYPE='base')
            if base_modifications:
                rules = _get_product_rules(cur, product_id)
                # OTIMIZAÇÃO: Busca preços de ingredientes de base em batch
                base_mod_ingredient_ids = []
                base_mod_deltas = {}
                for bm in base_modifications:
                    try:
                        ing_id = int(bm.get("ingredient_id"))
                        delta = int(bm.get("delta", 0))
                        rule = rules.get(ing_id)
                        if rule and float(rule["portions"]) != 0.0 and delta != 0:
                            base_mod_ingredient_ids.append(ing_id)
                            base_mod_deltas[ing_id] = delta
                    except (ValueError, TypeError, AttributeError):
                        continue
                
                # VALIDAÇÃO: Verifica estoque para base_modifications antes de inserir
                if base_mod_ingredient_ids:
                    # Busca nomes de ingredientes e base_portions para mensagens de erro
                    placeholders = ', '.join(['?' for _ in base_mod_ingredient_ids])
                    cur.execute(f"SELECT ID, NAME FROM INGREDIENTS WHERE ID IN ({placeholders})", tuple(base_mod_ingredient_ids))
                    base_mod_names = {}
                    for row in cur.fetchall():
                        base_mod_names[row[0]] = row[1]
                    
                    # Busca base_portions de cada ingrediente na receita base
                    base_portions_map = {}
                    placeholders = ', '.join(['?' for _ in base_mod_ingredient_ids])
                    cur.execute(f"""
                        SELECT INGREDIENT_ID, PORTIONS
                        FROM PRODUCT_INGREDIENTS
                        WHERE PRODUCT_ID = ? AND INGREDIENT_ID IN ({placeholders})
                    """, (product_id, *base_mod_ingredient_ids))
                    for row in cur.fetchall():
                        base_portions_map[row[0]] = float(row[1] or 0)
                    
                    # Busca informações de estoque de todos os ingredientes de base_modifications de uma vez
                    from .product_service import get_ingredient_max_available_quantity
                    from .stock_service import get_ingredient_available_stock
                    
                    # Valida cada base_modification
                    for ing_id in base_mod_ingredient_ids:
                        delta = base_mod_deltas[ing_id]
                        # Apenas deltas positivos consomem estoque
                        if delta <= 0:
                            continue
                        
                        # Busca informações do ingrediente
                        cur.execute("""
                            SELECT BASE_PORTION_QUANTITY, BASE_PORTION_UNIT, STOCK_UNIT, IS_AVAILABLE
                            FROM INGREDIENTS
                            WHERE ID = ?
                        """, (ing_id,))
                        ing_row = cur.fetchone()
                        if not ing_row or not ing_row[3]:  # IS_AVAILABLE
                            ing_name = base_mod_names.get(ing_id, 'Ingrediente')
                            return (False, "INSUFFICIENT_STOCK", 
                                   f"Ingrediente '{ing_name}' não disponível")
                        
                        base_portion_quantity = float(ing_row[0] or 1)
                        base_portion_unit = str(ing_row[1] or 'un')
                        stock_unit = str(ing_row[2] or 'un')
                        
                        # Obtém estoque disponível (considerando reservas temporárias)
                        # ALTERAÇÃO: Passa cart_id para excluir reservas temporárias do próprio carrinho
                        # ALTERAÇÃO CRÍTICA: exclude_confirmed_reservations=True para não subtrair reservas confirmadas
                        # Reservas confirmadas não devem bloquear adição ao carrinho
                        available_stock = get_ingredient_available_stock(
                            ing_id, 
                            cur, 
                            exclude_cart_id=cart_id,
                            exclude_confirmed_reservations=True
                        )
                        if not isinstance(available_stock, Decimal):
                            available_stock = Decimal(str(available_stock or 0))
                        
                        # Calcula consumo convertido para unidade do estoque
                        # Para base_modifications, delta é em porções por unidade
                        # O consumo total é: delta × BASE_PORTION_QUANTITY × quantity
                        try:
                            required_quantity = stock_service.calculate_consumption_in_stock_unit(
                                portions=delta,
                                base_portion_quantity=base_portion_quantity,
                                base_portion_unit=base_portion_unit,
                                stock_unit=stock_unit,
                                item_quantity=quantity
                            )
                        except ValueError as e:
                            ing_name = base_mod_names.get(ing_id, 'Ingrediente')
                            return (False, "INSUFFICIENT_STOCK", 
                                   f"Erro na conversão de unidades para '{ing_name}': {str(e)}")
                        
                        # Compara com estoque disponível
                        if available_stock < required_quantity:
                            ing_name = base_mod_names.get(ing_id, 'Ingrediente')
                            return (False, "INSUFFICIENT_STOCK", 
                                   f"Estoque insuficiente de '{ing_name}'. "
                                   f"Necessário: {required_quantity:.3f} {stock_unit}, "
                                   f"Disponível: {available_stock:.3f} {stock_unit}")
                
                base_mod_prices = {}
                if base_mod_ingredient_ids:
                    placeholders = ', '.join(['?' for _ in base_mod_ingredient_ids])
                    cur.execute(
                        f"SELECT ID, COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID IN ({placeholders}) AND IS_AVAILABLE = TRUE;",
                        tuple(base_mod_ingredient_ids)
                    )
                    for row in cur.fetchall():
                        base_mod_prices[row[0]] = float(row[1] or 0.0)
                
                # Insere modificações de base usando preços já carregados
                for bm in base_modifications:
                    try:
                        ing_id = int(bm.get("ingredient_id"))
                        delta = int(bm.get("delta", 0))
                    except (ValueError, TypeError, AttributeError):
                        continue
                    rule = rules.get(ing_id)
                    if not rule or float(rule["portions"]) == 0.0 or delta == 0:
                        continue
                    
                    unit_price = base_mod_prices.get(ing_id, 0.0)
                    if unit_price >= 0:  # Permite preço zero
                        cur.execute(
                            "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) VALUES (?, ?, 0, 'base', ?, ?);",
                            (new_item_id, ing_id, delta, unit_price)
                        )
            
            # NOVA INTEGRAÇÃO: Cria reservas temporárias para o novo item APÓS inserir todos os dados
            # (extras e base_modifications já foram inseridos)
            success, error_code, message, reservation_ids = _create_temporary_reservations_for_item(
                cart_id=cart_id,
                product_id=product_id,
                quantity=quantity,
                extras=extras,
                base_modifications=base_modifications,
                user_id=user_id,
                cur=cur
            )
            
            if not success:
                # Erro ao criar reservas - remove o item criado e retorna erro
                cur.execute("DELETE FROM CART_ITEM_EXTRAS WHERE CART_ITEM_ID = ?", (new_item_id,))
                cur.execute("DELETE FROM CART_ITEMS WHERE ID = ?", (new_item_id,))
                conn.rollback()
                return (False, error_code, message)
        
        conn.commit()
        return (True, None, "Item adicionado ao carrinho com sucesso")
        
    except fdb.Error as e:
        logger.error(f"Erro ao adicionar item ao carrinho: {e}", exc_info=True)
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def add_item_to_cart_by_cart_id(cart_id, product_id, quantity, extras=None, notes=None, base_modifications=None):
    """
    Adiciona item ao carrinho identificado por cart_id (convidado)
    """
    conn = None
    try:
        # Validações de limites de segurança
        if quantity <= 0 or quantity > 999:
            return (False, "INVALID_QUANTITY", "Quantidade deve estar entre 1 e 999")
        
        if extras and len(extras) > 50:
            return (False, "TOO_MANY_EXTRAS", "Número máximo de extras por item: 50")
        
        if base_modifications and len(base_modifications) > 50:
            return (False, "TOO_MANY_MODIFICATIONS", "Número máximo de modificações: 50")
        
        # Valida e converte cart_id
        cart_id = _validate_cart_id(cart_id)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Valida limite de itens no carrinho
        cur.execute("SELECT COUNT(*) FROM CART_ITEMS WHERE CART_ID = ?;", (cart_id,))
        item_count = cur.fetchone()[0]
        if item_count >= 100:
            return (False, "CART_FULL", "Carrinho cheio. Máximo de 100 itens diferentes")

        # Verifica existência do carrinho convidado ativo
        cur.execute("SELECT ID FROM CARTS WHERE ID = ? AND USER_ID IS NULL AND IS_ACTIVE = TRUE;", (cart_id,))
        if not cur.fetchone():
            return (False, "CART_NOT_FOUND", "Carrinho convidado não encontrado")

        # Verifica se produto existe e está ativo
        sql = "SELECT ID, NAME, PRICE FROM PRODUCTS WHERE ID = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql, (product_id,))
        product = cur.fetchone()
        if not product:
            return (False, "PRODUCT_NOT_FOUND", "Produto não encontrado ou inativo")

        # Verifica estoque suficiente para o produto
        # ALTERAÇÃO: Passa cart_id para excluir reservas temporárias do próprio carrinho
        stock_check = _check_product_stock_availability(cur, product_id, quantity, cart_id=cart_id)
        if not stock_check[0]:
            return (False, "INSUFFICIENT_STOCK", stock_check[1])

        # OTIMIZAÇÃO DE PERFORMANCE: Valida extras em batch ao invés de loop individual
        # Verifica e valida extras conforme regras do produto (PORTIONS=0, min/max)
        rules = _get_product_rules(cur, product_id)
        
        if extras:
            # Coleta todos os IDs de ingredientes primeiro
            extra_ingredient_ids = [extra.get("ingredient_id") for extra in extras if extra.get("ingredient_id")]
            
            # Busca disponibilidade de todos os ingredientes de uma vez (1 query ao invés de N)
            # ALTERAÇÃO: Passa cart_id para excluir reservas temporárias do próprio carrinho
            ingredient_availability = _batch_get_ingredient_availability(extra_ingredient_ids, quantity, cur, cart_id=cart_id)
            
            # Busca nomes de ingredientes de uma vez para mensagens de erro
            ingredient_names = {}
            if extra_ingredient_ids:
                placeholders = ', '.join(['?' for _ in extra_ingredient_ids])
                cur.execute(f"SELECT ID, NAME FROM INGREDIENTS WHERE ID IN ({placeholders})", tuple(extra_ingredient_ids))
                for row in cur.fetchall():
                    ingredient_names[row[0]] = row[1]
            
            # Valida cada extra usando dados já carregados em batch
            for extra in extras:
                ing_id = extra.get("ingredient_id")
                qty = int(extra.get("quantity", 1))
                rule = rules.get(ing_id)
                if not rule:
                    return (False, "EXTRA_NOT_ALLOWED", "Um ou mais extras não são permitidos para este produto")
                if float(rule["portions"]) != 0.0:
                    return (False, "EXTRA_NOT_ALLOWED", "Um dos extras selecionados já faz parte da receita base")
                min_q = int(rule["min_quantity"] or 0)
                max_q_rule = int(rule["max_quantity"]) if rule["max_quantity"] else None
                
                # Obtém disponibilidade do cache em memória (já carregado em batch)
                max_available_info = ingredient_availability.get(ing_id)
                if not max_available_info:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Ingrediente '{ing_name}' não encontrado ou indisponível")
                
                max_q_available = max_available_info['max_available']
                
                # Aplica limite da regra se existir
                if max_q_rule is not None and max_q_rule > 0:
                    max_q_available = min(max_q_rule, max_q_available)
                    # Atualiza limited_by se necessário
                    if max_q_available == max_q_rule and max_available_info['max_available'] > max_q_rule:
                        max_available_info['limited_by'] = 'rule'
                
                # Valida quantidade mínima
                if qty < min_q:
                    return (False, "EXTRA_OUT_OF_RANGE", 
                           f"Quantidade de extra abaixo do mínimo permitido [{min_q}]")
                
                # IMPORTANTE: qty é a quantidade TOTAL (incluindo min_quantity)
                # max_q_available é a quantidade máxima de EXTRAS disponíveis (sem incluir min_quantity)
                # Então a quantidade total máxima permitida é: min_q + max_q_available
                max_total_qty = min_q + max_q_available
                
                # Valida quantidade máxima (considerando estoque)
                # Se max_q_available > 0, há estoque para extras adicionais
                if max_q_available > 0 and qty > max_total_qty:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "EXTRA_OUT_OF_RANGE", 
                           f"Quantidade de extra excede o disponível. "
                           f"Máximo permitido: {max_total_qty} (mínimo: {min_q} + extras: {max_q_available}) "
                           f"(limitado por {'regra' if max_available_info['limited_by'] == 'rule' else 'estoque'})")
                
                # Verifica se ingrediente está disponível
                # Se max_q_available é 0, não há estoque para extras adicionais (mas pode ter min_q > 0)
                # Se não tem stock_info, ingrediente não está disponível
                if not max_available_info['stock_info']:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Ingrediente '{ing_name}' não disponível ou sem estoque")
                
                # Se max_q_available é 0 e qty > min_q, não há estoque suficiente
                if max_q_available == 0 and qty > min_q:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Ingrediente '{ing_name}' não tem estoque suficiente para a quantidade solicitada. "
                           f"Máximo permitido: {min_q}")
                
                # Verifica estoque suficiente para a quantidade solicitada com conversão de unidades
                stock_info = max_available_info['stock_info']
                base_portion_quantity = stock_info['base_portion_quantity']
                base_portion_unit = stock_info['base_portion_unit']
                stock_unit = stock_info['stock_unit']
                current_stock = stock_info['current_stock']
                
                # Calcula consumo convertido para unidade do estoque
                try:
                    required_quantity = stock_service.calculate_consumption_in_stock_unit(
                        portions=qty,
                        base_portion_quantity=float(base_portion_quantity),
                        base_portion_unit=str(base_portion_unit),
                        stock_unit=str(stock_unit),
                        item_quantity=quantity
                    )
                except ValueError as e:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Erro na conversão de unidades para '{ing_name}': {str(e)}")
                
                # Compara com estoque disponível
                if current_stock < required_quantity:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Estoque insuficiente para extra '{ing_name}'. "
                           f"Necessário: {required_quantity:.3f} {stock_unit}, "
                           f"Disponível: {current_stock:.3f} {stock_unit}")

        # Verifica item idêntico (inclui base_mods)
        existing_item_id = find_identical_cart_item(cart_id, product_id, extras or [], notes or "", base_modifications or [])

        if existing_item_id:
            # NOVA VALIDAÇÃO: Busca quantidade atual do item antes de incrementar
            cur.execute("SELECT QUANTITY FROM CART_ITEMS WHERE ID = ?", (existing_item_id,))
            existing_row = cur.fetchone()
            if existing_row:
                existing_quantity = existing_row[0]
                new_total_quantity = existing_quantity + quantity
                
                # Valida estoque para a nova quantidade total do produto
                # ALTERAÇÃO: Passa cart_id para excluir reservas temporárias do próprio carrinho
                stock_check_total = _check_product_stock_availability(cur, product_id, new_total_quantity, cart_id=cart_id)
                if not stock_check_total[0]:
                    return (False, "INSUFFICIENT_STOCK", stock_check_total[1])
                
                # OTIMIZAÇÃO: Valida estoque para extras com a nova quantidade total em batch
                if extras:
                    # Revalida disponibilidade com a nova quantidade total
                    extra_ingredient_ids = [extra.get("ingredient_id") for extra in extras if extra.get("ingredient_id")]
                    # ALTERAÇÃO: Passa cart_id para excluir reservas temporárias do próprio carrinho
                    ingredient_availability_total = _batch_get_ingredient_availability(extra_ingredient_ids, new_total_quantity, cur, cart_id=cart_id)
                    
                    # Busca nomes de ingredientes de uma vez
                    ingredient_names = {}
                    if extra_ingredient_ids:
                        placeholders = ', '.join(['?' for _ in extra_ingredient_ids])
                        cur.execute(f"SELECT ID, NAME FROM INGREDIENTS WHERE ID IN ({placeholders})", tuple(extra_ingredient_ids))
                        for row in cur.fetchall():
                            ingredient_names[row[0]] = row[1]
                    
                    for extra in extras:
                        ing_id = extra.get("ingredient_id")
                        qty = int(extra.get("quantity", 1))
                        
                        # Obtém disponibilidade do cache em memória
                        max_available_info = ingredient_availability_total.get(ing_id)
                        if not max_available_info or not max_available_info.get('stock_info'):
                            ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                            return (False, "INSUFFICIENT_STOCK", 
                                   f"Ingrediente '{ing_name}' não disponível ou sem estoque")
                        
                        stock_info = max_available_info['stock_info']
                        base_portion_quantity = stock_info['base_portion_quantity']
                        base_portion_unit = stock_info['base_portion_unit']
                        stock_unit = stock_info['stock_unit']
                        current_stock = stock_info['current_stock']
                        
                        # Calcula consumo para a NOVA quantidade total
                        try:
                            required_quantity_total = stock_service.calculate_consumption_in_stock_unit(
                                portions=qty,
                                base_portion_quantity=float(base_portion_quantity),
                                base_portion_unit=str(base_portion_unit),
                                stock_unit=str(stock_unit),
                                item_quantity=new_total_quantity  # ← Usa quantidade total
                            )
                        except ValueError as e:
                            ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                            return (False, "INSUFFICIENT_STOCK", 
                                   f"Erro na conversão de unidades para extra '{ing_name}': {str(e)}")
                        
                        current_stock_decimal = Decimal(str(current_stock))
                        
                        if current_stock_decimal < required_quantity_total:
                            ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                            return (False, "INSUFFICIENT_STOCK", 
                                   f"Estoque insuficiente para extra '{ing_name}'. "
                                   f"Necessário: {required_quantity_total:.3f} {stock_unit}, "
                                   f"Disponível: {current_stock_decimal:.3f} {stock_unit}")
            
            sql = "UPDATE CART_ITEMS SET QUANTITY = QUANTITY + ? WHERE ID = ?;"
            cur.execute(sql, (quantity, existing_item_id))
            
            # NOVA INTEGRAÇÃO: Recria reservas temporárias para todo o carrinho (visitante)
            # (porque a quantidade foi atualizada, precisa recalcular todas as reservas)
            success, error_code, message = _recreate_temporary_reservations_for_cart(
                cart_id=cart_id,
                user_id=None,  # Visitante
                cur=cur
            )
            
            if not success:
                conn.rollback()
                return (False, error_code, message)
        else:
            sql = "INSERT INTO CART_ITEMS (CART_ID, PRODUCT_ID, QUANTITY, NOTES) VALUES (?, ?, ?, ?) RETURNING ID;"
            cur.execute(sql, (cart_id, product_id, quantity, notes))
            new_item_id = cur.fetchone()[0]

            # OTIMIZAÇÃO: Busca preços de ingredientes em batch
            if extras:
                # Coleta IDs de ingredientes e busca preços de uma vez
                extra_ingredient_ids = [ex.get("ingredient_id") for ex in extras if ex.get("ingredient_id")]
                ingredient_prices = {}
                if extra_ingredient_ids:
                    placeholders = ', '.join(['?' for _ in extra_ingredient_ids])
                    cur.execute(
                        f"SELECT ID, COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID IN ({placeholders}) AND IS_AVAILABLE = TRUE;",
                        tuple(extra_ingredient_ids)
                    )
                    for row in cur.fetchall():
                        ingredient_prices[row[0]] = float(row[1] or 0.0)
                
                # Insere extras usando preços já carregados
                for extra in extras:
                    ingredient_id = extra.get("ingredient_id")
                    extra_quantity = int(extra.get("quantity", 1))
                    if extra_quantity <= 0:
                        continue
                    
                    unit_price = ingredient_prices.get(ingredient_id, 0.0)
                    if unit_price > 0:  # Só insere se ingrediente existe e tem preço
                        cur.execute(
                            "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) VALUES (?, ?, ?, 'extra', ?, ?);",
                            (new_item_id, ingredient_id, extra_quantity, extra_quantity, unit_price)
                        )

            if base_modifications:
                rules = _get_product_rules(cur, product_id)
                # OTIMIZAÇÃO: Busca preços de ingredientes de base em batch
                base_mod_ingredient_ids = []
                for bm in base_modifications:
                    try:
                        ing_id = int(bm.get("ingredient_id"))
                        delta = int(bm.get("delta", 0))
                        rule = rules.get(ing_id)
                        if rule and float(rule["portions"]) != 0.0 and delta != 0:
                            base_mod_ingredient_ids.append(ing_id)
                    except (ValueError, TypeError, AttributeError):
                        continue
                
                base_mod_prices = {}
                if base_mod_ingredient_ids:
                    placeholders = ', '.join(['?' for _ in base_mod_ingredient_ids])
                    cur.execute(
                        f"SELECT ID, COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID IN ({placeholders}) AND IS_AVAILABLE = TRUE;",
                        tuple(base_mod_ingredient_ids)
                    )
                    for row in cur.fetchall():
                        base_mod_prices[row[0]] = float(row[1] or 0.0)
                
                # Insere modificações de base usando preços já carregados
                for bm in base_modifications:
                    try:
                        ing_id = int(bm.get("ingredient_id"))
                        delta = int(bm.get("delta", 0))
                    except (ValueError, TypeError, AttributeError):
                        continue
                    rule = rules.get(ing_id)
                    if not rule or float(rule["portions"]) == 0.0 or delta == 0:
                        continue
                    
                    unit_price = base_mod_prices.get(ing_id, 0.0)
                    if unit_price >= 0:  # Permite preço zero
                        cur.execute(
                            "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) VALUES (?, ?, 0, 'base', ?, ?);",
                            (new_item_id, ing_id, delta, unit_price)
                        )
            
            # NOVA INTEGRAÇÃO: Cria reservas temporárias para o novo item APÓS inserir todos os dados (visitante)
            # (extras e base_modifications já foram inseridos)
            success, error_code, message, reservation_ids = _create_temporary_reservations_for_item(
                cart_id=cart_id,
                product_id=product_id,
                quantity=quantity,
                extras=extras,
                base_modifications=base_modifications,
                user_id=None,  # Visitante
                cur=cur
            )
            
            if not success:
                # Erro ao criar reservas - remove o item criado e retorna erro
                cur.execute("DELETE FROM CART_ITEM_EXTRAS WHERE CART_ITEM_ID = ?", (new_item_id,))
                cur.execute("DELETE FROM CART_ITEMS WHERE ID = ?", (new_item_id,))
                conn.rollback()
                return (False, error_code, message)

        conn.commit()
        return (True, None, "Item adicionado ao carrinho com sucesso")
    except fdb.Error as e:
        logger.error(f"Erro ao adicionar item ao carrinho por cart_id: {e}", exc_info=True)
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def find_identical_cart_item(cart_id, product_id, extras, notes, base_modifications=None):
    """
    Verifica se já existe um item idêntico no carrinho (mesmo produto e mesmos extras)
    
    OTIMIZAÇÃO DE PERFORMANCE: Busca todos os extras de todos os itens de uma vez,
    evitando N+1 queries quando há múltiplos itens do mesmo produto.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca itens do mesmo produto
        sql = "SELECT ID, CAST(NOTES AS VARCHAR(1000)) FROM CART_ITEMS WHERE CART_ID = ? AND PRODUCT_ID = ?;"
        cur.execute(sql, (cart_id, product_id))
        items = cur.fetchall()
        
        if not items:
            return None
        
        # OTIMIZAÇÃO: Busca todos os extras de todos os itens de uma vez (evita N+1)
        item_ids = [item[0] for item in items]
        placeholders = ', '.join(['?' for _ in item_ids])
        cur.execute(
            f"""
            SELECT CART_ITEM_ID, INGREDIENT_ID, COALESCE(DELTA, QUANTITY) AS DELTA, TYPE 
            FROM CART_ITEM_EXTRAS 
            WHERE CART_ITEM_ID IN ({placeholders})
            ORDER BY CART_ITEM_ID, TYPE, INGREDIENT_ID;
            """,
            tuple(item_ids)
        )
        all_extras_rows = cur.fetchall()
        
        # Agrupa extras por cart_item_id
        extras_by_item = {}
        for row in all_extras_rows:
            item_id = row[0]
            if item_id not in extras_by_item:
                extras_by_item[item_id] = {'extras': [], 'base': []}
            row_type = (row[3] or 'extra').lower()
            if row_type == 'extra':
                extras_by_item[item_id]['extras'].append((row[1], int(row[2])))
            elif row_type == 'base' and int(row[2]) != 0:
                extras_by_item[item_id]['base'].append((row[1], int(row[2])))
        
        # Normaliza listas de extras desejados
        wanted_extras = []
        for ex in (extras or []):
            try:
                wanted_extras.append((int(ex.get("ingredient_id")), int(ex.get("quantity", 1))))
            except (ValueError, TypeError, AttributeError):
                continue
        wanted_extras.sort()

        wanted_base = []
        for bm in (base_modifications or []):
            try:
                d = int(bm.get("delta", 0))
                if d != 0:
                    wanted_base.append((int(bm.get("ingredient_id")), d))
            except (ValueError, TypeError, AttributeError):
                continue
        wanted_base.sort()
        
        # Compara cada item com os extras desejados
        for item_id, existing_notes in items:
            item_extras_data = extras_by_item.get(item_id, {'extras': [], 'base': []})
            existing_extras = sorted(item_extras_data['extras'])
            existing_base = sorted(item_extras_data['base'])

            extras_match = (existing_extras == wanted_extras)
            base_match = (existing_base == wanted_base)

            if extras_match and base_match and (existing_notes or "") == (notes or ""):
                return item_id
        
        return None
        
    except fdb.Error as e:
        logger.error(f"Erro ao verificar item idêntico: {e}", exc_info=True)
        return None
    finally:
        if conn: conn.close()


def update_cart_item(user_id, cart_item_id, quantity=None, extras=None, notes=None, base_modifications=None):
    """
    Atualiza um item do carrinho
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se o item pertence ao usuário e busca informações necessárias
        sql = """
            SELECT ci.ID, ci.PRODUCT_ID, ci.QUANTITY, ci.CART_ID FROM CART_ITEMS ci
            JOIN CARTS c ON ci.CART_ID = c.ID
            WHERE ci.ID = ? AND c.USER_ID = ? AND c.IS_ACTIVE = TRUE;
        """
        cur.execute(sql, (cart_item_id, user_id))
        row = cur.fetchone()
        if not row:
            return (False, "ITEM_NOT_FOUND", "Item não encontrado no seu carrinho")
        
        current_product_id = row[1]
        cart_id = row[3]  # ALTERAÇÃO: Obtém cart_id para passar para validação de estoque
        
        # CORREÇÃO: Se quantidade está sendo atualizada, valida estoque para a nova quantidade
        if quantity is not None:
            if quantity <= 0:
                return (False, "INVALID_QUANTITY", "Quantidade deve ser maior que zero")
            
            # Valida estoque do produto para a nova quantidade
            # ALTERAÇÃO: Passa cart_id para excluir reservas temporárias do próprio carrinho
            stock_check = _check_product_stock_availability(cur, current_product_id, quantity, cart_id=cart_id)
            if not stock_check[0]:
                return (False, "INSUFFICIENT_STOCK", stock_check[1])
            
            # Valida estoque dos extras existentes para a nova quantidade
            # Busca extras atuais do item
            cur.execute("""
                SELECT cie.INGREDIENT_ID, cie.QUANTITY
                FROM CART_ITEM_EXTRAS cie
                WHERE cie.CART_ITEM_ID = ? AND cie.TYPE = 'extra'
            """, (cart_item_id,))
            existing_extras = cur.fetchall()
            
            for ing_id, extra_qty in existing_extras:
                cur.execute("""
                    SELECT BASE_PORTION_QUANTITY, BASE_PORTION_UNIT, STOCK_UNIT, CURRENT_STOCK, NAME
                    FROM INGREDIENTS
                    WHERE ID = ? AND IS_AVAILABLE = TRUE
                """, (ing_id,))
                ing_info = cur.fetchone()
                if not ing_info:
                    return (False, "INSUFFICIENT_STOCK", "Ingrediente do extra não encontrado ou indisponível")
                
                base_portion_quantity = ing_info[0] or 1
                base_portion_unit = ing_info[1] or 'un'
                stock_unit = ing_info[2] or 'un'
                current_stock = ing_info[3] or 0
                ing_name = ing_info[4]
                
                # Calcula consumo para a NOVA quantidade
                try:
                    required_quantity = stock_service.calculate_consumption_in_stock_unit(
                        portions=extra_qty,
                        base_portion_quantity=base_portion_quantity,
                        base_portion_unit=base_portion_unit,
                        stock_unit=stock_unit,
                        item_quantity=quantity  # ← Nova quantidade
                    )
                except ValueError as e:
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Erro na conversão de unidades para extra '{ing_name}': {str(e)}")
                
                current_stock_decimal = Decimal(str(current_stock))
                
                if current_stock_decimal < required_quantity:
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Estoque insuficiente para extra '{ing_name}'. "
                           f"Necessário: {required_quantity:.3f} {stock_unit}, "
                           f"Disponível: {current_stock_decimal:.3f} {stock_unit}")
            
            # Atualiza quantidade após validação
            sql = "UPDATE CART_ITEMS SET QUANTITY = ? WHERE ID = ?;"
            cur.execute(sql, (quantity, cart_item_id))
        
        # Atualiza notes se fornecido
        if notes is not None:
            sql = "UPDATE CART_ITEMS SET NOTES = ? WHERE ID = ?;"
            cur.execute(sql, (notes, cart_item_id))
        
        # ALTERAÇÃO: Busca informações do item uma única vez (cart_id, product_id, quantity atual)
        # Busca informações do item uma única vez para evitar queries duplicadas
        cur.execute("SELECT CART_ID, PRODUCT_ID, QUANTITY FROM CART_ITEMS WHERE ID = ?", (cart_item_id,))
        item_row = cur.fetchone()
        if not item_row:
            return (False, "ITEM_NOT_FOUND", "Item não encontrado")
        
        item_cart_id = item_row[0]
        item_product_id = item_row[1]
        # ALTERAÇÃO: Usa quantity atualizada se foi modificada, senão usa a do banco
        item_quantity = quantity if quantity is not None else item_row[2]
        
        cur.execute("SELECT USER_ID FROM CARTS WHERE ID = ?", (item_cart_id,))
        cart_user_row = cur.fetchone()
        item_user_id = cart_user_row[0] if cart_user_row else user_id
        
        # Atualiza extras se fornecidos (independente de notes)
        if extras is not None:
            # ALTERAÇÃO: Usa product_id já obtido acima
            product_id = item_product_id
            
            rules = _get_product_rules(cur, product_id)
            for extra in extras:
                ing_id = extra.get("ingredient_id")
                qty = int(extra.get("quantity", 1))
                rule = rules.get(ing_id)
                if not rule:
                    return (False, "EXTRA_NOT_ALLOWED", "Um ou mais extras não são permitidos para este produto")
                if float(rule["portions"]) != 0.0:
                    return (False, "EXTRA_NOT_ALLOWED", "Um dos extras selecionados já faz parte da receita base")
                min_q = int(rule["min_quantity"] or 0)
                max_q = int(rule["max_quantity"] or 0)
                if qty < min_q or (max_q > 0 and qty > max_q):
                    return (False, "EXTRA_OUT_OF_RANGE", f"Quantidade de extra fora do intervalo permitido [{min_q}, {max_q or '∞'}]")
                
                # VALIDAÇÃO DE ESTOQUE com conversão de unidades
                cur.execute("""
                    SELECT BASE_PORTION_QUANTITY, BASE_PORTION_UNIT, STOCK_UNIT, CURRENT_STOCK, NAME
                    FROM INGREDIENTS
                    WHERE ID = ? AND IS_AVAILABLE = TRUE
                """, (ing_id,))
                ing_info = cur.fetchone()
                if not ing_info:
                    return (False, "INSUFFICIENT_STOCK", "Ingrediente do extra não encontrado ou indisponível")
                
                base_portion_quantity = ing_info[0] or 1
                base_portion_unit = ing_info[1] or 'un'
                stock_unit = ing_info[2] or 'un'
                current_stock = ing_info[3] or 0
                ing_name = ing_info[4]
                
                # Calcula consumo convertido para unidade do estoque
                try:
                    required_quantity = stock_service.calculate_consumption_in_stock_unit(
                        portions=qty,
                        base_portion_quantity=base_portion_quantity,
                        base_portion_unit=base_portion_unit,
                        stock_unit=stock_unit,
                        item_quantity=item_quantity  # Usa quantidade do item no carrinho
                    )
                except ValueError as e:
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Erro na conversão de unidades para extra '{ing_name}': {str(e)}")
                
                # Converte current_stock para Decimal para comparação precisa
                current_stock_decimal = Decimal(str(current_stock))
                
                if current_stock_decimal < required_quantity:
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Estoque insuficiente para extra '{ing_name}'. "
                           f"Necessário: {required_quantity:.3f} {stock_unit}, "
                           f"Disponível: {current_stock_decimal:.3f} {stock_unit}")
            
            # Remove e recria apenas linhas TYPE='extra'
            cur.execute("DELETE FROM CART_ITEM_EXTRAS WHERE CART_ITEM_ID = ? AND TYPE = 'extra';", (cart_item_id,))
            for extra in extras:
                ingredient_id = extra.get("ingredient_id")
                extra_quantity_total = int(extra.get("quantity", 1))  # CORREÇÃO: quantity é o total
                if extra_quantity_total <= 0:
                    continue
                cur.execute("SELECT COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID = ? AND IS_AVAILABLE = TRUE;", (ingredient_id,))
                rowp = cur.fetchone()
                if rowp:
                    unit_price = float(rowp[0] or 0.0)
                    cur.execute(
                        "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) VALUES (?, ?, ?, 'extra', ?, ?);",
                        (cart_item_id, ingredient_id, extra_quantity_total, extra_quantity_total, unit_price)
                    )
        
        # Atualiza base_modifications se fornecido
        if base_modifications is not None:
            # Remove e recria TYPE='base'
            cur.execute("DELETE FROM CART_ITEM_EXTRAS WHERE CART_ITEM_ID = ? AND TYPE = 'base';", (cart_item_id,))
            # ALTERAÇÃO: Usa product_id já obtido acima (evita query duplicada)
            product_id = item_product_id
            rules = _get_product_rules(cur, product_id)
            for bm in base_modifications:
                try:
                    ing_id = int(bm.get("ingredient_id"))
                    delta = int(bm.get("delta", 0))
                except (ValueError, TypeError):
                    continue
                rule = rules.get(ing_id)
                if not rule or float(rule["portions"]) == 0.0 or delta == 0:
                    continue
                cur.execute("SELECT COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID = ? AND IS_AVAILABLE = TRUE;", (ing_id,))
                rowp = cur.fetchone()
                unit_price = float(rowp[0] or 0.0) if rowp else 0.0
                cur.execute(
                    "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) VALUES (?, ?, 0, 'base', ?, ?);",
                    (cart_item_id, ing_id, delta, unit_price)
                )
        
        # ALTERAÇÃO: Recria reservas temporárias APENAS UMA VEZ após todas as atualizações
        # (quantidade, extras, base_modifications) - remove duplicação
        # Recria reservas temporárias para todo o carrinho
        success, error_code, message = _recreate_temporary_reservations_for_cart(
            cart_id=item_cart_id,
            user_id=item_user_id,
            cur=cur
        )
        
        if not success:
            conn.rollback()
            return (False, error_code, message)
        
        conn.commit()
        return (True, None, "Item atualizado com sucesso")
        
    except fdb.Error as e:
        logger.error(f"Erro ao atualizar item do carrinho: {e}", exc_info=True)
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def update_cart_item_by_cart(cart_id, cart_item_id, quantity=None, extras=None, notes=None, base_modifications=None):
    """
    Atualiza um item do carrinho para carrinho convidado (por cart_id)
    """
    conn = None
    try:
        # Valida e converte cart_id
        cart_id = _validate_cart_id(cart_id)
        
        conn = get_db_connection()
        cur = conn.cursor()

        # Verifica se o item pertence ao carrinho convidado e busca informações necessárias
        sql = (
            "SELECT ci.ID, ci.PRODUCT_ID, ci.QUANTITY, ci.CART_ID FROM CART_ITEMS ci "
            "JOIN CARTS c ON ci.CART_ID = c.ID "
            "WHERE ci.ID = ? AND c.ID = ? AND c.USER_ID IS NULL AND c.IS_ACTIVE = TRUE;"
        )
        cur.execute(sql, (cart_item_id, cart_id))
        row = cur.fetchone()
        if not row:
            return (False, "ITEM_NOT_FOUND", "Item não encontrado no carrinho informado")

        current_product_id = row[1]
        # ALTERAÇÃO: cart_id já está disponível como parâmetro da função

        # CORREÇÃO: Se quantidade está sendo atualizada, valida estoque para a nova quantidade
        if quantity is not None:
            if quantity <= 0:
                return (False, "INVALID_QUANTITY", "Quantidade deve ser maior que zero")
            
            # Valida estoque do produto para a nova quantidade
            # ALTERAÇÃO: Passa cart_id para excluir reservas temporárias do próprio carrinho
            stock_check = _check_product_stock_availability(cur, current_product_id, quantity, cart_id=cart_id)
            if not stock_check[0]:
                return (False, "INSUFFICIENT_STOCK", stock_check[1])
            
            # Valida estoque dos extras existentes para a nova quantidade
            # Busca extras atuais do item
            cur.execute("""
                SELECT cie.INGREDIENT_ID, cie.QUANTITY
                FROM CART_ITEM_EXTRAS cie
                WHERE cie.CART_ITEM_ID = ? AND cie.TYPE = 'extra'
            """, (cart_item_id,))
            existing_extras = cur.fetchall()
            
            for ing_id, extra_qty in existing_extras:
                cur.execute("""
                    SELECT BASE_PORTION_QUANTITY, BASE_PORTION_UNIT, STOCK_UNIT, CURRENT_STOCK, NAME
                    FROM INGREDIENTS
                    WHERE ID = ? AND IS_AVAILABLE = TRUE
                """, (ing_id,))
                ing_info = cur.fetchone()
                if not ing_info:
                    return (False, "INSUFFICIENT_STOCK", "Ingrediente do extra não encontrado ou indisponível")
                
                base_portion_quantity = ing_info[0] or 1
                base_portion_unit = ing_info[1] or 'un'
                stock_unit = ing_info[2] or 'un'
                current_stock = ing_info[3] or 0
                ing_name = ing_info[4]
                
                # Calcula consumo para a NOVA quantidade
                try:
                    required_quantity = stock_service.calculate_consumption_in_stock_unit(
                        portions=extra_qty,
                        base_portion_quantity=base_portion_quantity,
                        base_portion_unit=base_portion_unit,
                        stock_unit=stock_unit,
                        item_quantity=quantity  # ← Nova quantidade
                    )
                except ValueError as e:
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Erro na conversão de unidades para extra '{ing_name}': {str(e)}")
                
                current_stock_decimal = Decimal(str(current_stock))
                
                if current_stock_decimal < required_quantity:
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Estoque insuficiente para extra '{ing_name}'. "
                           f"Necessário: {required_quantity:.3f} {stock_unit}, "
                           f"Disponível: {current_stock_decimal:.3f} {stock_unit}")
            
            # Atualiza quantidade após validação
            cur.execute("UPDATE CART_ITEMS SET QUANTITY = ? WHERE ID = ?;", (quantity, cart_item_id))

        # Atualiza notes se fornecido (independente de extras)
        if notes is not None:
            cur.execute("UPDATE CART_ITEMS SET NOTES = ? WHERE ID = ?;", (notes, cart_item_id))

        # ALTERAÇÃO: Busca informações do item uma única vez (product_id, quantity atual)
        cur.execute("SELECT PRODUCT_ID, QUANTITY FROM CART_ITEMS WHERE ID = ?", (cart_item_id,))
        item_row = cur.fetchone()
        if not item_row:
            return (False, "ITEM_NOT_FOUND", "Item não encontrado")
        
        item_product_id = item_row[0]
        # ALTERAÇÃO: Usa quantity atualizada se foi modificada, senão usa a do banco
        item_quantity = quantity if quantity is not None else item_row[1]

        # Atualiza extras se fornecidos (independente de notes)
        if extras is not None:
            # ALTERAÇÃO: Usa product_id já obtido acima
            product_id = item_product_id
            
            rules = _get_product_rules(cur, product_id)
            for extra in extras:
                ing_id = extra.get("ingredient_id")
                qty = int(extra.get("quantity", 1))
                rule = rules.get(ing_id)
                if not rule:
                    return (False, "EXTRA_NOT_ALLOWED", "Um ou mais extras não são permitidos para este produto")
                if float(rule["portions"]) != 0.0:
                    return (False, "EXTRA_NOT_ALLOWED", "Um dos extras selecionados já faz parte da receita base")
                min_q = int(rule["min_quantity"] or 0)
                max_q = int(rule["max_quantity"] or 0)
                if qty < min_q or (max_q > 0 and qty > max_q):
                    return (False, "EXTRA_OUT_OF_RANGE", f"Quantidade de extra fora do intervalo permitido [{min_q}, {max_q or '∞'}]")
                
                # VALIDAÇÃO DE ESTOQUE com conversão de unidades
                cur.execute("""
                    SELECT BASE_PORTION_QUANTITY, BASE_PORTION_UNIT, STOCK_UNIT, CURRENT_STOCK, NAME
                    FROM INGREDIENTS
                    WHERE ID = ? AND IS_AVAILABLE = TRUE
                """, (ing_id,))
                ing_info = cur.fetchone()
                if not ing_info:
                    return (False, "INSUFFICIENT_STOCK", "Ingrediente do extra não encontrado ou indisponível")
                
                base_portion_quantity = ing_info[0] or 1
                base_portion_unit = ing_info[1] or 'un'
                stock_unit = ing_info[2] or 'un'
                current_stock = ing_info[3] or 0
                ing_name = ing_info[4]
                
                # Calcula consumo convertido para unidade do estoque
                try:
                    required_quantity = stock_service.calculate_consumption_in_stock_unit(
                        portions=qty,
                        base_portion_quantity=base_portion_quantity,
                        base_portion_unit=base_portion_unit,
                        stock_unit=stock_unit,
                        item_quantity=item_quantity  # Usa quantidade do item no carrinho
                    )
                except ValueError as e:
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Erro na conversão de unidades para extra '{ing_name}': {str(e)}")
                
                # Converte current_stock para Decimal para comparação precisa
                current_stock_decimal = Decimal(str(current_stock))
                
                if current_stock_decimal < required_quantity:
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Estoque insuficiente para extra '{ing_name}'. "
                           f"Necessário: {required_quantity:.3f} {stock_unit}, "
                           f"Disponível: {current_stock_decimal:.3f} {stock_unit}")

            # Remove e recria apenas TYPE='extra'
            cur.execute("DELETE FROM CART_ITEM_EXTRAS WHERE CART_ITEM_ID = ? AND TYPE = 'extra';", (cart_item_id,))
            for extra in extras:
                ingredient_id = extra.get("ingredient_id")
                extra_quantity = int(extra.get("quantity", 1))
                if extra_quantity <= 0:
                    continue
                cur.execute("SELECT COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID = ? AND IS_AVAILABLE = TRUE;", (ingredient_id,))
                rowp = cur.fetchone()
                if rowp:
                    unit_price = float(rowp[0] or 0.0)
                    cur.execute(
                        "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) VALUES (?, ?, ?, 'extra', ?, ?);",
                        (cart_item_id, ingredient_id, extra_quantity, extra_quantity, unit_price)
                    )

        # Atualiza base_modifications se fornecido
        if base_modifications is not None:
            cur.execute("DELETE FROM CART_ITEM_EXTRAS WHERE CART_ITEM_ID = ? AND TYPE = 'base';", (cart_item_id,))
            # ALTERAÇÃO: Usa product_id já obtido acima (evita query duplicada)
            product_id = item_product_id
            rules = _get_product_rules(cur, product_id)
            for bm in base_modifications:
                try:
                    ing_id = int(bm.get("ingredient_id"))
                    delta = int(bm.get("delta", 0))
                except (ValueError, TypeError):
                    continue
                rule = rules.get(ing_id)
                if not rule or float(rule["portions"]) == 0.0 or delta == 0:
                    continue
                cur.execute("SELECT COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID = ? AND IS_AVAILABLE = TRUE;", (ing_id,))
                rowp = cur.fetchone()
                unit_price = float(rowp[0] or 0.0) if rowp else 0.0
                cur.execute(
                    "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) VALUES (?, ?, 0, 'base', ?, ?);",
                    (cart_item_id, ing_id, delta, unit_price)
                )
        
        # ALTERAÇÃO: Recria reservas temporárias APENAS UMA VEZ após todas as atualizações (visitante)
        # (quantidade, extras, base_modifications) - remove duplicação
        # Recria reservas temporárias para todo o carrinho
        success, error_code, message = _recreate_temporary_reservations_for_cart(
            cart_id=cart_id,  # ALTERAÇÃO: Usa cart_id já validado (função recebe cart_id como parâmetro)
            user_id=None,  # Visitante
            cur=cur
        )
        
        if not success:
            conn.rollback()
            return (False, error_code, message)

        conn.commit()
        return (True, None, "Item atualizado com sucesso")
    except fdb.Error as e:
        logger.error(f"Erro ao atualizar item do carrinho por cart_id: {e}", exc_info=True)
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def _get_product_rules(cur, product_id):
    """Busca regras de ingredientes para um produto e retorna dict por ingredient_id"""
    cur.execute(
        """
        SELECT INGREDIENT_ID, PORTIONS, MIN_QUANTITY, MAX_QUANTITY
        FROM PRODUCT_INGREDIENTS
        WHERE PRODUCT_ID = ?
        """,
        (product_id,)
    )
    rules = {}
    for row in cur.fetchall():
        rules[row[0]] = {
            "portions": float(row[1] or 0),
            "min_quantity": int(row[2] or 0),
            "max_quantity": int(row[3] or 0)
        }
    return rules


# =====================================================
# SISTEMA DE RESERVAS TEMPORÁRIAS - FUNÇÕES AUXILIARES
# =====================================================

def _calculate_item_ingredient_consumption(product_id, quantity, extras=None, base_modifications=None, cur=None):
    """
    Calcula consumo total de insumos de um item (produto + extras + base_modifications).
    
    Args:
        product_id: ID do produto
        quantity: Quantidade do item
        extras: Lista de extras [{ingredient_id: int, quantity: int}]
        base_modifications: Lista de base_modifications [{ingredient_id: int, delta: int}]
        cur: Cursor do banco (opcional)
    
    Returns:
        dict: {ingredient_id: consumption_quantity} onde consumption_quantity está na unidade do estoque
    """
    # ALTERAÇÃO: Validação de entrada
    try:
        product_id = int(product_id)
        quantity = int(quantity)
        if product_id <= 0 or quantity <= 0:
            raise ValueError("product_id e quantity devem ser positivos")
    except (ValueError, TypeError) as e:
        logger.error(f"Erro de validação em _calculate_item_ingredient_consumption: {e}")
        return {}
    
    conn = None
    should_close = False
    
    try:
        if cur is None:
            conn = get_db_connection()
            cur = conn.cursor()
            should_close = True
        
        consumption = {}
        
        # 1. Calcular consumo dos ingredientes da receita base (portions > 0)
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
              AND pi.PORTIONS > 0
        """, (product_id,))
        
        for row in cur.fetchall():
            ing_id, portions, base_portion_quantity, base_portion_unit, stock_unit = row
            
            try:
                # Calcula consumo convertido para unidade do estoque
                consumption_qty = stock_service.calculate_consumption_in_stock_unit(
                    portions=portions or 0,
                    base_portion_quantity=base_portion_quantity or 1,
                    base_portion_unit=base_portion_unit or 'un',
                    stock_unit=stock_unit or 'un',
                    item_quantity=quantity
                )
                
                if ing_id not in consumption:
                    consumption[ing_id] = Decimal('0')
                consumption[ing_id] += consumption_qty
            except ValueError as e:
                logger.warning(f"Erro ao calcular consumo do ingrediente {ing_id}: {e}")
                continue
        
        # 2. Calcular consumo dos extras (se fornecidos)
        # ALTERAÇÃO: Otimização - busca informações de todos os extras em batch para evitar N+1 queries
        if extras:
            # Coleta todos os IDs de ingredientes extras
            extra_ingredient_ids = []
            extra_quantities = {}
            for extra in extras:
                try:
                    ing_id = int(extra.get("ingredient_id", 0))
                    extra_qty = int(extra.get("quantity", 1))
                    if ing_id > 0 and extra_qty > 0:
                        extra_ingredient_ids.append(ing_id)
                        extra_quantities[ing_id] = extra_qty
                except (ValueError, TypeError):
                    continue
            
            # Busca informações de todos os extras de uma vez
            extras_info = {}
            if extra_ingredient_ids:
                placeholders = ', '.join(['?' for _ in extra_ingredient_ids])
                cur.execute(f"""
                    SELECT 
                        ID,
                        BASE_PORTION_QUANTITY,
                        BASE_PORTION_UNIT,
                        STOCK_UNIT
                    FROM INGREDIENTS
                    WHERE ID IN ({placeholders})
                """, tuple(extra_ingredient_ids))
                
                for row in cur.fetchall():
                    ing_id = row[0]
                    extras_info[ing_id] = {
                        'base_portion_quantity': row[1],
                        'base_portion_unit': row[2],
                        'stock_unit': row[3]
                    }
            
            # Busca portions da receita base para todos os extras de uma vez
            base_portions_map = {}
            if extra_ingredient_ids:
                placeholders = ', '.join(['?' for _ in extra_ingredient_ids])
                cur.execute(f"""
                    SELECT INGREDIENT_ID, PORTIONS
                    FROM PRODUCT_INGREDIENTS
                    WHERE PRODUCT_ID = ? AND INGREDIENT_ID IN ({placeholders})
                """, (product_id, *extra_ingredient_ids))
                
                for row in cur.fetchall():
                    base_portions_map[row[0]] = float(row[1] or 0)
            
            # Calcula consumo de cada extra
            for ing_id in extra_ingredient_ids:
                if ing_id not in extras_info:
                    continue
                
                extra_qty = extra_quantities[ing_id]
                info = extras_info[ing_id]
                base_portion_quantity = info['base_portion_quantity']
                base_portion_unit = info['base_portion_unit']
                stock_unit = info['stock_unit']
                
                try:
                    # Calcula consumo do extra convertido para unidade do estoque
                    # IMPORTANTE: Verificar se o ingrediente já está na receita base
                    # Se estiver, o extra consome apenas a quantidade adicional
                    base_portions = base_portions_map.get(ing_id, 0)
                    
                    if base_portions > 0:
                        # Ingrediente está na receita base, extra consome apenas quantidade adicional
                        base_total_portions = base_portions * quantity
                        extra_portions_to_consume = max(0, extra_qty - base_total_portions)
                        
                        if extra_portions_to_consume > 0:
                            extra_consumption = stock_service.calculate_consumption_in_stock_unit(
                                portions=extra_portions_to_consume,
                                base_portion_quantity=base_portion_quantity or 1,
                                base_portion_unit=base_portion_unit or 'un',
                                stock_unit=stock_unit or 'un',
                                item_quantity=quantity
                            )
                            
                            if ing_id not in consumption:
                                consumption[ing_id] = Decimal('0')
                            consumption[ing_id] += extra_consumption
                    else:
                        # Ingrediente não está na receita base, consome quantidade total do extra
                        extra_consumption = stock_service.calculate_consumption_in_stock_unit(
                            portions=extra_qty,
                            base_portion_quantity=base_portion_quantity or 1,
                            base_portion_unit=base_portion_unit or 'un',
                            stock_unit=stock_unit or 'un',
                            item_quantity=quantity
                        )
                        
                        if ing_id not in consumption:
                            consumption[ing_id] = Decimal('0')
                        consumption[ing_id] += extra_consumption
                except ValueError as e:
                    logger.warning(f"Erro ao calcular consumo do extra {ing_id}: {e}")
                    continue
        
        # 3. Calcular consumo das base_modifications (apenas deltas positivos)
        # ALTERAÇÃO: Otimização - busca informações de todos os base_modifications em batch
        if base_modifications:
            # Coleta todos os IDs de ingredientes de base_modifications
            bm_ingredient_ids = []
            bm_deltas = {}
            for bm in base_modifications:
                try:
                    delta = int(bm.get("delta", 0))
                    if delta <= 0:  # Apenas deltas positivos consomem estoque
                        continue
                    ing_id = int(bm.get("ingredient_id", 0))
                    if ing_id > 0:
                        bm_ingredient_ids.append(ing_id)
                        bm_deltas[ing_id] = delta
                except (ValueError, TypeError):
                    continue
            
            # Busca informações de todos os base_modifications de uma vez
            bm_info = {}
            if bm_ingredient_ids:
                placeholders = ', '.join(['?' for _ in bm_ingredient_ids])
                cur.execute(f"""
                    SELECT 
                        ID,
                        BASE_PORTION_QUANTITY,
                        BASE_PORTION_UNIT,
                        STOCK_UNIT
                    FROM INGREDIENTS
                    WHERE ID IN ({placeholders})
                """, tuple(bm_ingredient_ids))
                
                for row in cur.fetchall():
                    ing_id = row[0]
                    bm_info[ing_id] = {
                        'base_portion_quantity': row[1],
                        'base_portion_unit': row[2],
                        'stock_unit': row[3]
                    }
            
            # Calcula consumo de cada base_modification
            for ing_id in bm_ingredient_ids:
                if ing_id not in bm_info:
                    continue
                
                delta = bm_deltas[ing_id]
                info = bm_info[ing_id]
                base_portion_quantity = info['base_portion_quantity']
                base_portion_unit = info['base_portion_unit']
                stock_unit = info['stock_unit']
                
                try:
                    # DELTA é em porções, então multiplica por base_portion_quantity
                    delta_consumption = (
                        Decimal(str(delta)) * 
                        Decimal(str(base_portion_quantity or 1))
                    )
                    
                    # ALTERAÇÃO: Importa _convert_unit no topo (já está sendo usado)
                    # Converte para unidade do estoque
                    from .stock_service import _convert_unit
                    total_bm = _convert_unit(
                        delta_consumption,
                        base_portion_unit or 'un',
                        stock_unit or 'un'
                    ) * Decimal(str(quantity))
                    
                    if ing_id not in consumption:
                        consumption[ing_id] = Decimal('0')
                    consumption[ing_id] += total_bm
                except ValueError as e:
                    logger.warning(f"Erro ao calcular consumo da base_modification {ing_id}: {e}")
                    continue
        
        return consumption
        
    except fdb.Error as e:
        logger.error(f"Erro ao calcular consumo de insumos: {e}", exc_info=True)
        return {}
    finally:
        if should_close and conn:
            conn.close()


def _create_temporary_reservations_for_item(cart_id, product_id, quantity, extras=None, base_modifications=None, user_id=None, cur=None):
    """
    Cria reservas temporárias para um item do carrinho.
    
    Args:
        cart_id: ID do carrinho
        product_id: ID do produto
        quantity: Quantidade do item
        extras: Lista de extras (opcional)
        base_modifications: Lista de base_modifications (opcional)
        user_id: ID do usuário (opcional, None para visitante)
        cur: Cursor do banco (opcional)
    
    Returns:
        tuple: (success: bool, error_code: str, message: str, reservation_ids: list)
    """
    # ALTERAÇÃO: Validação de entrada
    try:
        cart_id = int(cart_id) if cart_id else None
        product_id = int(product_id) if product_id else None
        quantity = int(quantity) if quantity else 0
        if not cart_id or not product_id or quantity <= 0:
            raise ValueError("cart_id, product_id e quantity devem ser válidos e positivos")
    except (ValueError, TypeError) as e:
        logger.error(f"Erro de validação em _create_temporary_reservations_for_item: {e}")
        return (False, "VALIDATION_ERROR", f"Parâmetros inválidos: {str(e)}", [])
    
    conn = None
    should_close = False
    
    try:
        if cur is None:
            conn = get_db_connection()
            cur = conn.cursor()
            should_close = True
        
        # Calcula consumo total de insumos
        consumption = _calculate_item_ingredient_consumption(
            product_id=product_id,
            quantity=quantity,
            extras=extras,
            base_modifications=base_modifications,
            cur=cur
        )
        
        if not consumption:
            # Não há consumo de insumos (produto sem ingredientes?)
            return (True, None, "Nenhum insumo a reservar", [])
        
        # Gera session_id: para visitantes usa cart_id, para usuários usa user_id
        if user_id:
            session_id = f"user_{user_id}_cart_{cart_id}"
        else:
            session_id = f"cart_{cart_id}"
        
        reservation_ids = []
        
        # Cria reserva temporária para cada insumo
        for ingredient_id, consumption_qty in consumption.items():
            # Verifica se há estoque disponível antes de criar reserva
            # ALTERAÇÃO: Passa cart_id para excluir reservas temporárias do próprio carrinho
            # Isso garante que não bloqueie a criação de reservas quando já há reservas temporárias do mesmo carrinho
            # ALTERAÇÃO CRÍTICA: exclude_confirmed_reservations=True para não subtrair reservas confirmadas
            # Reservas confirmadas não devem bloquear criação de reservas temporárias no carrinho
            available_stock = stock_service.get_ingredient_available_stock(
                ingredient_id, 
                cur, 
                exclude_cart_id=cart_id,
                exclude_confirmed_reservations=True
            )
            
            if available_stock < consumption_qty:
                # Estoque insuficiente - limpa reservas já criadas e retorna erro
                if reservation_ids:
                    # Limpa reservas já criadas
                    for res_id in reservation_ids:
                        try:
                            cur.execute("DELETE FROM TEMPORARY_RESERVATIONS WHERE ID = ?", (res_id,))
                        except Exception as e:
                            logger.warning(f"Erro ao limpar reserva {res_id}: {e}")
                
                # Busca nome do insumo para mensagem de erro
                cur.execute("SELECT NAME FROM INGREDIENTS WHERE ID = ?", (ingredient_id,))
                row = cur.fetchone()
                ing_name = row[0] if row else f"Ingrediente ID {ingredient_id}"
                
                return (
                    False,
                    "INSUFFICIENT_STOCK",
                    f"Estoque insuficiente para '{ing_name}'. Disponível: {available_stock:.3f}, Necessário: {consumption_qty:.3f}",
                    []
                )
            
            # Calcula data de expiração (TTL de 10 minutos)
            expires_at = datetime.now() + timedelta(minutes=10)
            
            # ALTERAÇÃO: Converte Decimal para string para preservar precisão (evita perda ao converter para float)
            # Cria reserva temporária diretamente (dentro da transação existente)
            try:
                # ALTERAÇÃO: Mantém precisão usando Decimal ao invés de float
                consumption_qty_value = float(consumption_qty)  # Firebird requer float, mas preservamos precisão no cálculo
                cur.execute("""
                    INSERT INTO TEMPORARY_RESERVATIONS 
                    (INGREDIENT_ID, QUANTITY, SESSION_ID, USER_ID, CART_ID, EXPIRES_AT)
                    VALUES (?, ?, ?, ?, ?, ?)
                    RETURNING ID
                """, (ingredient_id, consumption_qty_value, session_id, user_id, cart_id, expires_at))
                
                reservation_id = cur.fetchone()[0]
                reservation_ids.append(reservation_id)
            except fdb.Error as e:
                # ALTERAÇÃO: Tratamento específico para erros de banco de dados
                # Erro ao criar reserva - limpa reservas já criadas e retorna erro
                logger.error(f"Erro ao criar reserva temporária para ingrediente {ingredient_id}: {e}", exc_info=True)
                
                if reservation_ids:
                    for res_id in reservation_ids:
                        try:
                            cur.execute("DELETE FROM TEMPORARY_RESERVATIONS WHERE ID = ?", (res_id,))
                        except fdb.Error as e2:
                            logger.warning(f"Erro ao limpar reserva {res_id}: {e2}")
                
                return (False, "DATABASE_ERROR", f"Erro ao criar reserva temporária: {str(e)}", [])
            except Exception as e:
                # ALTERAÇÃO: Captura outros erros inesperados
                logger.error(f"Erro inesperado ao criar reserva temporária para ingrediente {ingredient_id}: {e}", exc_info=True)
                
                if reservation_ids:
                    for res_id in reservation_ids:
                        try:
                            cur.execute("DELETE FROM TEMPORARY_RESERVATIONS WHERE ID = ?", (res_id,))
                        except Exception as e2:
                            logger.warning(f"Erro ao limpar reserva {res_id}: {e2}")
                
                return (False, "RESERVATION_ERROR", f"Erro ao criar reserva temporária: {str(e)}", [])
        
        return (True, None, f"{len(reservation_ids)} reservas temporárias criadas", reservation_ids)
        
    except Exception as e:
        logger.error(f"Erro ao criar reservas temporárias: {e}", exc_info=True)
        return (False, "RESERVATION_ERROR", f"Erro ao criar reservas temporárias: {str(e)}", [])
    finally:
        if should_close and conn:
            conn.close()


def _clear_temporary_reservations_for_item(cart_item_id, user_id=None, cart_id=None, cur=None):
    """
    Limpa reservas temporárias de um item do carrinho.
    
    Args:
        cart_item_id: ID do item do carrinho
        user_id: ID do usuário (opcional)
        cart_id: ID do carrinho (opcional)
        cur: Cursor do banco (opcional)
    
    Returns:
        tuple: (success: bool, cleared_count: int)
    """
    conn = None
    should_close = False
    
    try:
        if cur is None:
            conn = get_db_connection()
            cur = conn.cursor()
            should_close = True
        
        # Busca informações do item para calcular consumo
        cur.execute("""
            SELECT ci.PRODUCT_ID, ci.QUANTITY, ci.CART_ID, c.USER_ID
            FROM CART_ITEMS ci
            JOIN CARTS c ON ci.CART_ID = c.ID
            WHERE ci.ID = ?
        """, (cart_item_id,))
        
        row = cur.fetchone()
        if not row:
            return (True, 0)
        
        item_product_id, item_quantity, item_cart_id, item_user_id = row
        
        # Busca extras e base_modifications do item
        cur.execute("""
            SELECT INGREDIENT_ID, QUANTITY, TYPE, DELTA
            FROM CART_ITEM_EXTRAS
            WHERE CART_ITEM_ID = ?
        """, (cart_item_id,))
        
        extras = []
        base_modifications = []
        
        for row in cur.fetchall():
            ing_id, qty, extra_type, delta = row
            if extra_type == 'extra':
                extras.append({"ingredient_id": ing_id, "quantity": qty})
            elif extra_type == 'base' and delta:
                base_modifications.append({"ingredient_id": ing_id, "delta": delta})
        
        # Calcula consumo para limpar reservas correspondentes
        # Gera session_id
        if item_user_id:
            session_id = f"user_{item_user_id}_cart_{item_cart_id}"
        else:
            session_id = f"cart_{item_cart_id}"
        
        # Limpa reservas temporárias do carrinho (todas as reservas do carrinho serão recriadas)
        # Isso é mais seguro do que tentar limpar apenas as reservas deste item
        # Porque pode haver sobreposição entre itens
        cleared_count = 0
        
        # Limpa reservas expiradas primeiro
        cur.execute("""
            DELETE FROM TEMPORARY_RESERVATIONS
            WHERE EXPIRES_AT <= CURRENT_TIMESTAMP
        """)
        cleared_count += cur.rowcount
        
        # Limpa reservas do carrinho (serão recriadas quando necessário)
        cur.execute("""
            DELETE FROM TEMPORARY_RESERVATIONS
            WHERE CART_ID = ?
        """, (item_cart_id,))
        cleared_count += cur.rowcount
        
        if should_close and conn:
            conn.commit()
        
        return (True, cleared_count)
        
    except Exception as e:
        logger.error(f"Erro ao limpar reservas temporárias: {e}", exc_info=True)
        return (False, 0)
    finally:
        if should_close and conn:
            conn.close()


def _recreate_temporary_reservations_for_cart(cart_id, user_id=None, cur=None):
    """
    Recria reservas temporárias para todos os itens do carrinho.
    Usado após atualizar quantidade ou modificar itens.
    
    Args:
        cart_id: ID do carrinho
        user_id: ID do usuário (opcional, None para visitante)
        cur: Cursor do banco (opcional)
    
    Returns:
        tuple: (success: bool, error_code: str, message: str)
    """
    conn = None
    should_close = False
    
    try:
        if cur is None:
            conn = get_db_connection()
            cur = conn.cursor()
            should_close = True
        
        # Busca todos os itens do carrinho
        cur.execute("""
            SELECT ci.ID, ci.PRODUCT_ID, ci.QUANTITY
            FROM CART_ITEMS ci
            WHERE ci.CART_ID = ?
        """, (cart_id,))
        
        items = cur.fetchall()
        
        # ALTERAÇÃO: Limpa reservas expiradas primeiro para liberar estoque
        # Limpa reservas expiradas primeiro (otimização)
        cur.execute("""
            DELETE FROM TEMPORARY_RESERVATIONS
            WHERE EXPIRES_AT <= CURRENT_TIMESTAMP
        """)
        
        # Limpa todas as reservas temporárias do carrinho antes de recriar
        cur.execute("""
            DELETE FROM TEMPORARY_RESERVATIONS
            WHERE CART_ID = ?
        """, (cart_id,))
        
        # Cria reservas temporárias para cada item
        for item_id, product_id, quantity in items:
            # Busca extras e base_modifications do item
            cur.execute("""
                SELECT INGREDIENT_ID, QUANTITY, TYPE, DELTA
                FROM CART_ITEM_EXTRAS
                WHERE CART_ITEM_ID = ?
            """, (item_id,))
            
            extras = []
            base_modifications = []
            
            for row in cur.fetchall():
                ing_id, qty, extra_type, delta = row
                if extra_type == 'extra':
                    extras.append({"ingredient_id": ing_id, "quantity": qty})
                elif extra_type == 'base' and delta:
                    base_modifications.append({"ingredient_id": ing_id, "delta": delta})
            
            # Cria reservas temporárias para este item
            success, error_code, message, _ = _create_temporary_reservations_for_item(
                cart_id=cart_id,
                product_id=product_id,
                quantity=quantity,
                extras=extras if extras else None,
                base_modifications=base_modifications if base_modifications else None,
                user_id=user_id,
                cur=cur
            )
            
            if not success:
                # Erro ao criar reservas - limpa todas as reservas e retorna erro
                cur.execute("""
                    DELETE FROM TEMPORARY_RESERVATIONS
                    WHERE CART_ID = ?
                """, (cart_id,))
                
                if should_close and conn:
                    conn.rollback()
                
                return (False, error_code, message)
        
        if should_close and conn:
            conn.commit()
        
        return (True, None, "Reservas temporárias recriadas com sucesso")
        
    except fdb.Error as e:
        # ALTERAÇÃO: Tratamento específico para erros de banco de dados
        logger.error(f"Erro de banco de dados ao recriar reservas temporárias: {e}", exc_info=True)
        if should_close and conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", f"Erro ao recriar reservas temporárias: {str(e)}")
    except Exception as e:
        # ALTERAÇÃO: Captura outros erros inesperados
        logger.error(f"Erro inesperado ao recriar reservas temporárias: {e}", exc_info=True)
        if should_close and conn:
            conn.rollback()
        return (False, "RESERVATION_ERROR", f"Erro ao recriar reservas temporárias: {str(e)}")
    finally:
        if should_close and conn:
            conn.close()


def _batch_get_ingredient_availability(ingredient_ids, item_quantity, cur, cart_id=None):
    """
    OTIMIZAÇÃO DE PERFORMANCE: Busca disponibilidade de múltiplos ingredientes em uma única query.
    Evita N+1 queries quando validando extras em batch.
    
    Args:
        ingredient_ids: Lista de IDs de ingredientes
        item_quantity: Quantidade de itens do produto
        cur: Cursor do banco de dados
    
    Returns:
        dict: {ingredient_id: max_available_info}
    """
    if not ingredient_ids:
        return {}
    
    from .product_service import get_ingredient_max_available_quantity
    
    # Busca informações de todos os ingredientes de uma vez
    placeholders = ', '.join(['?' for _ in ingredient_ids])
    cur.execute(f"""
        SELECT 
            ID, NAME, CURRENT_STOCK, STOCK_UNIT, BASE_PORTION_QUANTITY, 
            BASE_PORTION_UNIT, IS_AVAILABLE
        FROM INGREDIENTS
        WHERE ID IN ({placeholders})
    """, tuple(ingredient_ids))
    
    ingredients_data = {}
    for row in cur.fetchall():
        ing_id, name, current_stock, stock_unit, base_portion_quantity, base_portion_unit, is_available = row
        
        if not is_available:
            ingredients_data[ing_id] = {
                'max_available': 0,
                'limited_by': 'unavailable',
                'stock_info': {
                    'current_stock': Decimal(str(current_stock or 0)),
                    'stock_unit': stock_unit or 'un',
                    'base_portion_quantity': Decimal(str(base_portion_quantity or 1)),
                    'base_portion_unit': base_portion_unit or 'un'
                }
            }
            continue
        
        # IMPORTANTE: Para extras (portions = 0), usa get_ingredient_max_available_quantity
        # que já calcula corretamente considerando estoque e quantidade do produto
        # Como não temos max_quantity_from_rule aqui, passa None (será aplicado depois na validação)
        # ALTERAÇÃO: Passa cart_id para excluir reservas temporárias do próprio carrinho
        try:
            max_available_info = get_ingredient_max_available_quantity(
                ingredient_id=ing_id,
                max_quantity_from_rule=None,  # Será aplicado na validação individual
                item_quantity=item_quantity,
                base_portions=0,  # Extras sempre têm portions = 0
                cur=cur,  # Reutiliza conexão existente
                cart_id=cart_id  # ALTERAÇÃO: Passa cart_id para excluir reservas temporárias
            )
            
            ingredients_data[ing_id] = max_available_info
        except Exception as e:
            logger.warning(f"Erro ao calcular quantidade máxima para ingrediente {ing_id}: {e}", exc_info=True)
            # Fallback: retorna disponibilidade zero em caso de erro
            current_stock_decimal = Decimal(str(current_stock or 0))
            ingredients_data[ing_id] = {
                'max_available': 0,
                'limited_by': 'error',
                'stock_info': {
                    'current_stock': current_stock_decimal,
                    'stock_unit': stock_unit or 'un',
                    'base_portion_quantity': Decimal(str(base_portion_quantity or 1)),
                    'base_portion_unit': base_portion_unit or 'un'
                }
            }
    
    return ingredients_data


def _check_product_stock_availability(cur, product_id, quantity, cart_id=None):
    """
    Verifica se há estoque suficiente para um produto.
    Faz conversão correta de unidades antes de verificar.
    
    ALTERAÇÃO: Usa get_ingredient_available_stock que considera reservas confirmadas e temporárias.
    Se cart_id for fornecido, exclui reservas temporárias do próprio carrinho.
    
    Args:
        cur: Cursor do banco de dados
        product_id: ID do produto
        quantity: Quantidade do produto
        cart_id: ID do carrinho (opcional) - usado para excluir reservas temporárias do próprio carrinho
    
    Retorna (is_available, message)
    """
    try:
        # Busca ingredientes do produto com informações completas de unidades
        cur.execute("""
            SELECT 
                i.ID, 
                i.NAME, 
                pi.PORTIONS, 
                i.STOCK_UNIT,
                i.BASE_PORTION_QUANTITY,
                i.BASE_PORTION_UNIT
            FROM PRODUCT_INGREDIENTS pi
            JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
            WHERE pi.PRODUCT_ID = ? AND i.IS_AVAILABLE = TRUE
        """, (product_id,))
        
        ingredients = cur.fetchall()
        if not ingredients:
            return (True, "Produto sem ingredientes cadastrados")
        
        for row in ingredients:
            ing_id = row[0]
            name = row[1]
            portions = row[2] or 0
            stock_unit = row[3] or 'un'
            base_portion_quantity = row[4] or 1
            base_portion_unit = row[5] or 'un'
            
            # Calcula consumo convertido para unidade do estoque
            try:
                required_quantity = stock_service.calculate_consumption_in_stock_unit(
                    portions=portions,
                    base_portion_quantity=base_portion_quantity,
                    base_portion_unit=base_portion_unit,
                    stock_unit=stock_unit,
                    item_quantity=quantity
                )
            except ValueError as e:
                return (False, f"Erro na conversão de unidades para '{name}': {str(e)}")
            
            # ALTERAÇÃO: Usa get_ingredient_available_stock que considera reservas temporárias
            # Se cart_id for fornecido, exclui reservas temporárias do próprio carrinho
            # ALTERAÇÃO CRÍTICA: exclude_confirmed_reservations=True para não subtrair reservas confirmadas
            # Reservas confirmadas são para pedidos já finalizados e não devem bloquear adição ao carrinho
            # A validação final de estoque acontece apenas na finalização do pedido
            available_stock = stock_service.get_ingredient_available_stock(
                ing_id, 
                cur, 
                exclude_cart_id=cart_id,
                exclude_confirmed_reservations=True  # ALTERAÇÃO: Não subtrair reservas confirmadas na validação de carrinho
            )
            
            if available_stock < required_quantity:
                return (False, f"Estoque insuficiente para '{name}'. Disponível: {available_stock:.3f} {stock_unit}, Necessário: {required_quantity:.3f} {stock_unit}")
        
        return (True, "Estoque disponível")
        
    except Exception as e:
        logger.error(f"Erro ao verificar estoque do produto: {e}", exc_info=True)
        return (False, "Erro ao verificar disponibilidade de estoque")


def _check_ingredient_stock_availability(cur, ingredient_id, quantity):
    """
    Verifica se há estoque suficiente para um ingrediente específico.
    Retorna (is_available, message)
    """
    try:
        cur.execute("""
            SELECT NAME, CURRENT_STOCK, STOCK_UNIT, IS_AVAILABLE
            FROM INGREDIENTS
            WHERE ID = ?
        """, (ingredient_id,))
        
        result = cur.fetchone()
        if not result:
            return (False, "Ingrediente não encontrado")
        
        name, current_stock, stock_unit, is_available = result
        
        if not is_available:
            return (False, f"Ingrediente '{name}' não está disponível")
        
        current_stock = float(current_stock or 0)
        if current_stock < quantity:
            return (False, f"Estoque insuficiente de '{name}'. Necessário: {quantity:.2f} {stock_unit}, Disponível: {current_stock:.2f} {stock_unit}")
        
        return (True, "Estoque disponível")
        
    except Exception as e:
        logger.error(f"Erro ao verificar estoque do ingrediente: {e}", exc_info=True)
        return (False, "Erro ao verificar disponibilidade de estoque")


def remove_cart_item(user_id, cart_item_id):
    """
    Remove um item do carrinho
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se o item pertence ao usuário
        sql = """
            SELECT ci.ID FROM CART_ITEMS ci
            JOIN CARTS c ON ci.CART_ID = c.ID
            WHERE ci.ID = ? AND c.USER_ID = ? AND c.IS_ACTIVE = TRUE;
        """
        cur.execute(sql, (cart_item_id, user_id))
        if not cur.fetchone():
            return (False, "ITEM_NOT_FOUND", "Item não encontrado no seu carrinho")
        
        # CORREÇÃO: Remove explicitamente os extras antes de remover o item
        # (garante remoção mesmo se não houver cascade configurado)
        cur.execute("DELETE FROM CART_ITEM_EXTRAS WHERE CART_ITEM_ID = ?;", (cart_item_id,))
        
        # ALTERAÇÃO: Busca cart_id e user_id ANTES de remover item para evitar queries após deleção
        cur.execute("SELECT CART_ID FROM CART_ITEMS WHERE ID = ?", (cart_item_id,))
        cart_row = cur.fetchone()
        if not cart_row:
            return (False, "ITEM_NOT_FOUND", "Item não encontrado")
        
        item_cart_id = cart_row[0]
        
        # Busca user_id do carrinho antes de remover
        cur.execute("SELECT USER_ID FROM CARTS WHERE ID = ?", (item_cart_id,))
        cart_user_row = cur.fetchone()
        item_user_id = cart_user_row[0] if cart_user_row else user_id
        
        # ALTERAÇÃO: Remove o item ANTES de recriar reservas para evitar race condition
        # Remove o item primeiro
        sql = "DELETE FROM CART_ITEMS WHERE ID = ?;"
        cur.execute(sql, (cart_item_id,))
        
        # NOVA INTEGRAÇÃO: Recria reservas temporárias após remover item
        # (para atualizar reservas dos itens restantes)
        success, error_code, message = _recreate_temporary_reservations_for_cart(
            cart_id=item_cart_id,
            user_id=item_user_id,
            cur=cur
        )
        
        # Nota: Não retorna erro se falhar ao recriar reservas (item já foi removido)
        # Apenas loga o erro, mas commit a transação mesmo assim
        if not success:
            logger.warning(f"Erro ao recriar reservas temporárias após remover item: {error_code} - {message}")
            # ALTERAÇÃO: Em caso de erro, limpa todas as reservas do carrinho para evitar inconsistências
            try:
                cur.execute("DELETE FROM TEMPORARY_RESERVATIONS WHERE CART_ID = ?", (item_cart_id,))
            except Exception as e:
                logger.error(f"Erro ao limpar reservas temporárias após falha: {e}")
        
        conn.commit()
        return (True, None, "Item removido do carrinho com sucesso")
        
    except fdb.Error as e:
        logger.error(f"Erro ao remover item do carrinho: {e}", exc_info=True)
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def remove_cart_item_by_cart(cart_id, cart_item_id):
    """
    Remove item do carrinho convidado (por cart_id)
    """
    conn = None
    try:
        # Valida e converte cart_id
        cart_id = _validate_cart_id(cart_id)
        
        conn = get_db_connection()
        cur = conn.cursor()

        sql = (
            "SELECT ci.ID FROM CART_ITEMS ci "
            "JOIN CARTS c ON ci.CART_ID = c.ID "
            "WHERE ci.ID = ? AND c.ID = ? AND c.USER_ID IS NULL AND c.IS_ACTIVE = TRUE;"
        )
        cur.execute(sql, (cart_item_id, cart_id))
        if not cur.fetchone():
            return (False, "ITEM_NOT_FOUND", "Item não encontrado no carrinho informado")

        # CORREÇÃO: Remove explicitamente os extras antes de remover o item
        # (garante remoção mesmo se não houver cascade configurado)
        cur.execute("DELETE FROM CART_ITEM_EXTRAS WHERE CART_ITEM_ID = ?;", (cart_item_id,))
        
        # ALTERAÇÃO: Remove o item ANTES de recriar reservas para evitar race condition
        # Remove o item primeiro
        cur.execute("DELETE FROM CART_ITEMS WHERE ID = ?;", (cart_item_id,))
        
        # NOVA INTEGRAÇÃO: Recria reservas temporárias após remover item (visitante)
        # (para atualizar reservas dos itens restantes)
        # Recria reservas temporárias para todos os itens restantes do carrinho
        success, error_code, message = _recreate_temporary_reservations_for_cart(
            cart_id=cart_id,
            user_id=None,  # Visitante
            cur=cur
        )
        
        # Nota: Não retorna erro se falhar ao recriar reservas (item já foi removido)
        # Apenas loga o erro, mas commit a transação mesmo assim
        if not success:
            logger.warning(f"Erro ao recriar reservas temporárias após remover item: {error_code} - {message}")
            # ALTERAÇÃO: Em caso de erro, limpa todas as reservas do carrinho para evitar inconsistências
            try:
                cur.execute("DELETE FROM TEMPORARY_RESERVATIONS WHERE CART_ID = ?", (cart_id,))
            except Exception as e:
                logger.error(f"Erro ao limpar reservas temporárias após falha: {e}")
        
        conn.commit()
        return (True, None, "Item removido do carrinho com sucesso")
    except fdb.Error as e:
        logger.error(f"Erro ao remover item do carrinho por cart_id: {e}", exc_info=True)
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def clear_cart(user_id):
    """
    Limpa todo o carrinho do usuário
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca carrinho ativo
        sql = "SELECT ID FROM CARTS WHERE USER_ID = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql, (user_id,))
        cart = cur.fetchone()
        
        if cart:
            cart_id = cart[0]
            # NOVA INTEGRAÇÃO: Limpa reservas temporárias do carrinho antes de remover itens
            # Usa a função de limpeza do stock_service que aceita user_id e cart_id
            cur.execute("""
                DELETE FROM TEMPORARY_RESERVATIONS
                WHERE (USER_ID = ? AND CART_ID = ?) OR CART_ID = ?
            """, (user_id, cart_id, cart_id))
            
            # Remove todos os itens (cascade remove os extras)
            sql = "DELETE FROM CART_ITEMS WHERE CART_ID = ?;"
            cur.execute(sql, (cart_id,))
        
        conn.commit()
        return (True, None, "Carrinho limpo com sucesso")
        
    except fdb.Error as e:
        logger.error(f"Erro ao limpar carrinho: {e}", exc_info=True)
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def get_cart_for_order(user_id):
    """
    Busca o carrinho do usuário para conversão em pedido
    Retorna os dados necessários para criar o pedido
    """
    cart_summary = get_cart_summary(user_id)
    if not cart_summary or cart_summary["summary"]["is_empty"]:
        return None
    
    # Converte para formato de pedido
    order_items = []
    for item in cart_summary["items"]:
        order_item = {
            "product_id": item["product_id"],
            "quantity": item["quantity"],
            "extras": [],
            "base_modifications": []
        }
        
        for extra in item["extras"]:
            order_item["extras"].append({
                "ingredient_id": extra["ingredient_id"],
                "quantity": extra["quantity"]
            })
        
        for base_mod in item.get("base_modifications", []):
            order_item["base_modifications"].append({
                "ingredient_id": base_mod["ingredient_id"],
                "delta": base_mod["delta"]
            })
        
        order_items.append(order_item)
    
    return {
        "cart_id": cart_summary["cart"]["id"],
        "items": order_items,
        "total_amount": cart_summary["summary"]["subtotal"]
    }


def get_cart_summary_by_cart_id(cart_id):
    """
    Retorna o resumo do carrinho por cart_id (convidado)
    """
    items = get_cart_items(cart_id)
    if items is None:
        return None

    # OTIMIZAÇÃO: Usar função otimizada de disponibilidade (seção 1.7)
    availability_alerts = _check_availability_alerts(items)

    # Calcula totais
    total_items = sum(item["quantity"] for item in items)
    subtotal = sum(item["item_subtotal"] for item in items)

    return {
        "cart": {"id": cart_id, "user_id": None},
        "items": items,
        "summary": {
            "total_items": total_items,
            "subtotal": subtotal,
            "total": subtotal,
            "is_empty": len(items) == 0,
            "availability_alerts": availability_alerts
        }
    }


def validate_guest_cart_for_order(cart_id):
    """
    Valida se um carrinho de convidado pode ser convertido em pedido.
    Verifica disponibilidade de produtos e ingredientes.
    Retorna (is_valid, alerts, total_amount)
    """
    conn = None
    try:
        # Valida e converte cart_id
        cart_id = _validate_cart_id(cart_id)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se o carrinho existe e está ativo
        cur.execute("SELECT ID FROM CARTS WHERE ID = ? AND USER_ID IS NULL AND IS_ACTIVE = TRUE;", (cart_id,))
        if not cur.fetchone():
            return (False, ["Carrinho não encontrado ou inativo"], 0.0)
        
        # Busca itens do carrinho
        items = get_cart_items(cart_id)
        if not items:
            return (False, ["Carrinho vazio"], 0.0)
        
        alerts = []
        total_amount = 0.0
        
        for item in items:
            product_id = item["product_id"]
            quantity = item["quantity"]
            
            # Verifica se produto está ativo
            cur.execute("SELECT IS_ACTIVE, PRICE FROM PRODUCTS WHERE ID = ?;", (product_id,))
            product_row = cur.fetchone()
            if not product_row or not product_row[0]:
                alerts.append(f"Produto {item['product']['name']} não está mais disponível")
                continue
            
            product_price = float(product_row[1]) if product_row[1] else 0.0
            item_total = product_price * quantity
            
            # Verifica ingredientes base do produto
            cur.execute(
                """
                SELECT i.ID, i.NAME, i.IS_AVAILABLE
                FROM PRODUCT_INGREDIENTS pi
                JOIN INGREDIENTS i ON i.ID = pi.INGREDIENT_ID
                WHERE pi.PRODUCT_ID = ?
                """,
                (product_id,)
            )
            for ing_id, ing_name, is_available in cur.fetchall():
                if not is_available:
                    alerts.append(f"Ingrediente '{ing_name}' do produto '{item['product']['name']}' está indisponível")
            
            # Verifica extras
            for extra in item.get("extras", []):
                extra_id = extra["ingredient_id"]
                extra_qty = extra["quantity"]
                
                cur.execute("SELECT NAME, IS_AVAILABLE, COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID = ?;", (extra_id,))
                extra_row = cur.fetchone()
                if not extra_row:
                    alerts.append(f"Extra {extra_id} não encontrado")
                    continue
                
                extra_name, is_available, extra_price = extra_row
                if not is_available:
                    alerts.append(f"Extra '{extra_name}' está indisponível")
                else:
                    item_total += float(extra_price) * extra_qty
            
            total_amount += item_total
        
        is_valid = len(alerts) == 0
        return (is_valid, alerts, total_amount)
        
    except fdb.Error as e:
        logger.error(f"Erro ao validar carrinho de convidado: {e}", exc_info=True)
        return (False, ["Erro interno do servidor"], 0.0)
    finally:
        if conn: conn.close()


def claim_guest_cart(guest_cart_id, user_id):
    """
    Reivindica um carrinho convidado para um usuário.
    V1: Se o usuário não possui carrinho ativo, apenas atualiza USER_ID.
    V2-lite: Se já possui carrinho ativo, mescla itens do convidado e desativa o convidado.
    """
    conn = None
    try:
        # Valida e converte guest_cart_id
        guest_cart_id = _validate_cart_id(guest_cart_id)
        
        conn = get_db_connection()
        cur = conn.cursor()

        # Verifica carrinho convidado
        cur.execute("SELECT ID FROM CARTS WHERE ID = ? AND USER_ID IS NULL AND IS_ACTIVE = TRUE;", (guest_cart_id,))
        guest_row = cur.fetchone()
        if not guest_row:
            return (False, "CART_NOT_FOUND", "Carrinho convidado não encontrado")

        # Verifica se usuário já possui carrinho ativo
        cur.execute("SELECT ID FROM CARTS WHERE USER_ID = ? AND IS_ACTIVE = TRUE;", (user_id,))
        user_cart_row = cur.fetchone()

        if not user_cart_row:
            # Atualiza o carrinho convidado para o usuário
            cur.execute("UPDATE CARTS SET USER_ID = ? WHERE ID = ? AND USER_ID IS NULL;", (user_id, guest_cart_id))
            if cur.rowcount == 0:
                return (False, "CONFLICT", "Carrinho já foi reivindicado")
            
            # ALTERAÇÃO: Recria reservas temporárias após transferir carrinho para usuário
            # Isso garante que:
            # 1. Reservas expiradas sejam renovadas
            # 2. session_id seja atualizado de cart_{cart_id} para user_{user_id}_cart_{cart_id}
            # 3. Estoque seja revalidado após possível expiração
            success, error_code, message = _recreate_temporary_reservations_for_cart(
                cart_id=guest_cart_id,
                user_id=user_id,
                cur=cur
            )
            
            if not success:
                # Se falhar ao recriar reservas, faz rollback e retorna erro
                logger.error(f"Erro ao recriar reservas temporárias ao transferir carrinho: {message}")
                conn.rollback()
                return (False, error_code, message or "Erro ao validar estoque do carrinho")
            
            conn.commit()
            return (True, None, "Carrinho reivindicado com sucesso")

        # Mescla itens: usa carrinho existente do usuário
        user_cart_id = user_cart_row[0]

        # Copia itens do convidado para o carrinho do usuário (mescla por item idêntico)
        cur.execute("SELECT ID, PRODUCT_ID, QUANTITY, CAST(NOTES AS VARCHAR(1000)) FROM CART_ITEMS WHERE CART_ID = ?;", (guest_cart_id,))
        guest_items = cur.fetchall()
        for item_id, product_id, quantity, notes in guest_items:
            # Busca extras e base_modifications do item convidado (com TYPE, DELTA, UNIT_PRICE)
            cur.execute(
                "SELECT INGREDIENT_ID, COALESCE(DELTA, QUANTITY) AS DELTA, TYPE, UNIT_PRICE FROM CART_ITEM_EXTRAS WHERE CART_ITEM_ID = ? ORDER BY TYPE, INGREDIENT_ID;",
                (item_id,)
            )
            extras_rows = cur.fetchall()
            
            # Separa extras e base_modifications
            extras = []
            base_modifications = []
            for r in extras_rows:
                row_type = (r[2] or 'extra').lower()
                if row_type == 'extra':
                    extras.append({"ingredient_id": r[0], "quantity": r[1]})
                elif row_type == 'base':
                    base_modifications.append({"ingredient_id": r[0], "delta": r[1]})

            # Verifica item idêntico no carrinho do usuário (inclui base_modifications)
            identical_id = find_identical_cart_item(user_cart_id, product_id, extras, notes or "", base_modifications)
            if identical_id:
                cur.execute("UPDATE CART_ITEMS SET QUANTITY = QUANTITY + ? WHERE ID = ?;", (quantity, identical_id))
            else:
                cur.execute(
                    "INSERT INTO CART_ITEMS (CART_ID, PRODUCT_ID, QUANTITY, NOTES) VALUES (?, ?, ?, ?) RETURNING ID;",
                    (user_cart_id, product_id, quantity, notes)
                )
                new_user_item_id = cur.fetchone()[0]
                
                # Insere extras (TYPE='extra')
                for ex in extras:
                    cur.execute("SELECT COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID = ?;", (ex["ingredient_id"],))
                    price_row = cur.fetchone()
                    unit_price = float(price_row[0] or 0.0) if price_row else 0.0
                    cur.execute(
                        "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) VALUES (?, ?, ?, 'extra', ?, ?);",
                        (new_user_item_id, ex["ingredient_id"], ex["quantity"], ex["quantity"], unit_price)
                    )
                
                # Insere base_modifications (TYPE='base')
                for bm in base_modifications:
                    cur.execute("SELECT COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID = ?;", (bm["ingredient_id"],))
                    price_row = cur.fetchone()
                    unit_price = float(price_row[0] or 0.0) if price_row else 0.0
                    cur.execute(
                        "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) VALUES (?, ?, 0, 'base', ?, ?);",
                        (new_user_item_id, bm["ingredient_id"], bm["delta"], unit_price)
                    )

        # CORREÇÃO: Recria reservas temporárias para o carrinho do usuário após mesclar itens
        # Isso garante que as reservas do carrinho visitante sejam transferidas para o carrinho autenticado
        # Evita perda de reservas de estoque ao fazer login após adicionar produtos como visitante
        success, error_code, message = _recreate_temporary_reservations_for_cart(
            cart_id=user_cart_id,
            user_id=user_id,
            cur=cur
        )
        
        if not success:
            # Se falhar ao recriar reservas, faz rollback e retorna erro
            logger.error(f"Erro ao recriar reservas temporárias ao mesclar carrinho: {message}")
            conn.rollback()
            return (False, error_code, f"Erro ao mesclar carrinho: {message}")
        
        logger.info(f"Reservas temporárias recriadas para carrinho {user_cart_id} após mesclar com carrinho convidado {guest_cart_id}")

        # Deleta o carrinho convidado após mesclar (os itens já foram copiados)
        # Usa DELETE em vez de UPDATE para evitar violação da constraint UK_CARTS_USER_ACTIVE
        # As foreign keys têm ON DELETE CASCADE, então os itens e extras serão deletados automaticamente
        cur.execute("DELETE FROM CARTS WHERE ID = ?;", (guest_cart_id,))
        conn.commit()
        return (True, None, "Carrinho mesclado com sucesso")
    except fdb.Error as e:
        logger.error(f"Erro ao reivindicar carrinho convidado: {e}", exc_info=True)
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()
