import fdb
from datetime import datetime
from ..database import get_db_connection


def _calculate_discount_from_price_and_value(product_price, discount_value):
    """Calcula a porcentagem de desconto baseada no preço e valor do desconto"""
    if product_price <= 0:
        return 0.0
    percentage = (discount_value / product_price) * 100
    return round(percentage, 2)


def _calculate_discount_value_from_percentage(product_price, discount_percentage):
    """Calcula o valor do desconto baseado no preço e porcentagem"""
    if discount_percentage <= 0:
        return 0.0
    value = (product_price * discount_percentage) / 100
    return round(value, 2)


def _get_product_price(product_id, cur):
    """Obtém o preço atual do produto"""
    cur.execute("SELECT PRICE FROM PRODUCTS WHERE ID = ?", (product_id,))
    row = cur.fetchone()
    if row:
        return float(row[0])
    return None


def create_promotion(product_id, discount_value=None, discount_percentage=None, conversion_method='reais', expires_at=None, user_id=None):
    """
    Cria uma nova promoção para um produto
    
    Args:
        product_id: ID do produto
        discount_value: Valor do desconto em reais (se conversion_method='reais')
        discount_percentage: Porcentagem de desconto (se conversion_method='porcento')
        conversion_method: 'reais' ou 'porcento'
        expires_at: Data/hora de expiração (datetime ou string ISO)
        user_id: ID do usuário que está criando
    
    Returns:
        Tuple (promotion_dict, error_code, error_message)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se o produto existe
        product_price = _get_product_price(product_id, cur)
        if product_price is None:
            return (None, "PRODUCT_NOT_FOUND", "Produto não encontrado")
        
        # Verifica se já existe uma promoção para este produto
        cur.execute("SELECT ID FROM PROMOTIONS WHERE PRODUCT_ID = ?", (product_id,))
        if cur.fetchone():
            return (None, "PROMOTION_EXISTS", "Já existe uma promoção para este produto")
        
        # Valida e converte expires_at
        if expires_at:
            if isinstance(expires_at, str):
                try:
                    expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                except ValueError:
                    return (None, "INVALID_DATE", "Formato de data inválido. Use ISO format (YYYY-MM-DDTHH:MM:SS)")
            if expires_at <= datetime.now():
                return (None, "INVALID_DATE", "Data de expiração deve ser futura")
        else:
            return (None, "INVALID_DATE", "Data de expiração é obrigatória")
        
        # Processa o desconto baseado no método de conversão
        if conversion_method == 'reais':
            if discount_value is None or discount_value <= 0:
                return (None, "INVALID_DISCOUNT", "Valor do desconto deve ser maior que zero")
            if discount_value >= product_price:
                return (None, "INVALID_DISCOUNT", "Valor do desconto não pode ser maior ou igual ao preço do produto")
            discount_percentage = _calculate_discount_from_price_and_value(product_price, discount_value)
            final_discount_value = discount_value
        elif conversion_method == 'porcento':
            if discount_percentage is None or discount_percentage <= 0:
                return (None, "INVALID_DISCOUNT", "Porcentagem de desconto deve ser maior que zero")
            if discount_percentage >= 100:
                return (None, "INVALID_DISCOUNT", "Porcentagem de desconto não pode ser maior ou igual a 100%")
            final_discount_value = _calculate_discount_value_from_percentage(product_price, discount_percentage)
        else:
            return (None, "INVALID_METHOD", "Método de conversão deve ser 'reais' ou 'porcento'")
        
        # Insere a promoção
        sql = """
            INSERT INTO PROMOTIONS (PRODUCT_ID, DISCOUNT_PERCENTAGE, DISCOUNT_VALUE, EXPIRES_AT, CREATED_BY, UPDATED_BY)
            VALUES (?, ?, ?, ?, ?, ?)
            RETURNING ID, PRODUCT_ID, DISCOUNT_PERCENTAGE, DISCOUNT_VALUE, EXPIRES_AT, CREATED_AT, UPDATED_AT, CREATED_BY, UPDATED_BY
        """
        cur.execute(sql, (product_id, discount_percentage, final_discount_value, expires_at, user_id, user_id))
        row = cur.fetchone()
        
        conn.commit()
        
        promotion = {
            "id": row[0],
            "product_id": row[1],
            "discount_percentage": float(row[2]),
            "discount_value": float(row[3]),
            "expires_at": row[4].isoformat() if isinstance(row[4], datetime) else str(row[4]),
            "created_at": row[5].isoformat() if isinstance(row[5], datetime) else str(row[5]),
            "updated_at": row[6].isoformat() if isinstance(row[6], datetime) else str(row[6]),
            "created_by": row[7],
            "updated_by": row[8]
        }
        
        return (promotion, None, None)
        
    except fdb.Error as e:
        print(f"Erro ao criar promoção: {e}")
        if conn:
            conn.rollback()
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    except Exception as e:
        print(f"Erro inesperado ao criar promoção: {e}")
        if conn:
            conn.rollback()
        return (None, "GENERAL_ERROR", str(e))
    finally:
        if conn:
            conn.close()


def update_promotion(promotion_id, update_data, user_id=None):
    """
    Atualiza uma promoção existente
    
    Args:
        promotion_id: ID da promoção
        update_data: Dicionário com campos para atualizar
        user_id: ID do usuário que está atualizando
    
    Returns:
        Tuple (success, error_code, error_message)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se a promoção existe
        cur.execute("SELECT PRODUCT_ID, EXPIRES_AT FROM PROMOTIONS WHERE ID = ?", (promotion_id,))
        existing = cur.fetchone()
        if not existing:
            return (False, "PROMOTION_NOT_FOUND", "Promoção não encontrada")
        
        product_id = existing[0]
        current_expires_at = existing[1]
        
        # Obtém o preço atual do produto
        product_price = _get_product_price(product_id, cur)
        if product_price is None:
            return (False, "PRODUCT_NOT_FOUND", "Produto associado não encontrado")
        
        # Campos permitidos para atualização
        allowed_fields = ['discount_value', 'discount_percentage', 'conversion_method', 'expires_at']
        fields_to_update = {k: v for k, v in update_data.items() if k in allowed_fields}
        
        if not fields_to_update:
            return (False, "NO_VALID_FIELDS", "Nenhum campo válido para atualização foi fornecido")
        
        # Processa atualização de desconto
        conversion_method = fields_to_update.get('conversion_method', None)
        discount_value = fields_to_update.get('discount_value', None)
        discount_percentage = fields_to_update.get('discount_percentage', None)
        
        # Se está atualizando o desconto, precisa recalcular
        if discount_value is not None or discount_percentage is not None or conversion_method is not None:
            if conversion_method == 'reais':
                if discount_value is None:
                    return (False, "INVALID_DISCOUNT", "Valor do desconto é obrigatório quando método é 'reais'")
                if discount_value <= 0:
                    return (False, "INVALID_DISCOUNT", "Valor do desconto deve ser maior que zero")
                if discount_value >= product_price:
                    return (False, "INVALID_DISCOUNT", "Valor do desconto não pode ser maior ou igual ao preço do produto")
                new_percentage = _calculate_discount_from_price_and_value(product_price, discount_value)
                new_value = discount_value
            elif conversion_method == 'porcento':
                if discount_percentage is None:
                    return (False, "INVALID_DISCOUNT", "Porcentagem de desconto é obrigatória quando método é 'porcento'")
                if discount_percentage <= 0:
                    return (False, "INVALID_DISCOUNT", "Porcentagem de desconto deve ser maior que zero")
                if discount_percentage >= 100:
                    return (False, "INVALID_DISCOUNT", "Porcentagem de desconto não pode ser maior ou igual a 100%")
                new_value = _calculate_discount_value_from_percentage(product_price, discount_percentage)
                new_percentage = discount_percentage
            else:
                # Se não especificou método, usa o que já existe na promoção
                cur.execute("SELECT DISCOUNT_PERCENTAGE, DISCOUNT_VALUE FROM PROMOTIONS WHERE ID = ?", (promotion_id,))
                existing_discount = cur.fetchone()
                if existing_discount:
                    existing_percentage = float(existing_discount[0])
                    existing_value = float(existing_discount[1])
                    
                    # Se forneceu apenas valor, recalcula porcentagem
                    if discount_value is not None and discount_percentage is None:
                        new_percentage = _calculate_discount_from_price_and_value(product_price, discount_value)
                        new_value = discount_value
                    # Se forneceu apenas porcentagem, recalcula valor
                    elif discount_percentage is not None and discount_value is None:
                        new_value = _calculate_discount_value_from_percentage(product_price, discount_percentage)
                        new_percentage = discount_percentage
                    else:
                        # Mantém o existente se não especificou nada
                        new_percentage = existing_percentage
                        new_value = existing_value
                else:
                    return (False, "PROMOTION_NOT_FOUND", "Promoção não encontrada")
            
            # Atualiza desconto
            cur.execute("""
                UPDATE PROMOTIONS 
                SET DISCOUNT_PERCENTAGE = ?, DISCOUNT_VALUE = ?, UPDATED_AT = CURRENT_TIMESTAMP, UPDATED_BY = ?
                WHERE ID = ?
            """, (new_percentage, new_value, user_id, promotion_id))
        
        # Atualiza data de expiração se fornecida
        if 'expires_at' in fields_to_update:
            expires_at = fields_to_update['expires_at']
            if isinstance(expires_at, str):
                try:
                    expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                except ValueError:
                    return (False, "INVALID_DATE", "Formato de data inválido. Use ISO format (YYYY-MM-DDTHH:MM:SS)")
            if expires_at <= datetime.now():
                return (False, "INVALID_DATE", "Data de expiração deve ser futura")
            
            cur.execute("""
                UPDATE PROMOTIONS 
                SET EXPIRES_AT = ?, UPDATED_AT = CURRENT_TIMESTAMP, UPDATED_BY = ?
                WHERE ID = ?
            """, (expires_at, user_id, promotion_id))
        
        conn.commit()
        return (True, None, "Promoção atualizada com sucesso")
        
    except fdb.Error as e:
        print(f"Erro ao atualizar promoção: {e}")
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    except Exception as e:
        print(f"Erro inesperado ao atualizar promoção: {e}")
        if conn:
            conn.rollback()
        return (False, "GENERAL_ERROR", str(e))
    finally:
        if conn:
            conn.close()


def delete_promotion(promotion_id):
    """
    Remove uma promoção
    
    Args:
        promotion_id: ID da promoção
    
    Returns:
        Tuple (success, error_code, error_message)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se a promoção existe
        cur.execute("SELECT ID FROM PROMOTIONS WHERE ID = ?", (promotion_id,))
        if not cur.fetchone():
            return (False, "PROMOTION_NOT_FOUND", "Promoção não encontrada")
        
        # Remove a promoção
        cur.execute("DELETE FROM PROMOTIONS WHERE ID = ?", (promotion_id,))
        conn.commit()
        
        return (True, None, "Promoção removida com sucesso")
        
    except fdb.Error as e:
        print(f"Erro ao remover promoção: {e}")
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()


def get_all_promotions(include_expired=False):
    """
    Lista todas as promoções com detalhes dos produtos
    
    Args:
        include_expired: Se True, inclui promoções expiradas
    
    Returns:
        Lista de promoções com detalhes
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        if include_expired:
            sql = """
                SELECT p.ID, p.PRODUCT_ID, p.DISCOUNT_PERCENTAGE, p.DISCOUNT_VALUE, 
                       p.EXPIRES_AT, p.CREATED_AT, p.UPDATED_AT, p.CREATED_BY, p.UPDATED_BY,
                       pr.NAME, pr.PRICE, pr.IMAGE_URL, pr.IS_ACTIVE,
                       u1.FULL_NAME as CREATED_BY_NAME, u2.FULL_NAME as UPDATED_BY_NAME
                FROM PROMOTIONS p
                JOIN PRODUCTS pr ON p.PRODUCT_ID = pr.ID
                LEFT JOIN USERS u1 ON p.CREATED_BY = u1.ID
                LEFT JOIN USERS u2 ON p.UPDATED_BY = u2.ID
                ORDER BY p.CREATED_AT DESC
            """
        else:
            sql = """
                SELECT p.ID, p.PRODUCT_ID, p.DISCOUNT_PERCENTAGE, p.DISCOUNT_VALUE, 
                       p.EXPIRES_AT, p.CREATED_AT, p.UPDATED_AT, p.CREATED_BY, p.UPDATED_BY,
                       pr.NAME, pr.PRICE, pr.IMAGE_URL, pr.IS_ACTIVE,
                       u1.FULL_NAME as CREATED_BY_NAME, u2.FULL_NAME as UPDATED_BY_NAME
                FROM PROMOTIONS p
                JOIN PRODUCTS pr ON p.PRODUCT_ID = pr.ID
                LEFT JOIN USERS u1 ON p.CREATED_BY = u1.ID
                LEFT JOIN USERS u2 ON p.UPDATED_BY = u2.ID
                WHERE p.EXPIRES_AT > CURRENT_TIMESTAMP
                ORDER BY p.CREATED_AT DESC
            """
        
        cur.execute(sql)
        promotions = []
        
        for row in cur.fetchall():
            promotion = {
                "id": row[0],
                "product_id": row[1],
                "discount_percentage": float(row[2]),
                "discount_value": float(row[3]),
                "expires_at": row[4].isoformat() if isinstance(row[4], datetime) else str(row[4]),
                "created_at": row[5].isoformat() if isinstance(row[5], datetime) else str(row[5]),
                "updated_at": row[6].isoformat() if isinstance(row[6], datetime) else str(row[6]),
                "created_by": row[7],
                "updated_by": row[8],
                "product": {
                    "id": row[1],
                    "name": row[9],
                    "price": float(row[10]),
                    "image_url": row[11],
                    "is_active": bool(row[12])
                },
                "created_by_name": row[13],
                "updated_by_name": row[14]
            }
            
            # Calcula preço final com desconto
            final_price = float(row[10]) - float(row[3])
            promotion["final_price"] = round(final_price, 2)
            
            promotions.append(promotion)
        
        return promotions
        
    except fdb.Error as e:
        print(f"Erro ao listar promoções: {e}")
        return []
    finally:
        if conn:
            conn.close()


def get_promotion_by_id(promotion_id):
    """
    Obtém uma promoção específica por ID
    
    Args:
        promotion_id: ID da promoção
    
    Returns:
        Dicionário com dados da promoção ou None
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT p.ID, p.PRODUCT_ID, p.DISCOUNT_PERCENTAGE, p.DISCOUNT_VALUE, 
                   p.EXPIRES_AT, p.CREATED_AT, p.UPDATED_AT, p.CREATED_BY, p.UPDATED_BY,
                   pr.NAME, pr.PRICE, pr.DESCRIPTION, pr.IMAGE_URL, pr.IS_ACTIVE, pr.CATEGORY_ID,
                   u1.FULL_NAME as CREATED_BY_NAME, u2.FULL_NAME as UPDATED_BY_NAME
            FROM PROMOTIONS p
            JOIN PRODUCTS pr ON p.PRODUCT_ID = pr.ID
            LEFT JOIN USERS u1 ON p.CREATED_BY = u1.ID
            LEFT JOIN USERS u2 ON p.UPDATED_BY = u2.ID
            WHERE p.ID = ?
        """
        
        cur.execute(sql, (promotion_id,))
        row = cur.fetchone()
        
        if row:
            promotion = {
                "id": row[0],
                "product_id": row[1],
                "discount_percentage": float(row[2]),
                "discount_value": float(row[3]),
                "expires_at": row[4].isoformat() if isinstance(row[4], datetime) else str(row[4]),
                "created_at": row[5].isoformat() if isinstance(row[5], datetime) else str(row[5]),
                "updated_at": row[6].isoformat() if isinstance(row[6], datetime) else str(row[6]),
                "created_by": row[7],
                "updated_by": row[8],
                "product": {
                    "id": row[1],
                    "name": row[9],
                    "price": float(row[10]),
                    "description": row[11],
                    "image_url": row[12],
                    "is_active": bool(row[13]),
                    "category_id": row[14]
                },
                "created_by_name": row[15],
                "updated_by_name": row[16]
            }
            
            # Calcula preço final com desconto
            final_price = float(row[10]) - float(row[3])
            promotion["final_price"] = round(final_price, 2)
            
            return promotion
        
        return None
        
    except fdb.Error as e:
        print(f"Erro ao buscar promoção por ID: {e}")
        return None
    finally:
        if conn:
            conn.close()


def get_promotion_by_product_id(product_id):
    """
    Obtém a promoção ativa de um produto específico
    
    Args:
        product_id: ID do produto
    
    Returns:
        Dicionário com dados da promoção ou None
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT ID, PRODUCT_ID, DISCOUNT_PERCENTAGE, DISCOUNT_VALUE, 
                   EXPIRES_AT, CREATED_AT, UPDATED_AT, CREATED_BY, UPDATED_BY
            FROM PROMOTIONS
            WHERE PRODUCT_ID = ? AND EXPIRES_AT > CURRENT_TIMESTAMP
        """
        
        cur.execute(sql, (product_id,))
        row = cur.fetchone()
        
        if row:
            return {
                "id": row[0],
                "product_id": row[1],
                "discount_percentage": float(row[2]),
                "discount_value": float(row[3]),
                "expires_at": row[4].isoformat() if isinstance(row[4], datetime) else str(row[4]),
                "created_at": row[5].isoformat() if isinstance(row[5], datetime) else str(row[5]),
                "updated_at": row[6].isoformat() if isinstance(row[6], datetime) else str(row[6]),
                "created_by": row[7],
                "updated_by": row[8]
            }
        
        return None
        
    except fdb.Error as e:
        print(f"Erro ao buscar promoção por produto: {e}")
        return None
    finally:
        if conn:
            conn.close()


def recalculate_promotion_discount_value(product_id):
    """
    Recalcula o valor do desconto de uma promoção quando o preço do produto muda
    Mantém a porcentagem e recalcula o valor em reais
    
    Args:
        product_id: ID do produto
    
    Returns:
        Tuple (success, error_code, error_message)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se existe promoção para este produto
        cur.execute("SELECT ID, DISCOUNT_PERCENTAGE FROM PROMOTIONS WHERE PRODUCT_ID = ?", (product_id,))
        promotion = cur.fetchone()
        
        if not promotion:
            # Não há promoção, não precisa recalcular
            return (True, None, None)
        
        promotion_id = promotion[0]
        discount_percentage = float(promotion[1])
        
        # Obtém o novo preço do produto
        product_price = _get_product_price(product_id, cur)
        if product_price is None:
            return (False, "PRODUCT_NOT_FOUND", "Produto não encontrado")
        
        # Recalcula o valor do desconto mantendo a porcentagem
        new_discount_value = _calculate_discount_value_from_percentage(product_price, discount_percentage)
        
        # Atualiza o valor do desconto
        cur.execute("""
            UPDATE PROMOTIONS 
            SET DISCOUNT_VALUE = ?, UPDATED_AT = CURRENT_TIMESTAMP
            WHERE ID = ?
        """, (new_discount_value, promotion_id))
        
        conn.commit()
        return (True, None, None)
        
    except fdb.Error as e:
        print(f"Erro ao recalcular desconto da promoção: {e}")
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()

