from flask import Blueprint, request, jsonify  # importa Blueprint, request e jsonify do Flask
from ..services import ingredient_service  # importa o serviço de ingredientes
from ..services.auth_service import require_role  # importa decorator de autorização por papel

ingredient_bp = Blueprint('ingredients', __name__)  # cria o blueprint de ingredientes

@ingredient_bp.route('/', methods=['GET'])  # lista todos os ingredientes
@require_role('admin', 'manager')  # restringe a admin/manager
def get_all_ingredients_route():  # função handler da listagem
    status_filter = request.args.get('status')  # obtém filtro ?status=low_stock|out_of_stock|in_stock
    ingredients = ingredient_service.get_all_ingredients(status_filter)  # busca ingredientes no serviço
    return jsonify(ingredients), 200  # retorna lista com status 200

@ingredient_bp.route('/', methods=['POST'])  # cria novo ingrediente
@require_role('admin', 'manager')  # restringe a admin/manager
def create_ingredient_route():  # função handler de criação
    data = request.get_json()  # captura corpo JSON
    if not data or not data.get('name'):  # valida campo obrigatório name
        return jsonify({"error": "O campo 'name' é obrigatório"}), 400  # retorna 400 se inválido
    new_ingredient = ingredient_service.create_ingredient(data)  # delega criação ao serviço
    if new_ingredient:  # criado com sucesso
        return jsonify(new_ingredient), 201  # retorna 201
    return jsonify({"error": "Não foi possível criar o ingrediente"}), 500  # erro 500

@ingredient_bp.route('/<int:ingredient_id>', methods=['PUT'])  # atualiza ingrediente
@require_role('admin', 'manager')  # restringe a admin/manager
def update_ingredient_route(ingredient_id):  # função handler de atualização
    data = request.get_json()  # captura corpo JSON
    if not data:  # valida corpo não vazio
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400  # retorna 400
    if ingredient_service.update_ingredient(ingredient_id, data):  # atualiza via serviço
        return jsonify({"msg": "Ingrediente atualizado com sucesso"}), 200  # retorna 200
    return jsonify({"error": "Falha ao atualizar ingrediente ou ingrediente não encontrado"}), 404  # retorna 404

@ingredient_bp.route('/<int:ingredient_id>', methods=['DELETE'])  # inativa ingrediente
@require_role('admin', 'manager')  # restringe a admin/manager
def delete_ingredient_route(ingredient_id):  # função handler de inativação
    if ingredient_service.deactivate_ingredient(ingredient_id):  # inativa via serviço
        return jsonify({"msg": "Ingrediente marcado como indisponível com sucesso"}), 200  # retorna 200
    return jsonify({"error": "Falha ao inativar ingrediente ou ingrediente não encontrado"}), 404  # retorna 404

@ingredient_bp.route('/<int:ingredient_id>/availability', methods=['PATCH'])  # atualiza disponibilidade
@require_role('admin', 'manager')  # restringe a admin/manager
def update_availability_route(ingredient_id):  # função handler de disponibilidade
    data = request.get_json()  # captura corpo JSON
    is_available = data.get('is_available')  # extrai flag de disponibilidade
    if is_available is None or not isinstance(is_available, bool):  # valida flag booleana
        return jsonify({"error": "O campo 'is_available' é obrigatório e deve ser true ou false"}), 400  # retorna 400
    if ingredient_service.update_ingredient_availability(ingredient_id, is_available):  # atualiza via serviço
        status_text = "disponível" if is_available else "esgotado"  # define texto de status
        return jsonify({"msg": f"Ingrediente marcado como {status_text} com sucesso."}), 200  # retorna 200
    else:  # falha ou não encontrado
        return jsonify({"error": "Ingrediente não encontrado ou falha ao atualizar"}), 404  # retorna 404

@ingredient_bp.route('/<int:ingredient_id>/stock', methods=['POST'])  # ajusta estoque de ingrediente
@require_role('admin', 'manager')  # restringe a admin/manager
def adjust_ingredient_stock_route(ingredient_id):  # função handler de ajuste de estoque
    data = request.get_json()  # captura corpo JSON
    change = data.get('change')  # extrai variação
    if change is None:  # valida presença
        return jsonify({"error": "O campo 'change' é obrigatório"}), 400  # retorna 400
    try:  # tenta converter para número
        change_amount = float(change)  # conversão
    except (ValueError, TypeError):  # falha na conversão
        return jsonify({"error": "O campo 'change' deve ser um número válido"}), 400  # retorna 400
    success, error_code, message = ingredient_service.adjust_ingredient_stock(ingredient_id, change_amount)  # delega ajuste ao serviço
    if success:  # ajustado com sucesso
        return jsonify({"msg": message}), 200  # retorna 200
    elif error_code == "INGREDIENT_NOT_FOUND":  # ingrediente não encontrado
        return jsonify({"error": message}), 404  # retorna 404
    elif error_code == "NEGATIVE_STOCK":  # impedir estoque negativo
        return jsonify({"error": message}), 400  # retorna 400
    else:  # erro interno
        return jsonify({"error": "Erro interno do servidor"}), 500  # retorna 500