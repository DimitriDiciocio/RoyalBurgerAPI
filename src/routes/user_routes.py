# src/routes/user_routes.py

from flask import Blueprint, request, jsonify
from ..services import user_service, auth_service  # Importamos os dois serviços
from ..services.auth_service import require_role
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from datetime import datetime, timezone

user_bp = Blueprint('users', __name__)


# --- ROTAS DE AUTENTICAÇÃO PÚBLICAS ---

@user_bp.route('/login', methods=['POST'])
def login_route():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "E-mail e senha são obrigatórios"}), 400

    token, error_code, error_message = auth_service.authenticate(email, password)

    if token:
        # Busca o nome do usuário diretamente do banco para a mensagem de boas-vindas
        user = user_service.get_user_by_email(email)
        full_name = user.get('full_name', 'Usuário') if user else 'Usuário'
        return jsonify({
            "access_token": token,
            "message": f"Bem-vindo, {full_name}"
        }), 200
    
    # Retorna códigos de status HTTP específicos baseados no erro
    if error_code == "USER_NOT_FOUND":
        return jsonify({"error": "E-mail ou senha incorretos"}), 404
    elif error_code == "ACCOUNT_INACTIVE":
        return jsonify({"error": error_message}), 403
    elif error_code == "INVALID_PASSWORD":
        return jsonify({"error": "E-mail ou senha incorretos"}), 401
    elif error_code == "DATABASE_ERROR":
        return jsonify({"error": error_message}), 500
    else:
        return jsonify({"error": "Erro interno do servidor"}), 500


@user_bp.route('/request-password-reset', methods=['POST'])
def request_password_reset_route():
    data = request.get_json()
    email = data.get('email')
    if not email:
        return jsonify({"error": "O campo 'email' é obrigatório"}), 400
    user_service.initiate_password_reset(email)
    return jsonify({"msg": "Se um usuário com este e-mail existir, um link de recuperação foi enviado."}), 200


@user_bp.route('/reset-password', methods=['POST'])
def reset_password_route():
    data = request.get_json()
    token = data.get('token')
    new_password = data.get('new_password')

    if not token or not new_password:
        return jsonify({"error": "Token e nova senha são obrigatórios"}), 400

    success, message = user_service.finalize_password_reset(token, new_password)

    if success:
        return jsonify({"msg": message}), 200
    else:
        return jsonify({"error": message}), 400


@user_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout_route():
    """
    Faz logout do usuário adicionando o JTI do token atual à blacklist.
    """
    # Pega o 'jti' (ID único) do token que está sendo usado nesta requisição
    jti = get_jwt()['jti']
    
    # Pega a data de expiração do token para guardar no banco
    exp_timestamp = get_jwt()['exp']
    expires_at = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
    
    # Chama o serviço para adicionar o token à blacklist
    auth_service.add_token_to_blacklist(jti, expires_at)
    
    return jsonify({"msg": "Logout realizado com sucesso"}), 200


# --- ROTAS DE GERENCIAMENTO DE FUNCIONÁRIOS (PROTEGIDAS) ---

@user_bp.route('/profile', methods=['GET'])
@jwt_required()
def get_my_profile_route():
    """Retorna o perfil do funcionário logado."""
    claims = get_jwt()
    user_id = int(claims.get('sub'))
    user = user_service.get_user_by_id(user_id)
    if user:
        return jsonify(user), 200
    return jsonify({"error": "Usuário não encontrado"}), 404


@user_bp.route('/', methods=['GET'])
@require_role('admin')
def get_all_users_route():
    """(Admin) Lista todos os funcionários."""
    # Passamos os papéis que queremos buscar
    users = user_service.get_users_by_role(['admin', 'manager', 'attendant'])
    return jsonify(users), 200


@user_bp.route('/', methods=['POST'])
@require_role('admin')
def create_user_route():
    """(Admin) Cria um novo funcionário."""
    data = request.get_json()
    if not all(k in data for k in ['full_name', 'email', 'password', 'role']):
        return jsonify({"error": "full_name, email, password e role são obrigatórios"}), 400

    # Garantir que o cargo seja válido
    if data['role'] not in ['admin', 'manager', 'attendant']:
        return jsonify({"error": "Cargo inválido."}), 400

    new_user, error_code, error_message = user_service.create_user(data)

    if new_user:
        return jsonify({
            **new_user,
            "message": "Usuário registrado com sucesso"
        }), 201
    else:
        # Retorna códigos de status HTTP específicos baseados no erro
        if error_code == "EMAIL_ALREADY_EXISTS":
            return jsonify({"error": "E-mail já cadastrado"}), 409
        elif error_code == "PHONE_ALREADY_EXISTS":
            return jsonify({"error": "Telefone já cadastrado"}), 409
        elif error_code == "CPF_ALREADY_EXISTS":
            return jsonify({"error": "CPF já cadastrado"}), 409
        elif error_code in ["INVALID_EMAIL", "INVALID_PHONE", "INVALID_CPF", "WEAK_PASSWORD"]:
            return jsonify({"error": error_message}), 400
        elif error_code == "DATABASE_ERROR":
            return jsonify({"error": error_message}), 500
        else:
            return jsonify({"error": "Não foi possível criar o usuário."}), 500


@user_bp.route('/<int:user_id>', methods=['GET'])
@require_role('admin')
def get_user_by_id_route(user_id):
    """(Admin) Busca um funcionário específico."""
    user = user_service.get_user_by_id(user_id)
    if user and user['role'] != 'customer':
        return jsonify(user), 200
    return jsonify({"error": "Funcionário não encontrado"}), 404


@user_bp.route('/<int:user_id>', methods=['PUT'])
@require_role('admin')
def update_user_route(user_id):
    """(Admin) Atualiza um funcionário."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400

    success, error_code, message = user_service.update_user(user_id, data)
    
    if success:
        return jsonify({"msg": "Dados atualizados com sucesso"}), 200
    
    # Retorna códigos de status HTTP específicos baseados no erro
    if error_code == "USER_NOT_FOUND":
        return jsonify({"error": message}), 404
    elif error_code in ["EMAIL_ALREADY_EXISTS", "PHONE_ALREADY_EXISTS"]:
        return jsonify({"error": message}), 409
    elif error_code in ["INVALID_EMAIL", "INVALID_PHONE", "INVALID_CPF", "NO_VALID_FIELDS"]:
        return jsonify({"error": message}), 400
    elif error_code == "DATABASE_ERROR":
        return jsonify({"error": message}), 500
    else:
        return jsonify({"error": "Falha ao atualizar funcionário"}), 500


@user_bp.route('/<int:user_id>', methods=['DELETE'])
@require_role('admin')
def delete_user_route(user_id):
    """(Admin) Inativa um funcionário."""
    if user_service.deactivate_user(user_id):
        return jsonify({"msg": "Funcionário inativado com sucesso"}), 200
    return jsonify({"error": "Falha ao inativar ou funcionário não encontrado"}), 404