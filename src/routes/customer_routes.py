from flask import Blueprint, request, jsonify  # importa funções e classes do Flask
from ..services import user_service, address_service, loyalty_service  # importa serviços de usuário, endereço e fidelidade
from ..services.auth_service import require_role  # importa decorator para restrição por papel
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity  # importa utilitários de JWT

customer_bp = Blueprint('customers', __name__)  # cria o blueprint de rotas de clientes

@customer_bp.route('/', methods=['POST'])  # define rota POST para criar cliente
def create_customer_route():  # função handler da criação de cliente
    data = request.get_json()  # captura JSON da requisição

    required_fields = ['full_name', 'email', 'password', 'password_confirmation', 'date_of_birth', 'phone']  # lista de campos obrigatórios
    if not data or not all(field in data for field in required_fields):  # verifica presença de todos os campos obrigatórios
        return jsonify({"error": "Todos os campos são obrigatórios: nome completo, email, senha, confirmação de senha, data de nascimento e telefone."}), 400  # retorna erro 400 se faltar campo

    password = data.get('password')  # obtém a senha do corpo
    password_confirmation = data.get('password_confirmation')  # obtém a confirmação de senha

    if password != password_confirmation:  # compara senha e confirmação
        return jsonify({"error": "As senhas não conferem."}), 400  # retorna erro 400 se divergirem

    new_user, error_code, error_message = user_service.create_user(data)  # delega criação ao serviço

    if new_user:  # verifica se criou com sucesso
        return jsonify({**new_user, "message": "Usuário registrado com sucesso"}), 201  # retorna 201 com dados do usuário
    else:  # trata erros do serviço
        if error_code == "EMAIL_ALREADY_EXISTS":  # e-mail duplicado
            return jsonify({"error": "E-mail já cadastrado"}), 409  # conflito 409
        elif error_code == "PHONE_ALREADY_EXISTS":  # telefone duplicado
            return jsonify({"error": "Telefone já cadastrado"}), 409  # conflito 409
        elif error_code == "CPF_ALREADY_EXISTS":  # CPF duplicado
            return jsonify({"error": "CPF já cadastrado"}), 409  # conflito 409
        elif error_code in ["INVALID_EMAIL", "INVALID_PHONE", "INVALID_CPF", "WEAK_PASSWORD", "INVALID_DATE"]:  # validações
            return jsonify({"error": error_message}), 400  # retorna 400 com mensagem específica
        elif error_code == "DATABASE_ERROR":  # erro interno de banco
            return jsonify({"error": error_message}), 500  # retorna 500
        else:  # fallback para erros inesperados
            return jsonify({"error": "Não foi possível criar o usuário."}), 500  # retorna 500 padrão

@customer_bp.route('/', methods=['GET'])  # define rota GET para listar clientes
@require_role('admin', 'manager')  # restringe a admin/manager
def get_all_customers_route():  # função handler da listagem
    customers = user_service.get_users_by_role('customer')  # busca usuários com papel customer
    return jsonify(customers), 200  # retorna lista e status 200

@customer_bp.route('/<int:user_id>', methods=['GET'])  # define rota GET para buscar cliente por ID
@jwt_required()  # exige autenticação JWT
def get_customer_by_id_route(user_id):  # função handler da busca por ID
    claims = get_jwt()  # obtém claims do token
    if 'admin' not in claims.get('roles', []) and get_jwt_identity() != str(user_id):  # valida acesso do próprio usuário ou admin
        return jsonify({"msg": "Acesso não autorizado"}), 403  # retorna 403 se não autorizado

    user = user_service.get_user_by_id(user_id)  # busca usuário no serviço
    if user and user['role'] == 'customer':  # confirma que é cliente
        return jsonify(user), 200  # retorna dados do cliente
    return jsonify({"msg": "Cliente não encontrado"}), 404  # retorna 404 se não encontrado

@customer_bp.route('/<int:user_id>', methods=['PUT'])  # define rota PUT para atualizar cliente
@jwt_required()  # exige autenticação JWT
def update_customer_route(user_id):  # função handler da atualização
    claims = get_jwt()  # obtém claims do token
    if 'admin' not in claims.get('roles', []) and get_jwt_identity() != str(user_id):  # valida se é o próprio usuário ou admin
        return jsonify({"msg": "Acesso não autorizado"}), 403  # retorna 403 se não autorizado

    data = request.get_json()  # captura JSON do corpo
    if not data:  # verifica se há dados
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400  # retorna 400 se vazio

    success, error_code, message = user_service.update_user(user_id, data)  # delega atualização ao serviço

    if success:  # se atualizou com sucesso
        return jsonify({"msg": "Dados atualizados com sucesso"}), 200  # retorna 200
    else:  # trata erros
        if error_code == "USER_NOT_FOUND":  # usuário não encontrado
            return jsonify({"error": message}), 404  # retorna 404
        elif error_code in ["EMAIL_ALREADY_EXISTS", "PHONE_ALREADY_EXISTS"]:  # conflitos de unicidade
            return jsonify({"error": message}), 409  # retorna 409
        elif error_code in ["INVALID_EMAIL", "INVALID_PHONE", "INVALID_CPF", "NO_VALID_FIELDS"]:  # validações
            return jsonify({"error": message}), 400  # retorna 400
        elif error_code == "DATABASE_ERROR":  # erro de banco
            return jsonify({"error": message}), 500  # retorna 500
        else:  # fallback
            return jsonify({"error": "Falha ao atualizar dados"}), 500  # retorna 500

@customer_bp.route('/<int:user_id>', methods=['DELETE'])  # define rota DELETE para inativar conta do cliente
@jwt_required()  # exige autenticação JWT
def delete_customer_route(user_id):  # função handler da inativação
    claims = get_jwt()  # obtém claims do token
    if 'admin' not in claims.get('roles', []) and get_jwt_identity() != str(user_id):  # valida acesso
        return jsonify({"msg": "Acesso não autorizado"}), 403  # retorna 403 se não autorizado

    if user_service.deactivate_user(user_id):  # chama serviço para inativar
        return jsonify({"msg": "Conta excluída com sucesso"}), 200  # retorna 200 em sucesso
    return jsonify({"error": "Falha ao excluir conta ou cliente não encontrado"}), 404  # retorna 404 em falha

@customer_bp.route('/delete-account', methods=['DELETE'])  # define rota DELETE para o próprio cliente deletar conta
@jwt_required()  # exige autenticação JWT
def delete_my_account_route():  # função handler da exclusão da própria conta
    claims = get_jwt()  # obtém claims do token
    user_id = int(claims.get('sub'))  # extrai ID do usuário logado
    user_roles = claims.get('roles', [])  # extrai papéis do usuário
    if 'customer' not in user_roles:  # verifica se é cliente
        return jsonify({"error": "Apenas clientes podem deletar suas próprias contas"}), 403  # retorna 403 se não for cliente
    if user_service.deactivate_user(user_id):  # inativa o usuário atual
        return jsonify({"msg": "Conta excluída com sucesso"}), 200  # retorna 200 em sucesso
    return jsonify({"error": "Falha ao excluir conta"}), 500  # retorna 500 em falha

@customer_bp.route('/me/verify-password', methods=['POST'])  # define rota POST para verificar senha do cliente autenticado
@jwt_required()  # exige autenticação JWT
def verify_my_password_route():  # função handler da verificação de senha
    data = request.get_json() or {}  # captura corpo JSON ou dicionário vazio
    password = data.get('password')  # extrai senha do corpo
    if not password:  # valida presença da senha
        return jsonify({"error": "O campo 'password' é obrigatório"}), 400  # retorna 400 se ausente
    user_id = int(get_jwt_identity())  # obtém ID do usuário a partir do token
    is_valid = user_service.verify_user_password(user_id, password)  # verifica senha no serviço
    if is_valid:  # se a senha confere
        return jsonify({"msg": "Senha verificada com sucesso"}), 200  # retorna 200
    else:  # caso contrário
        return jsonify({"error": "Senha incorreta"}), 401  # retorna 401

@customer_bp.route('/<int:user_id>/addresses', methods=['POST'])  # define rota POST para criar endereço
@jwt_required()  # exige autenticação JWT
def add_address_route(user_id):  # função handler da criação de endereço
    claims = get_jwt()  # obtém claims do token
    if int(claims.get('sub')) != user_id:  # garante que o endereço pertence ao usuário autenticado
        return jsonify({"msg": "Acesso não autorizado"}), 403  # retorna 403 se não autorizado
    data = request.get_json()  # captura JSON do corpo
    if not data or not all(k in data for k in ['city', 'neighborhood', 'street', 'number']):  # valida campos obrigatórios
        return jsonify({"error": "Campos obrigatórios: city, neighborhood, street, number"}), 400  # retorna 400 se inválido
    new_address = address_service.create_address(user_id, data)  # delega criação ao serviço
    if new_address:  # se criou com sucesso
        return jsonify(new_address), 201  # retorna 201 com endereço criado
    return jsonify({"error": "Não foi possível adicionar o endereço"}), 500  # retorna 500 em falha

@customer_bp.route('/<int:user_id>/addresses', methods=['GET'])  # define rota GET para listar endereços do cliente
@jwt_required()  # exige autenticação JWT
def get_addresses_route(user_id):  # função handler da listagem de endereços
    claims = get_jwt()  # obtém claims do token
    if int(claims.get('sub')) != user_id:  # garante acesso somente ao próprio usuário
        return jsonify({"msg": "Acesso não autorizado"}), 403  # retorna 403
    addresses = address_service.get_addresses_by_user_id(user_id)  # busca endereços no serviço
    return jsonify(addresses), 200  # retorna lista e 200

@customer_bp.route('/addresses/<int:address_id>', methods=['PUT'])  # define rota PUT para atualizar endereço
@jwt_required()  # exige autenticação JWT
def update_address_route(address_id):  # função handler da atualização de endereço
    claims = get_jwt()  # obtém claims do token
    address = address_service.get_address_by_id(address_id)  # busca endereço pelo ID
    if not address or address.get('user_id') != int(claims.get('sub')):  # verifica posse do endereço
        return jsonify({"msg": "Endereço não encontrado ou acesso não autorizado"}), 404  # retorna 404 se não encontrado/não autorizado
    data = request.get_json()  # captura JSON do corpo
    if not data:  # valida corpo não vazio
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400  # retorna 400
    if address_service.update_address(address_id, data):  # delega atualização ao serviço
        return jsonify({"msg": "Endereço atualizado com sucesso"}), 200  # retorna 200 em sucesso
    return jsonify({"error": "Falha ao atualizar endereço"}), 500  # retorna 500 em falha

@customer_bp.route('/addresses/<int:address_id>', methods=['DELETE'])  # define rota DELETE para remover endereço
@jwt_required()  # exige autenticação JWT
def delete_address_route(address_id):  # função handler da remoção de endereço
    claims = get_jwt()  # obtém claims do token
    address = address_service.get_address_by_id(address_id)  # busca endereço pelo ID
    if not address or address.get('user_id') != int(claims.get('sub')):  # valida posse do endereço
        return jsonify({"msg": "Endereço não encontrado ou acesso não autorizado"}), 404  # retorna 404
    if address_service.delete_address(address_id):  # delega remoção ao serviço
        return jsonify({"msg": "Endereço deletado com sucesso"}), 200  # retorna 200 em sucesso
    return jsonify({"error": "Falha ao deletar endereço"}), 500  # retorna 500 em falha

@customer_bp.route('/<int:user_id>/loyalty/balance', methods=['GET'])  # define rota GET para saldo de pontos de fidelidade
@require_role('customer')  # restringe a clientes
def get_loyalty_balance_route(user_id):  # função handler do saldo de fidelidade
    claims = get_jwt()  # obtém claims do token
    if int(claims.get('sub')) != user_id:  # garante acesso ao próprio saldo
        return jsonify({"msg": "Acesso não autorizado"}), 403  # retorna 403
    balance = loyalty_service.get_loyalty_balance(user_id)  # busca saldo no serviço
    if balance is not None:  # verifica se obteve saldo
        return jsonify(balance), 200  # retorna 200 com saldo
    return jsonify({"error": "Não foi possível buscar o saldo"}), 500  # retorna 500 em falha

@customer_bp.route('/<int:user_id>/loyalty/history', methods=['GET'])  # define rota GET para histórico de fidelidade
@require_role('customer')  # restringe a clientes
def get_loyalty_history_route(user_id):  # função handler do histórico de fidelidade
    claims = get_jwt()  # obtém claims do token
    if 'admin' not in claims.get('roles', []) and int(claims.get('sub')) != user_id:  # valida acesso do próprio usuário ou admin
        return jsonify({"msg": "Acesso não autorizado"}), 403  # retorna 403
    history = loyalty_service.get_loyalty_history(user_id)  # busca histórico no serviço
    return jsonify(history), 200  # retorna 200 com histórico

@customer_bp.route('/<int:user_id>/reactivate', methods:['POST'])  # define rota POST para reativar cliente (admin)
@jwt_required()  # exige autenticação JWT
def reactivate_customer_route(user_id):  # função handler da reativação de cliente
    claims = get_jwt()  # obtém claims do token
    if 'admin' not in claims.get('roles', []):  # garante que apenas admin reative
        return jsonify({"msg": "Acesso não autorizado. Apenas administradores podem reativar contas."}), 403  # retorna 403
    if user_service.reactivate_user(user_id):  # reativa via serviço
        return jsonify({"msg": "Cliente reativado com sucesso"}), 200  # retorna 200 em sucesso
    else:  # falha na reativação
        return jsonify({"error": "Falha ao reativar cliente ou cliente não encontrado"}), 404  # retorna 404