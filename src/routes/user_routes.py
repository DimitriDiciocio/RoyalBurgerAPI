# src/routes/user_routes.py

from flask import Blueprint, request, jsonify
from ..services import user_service, auth_service  # Importamos os dois serviços
from ..services.auth_service import require_role
from flask_jwt_extended import jwt_required, get_jwt

user_bp = Blueprint('users', __name__)


# --- ROTAS DE AUTENTICAÇÃO PÚBLICAS ---

@user_bp.route('/login', methods=['POST'])
def login_route():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"msg": "E-mail e senha são obrigatórios"}), 400

    token = auth_service.authenticate(email, password)

    if token:
        return jsonify(access_token=token), 200
    return jsonify({"msg": "Credenciais inválidas"}), 401


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


# --- ROTAS DE GERENCIAMENTO DE FUNCIONÁRIOS (PROTEGIDAS) ---

@user_bp.route('/profile', methods=['GET'])
@jwt_required()
def get_my_profile_route():
    """Retorna o perfil do funcionário logado."""
    claims = get_jwt()
    user_id = claims.get('id')
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

    new_user, error_message = user_service.create_user(data)

    if new_user:
        return jsonify(new_user), 201
    else:
        # Usa a mensagem de erro específica do serviço (ex: senha fraca)
        return jsonify({"error": error_message or "Não foi possível criar o usuário."}), 409


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

    if user_service.update_user(user_id, data):
        return jsonify({"msg": "Funcionário atualizado com sucesso"}), 200
    return jsonify({"error": "Falha ao atualizar ou funcionário não encontrado"}), 404


@user_bp.route('/<int:user_id>', methods=['DELETE'])
@require_role('admin')
def delete_user_route(user_id):
    """(Admin) Inativa um funcionário."""
    if user_service.deactivate_user(user_id):
        return jsonify({"msg": "Funcionário inativado com sucesso"}), 200
    return jsonify({"error": "Falha ao inativar ou funcionário não encontrado"}), 404