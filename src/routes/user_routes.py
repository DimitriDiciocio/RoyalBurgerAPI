from flask import Blueprint, request, jsonify
from ..services import user_service, auth_service, email_verification_service, two_factor_service
from ..services.auth_service import require_role
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from datetime import datetime, timezone

user_bp = Blueprint('users', __name__)


@user_bp.route('/login', methods=['POST'])
def login_route():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    # SMS removido: sempre e-mail
    if not email or not password:
        return jsonify({"error": "E-mail e senha são obrigatórios"}), 400
    
    result, error_code, error_message = auth_service.authenticate(email, password)
    
    # Se retornou um dicionário com requires_2fa, significa que 2FA está habilitado
    if isinstance(result, dict) and result.get('requires_2fa'):
        return jsonify({
            "requires_2fa": True, 
            "user_id": result['user_id'], 
            "message": error_message
        }), 200
    
    # Login normal (sem 2FA ou 2FA desabilitado)
    if result and isinstance(result, str):  # result é o token
        user = user_service.get_user_by_email(email)
        full_name = user.get('full_name', 'Usuário') if user else 'Usuário'
        return jsonify({"access_token": result, "message": f"Bem-vindo, {full_name}", "user": user}), 200
    
    # Tratamento de erros
    if error_code == "USER_NOT_FOUND":
        return jsonify({"error": "E-mail ou senha incorretos"}), 404
    elif error_code == "ACCOUNT_INACTIVE":
        return jsonify({"error": error_message}), 403
    elif error_code == "EMAIL_NOT_VERIFIED":
        return jsonify({"requires_email_verification": True, "error": error_message}), 403
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
    # SMS removido: sempre e-mail
    if not email:
        return jsonify({"error": "O campo 'email' é obrigatório"}), 400
    user_service.initiate_password_reset(email)
    return jsonify({"msg": "Se um usuário com este e-mail existir, um e-mail de recuperação foi enviado."}), 200


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
    jti = get_jwt()['jti']
    exp_timestamp = get_jwt()['exp']
    expires_at = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
    auth_service.add_token_to_blacklist(jti, expires_at)
    return jsonify({"msg": "Logout realizado com sucesso"}), 200


@user_bp.route('/profile', methods=['GET'])
@jwt_required()
def get_my_profile_route():
    claims = get_jwt()
    user_id = int(claims.get('sub'))
    user = user_service.get_user_by_id(user_id)
    if user:
        return jsonify(user), 200
    return jsonify({"error": "Usuário não encontrado"}), 404


@user_bp.route('/', methods=['GET'])
@require_role('admin')
def get_all_users_route():
    users = user_service.get_users_by_role(['admin', 'manager', 'attendant'])
    return jsonify(users), 200


@user_bp.route('/', methods=['POST'])
@require_role('admin')
def create_user_route():
    data = request.get_json()
    if not all(k in data for k in ['full_name', 'email', 'password', 'role']):
        return jsonify({"error": "full_name, email, password e role são obrigatórios"}), 400
    if data['role'] not in ['admin', 'manager', 'attendant']:
        return jsonify({"error": "Cargo inválido."}), 400
    new_user, error_code, error_message = user_service.create_user(data)
    if new_user:
        return jsonify({**new_user, "message": "Usuário registrado com sucesso"}), 201
    else:
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
    user = user_service.get_user_by_id(user_id)
    if user and user['role'] != 'customer':
        return jsonify(user), 200
    return jsonify({"error": "Funcionário não encontrado"}), 404


@user_bp.route('/<int:user_id>', methods=['PUT'])
@require_role('admin')
def update_user_route(user_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400
    success, error_code, message = user_service.update_user(user_id, data)
    if success:
        return jsonify({"msg": "Dados atualizados com sucesso"}), 200
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
    if user_service.deactivate_user(user_id):
        return jsonify({"msg": "Funcionário inativado com sucesso"}), 200
    return jsonify({"error": "Falha ao inativar ou funcionário não encontrado"}), 404


@user_bp.route('/<int:user_id>/metrics', methods=['GET'])
@require_role('admin', 'manager')
def get_user_metrics_route(user_id):
    metrics = user_service.get_user_metrics(user_id)
    if metrics is None:
        return jsonify({"error": "Usuário não encontrado ou não é um funcionário"}), 404
    return jsonify(metrics), 200


@user_bp.route('/request-email-verification', methods=['POST'])
def request_email_verification_route():
    data = request.get_json()
    email = data.get('email')

    if not email:
        return jsonify({"error": "O campo 'email' é obrigatório"}), 400

    success, error_code, message = email_verification_service.create_email_verification(email)

    if success:
        return jsonify({"msg": "Código de verificação enviado por e-mail"}), 200
    else:
        if error_code == "USER_NOT_FOUND":
            return jsonify({"error": "Usuário não encontrado"}), 404
        elif error_code == "EMAIL_ALREADY_VERIFIED":
            return jsonify({"error": "Este email já foi verificado"}), 400
        
        elif error_code == "DATABASE_ERROR":
            return jsonify({"error": "Erro interno do servidor"}), 500
        else:
            return jsonify({"error": message}), 400


@user_bp.route('/verify-email', methods=['POST'])
def verify_email_route():
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')

    if not email or not code:
        return jsonify({"error": "Os campos 'email' e 'code' são obrigatórios"}), 400

    if len(code) != 6 or not code.isdigit():
        return jsonify({"error": "Código deve ter exatamente 6 dígitos"}), 400

    success, error_code, message = email_verification_service.verify_email_code(email, code)

    if success:
        return jsonify({"msg": "Email verificado com sucesso"}), 200
    else:
        if error_code == "NO_VERIFICATION_FOUND":
            return jsonify({"error": "Nenhum código de verificação encontrado para este email"}), 404
        elif error_code == "CODE_EXPIRED":
            return jsonify({"error": "Código de verificação expirado. Solicite um novo código"}), 400
        elif error_code == "INVALID_CODE":
            return jsonify({"error": "Código de verificação inválido"}), 400
        elif error_code == "DATABASE_ERROR":
            return jsonify({"error": "Erro interno do servidor"}), 500
        else:
            return jsonify({"error": message}), 400


@user_bp.route('/resend-verification-code', methods=['POST'])
def resend_verification_code_route():
    data = request.get_json()
    email = data.get('email')

    if not email:
        return jsonify({"error": "O campo 'email' é obrigatório"}), 400

    success, error_code, message = email_verification_service.resend_verification_code(email)

    if success:
        return jsonify({"msg": "Novo código de verificação enviado por e-mail"}), 200
    else:
        if error_code == "USER_NOT_FOUND":
            return jsonify({"error": "Usuário não encontrado"}), 404
        elif error_code == "EMAIL_ALREADY_VERIFIED":
            return jsonify({"error": "Este email já foi verificado"}), 400
        
        elif error_code == "DATABASE_ERROR":
            return jsonify({"error": "Erro interno do servidor"}), 500
        else:
            return jsonify({"error": message}), 400


@user_bp.route('/verify-password', methods=['POST'])
@jwt_required()
def verify_password_route():
    data = request.get_json() or {}
    password = data.get('password')
    if not password:
        return jsonify({"error": "O campo 'password' é obrigatório"}), 400
    user_id = int(get_jwt_identity())
    is_valid = user_service.verify_user_password(user_id, password)
    if is_valid:
        return jsonify({"msg": "Senha verificada com sucesso"}), 200
    else:
        return jsonify({"error": "Senha incorreta"}), 401


@user_bp.route('/change-password', methods=['PUT'])
@jwt_required()
def change_password_route():
    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')

    if not current_password or not new_password:
        return jsonify({"error": "Senha atual e nova senha são obrigatórias"}), 400

    claims = get_jwt()
    user_id = int(claims.get('sub'))

    success, error_code, message = user_service.change_user_password(user_id, current_password, new_password)

    if success:
        return jsonify({"msg": message}), 200
    else:
        if error_code == "MISSING_PASSWORDS":
            return jsonify({"error": message}), 400
        elif error_code == "SAME_PASSWORD":
            return jsonify({"error": message}), 400
        elif error_code == "WEAK_PASSWORD":
            return jsonify({"error": message}), 400
        elif error_code == "INVALID_CURRENT_PASSWORD":
            return jsonify({"error": message}), 401
        elif error_code == "USER_NOT_FOUND":
            return jsonify({"error": message}), 404
        elif error_code == "DATABASE_ERROR":
            return jsonify({"error": message}), 500
        else:
            return jsonify({"error": "Erro interno do servidor"}), 500


@user_bp.route('/verify-2fa', methods=['POST'])
def verify_2fa_route():
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        code = data.get('code')
        
        if not user_id or not code:
            return jsonify({"error": "user_id e code são obrigatórios"}), 400
        
        token, error_code, message = auth_service.verify_2fa_and_login(user_id, code)
        
        if error_code:
            if error_code == "NO_VERIFICATION_FOUND":
                return jsonify({"error": "Nenhum código de verificação encontrado"}), 404
            elif error_code == "CODE_ALREADY_USED":
                return jsonify({"error": "Código já foi utilizado"}), 400
            elif error_code == "CODE_EXPIRED":
                return jsonify({"error": "Código de verificação expirado"}), 400
            elif error_code == "INVALID_CODE":
                return jsonify({"error": "Código de verificação inválido"}), 400
            
            elif error_code == "DATABASE_ERROR":
                return jsonify({"error": "Erro interno do servidor"}), 500
            else:
                return jsonify({"error": message}), 400
        
        # Busca dados do usuário para retornar na resposta
        user = user_service.get_user_by_id(user_id)
        full_name = user.get('full_name', 'Usuário') if user else 'Usuário'
        
        return jsonify({
            "access_token": token, 
            "message": f"Bem-vindo, {full_name}",
            "user": user
        }), 200
        
    except Exception as e:
        print(f"Erro na verificação 2FA: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500


@user_bp.route('/toggle-2fa', methods=['POST'])
@jwt_required()
def toggle_2fa_route():
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        enable = data.get('enable', False)
        # SMS removido

        if enable:
            # Passo 1: enviar código pelo canal escolhido
            success, error_code, message = two_factor_service.create_2fa_verification(user_id, None)
            if not success:
                return jsonify({"error": message}), 400
            return jsonify({"message": message, "requires_confirmation": True}), 200
        else:
            # Desabilitar diretamente
            success, error_code, message = two_factor_service.toggle_2fa(user_id, False)
            if not success:
                return jsonify({"error": message}), 400
            return jsonify({"message": message}), 200
    except Exception as e:
        print(f"Erro ao alterar 2FA: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500

@user_bp.route('/enable-2fa-confirm', methods=['POST'])
@jwt_required()
def enable_2fa_confirm_route():
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}
        code = data.get('code')
        if not code:
            return jsonify({"error": "O campo 'code' é obrigatório"}), 400
        success, error_code, message = two_factor_service.enable_2fa_confirm(user_id, code)
        if not success:
            return jsonify({"error": message}), 400
        return jsonify({"message": message}), 200
    except Exception as e:
        print(f"Erro ao confirmar 2FA: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500


@user_bp.route('/2fa-status', methods=['GET'])
@jwt_required()
def get_2fa_status_route():
    try:
        user_id = get_jwt_identity()
        is_enabled = two_factor_service.is_2fa_enabled(user_id)
        
        return jsonify({"two_factor_enabled": is_enabled}), 200
        
    except Exception as e:
        print(f"Erro ao verificar status 2FA: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500
