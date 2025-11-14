from flask import Blueprint, request, jsonify, send_from_directory, send_file, Response
import os
import logging
# ALTERAÇÃO: Mover import de database para topo quando usado frequentemente
from ..database import get_db_connection
from ..services import product_service  
from ..services.auth_service import require_role
from ..utils.image_handler import save_product_image, delete_product_image, update_product_image

product_bp = Blueprint('products', __name__)
logger = logging.getLogger(__name__)

@product_bp.route('/', methods=['GET'])  
def list_products_route():
    name = request.args.get('name')  
    category_id = request.args.get('category_id', type=int)  
    page = request.args.get('page', type=int, default=1)  
    page_size = request.args.get('page_size', type=int, default=10)  
    # Corrigir interpretação de parâmetro booleano
    # Flask interpreta qualquer string não vazia como True quando usa type=bool
    # Então precisamos verificar explicitamente
    include_inactive_param = request.args.get('include_inactive', '').lower()
    include_inactive = include_inactive_param in ('true', '1', 'yes') if include_inactive_param else False
    
    # NOVO: Aceita parâmetro filter_unavailable para filtrar produtos sem estoque
    # Frontend pode usar filter_unavailable=true para esconder produtos indisponíveis
    # Painel admin usa filter_unavailable=false (padrão) para ver todos os produtos
    filter_unavailable_param = request.args.get('filter_unavailable', '').lower()
    filter_unavailable = filter_unavailable_param in ('true', '1', 'yes') if filter_unavailable_param else False
    
    # ALTERAÇÃO: Reduzir logging excessivo - evitar logar detalhes de produtos em produção
    # Log apenas informações essenciais para debug quando necessário
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"list_products: page={page}, page_size={page_size}, "
                    f"include_inactive={include_inactive}, filter_unavailable={filter_unavailable}")
    
    result = product_service.list_products(
        name_filter=name, 
        category_id=category_id, 
        page=page, 
        page_size=page_size, 
        include_inactive=include_inactive,
        filter_unavailable=filter_unavailable  # Aceita parâmetro da query string
    )
    
    # ALTERAÇÃO: Log apenas contagem, não detalhes de produtos (evita exposição de dados)
    items_count = len(result.get('items', [])) if result else 0
    if items_count == 0 and logger.isEnabledFor(logging.DEBUG):
        logger.debug("list_products: Nenhum produto retornado")
        # TODO: REVISAR - Diagnóstico detalhado apenas em modo debug ou ambiente de desenvolvimento
        # Em produção, reduzir verbosidade do logging para evitar overhead e exposição de dados
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            # Verificar total de produtos ativos
            cur.execute("SELECT COUNT(*) FROM PRODUCTS WHERE IS_ACTIVE = TRUE")
            total_products = cur.fetchone()[0]
            logger.debug(f"Total de produtos ativos no banco: {total_products}")
            
            # Verificar produtos com ingredientes
            cur.execute("""
                SELECT p.ID, p.NAME, COUNT(pi.PRODUCT_ID) as total_ingredientes
                FROM PRODUCTS p
                LEFT JOIN PRODUCT_INGREDIENTS pi ON p.ID = pi.PRODUCT_ID AND pi.PORTIONS > 0
                WHERE p.IS_ACTIVE = TRUE
                GROUP BY p.ID, p.NAME
                ORDER BY p.ID
            """)
            products_with_ingredients = cur.fetchall()
            logger.debug(f"Produtos com ingredientes: {len(products_with_ingredients)}")
            
            # ALTERAÇÃO: Não logar detalhes de ingredientes em produção (reduzir exposição de dados)
            # Verificar ingredientes com estoque (apenas contagem)
            cur.execute("""
                SELECT COUNT(*) FROM INGREDIENTS WHERE IS_AVAILABLE = TRUE
            """)
            ingredients_count = cur.fetchone()[0]
            logger.debug(f"Ingredientes disponíveis: {ingredients_count}")
            
            conn.close()
        except Exception as e:
            # ALTERAÇÃO: Logging seguro sem expor detalhes internos
            logger.error(f"[PRODUCT_ROUTES] Erro ao verificar total de produtos no banco: {e}", exc_info=True)
            # Nota: Não expor detalhes do erro ao usuário final, apenas logar internamente
    
    return jsonify(result), 200

@product_bp.route('/<int:product_id>', methods=['GET'])  
def get_product_by_id_route(product_id):  
    # Aceita parâmetro quantity opcional para calcular max_available corretamente
    quantity = request.args.get('quantity', type=int, default=1)
    product = product_service.get_product_by_id(product_id, quantity=quantity)  
    if product:  
        return jsonify(product), 200  
    return jsonify({"msg": "Produto não encontrado"}), 404

@product_bp.route('/<int:product_id>/availability', methods=['GET'])
def check_product_availability_route(product_id):
    """
    Verifica a disponibilidade completa de um produto, incluindo estoque de todos os ingredientes.
    """
    quantity = request.args.get('quantity', type=int, default=1)
    availability = product_service.check_product_availability(product_id, quantity)
    
    if availability['status'] == 'unknown' and 'Produto não encontrado' in availability.get('message', ''):
        return jsonify({"error": "Produto não encontrado"}), 404
    
    return jsonify(availability), 200

@product_bp.route('/<int:product_id>/capacity', methods=['GET'])
def get_product_capacity_route(product_id):
    """
    Calcula a capacidade de produção de um produto.
    
    Query parameters:
        - extras: JSON opcional com lista de extras [{ingredient_id: int, quantity: int}]
    
    Returns:
        {
            'capacity': int,  # Capacidade máxima (número de unidades)
            'limiting_ingredient': dict,  # Insumo que limita a capacidade
            'ingredients': list,  # Lista de todos os insumos com suas capacidades
            'is_available': bool,
            'message': str
        }
    """
    from ..services import stock_service
    import json
    
    extras_param = request.args.get('extras', None)
    extras = None
    
    if extras_param:
        try:
            extras = json.loads(extras_param)
        except (json.JSONDecodeError, ValueError):
            return jsonify({"error": "Formato de extras inválido. Use JSON válido."}), 400
    
    if extras:
        capacity = stock_service.calculate_product_capacity_with_extras(product_id, extras)
    else:
        capacity = stock_service.calculate_product_capacity(product_id)
    
    return jsonify(capacity), 200


@product_bp.route('/simular_capacidade', methods=['POST'])
def simulate_product_capacity_route():
    """
    Simula a capacidade máxima de produção de um produto considerando receita e extras.
    
    Body (JSON):
        {
            "product_id": int,  # ID do produto (obrigatório)
            "extras": [  # Lista de extras (opcional)
                {"ingredient_id": int, "quantity": int}
            ],
            "base_modifications": [  # Modificações da receita base (opcional)
                {"ingredient_id": int, "delta": int}  # delta pode ser positivo ou negativo
            ],
            "quantity": int  # Quantidade desejada (opcional, padrão: 1)
        }
    
    Returns:
        {
            "product_id": int,
            "max_quantity": int,  # Capacidade máxima (número de unidades)
            "availability_status": str,  # "available", "limited", "unavailable", "low_stock"
            "limiting_ingredient": {  # Insumo que limita a capacidade
                "name": str,
                "available": float,
                "unit": str,
                "message": str
            },
            "capacity": int,  # Alias para max_quantity
            "is_available": bool,
            "message": str
        }
    
    Status codes:
        - 200: Sucesso
        - 400: Erro de validação (product_id ausente ou inválido)
        - 404: Produto não encontrado
        - 500: Erro interno do servidor
    """
    from ..services import stock_service
    import json
    
    # ALTERAÇÃO: logger já está definido no topo do arquivo - removido import duplicado
    # ALTERAÇÃO: Inicializar product_id para evitar erro no except se houver exceção antes da atribuição
    product_id = None
    
    try:
        # Valida se há dados JSON
        if not request.is_json:
            return jsonify({"error": "Content-Type deve ser application/json"}), 400
        
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
        
        # Valida product_id
        product_id = data.get("product_id")
        if not product_id:
            return jsonify({"error": "product_id é obrigatório"}), 400
        
        try:
            product_id = int(product_id)
            if product_id <= 0:
                return jsonify({"error": "product_id deve ser um número positivo"}), 400
            # ALTERAÇÃO: Limite máximo para evitar valores absurdos
            if product_id > 2147483647:  # Limite máximo de INT32
                return jsonify({"error": "product_id excede o limite máximo permitido"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "product_id deve ser um número válido"}), 400
        
        # ALTERAÇÃO: Valida quantity (opcional, mas se fornecido deve ser válido)
        quantity = data.get("quantity", 1)
        if quantity is not None:
            try:
                quantity = int(quantity)
                if quantity <= 0:
                    return jsonify({"error": "quantity deve ser um número positivo"}), 400
                # ALTERAÇÃO: Limite máximo para evitar valores absurdos
                if quantity > 999:
                    return jsonify({"error": "quantity excede o limite máximo permitido (999)"}), 400
            except (ValueError, TypeError):
                return jsonify({"error": "quantity deve ser um número válido"}), 400
        
        # Valida se o produto existe
        product = product_service.get_product_by_id(product_id)
        if not product:
            return jsonify({"error": "Produto não encontrado"}), 404
        
        # Obtém extras (opcional)
        extras = data.get("extras", [])
        if extras:
            # Valida formato dos extras
            if not isinstance(extras, list):
                return jsonify({"error": "extras deve ser uma lista"}), 400
            
            # Valida cada extra
            for extra in extras:
                if not isinstance(extra, dict):
                    return jsonify({"error": "Cada extra deve ser um objeto"}), 400
                
                ing_id = extra.get("ingredient_id")
                qty = extra.get("quantity", 1)
                
                if not ing_id:
                    return jsonify({"error": "ingredient_id é obrigatório em cada extra"}), 400
                
                try:
                    ing_id = int(ing_id)
                    qty = int(qty) if qty else 1
                    
                    if ing_id <= 0:
                        return jsonify({"error": "ingredient_id deve ser um número positivo"}), 400
                    # ALTERAÇÃO: Limite máximo para evitar valores absurdos
                    if ing_id > 2147483647:
                        return jsonify({"error": "ingredient_id excede o limite máximo permitido"}), 400
                    if qty <= 0:
                        return jsonify({"error": "quantity deve ser um número positivo"}), 400
                    # ALTERAÇÃO: Limite máximo para evitar valores absurdos
                    if qty > 999:
                        return jsonify({"error": "quantity do extra excede o limite máximo permitido (999)"}), 400
                except (ValueError, TypeError):
                    return jsonify({"error": "ingredient_id e quantity devem ser números válidos"}), 400
        
        # NOVO: Obtém base_modifications (opcional)
        base_modifications = data.get("base_modifications", [])
        if base_modifications:
            # Valida formato dos base_modifications
            if not isinstance(base_modifications, list):
                return jsonify({"error": "base_modifications deve ser uma lista"}), 400
            
            # Valida cada base_modification
            for bm in base_modifications:
                if not isinstance(bm, dict):
                    return jsonify({"error": "Cada base_modification deve ser um objeto"}), 400
                
                ing_id = bm.get("ingredient_id")
                delta = bm.get("delta", 0)
                
                if not ing_id:
                    return jsonify({"error": "ingredient_id é obrigatório em cada base_modification"}), 400
                
                try:
                    ing_id = int(ing_id)
                    # ALTERAÇÃO: Converter delta preservando sinal negativo (delta pode ser positivo ou negativo)
                    # delta negativo = remove da receita base, delta positivo = adiciona à receita base
                    try:
                        delta = int(delta)
                    except (ValueError, TypeError):
                        delta = 0
                    
                    if ing_id <= 0:
                        return jsonify({"error": "ingredient_id deve ser um número positivo"}), 400
                    # ALTERAÇÃO: Limite máximo para evitar valores absurdos
                    if ing_id > 2147483647:
                        return jsonify({"error": "ingredient_id excede o limite máximo permitido"}), 400
                    # ALTERAÇÃO: Delta deve ser diferente de zero (pode ser positivo ou negativo)
                    if delta == 0:
                        return jsonify({"error": "delta deve ser diferente de zero"}), 400
                    # ALTERAÇÃO: Limite máximo para evitar valores absurdos (positivo ou negativo)
                    # Usa abs() para permitir deltas negativos (ex: -1 remove 1 porção)
                    if abs(delta) > 999:
                        return jsonify({"error": "delta excede o limite máximo permitido (999)"}), 400
                except (ValueError, TypeError):
                    return jsonify({"error": "ingredient_id e delta devem ser números válidos"}), 400
        
        # Calcula capacidade usando a função existente
        if extras or base_modifications:
            capacity_result = stock_service.calculate_product_capacity_with_extras(
                product_id, 
                extras=extras,
                base_modifications=base_modifications
            )
        else:
            capacity_result = stock_service.calculate_product_capacity(product_id)
        
        # Verifica se houve erro no cálculo
        if not capacity_result or capacity_result.get('capacity') is None:
            return jsonify({
                "error": "Erro ao calcular capacidade",
                "message": capacity_result.get('message', 'Erro desconhecido') if capacity_result else 'Erro ao calcular capacidade'
            }), 500
        
        # Formata resposta no formato esperado pelo frontend
        capacity = capacity_result.get('capacity', 0)
        is_available = capacity_result.get('is_available', False)
        limiting_ingredient = capacity_result.get('limiting_ingredient')
        
        # Determina availability_status baseado na capacidade
        if not is_available or capacity < 1:
            availability_status = "unavailable"
        elif capacity == 1:
            availability_status = "limited"
        else:
            # Capacidade > 1: verifica se está baixo
            if limiting_ingredient:
                available_stock = limiting_ingredient.get('available_stock', 0)
                consumption_per_unit = limiting_ingredient.get('consumption_per_unit', 0)
                
                # Se o estoque disponível é menos que 2x o consumo por unidade, está baixo
                if available_stock < (consumption_per_unit * 2):
                    availability_status = "low_stock"
                else:
                    availability_status = "available"
            else:
                availability_status = "available"
        
        # Formata limiting_ingredient para o formato esperado
        limiting_ingredient_formatted = None
        if limiting_ingredient:
            ingredient_name = limiting_ingredient.get('name', 'Ingrediente desconhecido')
            available_stock = limiting_ingredient.get('available_stock', 0)
            stock_unit = limiting_ingredient.get('stock_unit', 'un')
            consumption_per_unit = limiting_ingredient.get('consumption_per_unit', 0)
            
            # Formata mensagem de limite
            if capacity == 1:
                message = f"Limite de {capacity} unidade — {ingredient_name.lower()} insuficiente (restam {available_stock:.2f} {stock_unit})."
            elif capacity > 1:
                message = f"Limite de {capacity} unidades — {ingredient_name.lower()} insuficiente (restam {available_stock:.2f} {stock_unit})."
            else:
                # Capacidade = 0: sem estoque disponível
                message = f"Sem estoque disponível — {ingredient_name.lower()} insuficiente (restam {available_stock:.2f} {stock_unit})."
            
            limiting_ingredient_formatted = {
                "name": ingredient_name,
                "available": round(available_stock, 2),
                "unit": stock_unit,
                "message": message
            }
        
        # Monta resposta final
        response = {
            "product_id": product_id,
            "max_quantity": capacity,
            "capacity": capacity,  # Alias para compatibilidade
            "availability_status": availability_status,
            "limiting_ingredient": limiting_ingredient_formatted,
            "is_available": is_available,
            "message": capacity_result.get('message', f'Capacidade: {capacity} unidades')
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        # ALTERAÇÃO: Não expõe detalhes internos do erro ao cliente
        # ALTERAÇÃO: Usar product_id apenas se estiver definido para evitar erro no log
        product_id_str = str(product_id) if product_id is not None else "desconhecido"
        logger.error(f"Erro ao simular capacidade do produto {product_id_str}: {e}", exc_info=True)
        return jsonify({
            "error": "Erro interno ao calcular capacidade",
            "message": "Não foi possível calcular a capacidade do produto. Tente novamente mais tarde."
        }), 500  

@product_bp.route('/', methods=['POST'])  
@require_role('admin', 'manager')  
def create_product_route():  
    # Verifica se há dados JSON ou form data
    data = {}
    if request.is_json:
        try:
            data = request.get_json()
            if data is None:
                return jsonify({"error": "JSON inválido ou vazio"}), 400
        except Exception as e:
            return jsonify({"error": "Erro ao processar JSON"}), 400
    else:
        # Para multipart/form-data, pega os dados do form
        data = {}
        
        # Campos de texto
        if request.form.get('name'):
            data['name'] = request.form.get('name')
        if request.form.get('description'):
            data['description'] = request.form.get('description')
            
        # Campos numéricos - converte string para float/int
        if request.form.get('price'):
            try:
                data['price'] = float(request.form.get('price'))
            except (ValueError, TypeError):
                pass
                
        if request.form.get('cost_price'):
            try:
                data['cost_price'] = float(request.form.get('cost_price'))
            except (ValueError, TypeError):
                pass
                
        if request.form.get('preparation_time_minutes'):
            try:
                data['preparation_time_minutes'] = int(request.form.get('preparation_time_minutes'))
            except (ValueError, TypeError):
                pass
                
        if request.form.get('category_id'):
            try:
                data['category_id'] = int(request.form.get('category_id'))
            except (ValueError, TypeError):
                pass
    
    # Verifica se há arquivo de imagem
    image_file = request.files.get('image')
    
    if not data and not image_file:
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400
    
    # Cria o produto primeiro (agora aceita lista "ingredients" com portions/min/max)
    new_product, error_code, error_message = product_service.create_product(data)  
    if not new_product:
        if error_code in ["INVALID_NAME", "INVALID_PRICE", "INVALID_COST_PRICE", "INVALID_PREP_TIME", "INVALID_CATEGORY"]:  
            return jsonify({"error": error_message}), 400  
        if error_code == "CATEGORY_NOT_FOUND":  
            return jsonify({"error": error_message}), 404  
        if error_code == "PRODUCT_NAME_EXISTS":  
            return jsonify({"error": error_message}), 409  
        if error_code == "INVALID_INGREDIENTS":
            return jsonify({"error": error_message}), 400
        if error_code == "INCOMPLETE_RECIPE":
            return jsonify({"error": error_message}), 400
        if error_code == "DATABASE_ERROR":  
            return jsonify({"error": error_message}), 500  
        return jsonify({"error": "Não foi possível criar o produto"}), 500
    
    # Se o produto foi criado com sucesso e há uma imagem, salva a imagem
    if image_file:
        product_id = new_product.get('id')
        success, file_path, error_msg = save_product_image(image_file, product_id)
        
        if not success:
            # Se falhou ao salvar a imagem, remove o produto criado
            product_service.deactivate_product(product_id)
            return jsonify({"error": f"Produto criado mas falha ao salvar imagem: {error_msg}"}), 500
        
        # Salva a URL da imagem no banco de dados
        image_url = f"/api/uploads/products/{product_id}.jpeg"
        product_service.update_product_image_url(product_id, image_url)
        
        # Adiciona a URL da imagem ao produto retornado
        new_product['image_url'] = image_url
    
    return jsonify(new_product), 201  

@product_bp.route('/<int:product_id>', methods=['PUT'])  
@require_role('admin', 'manager')  
def update_product_route(product_id):  
    # Verifica se há dados JSON ou form data
    data = {}
    if request.is_json:
        try:
            data = request.get_json()
            if data is None:
                return jsonify({"error": "JSON inválido ou vazio"}), 400
        except Exception as e:
            return jsonify({"error": "Erro ao processar JSON"}), 400
    else:
        # Para multipart/form-data, pega os dados do form
        data = {}
        
        # Campos de texto
        if request.form.get('name'):
            data['name'] = request.form.get('name')
        if request.form.get('description'):
            data['description'] = request.form.get('description')
            
        # Campos numéricos - converte string para float/int
        if request.form.get('price'):
            try:
                data['price'] = float(request.form.get('price'))
            except (ValueError, TypeError):
                pass
                
        if request.form.get('cost_price'):
            try:
                data['cost_price'] = float(request.form.get('cost_price'))
            except (ValueError, TypeError):
                pass
                
        if request.form.get('preparation_time_minutes'):
            try:
                data['preparation_time_minutes'] = int(request.form.get('preparation_time_minutes'))
            except (ValueError, TypeError):
                pass
                
        if request.form.get('category_id'):
            try:
                data['category_id'] = int(request.form.get('category_id'))
            except (ValueError, TypeError):
                pass
        if request.form.get('ingredients'):
            try:
                import json
                data['ingredients'] = json.loads(request.form.get('ingredients'))
                # ALTERAÇÃO: Substituído print() por logging estruturado
                logger.debug(f"Ingredientes recebidos do form: {len(data['ingredients'])} itens")
            except (ValueError, TypeError, json.JSONDecodeError) as e:
                logger.error(f"Erro ao fazer parse dos ingredientes: {e}", exc_info=True)
                return jsonify({"error": "Formato inválido para ingredientes"}), 400
    
    # Verifica se há arquivo de imagem ou se deve remover a imagem
    image_file = request.files.get('image')
    remove_image = request.form.get('remove_image', '').lower() == 'true' or data.get('remove_image', False)
    
    if not data and not image_file and not remove_image:
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400
    
    # Atualiza o produto primeiro (inclui diff de "ingredients")
    success, error_code, message = product_service.update_product(product_id, data)  
    if not success:
        if error_code == "PRODUCT_NOT_FOUND":  
            return jsonify({"error": message}), 404  
        if error_code == "PRODUCT_NAME_EXISTS":  
            return jsonify({"error": message}), 409  
        if error_code in ["INVALID_NAME", "INVALID_PRICE", "INVALID_COST_PRICE", "INVALID_PREP_TIME", "NO_VALID_FIELDS", "INVALID_CATEGORY"]:  
            return jsonify({"error": message}), 400  
        if error_code == "CATEGORY_NOT_FOUND":  
            return jsonify({"error": message}), 404  
        elif error_code == "INVALID_INGREDIENTS":
            return jsonify({"error": message}), 400
        elif error_code == "DATABASE_ERROR":  
            return jsonify({"error": message}), 500  
        else:  
            return jsonify({"error": "Falha ao atualizar produto"}), 500
    
    # Atualiza a imagem do produto usando a nova função
    if image_file or remove_image:
        img_success, image_url, img_error = update_product_image(
            product_id, 
            image_file=image_file, 
            remove_image=remove_image
        )
        
        if not img_success:
            return jsonify({"error": f"Produto atualizado mas falha ao processar imagem: {img_error}"}), 500
        
        # Atualiza a URL da imagem no banco de dados
        if image_url:
            product_service.update_product_image_url(product_id, image_url)
        else:
            # Remove a URL da imagem do banco se foi removida
            product_service.update_product_image_url(product_id, None)
    
    return jsonify({"msg": message}), 200  

@product_bp.route('/<int:product_id>', methods=['DELETE'])  
@require_role('admin', 'manager')  
def delete_product_route(product_id):
    if product_service.deactivate_product(product_id):
        # Não apague a imagem no soft delete
        return jsonify({"msg": "Produto inativado com sucesso"}), 200

@product_bp.route('/<int:product_id>/reactivate', methods=['POST'])  
@require_role('admin', 'manager')  
def reactivate_product_route(product_id):  
    if product_service.reactivate_product(product_id):  
        return jsonify({"msg": "Produto reativado com sucesso"}), 200  
    return jsonify({"error": "Falha ao reativar produto ou produto não encontrado"}), 404  

@product_bp.route('/<int:product_id>/ingredients', methods=['GET'])  
def get_product_ingredients_route(product_id):  
    # Aceita parâmetro quantity opcional para calcular max_quantity dos ingredientes
    # considerando consumo proporcional: consumo_total = consumo_por_unidade × quantity
    quantity = request.args.get('quantity', type=int, default=1)
    # redireciona para ingredient_service para incluir custo estimado
    from ..services import ingredient_service
    result = ingredient_service.get_ingredients_for_product(product_id, quantity=quantity)
    return jsonify(result), 200  

@product_bp.route('/<int:product_id>/ingredients', methods=['POST'])  
@require_role('admin', 'manager')  
def add_ingredient_to_product_route(product_id):  
    # ALTERAÇÃO: Validação de product_id da rota
    if not isinstance(product_id, int) or product_id <= 0:
        return jsonify({"error": "ID do produto inválido"}), 400
    
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception as e:
        # ALTERAÇÃO: Logging de erro sem expor detalhes ao cliente
        logger.error(f"Erro ao processar JSON na rota add_ingredient_to_product: {e}", exc_info=True)
        return jsonify({"error": "Erro ao processar JSON"}), 400
    
    ingredient_id = data.get('ingredient_id')  
    portions = data.get('portions')  
    
    # ALTERAÇÃO: Validação mais robusta de campos obrigatórios
    if not ingredient_id:
        return jsonify({"error": "Campo 'ingredient_id' é obrigatório"}), 400
    if portions is None:
        return jsonify({"error": "Campo 'portions' é obrigatório"}), 400
    
    # ALTERAÇÃO: Validação de tipo de ingredient_id
    try:
        ingredient_id = int(ingredient_id)
        if ingredient_id <= 0:
            return jsonify({"error": "ID do ingrediente deve ser um número positivo"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "ID do ingrediente deve ser um número válido"}), 400
    
    # ALTERAÇÃO: Validação de tipo de portions
    try:
        portions = float(portions)
        if portions <= 0:
            return jsonify({"error": "Número de porções deve ser maior que zero"}), 400
        if portions > 999999.99:
            return jsonify({"error": "Número de porções muito grande (máximo: 999999.99)"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Campo 'portions' deve ser um número válido"}), 400
    
    from ..services import ingredient_service
    try:
        if ingredient_service.add_ingredient_to_product(product_id, ingredient_id, portions):  
            return jsonify({"msg": "Ingrediente associado/atualizado com sucesso"}), 201  
        # ALTERAÇÃO: Mensagem de erro mais específica
        return jsonify({"error": "Falha ao associar ingrediente. Verifique se o produto e ingrediente existem."}), 500
    except Exception as e:
        # ALTERAÇÃO: Tratamento de exceções não esperadas
        logger.error(f"Erro inesperado ao associar ingrediente: {e}", exc_info=True)
        return jsonify({"error": "Erro interno ao associar ingrediente"}), 500  

@product_bp.route('/<int:product_id>/ingredients/<int:ingredient_id>', methods=['DELETE'])  
@require_role('admin', 'manager')  
def remove_ingredient_from_product_route(product_id, ingredient_id):  
    # ALTERAÇÃO: Validação de IDs da rota
    if not isinstance(product_id, int) or product_id <= 0:
        return jsonify({"error": "ID do produto inválido"}), 400
    if not isinstance(ingredient_id, int) or ingredient_id <= 0:
        return jsonify({"error": "ID do ingrediente inválido"}), 400
    
    from ..services import ingredient_service
    try:
        if ingredient_service.remove_ingredient_from_product(product_id, ingredient_id):  
            return jsonify({"msg": "Ingrediente desassociado com sucesso"}), 200  
        # ALTERAÇÃO: Mensagem mais específica
        return jsonify({"error": "Vínculo produto-ingrediente não encontrado"}), 404
    except Exception as e:
        # ALTERAÇÃO: Tratamento de exceções não esperadas
        logger.error(f"Erro inesperado ao remover ingrediente: {e}", exc_info=True)
        return jsonify({"error": "Erro interno ao remover ingrediente"}), 500  


@product_bp.route('/<int:product_id>/ingredients/<int:ingredient_id>', methods=['PUT'])
@require_role('admin', 'manager')
def update_product_ingredient_route(product_id, ingredient_id):
    # ALTERAÇÃO: Validação de IDs da rota
    if not isinstance(product_id, int) or product_id <= 0:
        return jsonify({"error": "ID do produto inválido"}), 400
    if not isinstance(ingredient_id, int) or ingredient_id <= 0:
        return jsonify({"error": "ID do ingrediente inválido"}), 400
    
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception as e:
        # ALTERAÇÃO: Logging de erro sem expor detalhes ao cliente
        logger.error(f"Erro ao processar JSON na rota update_product_ingredient: {e}", exc_info=True)
        return jsonify({"error": "Erro ao processar JSON"}), 400
    
    portions = data.get('portions')
    if portions is None:
        return jsonify({"error": "Campo 'portions' é obrigatório"}), 400
    
    # ALTERAÇÃO: Validação de tipo de portions antes de passar para o serviço
    try:
        portions_float = float(portions)
        if portions_float <= 0:
            return jsonify({"error": "Número de porções deve ser maior que zero"}), 400
        if portions_float > 999999.99:
            return jsonify({"error": "Número de porções muito grande (máximo: 999999.99)"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Campo 'portions' deve ser um número válido"}), 400
    
    from ..services import ingredient_service
    try:
        success, error_code, message = ingredient_service.update_product_ingredient(product_id, ingredient_id, portions=portions)
        if success:
            return jsonify({"msg": message}), 200
        # ALTERAÇÃO: Tratamento específico de códigos de erro
        if error_code == "NO_VALID_FIELDS":
            return jsonify({"error": message}), 400
        if error_code in ["INVALID_PRODUCT_ID", "INVALID_INGREDIENT_ID"]:
            return jsonify({"error": message}), 400
        if error_code == "LINK_NOT_FOUND":
            return jsonify({"error": message}), 404
        if error_code == "UPDATE_FAILED":
            return jsonify({"error": message}), 500
        if error_code == "DATABASE_ERROR":
            return jsonify({"error": message}), 500
        # ALTERAÇÃO: Fallback para códigos de erro não mapeados
        return jsonify({"error": message or "Falha ao atualizar vínculo"}), 500
    except Exception as e:
        # ALTERAÇÃO: Tratamento de exceções não esperadas
        logger.error(f"Erro inesperado ao atualizar ingrediente: {e}", exc_info=True)
        return jsonify({"error": "Erro interno ao atualizar vínculo"}), 500


@product_bp.route('/search', methods=['GET'])  
def search_products_route():  
    name = request.args.get('name')  
    category_id = request.args.get('category_id', type=int)  
    page = request.args.get('page', type=int, default=1)  
    page_size = request.args.get('page_size', type=int, default=10)  
    # Corrigir interpretação de parâmetro booleano
    include_inactive_param = request.args.get('include_inactive', '').lower()
    include_inactive = include_inactive_param in ('true', '1', 'yes') if include_inactive_param else False  
    result = product_service.search_products(name=name, category_id=category_id, page=page, page_size=page_size, include_inactive=include_inactive)  
    return jsonify(result), 200


@product_bp.route('/most-ordered', methods=['GET'])
def get_most_ordered_products_route():
    """Retorna os produtos mais pedidos baseado no histórico de pedidos completos."""
    page = request.args.get('page', type=int, default=1)
    page_size = request.args.get('page_size', type=int, default=10)
    result = product_service.get_most_ordered_products(page=page, page_size=page_size)
    return jsonify(result), 200


@product_bp.route('/recently-added', methods=['GET'])
def get_recently_added_products_route():
    """Retorna os produtos mais recentemente adicionados ao catálogo."""
    page = request.args.get('page', type=int, default=1)
    page_size = request.args.get('page_size', type=int, default=10)
    result = product_service.get_recently_added_products(page=page, page_size=page_size)
    return jsonify(result), 200


@product_bp.route('/<int:product_id>/apply-group', methods=['POST'])
@require_role('admin', 'manager')
def apply_group_to_product_route(product_id):
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception:
        return jsonify({"error": "Erro ao processar JSON"}), 400

    group_id = data.get('group_id')
    if not group_id:
        return jsonify({"error": "'group_id' é obrigatório"}), 400

    default_min = int(data.get('default_min_quantity', 0))
    default_max = int(data.get('default_max_quantity', 1))
    added, error_code, message = product_service.apply_group_to_product(product_id, group_id, default_min, default_max)
    if added is not None and error_code is None:
        return jsonify({"added_ingredients": added}), 200
    if error_code == "PRODUCT_NOT_FOUND":
        return jsonify({"error": message}), 404
    if error_code == "GROUP_NOT_FOUND":
        return jsonify({"error": message}), 404
    if error_code == "DATABASE_ERROR":
        return jsonify({"error": message}), 500
    return jsonify({"error": "Falha ao aplicar grupo"}), 500

@product_bp.route('/inactive', methods=['GET'])  
@require_role('admin', 'manager')  
def list_inactive_products_route():  
    """Lista apenas produtos inativos - apenas para administradores e gerentes"""
    name = request.args.get('name')  
    category_id = request.args.get('category_id', type=int)  
    page = request.args.get('page', type=int, default=1)  
    page_size = request.args.get('page_size', type=int, default=10)  
    result = product_service.list_products(name_filter=name, category_id=category_id, page=page, page_size=page_size, include_inactive=True)  
    # Filtra apenas produtos inativos
    if result and 'items' in result:
        result['items'] = [item for item in result['items'] if not item.get('is_active', True)]
        result['pagination']['total'] = len(result['items'])
    return jsonify(result), 200

@product_bp.route('/category/<int:category_id>', methods=['GET'])
def get_products_by_category_route(category_id):
    """
    Busca produtos por ID da categoria
    """
    page = request.args.get('page', type=int, default=1)
    page_size = request.args.get('page_size', type=int, default=10)
    # Corrigir interpretação de parâmetro booleano
    include_inactive_param = request.args.get('include_inactive', '').lower()
    include_inactive = include_inactive_param in ('true', '1', 'yes') if include_inactive_param else False
    
    # CORREÇÃO: Painel admin mostra todos os produtos (incluindo indisponíveis)
    # Rotas /api/products/* são usadas pelo painel administrativo
    result, error_code, error_message = product_service.get_products_by_category_id(
        category_id=category_id, 
        page=page, 
        page_size=page_size, 
        include_inactive=include_inactive,
        filter_unavailable=False  # Painel admin vê todos os produtos
    )
    
    if result:
        return jsonify(result), 200
    
    if error_code == "CATEGORY_NOT_FOUND":
        return jsonify({"error": error_message}), 404
    if error_code == "DATABASE_ERROR":
        return jsonify({"error": error_message}), 500
    
    return jsonify({"error": "Erro interno do servidor"}), 500


@product_bp.route('/<int:product_id>/image', methods=['PUT'])
@require_role('admin', 'manager')
def update_product_image_route(product_id):
    """
    Atualiza apenas a imagem do produto
    - Se enviar arquivo: substitui a imagem atual
    - Se enviar remove_image=true: remove a imagem atual
    """
    try:
        # Verifica se o produto existe
        product = product_service.get_product_by_id(product_id)
        if not product:
            return jsonify({"error": "Produto não encontrado"}), 404
        
        # Verifica se há arquivo de imagem ou se deve remover
        image_file = request.files.get('image')
        remove_image = request.form.get('remove_image', '').lower() == 'true'
        
        if not image_file and not remove_image:
            return jsonify({"error": "Deve enviar uma imagem ou marcar remove_image=true"}), 400
        
        # Atualiza a imagem
        img_success, image_url, img_error = update_product_image(
            product_id, 
            image_file=image_file, 
            remove_image=remove_image
        )
        
        if not img_success:
            return jsonify({"error": img_error}), 500
        
        # Atualiza a URL da imagem no banco de dados
        if image_url:
            product_service.update_product_image_url(product_id, image_url)
            return jsonify({
                "msg": "Imagem atualizada com sucesso",
                "image_url": image_url
            }), 200
        else:
            # Remove a URL da imagem do banco
            product_service.update_product_image_url(product_id, None)
            return jsonify({
                "msg": "Imagem removida com sucesso"
            }), 200
            
    except Exception as e:
        return jsonify({"error": f"Erro interno: {str(e)}"}), 500


@product_bp.route('/image/<int:product_id>', methods=['GET'])
def get_product_image_route(product_id):
    """
    Serve a imagem do produto de forma segura
    """
    try:
        # Primeiro verifica se o produto existe e tem imagem no banco
        product = product_service.get_product_by_id(product_id)
        if not product:
            return jsonify({"error": "Produto não encontrado"}), 404
        
        # Verifica se o produto tem imagem_url no banco
        image_url = product.get('image_url')
        if not image_url:
            return jsonify({"error": "Produto não possui imagem"}), 404
        
        # Extrai o nome do arquivo da URL
        filename = os.path.basename(image_url)
        if not filename.endswith('.jpeg'):
            return jsonify({"error": "Formato de imagem inválido"}), 400
        
        # Caminho seguro para a pasta de uploads
        upload_dir = os.path.join(os.getcwd(), 'uploads', 'products')
        file_path = os.path.join(upload_dir, filename)
        
        # Verifica se o arquivo existe fisicamente
        if not os.path.exists(file_path):
            return jsonify({"error": "Arquivo de imagem não encontrado"}), 404
        
        # OTIMIZAÇÃO DE PERFORMANCE: Usar streaming para arquivos grandes
        # Melhorar headers de cache com ETag e Last-Modified
        import hashlib
        from datetime import datetime
        
        file_size = os.path.getsize(file_path)
        file_mtime = os.path.getmtime(file_path)
        
        # Gera ETag baseado no tamanho e data de modificação do arquivo
        etag_input = f"{filename}_{file_size}_{file_mtime}"
        etag = hashlib.md5(etag_input.encode()).hexdigest()
        
        # Verifica se o cliente já tem a versão mais recente (304 Not Modified)
        if_none_match = request.headers.get('If-None-Match')
        if if_none_match == etag:
            return Response(status=304, headers={'ETag': etag})
        
        # Para arquivos menores que 1MB, carrega em memória (mais rápido)
        # Para arquivos maiores, usa streaming
        if file_size < 1024 * 1024:  # < 1MB
            with open(file_path, 'rb') as f:
                image_data = f.read()
            response = Response(
                image_data,
                mimetype='image/jpeg',
                headers={
                    'Content-Type': 'image/jpeg',
                    'Content-Length': str(file_size),
                    'Accept-Ranges': 'bytes',
                    'X-Content-Type-Options': 'nosniff',
                    'Cache-Control': 'public, max-age=86400',  # 24 horas (aumentado de 1 hora)
                    'ETag': etag,
                    'Last-Modified': datetime.fromtimestamp(file_mtime).strftime('%a, %d %b %Y %H:%M:%S GMT'),
                }
            )
        else:
            # Streaming para arquivos grandes
            def generate():
                with open(file_path, 'rb') as f:
                    while True:
                        chunk = f.read(8192)  # 8KB chunks
                        if not chunk:
                            break
                        yield chunk
            
            response = Response(
                generate(),
                mimetype='image/jpeg',
                headers={
                    'Content-Type': 'image/jpeg',
                    'Content-Length': str(file_size),
                    'Accept-Ranges': 'bytes',
                    'X-Content-Type-Options': 'nosniff',
                    'Cache-Control': 'public, max-age=86400',  # 24 horas
                    'ETag': etag,
                    'Last-Modified': datetime.fromtimestamp(file_mtime).strftime('%a, %d %b %Y %H:%M:%S GMT'),
                }
            )
        
        # Headers CORS
        origin = request.headers.get('Origin')
        if origin:
            response.headers.add('Access-Control-Allow-Origin', origin)
        else:
            response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Methods', 'GET, OPTIONS')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        response.headers.add('Cross-Origin-Resource-Policy', 'cross-origin')
        
        return response
        
    except Exception as e:
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao servir imagem: {e}", exc_info=True)
        return jsonify({"error": "Erro interno ao carregar imagem"}), 500


@product_bp.route('/<int:product_id>/cost-calculation', methods=['GET'])
@require_role('admin', 'manager')
def get_product_cost_calculation_route(product_id):
    """
    Calcula o custo do produto baseado nas porções dos ingredientes
    """
    try:
        result = product_service.calculate_product_cost_by_ingredients(product_id)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": f"Erro ao calcular custo: {str(e)}"}), 500


@product_bp.route('/<int:product_id>/consume-ingredients', methods=['POST'])
@require_role('admin', 'manager')
def consume_ingredients_route(product_id):
    """
    Consome ingredientes do estoque para produção/venda do produto
    """
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception as e:
        return jsonify({"error": "Erro ao processar JSON"}), 400
    
    quantity = data.get('quantity', 1)
    if quantity <= 0:
        return jsonify({"error": "Quantidade deve ser maior que zero"}), 400
    
    success, error_code, message = product_service.consume_ingredients_for_sale(product_id, quantity)
    
    if success:
        return jsonify({"msg": message}), 200
    elif error_code == "NO_INGREDIENTS":
        return jsonify({"error": message}), 400
    elif error_code == "INSUFFICIENT_STOCK":
        return jsonify({"error": message}), 409
    elif error_code == "DATABASE_ERROR":
        return jsonify({"error": message}), 500
    else:
        return jsonify({"error": "Erro interno do servidor"}), 500


@product_bp.route('/<int:product_id>/can-delete', methods=['GET'])
@require_role('admin', 'manager')
def can_delete_product_route(product_id):
    """
    Verifica se um produto pode ser excluído permanentemente
    """
    try:
        conn = None
        try:
            from ..database import get_db_connection
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Verificar se o produto existe
            cur.execute("SELECT ID, NAME FROM PRODUCTS WHERE ID = ?", (product_id,))
            product = cur.fetchone()
            if not product:
                return jsonify({"error": "Produto não encontrado"}), 404
            
            product_name = product[1]
            
            # Verificar pedidos ativos
            cur.execute("""
                SELECT COUNT(*) FROM ORDER_ITEMS oi
                JOIN ORDERS o ON oi.ORDER_ID = o.ID
                WHERE oi.PRODUCT_ID = ? AND o.STATUS NOT IN ('cancelled', 'delivered')
            """, (product_id,))
            active_orders = cur.fetchone()[0] or 0
            
            # Verificar itens no carrinho
            cur.execute("""
                SELECT COUNT(*) FROM CART_ITEMS ci
                JOIN CARTS c ON ci.CART_ID = c.ID
                WHERE ci.PRODUCT_ID = ? AND c.IS_ACTIVE = TRUE
            """, (product_id,))
            cart_items = cur.fetchone()[0] or 0
            
            # Verificar ingredientes relacionados
            cur.execute("SELECT COUNT(*) FROM PRODUCT_INGREDIENTS WHERE PRODUCT_ID = ?", (product_id,))
            ingredients_count = cur.fetchone()[0] or 0
            
            can_delete = active_orders == 0 and cart_items == 0
            reasons = []
            
            if active_orders > 0:
                reasons.append(f"Produto possui {active_orders} pedido(s) ativo(s)")
            if cart_items > 0:
                reasons.append(f"Produto está em {cart_items} carrinho(s) ativo(s)")
            
            return jsonify({
                "product_id": product_id,
                "product_name": product_name,
                "can_delete": can_delete,
                "reasons": reasons,
                "details": {
                    "active_orders": active_orders,
                    "cart_items": cart_items,
                    "ingredients_count": ingredients_count
                }
            }), 200
            
        except Exception as e:
            return jsonify({"error": f"Erro ao verificar: {str(e)}"}), 500
        finally:
            if conn:
                conn.close()
                
    except Exception as e:
        return jsonify({"error": f"Erro interno: {str(e)}"}), 500


@product_bp.route('/<int:product_id>/permanent-delete', methods=['DELETE'])
@require_role('admin')  # Apenas admin pode excluir permanentemente
def permanent_delete_product_route(product_id):
    """
    Exclui permanentemente um produto e todos os seus relacionamentos
    ATENÇÃO: Esta operação é irreversível!
    """
    try:
        success, error_code, message = product_service.delete_product(product_id)
        
        if success:
            return jsonify(message), 200
        elif error_code == "PRODUCT_NOT_FOUND":
            return jsonify({"error": message}), 404
        elif error_code == "PRODUCT_IN_ACTIVE_ORDERS":
            return jsonify({"error": message}), 409
        elif error_code == "PRODUCT_IN_CART":
            return jsonify({"error": message}), 409
        elif error_code == "DELETE_FAILED":
            return jsonify({"error": message}), 500
        elif error_code == "DATABASE_ERROR":
            return jsonify({"error": message}), 500
        elif error_code == "GENERAL_ERROR":
            return jsonify({"error": message}), 500
        else:
            return jsonify({"error": "Erro interno do servidor"}), 500
            
    except Exception as e:
        return jsonify({"error": f"Erro interno: {str(e)}"}), 500  
