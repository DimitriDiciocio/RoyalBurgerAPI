from flask import Blueprint, request, jsonify, send_from_directory
import os
from ..services import product_service  
from ..services.auth_service import require_role
from ..utils.image_handler import save_product_image, delete_product_image, update_product_image  

product_bp = Blueprint('products', __name__)  

@product_bp.route('/', methods=['GET'])  
def list_products_route():  
    name = request.args.get('name')  
    category_id = request.args.get('category_id', type=int)  
    page = request.args.get('page', type=int, default=1)  
    page_size = request.args.get('page_size', type=int, default=10)  
    include_inactive = request.args.get('include_inactive', type=bool, default=False)  
    result = product_service.list_products(name_filter=name, category_id=category_id, page=page, page_size=page_size, include_inactive=include_inactive)  
    return jsonify(result), 200  

@product_bp.route('/<int:product_id>', methods=['GET'])  
def get_product_by_id_route(product_id):  
    product = product_service.get_product_by_id(product_id)  
    if product:  
        return jsonify(product), 200  
    return jsonify({"msg": "Produto não encontrado"}), 404  

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
                print(f"📦 Ingredientes recebidos do form: {len(data['ingredients'])} itens")
            except (ValueError, TypeError, json.JSONDecodeError) as e:
                print(f"❌ Erro ao fazer parse dos ingredientes: {e}")
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
    # redireciona para ingredient_service para incluir custo estimado
    from ..services import ingredient_service
    result = ingredient_service.get_ingredients_for_product(product_id)
    return jsonify(result), 200  

@product_bp.route('/<int:product_id>/ingredients', methods=['POST'])  
@require_role('admin', 'manager')  
def add_ingredient_to_product_route(product_id):  
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception as e:
        return jsonify({"error": "Erro ao processar JSON"}), 400
    ingredient_id = data.get('ingredient_id')  
    portions = data.get('portions')  
    if not ingredient_id or portions is None:  
        return jsonify({"error": "'ingredient_id' e 'portions' são obrigatórios"}), 400  
    if portions <= 0:
        return jsonify({"error": "Número de porções deve ser maior que zero"}), 400
    from ..services import ingredient_service
    if ingredient_service.add_ingredient_to_product(product_id, ingredient_id, portions):  
        return jsonify({"msg": "Ingrediente associado/atualizado com sucesso"}), 201  
    return jsonify({"error": "Falha ao associar ingrediente"}), 500  

@product_bp.route('/<int:product_id>/ingredients/<int:ingredient_id>', methods=['DELETE'])  
@require_role('admin', 'manager')  
def remove_ingredient_from_product_route(product_id, ingredient_id):  
    from ..services import ingredient_service
    if ingredient_service.remove_ingredient_from_product(product_id, ingredient_id):  
        return jsonify({"msg": "Ingrediente desassociado com sucesso"}), 200  
    return jsonify({"error": "Falha ao desassociar ingrediente ou associação não encontrada"}), 404  


@product_bp.route('/<int:product_id>/ingredients/<int:ingredient_id>', methods=['PUT'])
@require_role('admin', 'manager')
def update_product_ingredient_route(product_id, ingredient_id):
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception as e:
        return jsonify({"error": "Erro ao processar JSON"}), 400
    portions = data.get('portions')
    if portions is None:
        return jsonify({"error": "Campo 'portions' é obrigatório"}), 400
    if portions <= 0:
        return jsonify({"error": "Número de porções deve ser maior que zero"}), 400
    from ..services import ingredient_service
    success, error_code, message = ingredient_service.update_product_ingredient(product_id, ingredient_id, portions=portions)
    if success:
        return jsonify({"msg": message}), 200
    if error_code == "NO_VALID_FIELDS":
        return jsonify({"error": message}), 400
    if error_code == "LINK_NOT_FOUND":
        return jsonify({"error": message}), 404
    if error_code == "DATABASE_ERROR":
        return jsonify({"error": message}), 500
    return jsonify({"error": "Falha ao atualizar vínculo"}), 500


@product_bp.route('/search', methods=['GET'])  
def search_products_route():  
    name = request.args.get('name')  
    category_id = request.args.get('category_id', type=int)  
    page = request.args.get('page', type=int, default=1)  
    page_size = request.args.get('page_size', type=int, default=10)  
    include_inactive = request.args.get('include_inactive', type=bool, default=False)  
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
    include_inactive = request.args.get('include_inactive', type=bool, default=False)
    
    result, error_code, error_message = product_service.get_products_by_category_id(
        category_id=category_id, 
        page=page, 
        page_size=page_size, 
        include_inactive=include_inactive
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
        
        # Serve o arquivo com headers de segurança
        response = send_from_directory(upload_dir, filename, mimetype='image/jpeg')
        # Cache mais curto para evitar problemas com imagens atualizadas
        response.headers['Cache-Control'] = 'public, max-age=300'  # Cache por 5 minutos
        response.headers['X-Content-Type-Options'] = 'nosniff'
        # Adiciona ETag baseado na data de modificação do arquivo para cache mais inteligente
        import time
        file_mtime = os.path.getmtime(file_path)
        response.headers['ETag'] = f'"{int(file_mtime)}"'
        # Adiciona timestamp para cache busting
        response.headers['Last-Modified'] = time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(file_mtime))
        return response
        
    except Exception as e:
        print(f"Erro ao servir imagem: {e}")
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
