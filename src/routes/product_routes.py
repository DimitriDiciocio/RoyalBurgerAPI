from flask import Blueprint, request, jsonify  # importa Blueprint, request e jsonify do Flask
from ..services import product_service  # importa o serviço de produtos
from ..services.auth_service import require_role  # importa decorator de autorização por papel

product_bp = Blueprint('products', __name__)  # cria o blueprint de produtos

@product_bp.route('/', methods=['GET'])  # define rota GET para listar todos os produtos
def get_all_products_route():  # função handler para listagem
    products = product_service.get_all_products()  # busca todos os produtos no serviço
    return jsonify(products), 200  # retorna lista de produtos com status 200

@product_bp.route('/<int:product_id>', methods=['GET'])  # define rota GET para buscar produto por ID
def get_product_by_id_route(product_id):  # função handler para busca por ID
    product = product_service.get_product_by_id(product_id)  # busca produto no serviço
    if product:  # se encontrado
        return jsonify(product), 200  # retorna produto e status 200
    return jsonify({"msg": "Produto não encontrado"}), 404  # retorna 404 se não encontrado

@product_bp.route('/', methods=['POST'])  # define rota POST para criar produto
@require_role('admin', 'manager')  # restringe a admin/manager
def create_product_route():  # função handler de criação
    data = request.get_json()  # captura corpo JSON
    if not data or not data.get('name') or not data.get('price'):  # valida campos obrigatórios
        return jsonify({"error": "Nome e preço são obrigatórios"}), 400  # retorna 400 se inválido
    new_product, error_code, error_message = product_service.create_product(data)  # delega criação ao serviço
    if new_product:  # criado com sucesso
        return jsonify(new_product), 201  # retorna 201 com novo produto
    if error_code == "PRODUCT_NAME_EXISTS":  # nome duplicado
        return jsonify({"error": error_message}), 409  # conflito 409
    elif error_code in ["INVALID_NAME", "INVALID_PRICE"]:  # validações
        return jsonify({"error": error_message}), 400  # erro 400
    elif error_code == "DATABASE_ERROR":  # erro no banco
        return jsonify({"error": error_message}), 500  # erro 500
    else:  # fallback
        return jsonify({"error": "Não foi possível criar o produto"}), 500  # erro 500 genérico

@product_bp.route('/<int:product_id>', methods=['PUT'])  # define rota PUT para atualizar produto
@require_role('admin', 'manager')  # restringe a admin/manager
def update_product_route(product_id):  # função handler de atualização
    data = request.get_json()  # captura corpo JSON
    if not data:  # valida corpo não vazio
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400  # retorna 400
    success, error_code, message = product_service.update_product(product_id, data)  # delega atualização ao serviço
    if success:  # atualizado com sucesso
        return jsonify({"msg": message}), 200  # retorna 200
    if error_code == "PRODUCT_NOT_FOUND":  # produto não encontrado
        return jsonify({"error": message}), 404  # retorna 404
    elif error_code == "PRODUCT_NAME_EXISTS":  # nome duplicado
        return jsonify({"error": message}), 409  # conflito 409
    elif error_code in ["INVALID_NAME", "INVALID_PRICE", "NO_VALID_FIELDS"]:  # validações
        return jsonify({"error": message}), 400  # retorna 400
    elif error_code == "DATABASE_ERROR":  # erro no banco
        return jsonify({"error": message}), 500  # retorna 500
    else:  # fallback
        return jsonify({"error": "Falha ao atualizar produto"}), 500  # retorno 500 genérico

@product_bp.route('/<int:product_id>', methods=['DELETE'])  # define rota DELETE para inativar produto
@require_role('admin', 'manager')  # restringe a admin/manager
def delete_product_route(product_id):  # função handler de inativação
    if product_service.deactivate_product(product_id):  # inativa via serviço
        return jsonify({"msg": "Produto inativado com sucesso"}), 200  # retorna 200 em sucesso
    return jsonify({"error": "Falha ao inativar produto ou produto não encontrado"}), 404  # retorna 404 em falha

@product_bp.route('/<int:product_id>/ingredients', methods=['GET'])  # lista ingredientes de um produto
def get_product_ingredients_route(product_id):  # função handler de listagem de ingredientes
    ingredients = product_service.get_ingredients_for_product(product_id)  # busca ingredientes no serviço
    return jsonify(ingredients), 200  # retorna lista com status 200

@product_bp.route('/<int:product_id>/ingredients', methods=['POST'])  # adiciona ingrediente ao produto
@require_role('admin', 'manager')  # restringe a admin/manager
def add_ingredient_to_product_route(product_id):  # função handler de associação
    data = request.get_json()  # captura corpo JSON
    ingredient_id = data.get('ingredient_id')  # extrai id do ingrediente
    quantity = data.get('quantity')  # extrai quantidade
    if not ingredient_id or not quantity:  # valida presença de campos
        return jsonify({"error": "'ingredient_id' e 'quantity' são obrigatórios"}), 400  # erro 400
    if product_service.add_ingredient_to_product(product_id, ingredient_id, quantity):  # associa via serviço
        return jsonify({"msg": "Ingrediente associado/atualizado com sucesso"}), 201  # retorna 201 em sucesso
    return jsonify({"error": "Falha ao associar ingrediente"}), 500  # erro 500 em falha

@product_bp.route('/<int:product_id>/ingredients/<int:ingredient_id>', methods=['DELETE'])  # remove ingrediente do produto
@require_role('admin', 'manager')  # restringe a admin/manager
def remove_ingredient_from_product_route(product_id, ingredient_id):  # função handler de remoção de associação
    if product_service.remove_ingredient_from_product(product_id, ingredient_id):  # remove via serviço
        return jsonify({"msg": "Ingrediente desassociado com sucesso"}), 200  # retorna 200 em sucesso
    return jsonify({"error": "Falha ao desassociar ingrediente ou associação não encontrada"}), 404  # retorna 404 em falha