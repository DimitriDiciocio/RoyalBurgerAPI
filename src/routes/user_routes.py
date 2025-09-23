from flask import Blueprint, request, jsonify  # importa utilitários do Flask
from ..services import user_service, auth_service  # importa serviços de usuário e autenticação
from ..services.auth_service import require_role  # importa decorator de autorização por papel
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity  # importa utilitários de JWT
from datetime import datetime, timezone  # importa classes de data/tempo

user_bp = Blueprint('users', __name__)  # cria o blueprint para rotas de usuários

@user_bp.route('/login', methods=['POST'])  # define rota POST de login
def login_route():  # handler de login
    data = request.get_json()  # obtém JSON da requisição
    email = data.get('email')  # extrai e-mail do corpo
    password = data.get('password')  # extrai senha do corpo
    if not email or not password:  # valida presença de e-mail e senha
        return jsonify({"error": "E-mail e senha são obrigatórios"}), 400  # retorna 400 se inválido
    token, error_code, error_message = auth_service.authenticate(email, password)  # autentica via serviço
    if token:  # se autenticado com sucesso
        user = user_service.get_user_by_email(email)  # carrega dados do usuário
        full_name = user.get('full_name', 'Usuário') if user else 'Usuário'  # obtém nome para saudação
        return jsonify({"access_token": token, "message": f"Bem-vindo, {full_name}", "user": user}), 200  # retorna token e usuário
    if error_code == "USER_NOT_FOUND":  # trata usuário não encontrado
        return jsonify({"error": "E-mail ou senha incorretos"}), 404  # retorna 404
    elif error_code == "ACCOUNT_INACTIVE":  # conta inativa
        return jsonify({"error": error_message}), 403  # retorna 403
    elif error_code == "INVALID_PASSWORD":  # senha incorreta
        return jsonify({"error": "E-mail ou senha incorretos"}), 401  # retorna 401
    elif error_code == "DATABASE_ERROR":  # erro interno
        return jsonify({"error": error_message}), 500  # retorna 500
    else:  # fallback
        return jsonify({"error": "Erro interno do servidor"}), 500  # retorna 500

@user_bp.route('/request-password-reset', methods=['POST'])  # rota para solicitar recuperação de senha
def request_password_reset_route():  # handler do pedido de recuperação
    data = request.get_json()  # lê JSON
    email = data.get('email')  # extrai e-mail
    if not email:  # valida e-mail presente
        return jsonify({"error": "O campo 'email' é obrigatório"}), 400  # retorna 400
    user_service.initiate_password_reset(email)  # inicia processo de recuperação
    return jsonify({"msg": "Se um usuário com este e-mail existir, um link de recuperação foi enviado."}), 200  # resposta 200

@user_bp.route('/reset-password', methods=['POST'])  # rota para redefinir senha
def reset_password_route():  # handler da redefinição de senha
    data = request.get_json()  # obtém JSON
    token = data.get('token')  # extrai token
    new_password = data.get('new_password')  # extrai nova senha
    if not token or not new_password:  # valida campos
        return jsonify({"error": "Token e nova senha são obrigatórios"}), 400  # retorna 400
    success, message = user_service.finalize_password_reset(token, new_password)  # finaliza recuperação
    if success:  # se deu certo
        return jsonify({"msg": message}), 200  # retorna 200
    else:  # caso contrário
        return jsonify({"error": message}), 400  # retorna 400 com mensagem

@user_bp.route('/logout', methods=['POST'])  # rota de logout
@jwt_required()  # exige autenticação JWT
def logout_route():  # handler de logout
    jti = get_jwt()['jti']  # lê identificador único do token
    exp_timestamp = get_jwt()['exp']  # lê timestamp de expiração
    expires_at = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)  # converte expiração para datetime com timezone
    auth_service.add_token_to_blacklist(jti, expires_at)  # adiciona token à blacklist
    return jsonify({"msg": "Logout realizado com sucesso"}), 200  # retorna 200

@user_bp.route('/profile', methods=['GET'])  # rota para obter perfil do usuário logado
@jwt_required()  # exige autenticação JWT
def get_my_profile_route():  # handler do perfil
    claims = get_jwt()  # obtém claims do token
    user_id = int(claims.get('sub'))  # extrai ID do usuário
    user = user_service.get_user_by_id(user_id)  # busca usuário no serviço
    if user:  # se encontrado
        return jsonify(user), 200  # retorna dados do usuário
    return jsonify({"error": "Usuário não encontrado"}), 404  # retorna 404

@user_bp.route('/', methods=['GET'])  # rota para listar funcionários
@require_role('admin')  # restringe a administradores
def get_all_users_route():  # handler da listagem de funcionários
    users = user_service.get_users_by_role(['admin', 'manager', 'attendant'])  # busca por papéis específicos
    return jsonify(users), 200  # retorna lista com 200

@user_bp.route('/', methods=['POST'])  # rota para criar funcionário
@require_role('admin')  # restringe a administradores
def create_user_route():  # handler da criação de funcionário
    data = request.get_json()  # lê JSON do corpo
    if not all(k in data for k in ['full_name', 'email', 'password', 'role']):  # valida campos obrigatórios
        return jsonify({"error": "full_name, email, password e role são obrigatórios"}), 400  # retorna 400
    if data['role'] not in ['admin', 'manager', 'attendant']:  # valida papel permitido
        return jsonify({"error": "Cargo inválido."}), 400  # retorna 400
    new_user, error_code, error_message = user_service.create_user(data)  # cria usuário via serviço
    if new_user:  # se criou com sucesso
        return jsonify({**new_user, "message": "Usuário registrado com sucesso"}), 201  # retorna 201
    else:  # trata erros de criação
        if error_code == "EMAIL_ALREADY_EXISTS":  # e-mail duplicado
            return jsonify({"error": "E-mail já cadastrado"}), 409  # 409 conflito
        elif error_code == "PHONE_ALREADY_EXISTS":  # telefone duplicado
            return jsonify({"error": "Telefone já cadastrado"}), 409  # 409 conflito
        elif error_code == "CPF_ALREADY_EXISTS":  # CPF duplicado
            return jsonify({"error": "CPF já cadastrado"}), 409  # 409 conflito
        elif error_code in ["INVALID_EMAIL", "INVALID_PHONE", "INVALID_CPF", "WEAK_PASSWORD"]:  # validações
            return jsonify({"error": error_message}), 400  # 400 validação
        elif error_code == "DATABASE_ERROR":  # erro interno
            return jsonify({"error": error_message}), 500  # 500
        else:  # fallback
            return jsonify({"error": "Não foi possível criar o usuário."}), 500  # 500

@user_bp.route('/<int:user_id>', methods=['GET'])  # rota para buscar funcionário por ID
@require_role('admin')  # restringe a administradores
def get_user_by_id_route(user_id):  # handler da busca por ID
    user = user_service.get_user_by_id(user_id)  # busca no serviço
    if user and user['role'] != 'customer':  # garante que não é cliente
        return jsonify(user), 200  # retorna 200
    return jsonify({"error": "Funcionário não encontrado"}), 404  # retorna 404

@user_bp.route('/<int:user_id>', methods=['PUT'])  # rota para atualizar funcionário
@require_role('admin')  # restringe a administradores
def update_user_route(user_id):  # handler da atualização
    data = request.get_json()  # lê JSON do corpo
    if not data:  # valida corpo presente
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400  # 400
    success, error_code, message = user_service.update_user(user_id, data)  # atualiza via serviço
    if success:  # se atualizou
        return jsonify({"msg": "Dados atualizados com sucesso"}), 200  # 200
    if error_code == "USER_NOT_FOUND":  # não encontrado
        return jsonify({"error": message}), 404  # 404
    elif error_code in ["EMAIL_ALREADY_EXISTS", "PHONE_ALREADY_EXISTS"]:  # conflito
        return jsonify({"error": message}), 409  # 409
    elif error_code in ["INVALID_EMAIL", "INVALID_PHONE", "INVALID_CPF", "NO_VALID_FIELDS"]:  # validação
        return jsonify({"error": message}), 400  # 400
    elif error_code == "DATABASE_ERROR":  # erro interno
        return jsonify({"error": message}), 500  # 500
    else:  # fallback
        return jsonify({"error": "Falha ao atualizar funcionário"}), 500  # 500

@user_bp.route('/<int:user_id>', methods=['DELETE'])  # rota para inativar funcionário
@require_role('admin')  # restringe a administradores
def delete_user_route(user_id):  # handler da inativação
    if user_service.deactivate_user(user_id):  # tenta inativar via serviço
        return jsonify({"msg": "Funcionário inativado com sucesso"}), 200  # 200
    return jsonify({"error": "Falha ao inativar ou funcionário não encontrado"}), 404  # 404

@user_bp.route('/<int:user_id>/metrics', methods=['GET'])  # rota para métricas de funcionário
@require_role('admin', 'manager')  # restringe a admin/manager
def get_user_metrics_route(user_id):  # handler das métricas
    metrics = user_service.get_user_metrics(user_id)  # busca métricas via serviço
    if metrics is None:  # se não houver métricas
        return jsonify({"error": "Usuário não encontrado ou não é um funcionário"}), 404  # 404
    return jsonify(metrics), 200  # retorna 200 com métricas