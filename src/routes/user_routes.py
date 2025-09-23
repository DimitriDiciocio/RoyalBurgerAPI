from flask import Blueprint, request, jsonify  # importa funções e classes do Flask
from ..services import user_service, auth_service  # importa serviços de usuário e autenticação
from ..services.auth_service import require_role  # importa decorator para restrição por papel
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity  # importa utilitários de JWT
from datetime import datetime, timezone  # importa classes de data e tempo

user_bp = Blueprint('users', __name__)  # cria o blueprint de rotas de usuários

@user_bp.route('/login', methods=['POST'])  # define rota POST para login
def login_route():  # função handler do login
    data = request.get_json()  # captura JSON da requisição
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

@user_bp.route('/request-password-reset', methods=['POST'])  # define rota POST para solicitar recuperação de senha
def request_password_reset_route():  # função handler da solicitação de recuperação
    data = request.get_json()  # captura JSON da requisição
    email = data.get('email')  # extrai e-mail do corpo
    if not email:  # valida presença do e-mail
        return jsonify({"error": "O campo 'email' é obrigatório"}), 400  # retorna 400 se ausente
    user_service.initiate_password_reset(email)  # inicia processo de recuperação via serviço
    return jsonify({"msg": "Se um usuário com este e-mail existir, um link de recuperação foi enviado."}), 200  # retorna 200

@user_bp.route('/reset-password', methods=['POST'])  # define rota POST para redefinir senha
def reset_password_route():  # função handler da redefinição de senha
    data = request.get_json()  # captura JSON da requisição
    token = data.get('token')  # extrai token do corpo
    new_password = data.get('new_password')  # extrai nova senha do corpo
    if not token or not new_password:  # valida presença dos campos
        return jsonify({"error": "Token e nova senha são obrigatórios"}), 400  # retorna 400 se inválido
    success, message = user_service.finalize_password_reset(token, new_password)  # finaliza recuperação via serviço
    if success:  # se redefinição bem-sucedida
        return jsonify({"msg": message}), 200  # retorna 200 com mensagem
    else:  # caso contrário
        return jsonify({"error": message}), 400  # retorna 400 com mensagem de erro

@user_bp.route('/logout', methods=['POST'])  # define rota POST para logout
@jwt_required()  # exige autenticação JWT
def logout_route():  # função handler do logout
    jti = get_jwt()['jti']  # obtém identificador único do token
    exp_timestamp = get_jwt()['exp']  # obtém timestamp de expiração
    expires_at = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)  # converte expiração para datetime com timezone
    auth_service.add_token_to_blacklist(jti, expires_at)  # adiciona token à blacklist via serviço
    return jsonify({"msg": "Logout realizado com sucesso"}), 200  # retorna 200 com mensagem

@user_bp.route('/profile', methods=['GET'])  # define rota GET para obter perfil do usuário logado
@jwt_required()  # exige autenticação JWT
def get_my_profile_route():  # função handler do perfil
    claims = get_jwt()  # obtém claims do token
    user_id = int(claims.get('sub'))  # extrai ID do usuário
    user = user_service.get_user_by_id(user_id)  # busca usuário no serviço
    if user:  # se usuário encontrado
        return jsonify(user), 200  # retorna dados do usuário
    return jsonify({"error": "Usuário não encontrado"}), 404  # retorna 404 se não encontrado

@user_bp.route('/', methods=['GET'])  # define rota GET para listar funcionários
@require_role('admin')  # restringe a administradores
def get_all_users_route():  # função handler da listagem de funcionários
    users = user_service.get_users_by_role(['admin', 'manager', 'attendant'])  # busca usuários por papéis específicos
    return jsonify(users), 200  # retorna lista com status 200

@user_bp.route('/', methods=['POST'])  # define rota POST para criar funcionário
@require_role('admin')  # restringe a administradores
def create_user_route():  # função handler da criação de funcionário
    data = request.get_json()  # captura JSON da requisição
    if not all(k in data for k in ['full_name', 'email', 'password', 'role']):  # valida campos obrigatórios
        return jsonify({"error": "full_name, email, password e role são obrigatórios"}), 400  # retorna 400 se inválido
    if data['role'] not in ['admin', 'manager', 'attendant']:  # valida papel permitido
        return jsonify({"error": "Cargo inválido."}), 400  # retorna 400 se cargo inválido
    new_user, error_code, error_message = user_service.create_user(data)  # cria usuário via serviço
    if new_user:  # se usuário criado com sucesso
        return jsonify({**new_user, "message": "Usuário registrado com sucesso"}), 201  # retorna 201 com dados
    else:  # trata erros de criação
        if error_code == "EMAIL_ALREADY_EXISTS":  # e-mail duplicado
            return jsonify({"error": "E-mail já cadastrado"}), 409  # retorna 409 conflito
        elif error_code == "PHONE_ALREADY_EXISTS":  # telefone duplicado
            return jsonify({"error": "Telefone já cadastrado"}), 409  # retorna 409 conflito
        elif error_code == "CPF_ALREADY_EXISTS":  # CPF duplicado
            return jsonify({"error": "CPF já cadastrado"}), 409  # retorna 409 conflito
        elif error_code in ["INVALID_EMAIL", "INVALID_PHONE", "INVALID_CPF", "WEAK_PASSWORD"]:  # validações
            return jsonify({"error": error_message}), 400  # retorna 400 validação
        elif error_code == "DATABASE_ERROR":  # erro interno
            return jsonify({"error": error_message}), 500  # retorna 500
        else:  # fallback
            return jsonify({"error": "Não foi possível criar o usuário."}), 500  # retorna 500

@user_bp.route('/<int:user_id>', methods=['GET'])  # define rota GET para buscar funcionário por ID
@require_role('admin')  # restringe a administradores
def get_user_by_id_route(user_id):  # função handler da busca por ID
    user = user_service.get_user_by_id(user_id)  # busca usuário no serviço
    if user and user['role'] != 'customer':  # garante que não é cliente
        return jsonify(user), 200  # retorna dados do funcionário
    return jsonify({"error": "Funcionário não encontrado"}), 404  # retorna 404 se não encontrado

@user_bp.route('/<int:user_id>', methods=['PUT'])  # define rota PUT para atualizar funcionário
@require_role('admin')  # restringe a administradores
def update_user_route(user_id):  # função handler da atualização
    data = request.get_json()  # captura JSON da requisição
    if not data:  # valida presença do corpo
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400  # retorna 400 se vazio
    success, error_code, message = user_service.update_user(user_id, data)  # atualiza via serviço
    if success:  # se atualização bem-sucedida
        return jsonify({"msg": "Dados atualizados com sucesso"}), 200  # retorna 200 com mensagem
    if error_code == "USER_NOT_FOUND":  # usuário não encontrado
        return jsonify({"error": message}), 404  # retorna 404
    elif error_code in ["EMAIL_ALREADY_EXISTS", "PHONE_ALREADY_EXISTS"]:  # conflitos de unicidade
        return jsonify({"error": message}), 409  # retorna 409
    elif error_code in ["INVALID_EMAIL", "INVALID_PHONE", "INVALID_CPF", "NO_VALID_FIELDS"]:  # validações
        return jsonify({"error": message}), 400  # retorna 400
    elif error_code == "DATABASE_ERROR":  # erro interno
        return jsonify({"error": message}), 500  # retorna 500
    else:  # fallback
        return jsonify({"error": "Falha ao atualizar funcionário"}), 500  # retorna 500

@user_bp.route('/<int:user_id>', methods=['DELETE'])  # define rota DELETE para inativar funcionário
@require_role('admin')  # restringe a administradores
def delete_user_route(user_id):  # função handler da inativação
    if user_service.deactivate_user(user_id):  # tenta inativar via serviço
        return jsonify({"msg": "Funcionário inativado com sucesso"}), 200  # retorna 200 em sucesso
    return jsonify({"error": "Falha ao inativar ou funcionário não encontrado"}), 404  # retorna 404 em falha

@user_bp.route('/<int:user_id>/metrics', methods=['GET'])  # define rota GET para métricas de funcionário
@require_role('admin', 'manager')  # restringe a admin/manager
def get_user_metrics_route(user_id):  # função handler das métricas
    metrics = user_service.get_user_metrics(user_id)  # busca métricas via serviço
    if metrics is None:  # se não houver métricas
        return jsonify({"error": "Usuário não encontrado ou não é um funcionário"}), 404  # retorna 404
    return jsonify(metrics), 200  # retorna 200 com métricas