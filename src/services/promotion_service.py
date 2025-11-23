import fdb
import logging
from datetime import datetime, timezone
from ..database import get_db_connection

# ALTERAÇÃO: Logger centralizado para substituir print() em produção
logger = logging.getLogger(__name__)


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
        
        # ALTERAÇÃO: Verifica se já existe uma promoção para este produto
        cur.execute("SELECT ID FROM PROMOTIONS WHERE PRODUCT_ID = ?", (product_id,))
        existing_promo = cur.fetchone()
        if existing_promo:
            return (None, "PROMOTION_EXISTS", f"Já existe uma promoção para este produto (ID: {existing_promo[0]})")
        
        # ALTERAÇÃO: Valida e converte expires_at - tratar como hora local (sem conversão de timezone)
        if expires_at:
            if isinstance(expires_at, str):
                try:
                    # Remove 'Z' se presente e tratar como hora local (sem timezone)
                    if expires_at.endswith('Z'):
                        expires_at = expires_at[:-1]  # Remove apenas o 'Z'
                    expires_at = datetime.fromisoformat(expires_at)
                    # Não adicionar timezone - tratar como naive datetime (hora local)
                    # O banco de dados armazenará como está
                except ValueError:
                    return (None, "INVALID_DATE", "Formato de data inválido. Use ISO format (YYYY-MM-DDTHH:MM:SS)")
            # ALTERAÇÃO: Comparar com datetime local (sem timezone)
            now_local = datetime.now()
            if expires_at.tzinfo is not None:
                # Se tiver timezone, remover para comparar como local
                expires_at = expires_at.replace(tzinfo=None)
            if expires_at <= now_local:
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
        
        # ALTERAÇÃO: Enviar notificações e emails para clientes sobre a nova promoção
        # Respeita preferências de notificação de cada usuário
        try:
            from . import notification_service, product_service, user_service, email_service
            
            # Obter informações do produto para a mensagem
            product = product_service.get_product_by_id(product_id)
            product_name = product.get('name', 'produto') if product else 'produto'
            
            # Formatar mensagem da promoção
            if conversion_method == 'reais':
                discount_text = f"R$ {discount_value:.2f} de desconto"
            else:
                discount_text = f"{discount_percentage:.0f}% de desconto"
            
            message = f"🎉 Nova promoção! {discount_text} em {product_name}! Aproveite já!"
            link = f"/menu?promotion={promotion['id']}"
            
            # Enviar notificação para todos os clientes (respeitando preferências)
            notification_service.create_notification_for_roles(
                roles=['customer'],
                message=message,
                link=link,
                notification_type='promotion'
            )
            
            # ALTERAÇÃO: Enviar emails de promoção respeitando preferências
            try:
                # Obter todos os clientes
                customers = user_service.get_users_by_role(['customer'])
                
                # Obter URL da aplicação
                from ..config import Config
                
                emails_sent = 0
                for customer in customers:
                    # Verificar preferências de notificação
                    preferences = user_service.get_notification_preferences(customer['id'])
                    
                    # Enviar email apenas se o cliente tiver preferência habilitada
                    if preferences and preferences.get('notify_promotions', True):
                        try:
                            email_service.send_email(
                                to=customer['email'],
                                subject=f"🎉 Nova Promoção: {product_name} - Royal Burger",
                                template='promotion_notification',
                                user={'full_name': customer['full_name']},
                                promotion=promotion,
                                product=product if product else {'name': product_name, 'description': ''},
                                app_url=Config.APP_URL
                            )
                            emails_sent += 1
                        except Exception as email_err:
                            # Log erro individual mas continua para outros clientes
                            logger.warning(f"Erro ao enviar email de promoção para {customer['email']}: {email_err}")
                
                logger.info(f"Emails de promoção enviados: {emails_sent} de {len(customers)} clientes")
            except Exception as email_batch_err:
                # Não falha a criação da promoção se houver erro ao enviar emails
                logger.warning(f"Erro ao enviar emails de promoção: {email_batch_err}", exc_info=True)
        except Exception as e:
            # Não falha a criação da promoção se houver erro ao enviar notificações
            logger.warning(f"Erro ao enviar notificações de promoção: {e}", exc_info=True)
        
        return (promotion, None, None)
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logger.error() para logging estruturado
        logger.error(f"Erro ao criar promoção: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    except Exception as e:
        # ALTERAÇÃO: Substituído print() por logger.error() para logging estruturado
        logger.error(f"Erro inesperado ao criar promoção: {e}", exc_info=True)
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
                    # Remove 'Z' se presente e tratar como hora local (sem timezone)
                    if expires_at.endswith('Z'):
                        expires_at = expires_at[:-1]  # Remove apenas o 'Z'
                    expires_at = datetime.fromisoformat(expires_at)
                    # Não adicionar timezone - tratar como naive datetime (hora local)
                except ValueError:
                    return (False, "INVALID_DATE", "Formato de data inválido. Use ISO format (YYYY-MM-DDTHH:MM:SS)")
            # ALTERAÇÃO: Comparar com datetime local (sem timezone)
            now_local = datetime.now()
            if expires_at.tzinfo is not None:
                # Se tiver timezone, remover para comparar como local
                expires_at = expires_at.replace(tzinfo=None)
            if expires_at <= now_local:
                return (False, "INVALID_DATE", "Data de expiração deve ser futura")
            
            cur.execute("""
                UPDATE PROMOTIONS 
                SET EXPIRES_AT = ?, UPDATED_AT = CURRENT_TIMESTAMP, UPDATED_BY = ?
                WHERE ID = ?
            """, (expires_at, user_id, promotion_id))
        
        conn.commit()
        return (True, None, "Promoção atualizada com sucesso")
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logger.error() para logging estruturado
        logger.error(f"Erro ao atualizar promoção: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    except Exception as e:
        # ALTERAÇÃO: Substituído print() por logger.error() para logging estruturado
        logger.error(f"Erro inesperado ao atualizar promoção: {e}", exc_info=True)
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
        # ALTERAÇÃO: Substituído print() por logger.error() para logging estruturado
        logger.error(f"Erro ao remover promoção: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()


def get_all_promotions(include_expired=False, search=None, status=None, page=1, page_size=20):
    """
    Lista todas as promoções com detalhes dos produtos
    ALTERAÇÃO: Suporta filtros padronizados (search, status) e paginação
    
    Args:
        include_expired: Se True, inclui promoções expiradas (legado)
        search: Busca por nome do produto ou ID da promoção (padronizado)
        status: Filtro por status - "ativas" ou "expiradas" (padronizado)
        page: Número da página (padronizado)
        page_size: Itens por página (padronizado)
    
    Returns:
        Dict com items, pagination (count, total_pages, current_page, next, previous)
    """
    # ALTERAÇÃO: Validação de paginação
    from ..utils.validators import validate_pagination_params
    try:
        page, page_size, offset = validate_pagination_params(page, page_size, max_page_size=100)
    except ValueError:
        page, page_size, offset = 1, 20, 0
    
    # ALTERAÇÃO: Determinar filtro de status baseado em parâmetros padronizados
    now = datetime.now()
    if status:
        if status.lower() == 'ativas':
            include_expired = False
            filter_expired = "CAST(p.EXPIRES_AT AS TIMESTAMP) > CAST(CURRENT_TIMESTAMP AS TIMESTAMP)"
        elif status.lower() == 'expiradas':
            include_expired = True
            filter_expired = "CAST(p.EXPIRES_AT AS TIMESTAMP) <= CAST(CURRENT_TIMESTAMP AS TIMESTAMP)"
        else:
            # Status não reconhecido, usar include_expired padrão
            filter_expired = "1=1" if include_expired else "CAST(p.EXPIRES_AT AS TIMESTAMP) > CAST(CURRENT_TIMESTAMP AS TIMESTAMP)"
    else:
        # Sem status padronizado, usar include_expired legado
        filter_expired = "1=1" if include_expired else "CAST(p.EXPIRES_AT AS TIMESTAMP) > CAST(CURRENT_TIMESTAMP AS TIMESTAMP)"
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # ALTERAÇÃO: Construir WHERE clauses dinamicamente
        where_clauses = ["pr.IS_ACTIVE = TRUE", filter_expired]
        params = []
        
        # ALTERAÇÃO: Adicionar filtro de busca (search)
        if search:
            where_clauses.append("(UPPER(pr.NAME) LIKE UPPER(?) OR CAST(p.ID AS VARCHAR(50)) LIKE ?)")
            search_pattern = f"%{search}%"
            params.append(search_pattern)
            params.append(search_pattern)
        
        where_sql = " AND ".join(where_clauses)
        
        # ALTERAÇÃO: Contar total antes de paginar
        count_sql = f"""
            SELECT COUNT(*)
            FROM PROMOTIONS p
            INNER JOIN PRODUCTS pr ON p.PRODUCT_ID = pr.ID
            WHERE {where_sql}
        """
        cur.execute(count_sql, tuple(params))
        total = cur.fetchone()[0] or 0
        
        # ALTERAÇÃO: Query com paginação usando FIRST/SKIP do Firebird
        sql = f"""
            SELECT FIRST {page_size} SKIP {offset}
                p.ID, p.PRODUCT_ID, p.DISCOUNT_PERCENTAGE, p.DISCOUNT_VALUE, 
                p.EXPIRES_AT, p.CREATED_AT, p.UPDATED_AT, p.CREATED_BY, p.UPDATED_BY,
                pr.NAME, pr.DESCRIPTION, pr.PRICE, pr.IMAGE_URL, pr.IS_ACTIVE,
                pr.PREPARATION_TIME_MINUTES, pr.CATEGORY_ID,
                u1.FULL_NAME as CREATED_BY_NAME, u2.FULL_NAME as UPDATED_BY_NAME
            FROM PROMOTIONS p
            INNER JOIN PRODUCTS pr ON p.PRODUCT_ID = pr.ID
            LEFT JOIN USERS u1 ON p.CREATED_BY = u1.ID
            LEFT JOIN USERS u2 ON p.UPDATED_BY = u2.ID
            WHERE {where_sql}
            ORDER BY p.CREATED_AT DESC
        """
        
        cur.execute(sql, tuple(params))
        promotions = []
        
        for row in cur.fetchall():
            promotion = {
                "id": row[0],
                "product_id": row[1],
                "discount_percentage": float(row[2]) if row[2] else 0.0,
                "discount_value": float(row[3]) if row[3] else 0.0,
                "expires_at": row[4].isoformat() if isinstance(row[4], datetime) else str(row[4]),
                "created_at": row[5].isoformat() if isinstance(row[5], datetime) else str(row[5]),
                "updated_at": row[6].isoformat() if isinstance(row[6], datetime) else str(row[6]),
                "created_by": row[7],
                "updated_by": row[8],
                "product": {
                    "id": row[1],
                    "name": row[9],
                    "description": row[10] if row[10] else "",
                    "price": str(float(row[11])),
                    "image_url": row[12] if row[12] else None,
                    "is_active": bool(row[13]),
                    "preparation_time_minutes": row[14] if row[14] else 0,
                    "category_id": row[15] if row[15] else None
                },
                "created_by_name": row[16] if row[16] else None,
                "updated_by_name": row[17] if row[17] else None
            }
            
            # ALTERAÇÃO: Calcula preço final com desconto (valor ou percentual)
            # Se tem discount_value, usa ele; senão calcula do percentual
            product_price = float(row[11])
            discount_value = float(row[3]) if row[3] else 0.0
            discount_percentage = float(row[2]) if row[2] else 0.0
            
            if discount_value > 0:
                final_price = product_price - discount_value
            elif discount_percentage > 0:
                final_price = product_price * (1 - discount_percentage / 100)
            else:
                final_price = product_price
            
            promotion["final_price"] = round(final_price, 2)
            
            # ALTERAÇÃO: Adicionar hash da imagem se existir
            # Usa a mesma função que product_service para consistência
            if row[12]:
                try:
                    # Importar função de product_service que já tem a implementação
                    from . import product_service
                    promotion["product"]["image_hash"] = product_service._get_image_hash(row[12])
                except Exception:
                    promotion["product"]["image_hash"] = None
            
            promotions.append(promotion)
        
        # ALTERAÇÃO: Retornar formato padronizado com paginação
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        
        return {
            "items": promotions,
            "pagination": {
                "total": total,
                "total_pages": total_pages,
                "current_page": page,
                "page_size": page_size,
                "next": page + 1 if page < total_pages else None,
                "previous": page - 1 if page > 1 else None
            }
        }
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logger.error() para logging estruturado
        logger.error(f"Erro ao listar promoções: {e}", exc_info=True)
        return {
            "items": [],
            "pagination": {
                "total": 0,
                "total_pages": 1,
                "current_page": page,
                "page_size": page_size,
                "next": None,
                "previous": None
            }
        }
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
        # ALTERAÇÃO: Substituído print() por logger.error() para logging estruturado
        logger.error(f"Erro ao buscar promoção por ID: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def get_promotion_by_product_id(product_id, include_expired=False):
    """
    Obtém a promoção de um produto específico
    
    Args:
        product_id: ID do produto
        include_expired: Se True, inclui promoções expiradas
    
    Returns:
        Dicionário com dados da promoção ou None
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # ALTERAÇÃO: Buscar qualquer promoção se include_expired=True, senão apenas ativas
        if include_expired:
            sql = """
                SELECT ID, PRODUCT_ID, DISCOUNT_PERCENTAGE, DISCOUNT_VALUE, 
                       EXPIRES_AT, CREATED_AT, UPDATED_AT, CREATED_BY, UPDATED_BY
                FROM PROMOTIONS
                WHERE PRODUCT_ID = ?
                ORDER BY CREATED_AT DESC
            """
            cur.execute(sql, (product_id,))
        else:
            sql = """
                SELECT ID, PRODUCT_ID, DISCOUNT_PERCENTAGE, DISCOUNT_VALUE, 
                       EXPIRES_AT, CREATED_AT, UPDATED_AT, CREATED_BY, UPDATED_BY
                FROM PROMOTIONS
                WHERE PRODUCT_ID = ? AND CAST(EXPIRES_AT AS TIMESTAMP) > CAST(CURRENT_TIMESTAMP AS TIMESTAMP)
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
        # ALTERAÇÃO: Substituído print() por logger.error() para logging estruturado
        logger.error(f"Erro ao buscar promoção por produto: {e}", exc_info=True)
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
        # ALTERAÇÃO: Substituído print() por logger.error() para logging estruturado
        logger.error(f"Erro ao recalcular desconto da promoção: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()

