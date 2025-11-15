import fdb  
import logging
from decimal import Decimal
from ..database import get_db_connection

# ALTERAÇÃO: Configurar logger estruturado para substituir print()
logger = logging.getLogger(__name__)  

def create_ingredient(data):  
    name = (data.get('name') or '').strip()  
    stock_unit = (data.get('stock_unit') or '').strip()  
    price = data.get('price', 0.0)  
    additional_price = data.get('additional_price', 0.0)
    current_stock = data.get('current_stock', 0.0)  
    min_stock_threshold = data.get('min_stock_threshold', 0.0)  
    max_stock = data.get('max_stock', 0.0)  
    supplier = (data.get('supplier') or '').strip()  
    category = (data.get('category') or '').strip()  
    # Campos para porção base
    base_portion_quantity = data.get('base_portion_quantity', 1.0)
    base_portion_unit = (data.get('base_portion_unit') or 'un').strip()
    
    if not name:  
        return (None, "INVALID_NAME", "Nome do insumo é obrigatório")  
    if not stock_unit:  
        return (None, "INVALID_UNIT", "Unidade do insumo é obrigatória")  
    if price is None or float(price) < 0:  
        return (None, "INVALID_COST", "Custo (price) deve ser maior ou igual a zero")  
    if additional_price is None or float(additional_price) < 0:
        return (None, "INVALID_ADDITIONAL_PRICE", "additional_price deve ser maior ou igual a zero")
    if current_stock is not None and float(current_stock) < 0:  
        return (None, "INVALID_STOCK", "Estoque atual não pode ser negativo")  
    if min_stock_threshold is not None and float(min_stock_threshold) < 0:  
        return (None, "INVALID_MIN_STOCK", "Estoque mínimo não pode ser negativo")  
    if max_stock is not None and float(max_stock) < 0:  
        return (None, "INVALID_MAX_STOCK", "Estoque máximo não pode ser negativo")
    if base_portion_quantity is None or float(base_portion_quantity) <= 0:  
        return (None, "INVALID_BASE_PORTION_QUANTITY", "Quantidade da porção base deve ser maior que zero")  
    if not base_portion_unit:  
        return (None, "INVALID_BASE_PORTION_UNIT", "Unidade da porção base é obrigatória")  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        # nome único (case-insensitive) - verificação mais robusta
        cur.execute("SELECT ID, NAME FROM INGREDIENTS WHERE UPPER(TRIM(NAME)) = UPPER(TRIM(?))", (name,))  
        existing = cur.fetchone()
        if existing:  
            return (None, "INGREDIENT_NAME_EXISTS", f"Já existe um insumo com o nome '{existing[1]}' (ID: {existing[0]})")  
        sql = "INSERT INTO INGREDIENTS (NAME, PRICE, ADDITIONAL_PRICE, CURRENT_STOCK, STOCK_UNIT, MIN_STOCK_THRESHOLD, MAX_STOCK, SUPPLIER, CATEGORY, BASE_PORTION_QUANTITY, BASE_PORTION_UNIT) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING ID, NAME, PRICE, ADDITIONAL_PRICE, IS_AVAILABLE, CURRENT_STOCK, STOCK_UNIT, MIN_STOCK_THRESHOLD, MAX_STOCK, SUPPLIER, CATEGORY, BASE_PORTION_QUANTITY, BASE_PORTION_UNIT;"  
        cur.execute(sql, (  
            name,  
            price,
            additional_price,
            current_stock,  
            stock_unit,  
            min_stock_threshold,  
            max_stock,  
            supplier,  
            category,
            base_portion_quantity,
            base_portion_unit
        ))  
        row = cur.fetchone()  
        conn.commit()  
        return ({  
            "id": row[0], "name": row[1],  
            "price": float(row[2]) if row[2] is not None else 0.0,
            "additional_price": float(row[3]) if row[3] is not None else 0.0,
            "is_available": row[4],  
            "current_stock": float(row[5]) if row[5] is not None else 0.0,  
            "stock_unit": row[6],  
            "min_stock_threshold": float(row[7]) if row[7] is not None else 0.0,  
            "max_stock": float(row[8]) if row[8] is not None else 0.0,  
            "supplier": row[9] if row[9] else "",  
            "category": row[10] if row[10] else "",
            "base_portion_quantity": float(row[11]) if row[11] is not None else 1.0,
            "base_portion_unit": row[12] if row[12] else "un"
        }, None, None)
    except fdb.Error as e:  
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao criar ingrediente: {e}", exc_info=True)  
        if conn: conn.rollback()  
        
        # Verificar se é erro de constraint de nome único
        if e.args and len(e.args) > 1 and e.args[1] == -803:
            return (None, "INGREDIENT_NAME_EXISTS", f"Já existe um insumo com o nome '{name}'. Verifique se não há duplicatas.")
        
        return (None, "DATABASE_ERROR", "Erro interno do servidor")  
    finally:  
        if conn: conn.close()  

def list_ingredients(name_filter=None, status_filter=None, category_filter=None, page=1, page_size=10):  
    # OTIMIZAÇÃO: Usar validador centralizado de paginação
    from ..utils.validators import validate_pagination_params
    try:
        page, page_size, offset = validate_pagination_params(page, page_size, max_page_size=100)
    except ValueError:
        page, page_size, offset = 1, 10, 0  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        where = []  
        params = []  
        if name_filter:  
            where.append("UPPER(NAME) LIKE UPPER(?)")  
            params.append(f"%{name_filter}%")  
        if category_filter:  
            where.append("UPPER(CATEGORY) = UPPER(?)")  
            params.append(category_filter)  
        if status_filter == 'low_stock':  
            where.append("CURRENT_STOCK <= MIN_STOCK_THRESHOLD AND CURRENT_STOCK > 0")  
        elif status_filter == 'out_of_stock':  
            where.append("CURRENT_STOCK = 0")  
        elif status_filter == 'in_stock':  
            where.append("CURRENT_STOCK > MIN_STOCK_THRESHOLD")  
        elif status_filter == 'unavailable':  
            where.append("IS_AVAILABLE = FALSE")  
        elif status_filter == 'available':  
            where.append("IS_AVAILABLE = TRUE")  
        elif status_filter == 'overstock':  
            where.append("CURRENT_STOCK > MAX_STOCK AND MAX_STOCK > 0")  
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""  
        # total  
        # ALTERAÇÃO: Query parametrizada - where_sql é construído de forma segura (apenas cláusulas fixas)
        cur.execute(f"SELECT COUNT(*) FROM INGREDIENTS{where_sql};", tuple(params))  
        total = cur.fetchone()[0] or 0  
        # page  
        cur.execute(  
            f"SELECT FIRST {page_size} SKIP {offset} ID, NAME, PRICE, ADDITIONAL_PRICE, IS_AVAILABLE, CURRENT_STOCK, STOCK_UNIT, MIN_STOCK_THRESHOLD, MAX_STOCK, SUPPLIER, CATEGORY, BASE_PORTION_QUANTITY, BASE_PORTION_UNIT "  
            f"FROM INGREDIENTS{where_sql} ORDER BY NAME;",  
            tuple(params)  
        )  
        items = [{  
            "id": row[0],  
            "name": row[1],  
            "price": float(row[2]) if row[2] is not None else 0.0,
            "additional_price": float(row[3]) if row[3] is not None else 0.0,
            "is_available": row[4],  
            "current_stock": float(row[5]) if row[5] is not None else 0.0,  
            "stock_unit": row[6],  
            "min_stock_threshold": float(row[7]) if row[7] is not None else 0.0,  
            "max_stock": float(row[8]) if row[8] is not None else 0.0,  
            "supplier": row[9] if row[9] else "",  
            "category": row[10] if row[10] else "",
            "base_portion_quantity": float(row[11]) if row[11] is not None else 1.0,
            "base_portion_unit": row[12] if row[12] else "un"
        } for row in cur.fetchall()]  
        total_pages = (total + page_size - 1) // page_size  
        return {  
            "items": items,  
            "pagination": {  
                "total": total,  
                "page": page,  
                "page_size": page_size,  
                "total_pages": total_pages  
            }  
        }  
    except fdb.Error as e:  
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao buscar ingredientes: {e}", exc_info=True)  
        return {  
            "items": [],  
            "pagination": {  
                "total": 0,  
                "page": page,  
                "page_size": page_size,  
                "total_pages": 0  
            }  
        }  
    finally:  
        if conn: conn.close()  

def update_ingredient(ingredient_id, data):  
    allowed_fields = ['name', 'price', 'additional_price', 'stock_unit', 'current_stock', 'min_stock_threshold', 'max_stock', 'supplier', 'category', 'is_available', 'base_portion_quantity', 'base_portion_unit']
    fields_to_update = {k: v for k, v in data.items() if k in allowed_fields}  
    if not fields_to_update:  
        return (False, "NO_VALID_FIELDS", "Nenhum campo válido para atualização foi fornecido")  
    if 'name' in fields_to_update:  
        new_name = (fields_to_update['name'] or '').strip()  
        if not new_name:  
            return (False, "INVALID_NAME", "Nome do insumo é obrigatório")  
    if 'stock_unit' in fields_to_update:  
        unit = (fields_to_update['stock_unit'] or '').strip()  
        if not unit:  
            return (False, "INVALID_UNIT", "Unidade do insumo é obrigatória")  
    if 'price' in fields_to_update and float(fields_to_update['price']) < 0:  
        return (False, "INVALID_COST", "Custo (price) deve ser maior ou igual a zero")  
    if 'additional_price' in fields_to_update and float(fields_to_update['additional_price']) < 0:
        return (False, "INVALID_ADDITIONAL_PRICE", "additional_price deve ser maior ou igual a zero")
    if 'current_stock' in fields_to_update and float(fields_to_update['current_stock']) < 0:  
        return (False, "INVALID_STOCK", "Estoque atual não pode ser negativo")  
    if 'min_stock_threshold' in fields_to_update and float(fields_to_update['min_stock_threshold']) < 0:  
        return (False, "INVALID_MIN_STOCK", "Estoque mínimo não pode ser negativo")  
    if 'max_stock' in fields_to_update and float(fields_to_update['max_stock']) < 0:  
        return (False, "INVALID_MAX_STOCK", "Estoque máximo não pode ser negativo")
    if 'base_portion_quantity' in fields_to_update and float(fields_to_update['base_portion_quantity']) <= 0:  
        return (False, "INVALID_BASE_PORTION_QUANTITY", "Quantidade da porção base deve ser maior que zero")
    if 'base_portion_unit' in fields_to_update:  
        unit = (fields_to_update['base_portion_unit'] or '').strip()  
        if not unit:  
            return (False, "INVALID_BASE_PORTION_UNIT", "Unidade da porção base é obrigatória")  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        # verificar existência  
        cur.execute("SELECT 1 FROM INGREDIENTS WHERE ID = ?", (ingredient_id,))  
        if not cur.fetchone():  
            return (False, "INGREDIENT_NOT_FOUND", "Ingrediente não encontrado")  
        # nome único  
        if 'name' in fields_to_update:
            cur.execute("SELECT 1 FROM INGREDIENTS WHERE UPPER(NAME) = UPPER(?) AND ID <> ?", (fields_to_update['name'], ingredient_id))  
            if cur.fetchone():  
                return (False, "INGREDIENT_NAME_EXISTS", "Já existe um insumo com este nome")
        
        # CORREÇÃO: Se current_stock está sendo atualizado, recalcular STOCK_STATUS
        if 'current_stock' in fields_to_update:
            # Buscar MIN_STOCK_THRESHOLD e STOCK_STATUS atual
            cur.execute("SELECT MIN_STOCK_THRESHOLD, STOCK_STATUS FROM INGREDIENTS WHERE ID = ?", (ingredient_id,))
            threshold_row = cur.fetchone()
            min_threshold = float(threshold_row[0]) if threshold_row and threshold_row[0] is not None else 0.0
            current_status = threshold_row[1] if threshold_row and threshold_row[1] else 'ok'
            new_stock = float(fields_to_update['current_stock'])
            
            # Recalcular STOCK_STATUS baseado no novo estoque
            from ..services.stock_service import _determine_new_status
            # ALTERAÇÃO: Usar Decimal importado no topo do módulo
            new_status = _determine_new_status(Decimal(str(new_stock)), Decimal(str(min_threshold)), current_status)
            
            # Adicionar STOCK_STATUS aos campos a atualizar
            fields_to_update['stock_status'] = new_status
        
        # ALTERAÇÃO: Construção segura de SQL - apenas campos permitidos são usados
        # allowed_fields garante que apenas campos válidos entram na query
        set_parts = [f"{key.upper()} = ?" for key in fields_to_update]  
        values = list(fields_to_update.values())  
        values.append(ingredient_id)  
        sql = f"UPDATE INGREDIENTS SET {', '.join(set_parts)} WHERE ID = ?;"  
        cur.execute(sql, tuple(values))  
        conn.commit()  
        return (True, None, "Ingrediente atualizado com sucesso")
    except fdb.Error as e:  
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao atualizar ingrediente: {e}", exc_info=True)  
        if conn: conn.rollback()  
        return (False, "DATABASE_ERROR", "Erro interno do servidor")  
    finally:  
        if conn: conn.close()  

def update_ingredient_availability(ingredient_id, is_available):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        sql = "UPDATE INGREDIENTS SET IS_AVAILABLE = ? WHERE ID = ?;"  
        cur.execute(sql, (is_available, ingredient_id))  
        conn.commit()  
        return cur.rowcount > 0  
    except fdb.Error as e:  
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao atualizar disponibilidade do ingrediente: {e}", exc_info=True)  
        if conn: conn.rollback()  
        return False  
    finally:  
        if conn: conn.close()  

def delete_ingredient(ingredient_id):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        
        # Verificar se existe
        cur.execute("SELECT 1 FROM INGREDIENTS WHERE ID = ?", (ingredient_id,))  
        if not cur.fetchone():  
            return (False, "INGREDIENT_NOT_FOUND", "Ingrediente não encontrado")  
        
        # Verificar vínculos com produtos
        cur.execute("SELECT COUNT(*) FROM PRODUCT_INGREDIENTS WHERE INGREDIENT_ID = ?", (ingredient_id,))  
        count_links = cur.fetchone()[0] or 0  
        
        if count_links > 0:  
            return (False, "INGREDIENT_IN_USE", "Exclusão bloqueada: há produtos vinculados a este insumo")  
        
        # Excluir
        cur.execute("DELETE FROM INGREDIENTS WHERE ID = ?", (ingredient_id,))  
        rows_affected = cur.rowcount
        
        conn.commit()  
        
        if rows_affected > 0:
            return (True, None, "Ingrediente excluído com sucesso")
        else:
            return (False, "NO_ROWS_AFFECTED", "Nenhuma linha foi afetada na exclusão")
            
    except fdb.Error as e:  
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao excluir ingrediente: {e}", exc_info=True)  
        if conn: conn.rollback()  
        return (False, "DATABASE_ERROR", "Erro interno do servidor")  
    except Exception as e:
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro geral ao excluir ingrediente: {e}", exc_info=True)
        if conn: conn.rollback()
        return (False, "GENERAL_ERROR", "Erro geral")
    finally:  
        if conn: conn.close()  


def add_ingredient_to_product(product_id, ingredient_id, portions):  
    # ALTERAÇÃO: Validação de IDs antes de processar
    if not isinstance(product_id, int) or product_id <= 0:
        logger.error(f"ID de produto inválido: {product_id} (tipo: {type(product_id).__name__})")
        return False
    if not isinstance(ingredient_id, int) or ingredient_id <= 0:
        logger.error(f"ID de ingrediente inválido: {ingredient_id} (tipo: {type(ingredient_id).__name__})")
        return False
    
    conn = None  
    try:
        # ALTERAÇÃO: Converter portions para Decimal com validação robusta
        try:
            portions_float = float(portions)
            if portions_float != portions_float:  # NaN check
                logger.error(f"Valor de portions é NaN: {portions}")
                return False
            if portions_float <= 0:
                logger.error(f"Valor de portions deve ser maior que zero: {portions}")
                return False
            # ALTERAÇÃO: Limitar precisão para evitar valores muito grandes
            if portions_float > 999999.99:
                logger.error(f"Valor de portions muito grande: {portions}")
                return False
            portions_decimal = Decimal(str(portions_float))
        except (ValueError, TypeError) as e:
            logger.error(f"Erro ao converter portions para Decimal: {e}, valor recebido: {portions} (tipo: {type(portions).__name__})")
            return False
        except Exception as e:
            # ALTERAÇÃO: Capturar outras exceções não esperadas
            logger.error(f"Erro inesperado ao processar portions: {e}", exc_info=True)
            return False
            
        conn = get_db_connection()  
        cur = conn.cursor()  
        
        # ALTERAÇÃO: Verificar se produto e ingrediente existem antes de vincular
        cur.execute("SELECT 1 FROM PRODUCTS WHERE ID = ?", (product_id,))
        if not cur.fetchone():
            logger.warning(f"Tentativa de vincular ingrediente a produto inexistente: product_id={product_id}")
            return False
        
        cur.execute("SELECT 1 FROM INGREDIENTS WHERE ID = ?", (ingredient_id,))
        if not cur.fetchone():
            logger.warning(f"Tentativa de vincular ingrediente inexistente: ingredient_id={ingredient_id}")
            return False
        
        # Verificar se a vinculação já existe
        cur.execute("SELECT 1 FROM PRODUCT_INGREDIENTS WHERE PRODUCT_ID = ? AND INGREDIENT_ID = ?", (product_id, ingredient_id))
        existing = cur.fetchone()
        
        if existing:
            # Atualizar vinculação existente
            sql = "UPDATE PRODUCT_INGREDIENTS SET PORTIONS = ? WHERE PRODUCT_ID = ? AND INGREDIENT_ID = ?"
            cur.execute(sql, (portions_decimal, product_id, ingredient_id))
        else:
            # Inserir nova vinculação
            sql = "INSERT INTO PRODUCT_INGREDIENTS (PRODUCT_ID, INGREDIENT_ID, PORTIONS) VALUES (?, ?, ?)"
            cur.execute(sql, (product_id, ingredient_id, portions_decimal))
        
        conn.commit()  
        return True  
    except fdb.Error as e:  
        # ALTERAÇÃO: Logging estruturado sem expor dados sensíveis
        logger.error(f"Erro ao associar ingrediente ao produto: product_id={product_id}, ingredient_id={ingredient_id}, error={type(e).__name__}", exc_info=True)  
        if conn: 
            conn.rollback()  
        return False  
    except Exception as e:
        # ALTERAÇÃO: Capturar exceções genéricas não tratadas
        logger.error(f"Erro inesperado ao associar ingrediente: {e}", exc_info=True)
        if conn: 
            conn.rollback()
        return False
    finally:  
        if conn: 
            conn.close()  


def update_product_ingredient(product_id, ingredient_id, portions=None):
    # ALTERAÇÃO: Validação de IDs antes de processar portions
    if not isinstance(product_id, int) or product_id <= 0:
        return (False, "INVALID_PRODUCT_ID", "ID do produto inválido")
    if not isinstance(ingredient_id, int) or ingredient_id <= 0:
        return (False, "INVALID_INGREDIENT_ID", "ID do ingrediente inválido")
    
    if portions is None:
        return (False, "NO_VALID_FIELDS", "Forneça 'portions' para atualizar")
    
    # ALTERAÇÃO: Validar que portions é um número válido e converter para Decimal
    try:
        # Converter para float primeiro para validar
        portions_float = float(portions)
        if portions_float != portions_float:  # NaN check
            return (False, "NO_VALID_FIELDS", "Campo 'portions' deve ser um número válido")
        if portions_float <= 0:
            return (False, "NO_VALID_FIELDS", "Número de porções deve ser maior que zero")
        # ALTERAÇÃO: Limitar precisão para evitar valores muito grandes
        if portions_float > 999999.99:
            return (False, "NO_VALID_FIELDS", "Número de porções muito grande (máximo: 999999.99)")
        # Converter para Decimal para garantir compatibilidade com Firebird DECIMAL
        portions_decimal = Decimal(str(portions_float))
    except (ValueError, TypeError) as e:
        logger.error(f"Erro ao converter portions para Decimal: {e}")
        return (False, "NO_VALID_FIELDS", "Campo 'portions' deve ser um número válido")
    except Exception as e:
        # ALTERAÇÃO: Capturar outras exceções não esperadas
        logger.error(f"Erro inesperado ao processar portions: {e}", exc_info=True)
        return (False, "NO_VALID_FIELDS", "Erro ao processar valor de porções")
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # ALTERAÇÃO: Verificar existência do vínculo antes de atualizar
        cur.execute("SELECT 1 FROM PRODUCT_INGREDIENTS WHERE PRODUCT_ID = ? AND INGREDIENT_ID = ?", (product_id, ingredient_id))
        if not cur.fetchone():
            return (False, "LINK_NOT_FOUND", "Vínculo produto-insumo não encontrado")
        
        sql = "UPDATE PRODUCT_INGREDIENTS SET PORTIONS = ? WHERE PRODUCT_ID = ? AND INGREDIENT_ID = ?;"
        cur.execute(sql, (portions_decimal, product_id, ingredient_id))
        conn.commit()
        
        # ALTERAÇÃO: Verificar se a atualização foi bem-sucedida
        if cur.rowcount == 0:
            logger.warning(f"Atualização de vínculo não afetou nenhuma linha: product_id={product_id}, ingredient_id={ingredient_id}")
            return (False, "UPDATE_FAILED", "Falha ao atualizar vínculo")
        
        return (True, None, "Vínculo atualizado com sucesso")
    except fdb.Error as e:
        # ALTERAÇÃO: Logging estruturado sem expor dados sensíveis
        logger.error(f"Erro ao atualizar vínculo produto-insumo: product_id={product_id}, ingredient_id={ingredient_id}, error={type(e).__name__}", exc_info=True)
        if conn: 
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    except Exception as e:
        # ALTERAÇÃO: Capturar exceções genéricas não tratadas
        logger.error(f"Erro inesperado ao atualizar vínculo: {e}", exc_info=True)
        if conn: 
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: 
            conn.close()

def remove_ingredient_from_product(product_id, ingredient_id):  
    # ALTERAÇÃO: Validação de IDs antes de processar
    if not isinstance(product_id, int) or product_id <= 0:
        logger.warning(f"Tentativa de remover com ID de produto inválido: {product_id} (tipo: {type(product_id).__name__})")
        return False
    if not isinstance(ingredient_id, int) or ingredient_id <= 0:
        logger.warning(f"Tentativa de remover com ID de ingrediente inválido: {ingredient_id} (tipo: {type(ingredient_id).__name__})")
        return False
    
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        # ALTERAÇÃO: Verificar se o vínculo existe antes de tentar remover
        cur.execute("SELECT 1 FROM PRODUCT_INGREDIENTS WHERE PRODUCT_ID = ? AND INGREDIENT_ID = ?", (product_id, ingredient_id))
        if not cur.fetchone():
            logger.warning(f"Tentativa de remover vínculo inexistente: produto_id={product_id}, ingredient_id={ingredient_id}")
            return False
        sql = "DELETE FROM PRODUCT_INGREDIENTS WHERE PRODUCT_ID = ? AND INGREDIENT_ID = ?;"  
        cur.execute(sql, (product_id, ingredient_id))  
        conn.commit()  
        
        # ALTERAÇÃO: Verificar se a remoção foi bem-sucedida
        deleted = cur.rowcount > 0
        if not deleted:
            logger.warning(f"Nenhuma linha afetada ao remover vínculo: produto_id={product_id}, ingredient_id={ingredient_id}")
        return deleted
    except fdb.Error as e:  
        # ALTERAÇÃO: Logging estruturado sem expor dados sensíveis
        logger.error(f"Erro ao remover associação de ingrediente: product_id={product_id}, ingredient_id={ingredient_id}, error={type(e).__name__}", exc_info=True)  
        if conn: 
            conn.rollback()  
        return False  
    except Exception as e:
        # ALTERAÇÃO: Capturar exceções genéricas não tratadas
        logger.error(f"Erro inesperado ao remover associação: {e}", exc_info=True)
        if conn: 
            conn.rollback()
        return False
    finally:  
        if conn: 
            conn.close()  

def get_ingredients_for_product(product_id, quantity=1):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        # AJUSTE: Incluir CURRENT_STOCK e ADDITIONAL_PRICE na query para validação de estoque e preço adicional
        sql = """
            SELECT i.ID, i.NAME, pi.PORTIONS, i.BASE_PORTION_QUANTITY, i.BASE_PORTION_UNIT, 
                   i.PRICE, i.ADDITIONAL_PRICE, i.IS_AVAILABLE, i.STOCK_UNIT, i.CURRENT_STOCK,
                   pi.MIN_QUANTITY, pi.MAX_QUANTITY
            FROM PRODUCT_INGREDIENTS pi
            JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
            WHERE pi.PRODUCT_ID = ?;
        """  
        cur.execute(sql, (product_id,))  
        items = []
        estimated_cost = 0.0
        # AJUSTE: Importar função para calcular quantidade máxima disponível
        from .product_service import get_ingredient_max_available_quantity
        
        for row in cur.fetchall():
            ingredient_id = row[0]
            name = row[1]
            portions = float(row[2]) if row[2] is not None else 0.0
            base_portion_quantity = float(row[3]) if row[3] is not None else 1.0
            base_portion_unit = row[4] if row[4] else "un"
            price = float(row[5]) if row[5] is not None else 0.0
            additional_price = float(row[6]) if row[6] is not None else 0.0
            is_available = row[7]
            stock_unit = row[8] if row[8] else "un"
            current_stock = float(row[9]) if row[9] is not None else 0.0
            min_quantity = int(row[10]) if row[10] is not None else 0
            max_quantity = int(row[11]) if row[11] is not None else 0
            
            # Calcular quantidade real consumida baseada na porção
            actual_quantity = portions * base_portion_quantity
            # Calcular custo por porção (preço por unidade base * quantidade da porção base)
            portion_cost = price * base_portion_quantity
            # Calcular custo total da linha (custo por porção * número de porções)
            line_cost = portion_cost * portions
            
            # AJUSTE: Calcular quantidade máxima disponível baseada no estoque
            # IMPORTANTE: REGRA DE CONSUMO PROPORCIONAL POR QUANTIDADE
            # Passa quantity (quantidade do produto) para calcular max_available considerando consumo acumulado
            # O backend calcula: consumo_total = consumo_por_unidade × quantity
            # Isso garante que o max_quantity dos ingredientes seja calculado considerando todas as unidades
            max_available_info = get_ingredient_max_available_quantity(
                ingredient_id=ingredient_id,
                max_quantity_from_rule=max_quantity if max_quantity > 0 else None,
                item_quantity=quantity,  # CORREÇÃO: Usar quantity passado (não sempre 1)
                base_portions=portions,  # AJUSTE: Passar porções base do produto
                cur=cur  # Reutiliza conexão existente
            )
            
            # IMPORTANTE: max_available já é o menor entre regra e estoque (calculado pela função)
            # Para ingredientes base (portions > 0), max_available é o total de porções possíveis
            # Para extras (portions = 0), max_available é apenas extras disponíveis (sem incluir min_quantity)
            max_available_value = max_available_info.get('max_available', 0) if max_available_info else 0
            
            # Calcula max_quantity final: menor entre regra e estoque
            if portions == 0.0:  # É ingrediente extra
                # max_available é apenas extras, então precisa somar com min_quantity
                max_from_stock_total = min_quantity + max_available_value if max_available_value > 0 else min_quantity
                # Retorna o menor entre estoque e regra
                if max_quantity > 0:
                    effective_max_quantity = min(max_from_stock_total, max_quantity)
                else:
                    effective_max_quantity = max_from_stock_total
            else:  # É ingrediente base
                # max_available já é o total de porções possíveis (menor entre regra e estoque)
                # Se há regra, compara com ela; senão usa o valor do estoque
                if max_quantity > 0:
                    effective_max_quantity = min(max_available_value, max_quantity)
                else:
                    effective_max_quantity = max_available_value if max_available_value > 0 else None
            
            items.append({
                "ingredient_id": ingredient_id,
                "name": name,
                "portions": portions,
                "base_portion_quantity": base_portion_quantity,
                "base_portion_unit": base_portion_unit,
                "actual_quantity": round(actual_quantity, 3),
                "actual_unit": base_portion_unit,
                "stock_unit": stock_unit,
                "price": price,
                "additional_price": additional_price,  # Preço adicional do ingrediente (para extras)
                "portion_cost": round(portion_cost, 2),
                "is_available": is_available,
                "line_cost": round(line_cost, 2),
                "min_quantity": min_quantity,
                "max_quantity": effective_max_quantity,  # Menor entre regra e estoque (já calculado)
                # AJUSTE: Adicionar informações de estoque para validação
                "current_stock": round(current_stock, 3),
                "max_available": max_available_value,  # Mantém para referência
                "limited_by": max_available_info.get('limited_by', 'rule') if max_available_info else 'rule',
                "stock_info": max_available_info.get('stock_info') if max_available_info else None
            })
            estimated_cost += line_cost
        return {"items": items, "estimated_cost": round(estimated_cost, 2)}  
    except fdb.Error as e:  
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao buscar ingredientes do produto: {e}", exc_info=True)  
        return {"items": [], "estimated_cost": 0.0}  
    finally:  
        if conn: conn.close()  


def adjust_ingredient_stock(ingredient_id, change_amount):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        # CORREÇÃO: Buscar também MIN_STOCK_THRESHOLD e STOCK_STATUS para recalcular status
        cur.execute("SELECT CURRENT_STOCK, MIN_STOCK_THRESHOLD, STOCK_STATUS FROM INGREDIENTS WHERE ID = ?", (ingredient_id,))  
        row = cur.fetchone()  
        if not row:  
            return (False, "INGREDIENT_NOT_FOUND", "Ingrediente não encontrado")  
        current_stock = float(row[0]) if row[0] is not None else 0.0
        min_threshold = float(row[1]) if row[1] is not None else 0.0
        current_status = row[2] if row[2] else 'ok'
        new_stock = current_stock + change_amount  
        if new_stock < 0:  
            return (False, "NEGATIVE_STOCK", "Não é possível ter estoque negativo")
        
        # CORREÇÃO: Recalcular STOCK_STATUS baseado no novo estoque
        from ..services.stock_service import _determine_new_status
        from decimal import Decimal
        new_status = _determine_new_status(Decimal(str(new_stock)), Decimal(str(min_threshold)), current_status)
        
        cur.execute("UPDATE INGREDIENTS SET CURRENT_STOCK = ?, STOCK_STATUS = ? WHERE ID = ?", (new_stock, new_status, ingredient_id))  
        conn.commit()  
        return (True, None, f"Estoque ajustado de {current_stock} para {new_stock} (status: {new_status})")  
    except fdb.Error as e:  
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao ajustar estoque: {e}", exc_info=True)  
        if conn: conn.rollback()  
        return (False, "DATABASE_ERROR", "Erro interno do servidor")  
    finally:  
        if conn: conn.close()


def add_ingredient_quantity(ingredient_id, quantity_to_add):  
    """Adiciona uma quantidade ao estoque atual do ingrediente"""  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        
        # CORREÇÃO: Buscar também MIN_STOCK_THRESHOLD e STOCK_STATUS para recalcular status
        cur.execute("SELECT CURRENT_STOCK, MIN_STOCK_THRESHOLD, STOCK_STATUS FROM INGREDIENTS WHERE ID = ?", (ingredient_id,))  
        row = cur.fetchone()  
        if not row:  
            return (False, "INGREDIENT_NOT_FOUND", "Ingrediente não encontrado")  
        
        current_stock = float(row[0]) if row[0] is not None else 0.0
        min_threshold = float(row[1]) if row[1] is not None else 0.0
        current_status = row[2] if row[2] else 'ok'
        
        if quantity_to_add < 0:  
            return (False, "INVALID_QUANTITY", "Quantidade a adicionar não pode ser negativa")  
        
        new_stock = current_stock + quantity_to_add
        
        # CORREÇÃO: Recalcular STOCK_STATUS baseado no novo estoque
        from ..services.stock_service import _determine_new_status
        from decimal import Decimal
        new_status = _determine_new_status(Decimal(str(new_stock)), Decimal(str(min_threshold)), current_status)
        
        cur.execute("UPDATE INGREDIENTS SET CURRENT_STOCK = ?, STOCK_STATUS = ? WHERE ID = ?", (new_stock, new_status, ingredient_id))  
        conn.commit()  
        return (True, None, f"Estoque atualizado de {current_stock} para {new_stock} (+{quantity_to_add}, status: {new_status})")  
    except fdb.Error as e:  
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao adicionar quantidade ao estoque: {e}", exc_info=True)  
        if conn: conn.rollback()  
        return (False, "DATABASE_ERROR", "Erro interno do servidor")  
    finally:  
        if conn: conn.close()


def check_ingredient_name_exists(name):
    """
    Verifica se um nome de ingrediente já existe (case-insensitive)
    Retorna: (exists: bool, existing_ingredient: dict or None)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca ingrediente com nome similar (case-insensitive, ignorando espaços)
        cur.execute("SELECT ID, NAME FROM INGREDIENTS WHERE UPPER(TRIM(NAME)) = UPPER(TRIM(?))", (name,))
        existing = cur.fetchone()
        
        if existing:
            return (True, {
                "id": existing[0],
                "name": existing[1]
            })
        
        return (False, None)
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao verificar nome do ingrediente: {e}", exc_info=True)
        return (False, None)
    finally:
        if conn: conn.close()  


def get_stock_summary():  
    """
    Retorna resumo de estoque via consultas SQL.
    ALTERAÇÃO: Adicionados CASTs explícitos para evitar erro SQLDA (-804)
    """
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        
        # ALTERAÇÃO: Query consolidada com CASTs explícitos para evitar erro SQLDA
        # Calcular todos os valores em uma única query para melhor performance
        cur.execute("""
            SELECT
                -- Valor total do estoque (apenas itens com estoque > 0 e preço válido)
                CAST(COALESCE(SUM(
                    CASE 
                        WHEN CURRENT_STOCK > 0 AND PRICE IS NOT NULL AND PRICE > 0 
                        THEN CURRENT_STOCK * PRICE 
                        ELSE 0 
                    END
                ), 0) AS NUMERIC(18,2)) as total_value,
                
                -- Itens sem estoque
                CAST(COALESCE(SUM(
                    CASE WHEN CURRENT_STOCK = 0 OR CURRENT_STOCK IS NULL THEN 1 ELSE 0 END
                ), 0) AS INTEGER) as out_of_stock,
                
                -- Estoque baixo (entre 0 e threshold)
                CAST(COALESCE(SUM(
                    CASE 
                        WHEN CURRENT_STOCK > 0 
                             AND CURRENT_STOCK <= COALESCE(MIN_STOCK_THRESHOLD, 0)
                        THEN 1 
                        ELSE 0 
                    END
                ), 0) AS INTEGER) as low_stock,
                
                -- Em estoque adequado (acima do threshold)
                CAST(COALESCE(SUM(
                    CASE 
                        WHEN CURRENT_STOCK > COALESCE(MIN_STOCK_THRESHOLD, 0)
                        THEN 1 
                        ELSE 0 
                    END
                ), 0) AS INTEGER) as in_stock
            FROM INGREDIENTS
        """)  
        
        row = cur.fetchone()  
        
        return {  
            "total_stock_value": float(row[0]) if row and row[0] is not None else 0.0,
            "out_of_stock_count": int(row[1]) if row and row[1] is not None else 0,
            "low_stock_count": int(row[2]) if row and row[2] is not None else 0,
            "in_stock_count": int(row[3]) if row and row[3] is not None else 0
        }
    except fdb.Error as e:  
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao buscar resumo de estoque: {e}", exc_info=True)  
        return {  
            "total_stock_value": 0.0,
            "out_of_stock_count": 0,
            "low_stock_count": 0,
            "in_stock_count": 0
        }
    finally:  
        if conn: 
            conn.close()  


def generate_purchase_order():  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        cur.execute("""
            SELECT ID, NAME, CURRENT_STOCK, MIN_STOCK_THRESHOLD, STOCK_UNIT, PRICE
            FROM INGREDIENTS 
            WHERE CURRENT_STOCK <= MIN_STOCK_THRESHOLD
            ORDER BY CURRENT_STOCK ASC, NAME
        """)  
        items_to_buy = []  
        for row in cur.fetchall():  
            suggested_quantity = float(row[3]) * 2  
            current_stock = float(row[2]) if row[2] is not None else 0.0  
            items_to_buy.append({  
                "ingredient_id": row[0],
                "name": row[1],
                "current_stock": current_stock,
                "min_threshold": float(row[3]),
                "stock_unit": row[4],
                "unit_price": float(row[5]) if row[5] is not None else 0.0,
                "suggested_quantity": suggested_quantity,
                "estimated_cost": suggested_quantity * (float(row[5]) if row[5] is not None else 0.0)
            })
        total_estimated_cost = sum(item["estimated_cost"] for item in items_to_buy)  
        return {  
            "items": items_to_buy,
            "total_items": len(items_to_buy),
            "total_estimated_cost": total_estimated_cost
        }
    except fdb.Error as e:  
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao gerar pedido de compra: {e}", exc_info=True)  
        return {"items": [], "total_items": 0, "total_estimated_cost": 0.0}  
    finally:  
        if conn: conn.close()


def consume_ingredients_for_product(product_id, quantity=1):
    """
    Consome ingredientes do estoque baseado na ficha técnica do produto
    quantity: quantidade de unidades do produto a ser produzida
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Buscar ingredientes do produto com suas porções
        sql = """
            SELECT i.ID, i.NAME, pi.PORTIONS, i.BASE_PORTION_QUANTITY, i.BASE_PORTION_UNIT, 
                   i.CURRENT_STOCK, i.STOCK_UNIT
            FROM PRODUCT_INGREDIENTS pi
            JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
            WHERE pi.PRODUCT_ID = ? AND i.IS_AVAILABLE = TRUE;
        """
        cur.execute(sql, (product_id,))
        ingredients = cur.fetchall()
        
        if not ingredients:
            return (False, "NO_INGREDIENTS", "Produto não possui ingredientes cadastrados")
        
        # Verificar se há estoque suficiente para todos os ingredientes
        consumption_plan = []
        for row in ingredients:
            ingredient_id = row[0]
            name = row[1]
            portions = float(row[2])
            base_portion_quantity = float(row[3])
            base_portion_unit = row[4]
            current_stock = float(row[5]) if row[5] is not None else 0.0
            stock_unit = row[6]
            
            # Calcular consumo total (porções * quantidade da porção base * quantidade do produto)
            total_consumption = portions * base_portion_quantity * quantity
            
            if current_stock < total_consumption:
                return (False, "INSUFFICIENT_STOCK", 
                       f"Estoque insuficiente para {name}. Necessário: {total_consumption:.3f} {base_portion_unit}, "
                       f"disponível: {current_stock:.3f} {stock_unit}")
            
            consumption_plan.append({
                "ingredient_id": ingredient_id,
                "name": name,
                "consumption": total_consumption,
                "new_stock": current_stock - total_consumption
            })
        
        # CORREÇÃO: Executar baixa de estoque para todos os ingredientes e atualizar STOCK_STATUS
        from ..services.stock_service import _determine_new_status
        # ALTERAÇÃO: Usar Decimal importado no topo do módulo
        
        for item in consumption_plan:
            # Buscar MIN_STOCK_THRESHOLD e STOCK_STATUS atual
            cur.execute("""
                SELECT MIN_STOCK_THRESHOLD, STOCK_STATUS 
                FROM INGREDIENTS 
                WHERE ID = ?
            """, (item["ingredient_id"],))
            threshold_row = cur.fetchone()
            min_threshold = float(threshold_row[0]) if threshold_row and threshold_row[0] is not None else 0.0
            current_status = threshold_row[1] if threshold_row and threshold_row[1] else 'ok'
            
            # Recalcular STOCK_STATUS baseado no novo estoque
            new_status = _determine_new_status(
                Decimal(str(item["new_stock"])), 
                Decimal(str(min_threshold)), 
                current_status
            )
            
            cur.execute(
                "UPDATE INGREDIENTS SET CURRENT_STOCK = ?, STOCK_STATUS = ? WHERE ID = ?",
                (item["new_stock"], new_status, item["ingredient_id"])
            )
        
        conn.commit()
        return (True, None, f"Estoque consumido com sucesso para {quantity} unidade(s) do produto")
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao consumir ingredientes: {e}", exc_info=True)
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def calculate_product_cost_by_portions(product_id):
    """
    Calcula o custo do produto baseado nas porções dos ingredientes
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT i.ID, i.NAME, pi.PORTIONS, i.BASE_PORTION_QUANTITY, i.PRICE
            FROM PRODUCT_INGREDIENTS pi
            JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
            WHERE pi.PRODUCT_ID = ? AND i.IS_AVAILABLE = TRUE;
        """
        cur.execute(sql, (product_id,))
        ingredients = cur.fetchall()
        
        total_cost = 0.0
        cost_breakdown = []
        
        for row in ingredients:
            ingredient_id = row[0]
            name = row[1]
            portions = float(row[2])
            base_portion_quantity = float(row[3])
            price = float(row[4]) if row[4] is not None else 0.0
            
            # Custo por porção = preço por unidade base * quantidade da porção base
            portion_cost = price * base_portion_quantity
            # Custo total do ingrediente = custo por porção * número de porções
            ingredient_cost = portion_cost * portions
            
            cost_breakdown.append({
                "ingredient_id": ingredient_id,
                "name": name,
                "portions": portions,
                "base_portion_quantity": base_portion_quantity,
                "portion_cost": round(portion_cost, 2),
                "ingredient_cost": round(ingredient_cost, 2)
            })
            
            total_cost += ingredient_cost
        
        return {
            "total_cost": round(total_cost, 2),
            "cost_breakdown": cost_breakdown
        }
        
    except fdb.Error as e:
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao calcular custo do produto: {e}", exc_info=True)
        return {"total_cost": 0.0, "cost_breakdown": []}
    finally:
        if conn: conn.close()  
