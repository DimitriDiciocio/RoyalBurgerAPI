from flask import Blueprint, request, jsonify  # importa Blueprint, request e jsonify do Flask
from ..services import product_service  # importa serviço de produtos (seções)
from ..services.auth_service import require_role  # importa decorator de autorização por papel
from flask_jwt_extended import get_jwt  # importa utilitário para ler claims do JWT

section_bp = Blueprint('sections', __name__)  # cria o blueprint de seções

@section_bp.route('/', methods=['GET'])  # lista todas as seções
def get_all_sections_route():  # função handler da listagem
    sections = product_service.get_all_sections()  # busca seções no serviço
    return jsonify(sections), 200  # retorna lista com status 200

@section_bp.route('/', methods=['POST'])  # cria nova seção
@require_role('admin', 'manager')  # restringe a admin/manager
def create_section_route():  # função handler de criação
    claims = get_jwt()  # obtém claims do token
    user_id = claims.get('id')  # extrai id do usuário
    data = request.get_json()  # captura corpo JSON
    if not data or not data.get('name'):  # valida campo obrigatório name
        return jsonify({"error": "O campo 'name' é obrigatório"}), 400  # retorna 400
    new_section = product_service.create_section(data, user_id)  # cria seção via serviço
    if new_section:  # criada com sucesso
        return jsonify(new_section), 201  # retorna 201
    return jsonify({"error": "Não foi possível criar a seção"}), 500  # retorna 500

@section_bp.route('/<int:section_id>', methods=['PUT'])  # atualiza seção
@require_role('admin', 'manager')  # restringe a admin/manager
def update_section_route(section_id):  # função handler de atualização
    data = request.get_json()  # captura corpo JSON
    if not data:  # valida corpo não vazio
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400  # retorna 400
    if product_service.update_section(section_id, data):  # atualiza via serviço
        return jsonify({"msg": "Seção atualizada com sucesso"}), 200  # retorna 200
    return jsonify({"error": "Falha ao atualizar seção ou seção não encontrada"}), 404  # retorna 404

@section_bp.route('/<int:section_id>', methods=['DELETE'])  # deleta seção
@require_role('admin', 'manager')  # restringe a admin/manager
def delete_section_route(section_id):  # função handler de deleção
    if product_service.delete_section(section_id):  # deleta via serviço
        return jsonify({"msg": "Seção deletada com sucesso"}), 200  # retorna 200
    return jsonify({"error": "Falha ao deletar seção ou seção não encontrada"}), 404  # retorna 404

@section_bp.route('/<int:section_id>/products/<int:product_id>', methods=['POST'])  # associa produto à seção
@require_role('admin', 'manager')  # restringe a admin/manager
def add_product_to_section_route(section_id, product_id):  # função handler de associação
    if product_service.add_product_to_section(product_id, section_id):  # associa via serviço
        return jsonify({"msg": f"Produto {product_id} associado à seção {section_id} com sucesso"}), 201  # retorna 201
    return jsonify({"error": "Falha ao realizar associação"}), 500  # retorna 500

@section_bp.route('/<int:section_id>/products/<int:product_id>', methods=['DELETE'])  # remove associação produto/seção
@require_role('admin', 'manager')  # restringe a admin/manager
def remove_product_from_section_route(section_id, product_id):  # função handler de remoção de associação
    if product_service.remove_product_from_section(product_id, section_id):  # remove via serviço
        return jsonify({"msg": f"Associação do produto {product_id} com a seção {section_id} removida"}), 200  # retorna 200
    return jsonify({"error": "Falha ao remover associação ou associação não encontrada"}), 404  # retorna 404

@section_bp.route('/<int:section_id>', methods=['GET'])  # busca seção por ID
def get_section_by_id_route(section_id):  # função handler da busca por ID
    section = product_service.get_section_by_id(section_id)  # busca seção no serviço
    if section:  # se encontrada
        return jsonify(section), 200  # retorna 200
    return jsonify({"error": "Seção não encontrada"}), 404  # retorna 404
