from flask import Blueprint, request, jsonify
from ..services import user_service, auth_service, email_verification_service, two_factor_service, pending_email_service, push_service
from ..services.auth_service import require_role
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from datetime import datetime, timezone
from ..utils.validators import validate_birth_date, convert_br_date_to_iso
# IMPLEMENTAÇÃO: Rate limiting para endpoints de autenticação (Recomendação #2)
from ..middleware.rate_limiter import rate_limit
import logging  # ALTERAÇÃO: Import centralizado para logging estruturado

user_bp = Blueprint('users', __name__)
logger = logging.getLogger(__name__)  # ALTERAÇÃO: Logger centralizado

@user_bp.route('/login', methods=['POST'])
@rate_limit(max_requests=5, window_seconds=60)  # IMPLEMENTAÇÃO: Rate limiting - 5 tentativas por minuto
def login_route():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    guest_cart_id = data.get('guest_cart_id')
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

        # Fusão (V1 + V2-lite): se guest_cart_id fornecido, tenta reivindicar/mesclar
        if guest_cart_id and user and user.get('id'):
            from ..services import cart_service
            try:
                ok, err, msg = cart_service.claim_guest_cart(guest_cart_id, user['id'])
                if not ok:
                    # Não bloqueia o login: apenas anexa aviso
                    return jsonify({
                        "access_token": result,
                        "message": f"Bem-vindo, {full_name}",
                        "user": user,
                        "cart_merge_warning": msg or "Não foi possível mesclar o carrinho"
                    }), 200
            except Exception as e:
                # ALTERAÇÃO: Logging estruturado ao invés de print
                logger.error(f"Erro ao reivindicar carrinho convidado no login: {e}", exc_info=True)
                # Não bloqueia o login: apenas anexa aviso
                return jsonify({
                    "access_token": result,
                    "message": f"Bem-vindo, {full_name}",
                    "user": user,
                    "cart_merge_warning": "Erro interno ao mesclar o carrinho"
                }), 200

        return jsonify({"access_token": result, "message": f"Bem-vindo, {full_name}", "user": user}), 200
    
    # Tratamento de erros
    if error_code == "USER_NOT_FOUND":
        return jsonify({"error": "E-mail ou senha incorretos"}), 404
    elif error_code == "ACCOUNT_INACTIVE":
        return jsonify({"error": error_message}), 403
    elif error_code == "EMAIL_NOT_VERIFIED":
        # Automaticamente cria e envia código de verificação
        success, verify_error_code, verify_message = email_verification_service.create_email_verification(email)
        if success:
            if verify_error_code == "EMAIL_WARNING":
                # Código foi criado mas email falhou
                return jsonify({
                    "requires_email_verification": True, 
                    "error": error_message,
                    "warning": verify_message,
                    "message": "Código de verificação criado. Use a opção 'Reenviar código' se necessário."
                }), 403
            else:
                # Sucesso completo
                return jsonify({
                    "requires_email_verification": True, 
                    "error": error_message,
                    "message": "Código de verificação enviado automaticamente para seu e-mail"
                }), 403
        else:
            # Se falhou completamente, retorna erro mas ainda indica que precisa verificar
            return jsonify({
                "requires_email_verification": True, 
                "error": error_message,
                "warning": "Não foi possível criar o código automaticamente. Use a opção 'Reenviar código'."
            }), 403
    elif error_code == "INVALID_PASSWORD":
        return jsonify({"error": "E-mail ou senha incorretos"}), 401
    elif error_code == "DATABASE_ERROR":
        return jsonify({"error": error_message}), 500
    else:
        return jsonify({"error": "Erro interno do servidor"}), 500


@user_bp.route('/request-password-reset', methods=['POST'])
@rate_limit(max_requests=3, window_seconds=300)  # IMPLEMENTAÇÃO: Rate limiting - 3 tentativas por 5 minutos
def request_password_reset_route():
    data = request.get_json()
    email = data.get('email')
    
    if not email:
        return jsonify({"error": "O campo 'email' é obrigatório"}), 400
    
    # Verifica se o email existe no banco
    success, message = user_service.initiate_password_reset(email)
    if success:
        return jsonify({
            "msg": "Código de recuperação enviado! Verifique sua caixa de entrada e spam.",
            "success": True
        }), 200
    else:
        return jsonify({
            "error": "E-mail não encontrado em nossa base de dados. Verifique se digitou corretamente ou cadastre-se.",
            "error_code": "EMAIL_NOT_FOUND",
            "suggestion": "Se você não tem uma conta, clique em 'Cadastrar' para criar uma nova."
        }), 404


@user_bp.route('/verify-reset-code', methods=['POST'])
@rate_limit(max_requests=5, window_seconds=300)  # IMPLEMENTAÇÃO: Rate limiting - 5 tentativas por 5 minutos
def verify_reset_code_route():
    """Verifica se o código de reset é válido"""
    data = request.get_json()
    email = data.get('email')
    reset_code = data.get('reset_code')
    
    if not email or not reset_code:
        return jsonify({"error": "Email e código de recuperação são obrigatórios"}), 400
    
    # Valida formato do código (6 dígitos)
    if not reset_code.isdigit() or len(reset_code) != 6:
        return jsonify({"error": "Código deve ter exatamente 6 dígitos"}), 400
    
    success, message = user_service.verify_reset_code(email, reset_code)
    if success:
        return jsonify({
            "msg": "Código válido! Você pode prosseguir para redefinir sua senha.",
            "success": True
        }), 200
    else:
        # Mensagens mais amigáveis baseadas no tipo de erro
        if "não encontrado" in message.lower():
            error_msg = "E-mail não encontrado. Verifique se digitou corretamente."
            error_code = "EMAIL_NOT_FOUND"
        elif "inválido" in message.lower():
            error_msg = "Código inválido. Verifique se digitou os 6 dígitos corretamente."
            error_code = "INVALID_CODE"
        elif "já foi utilizado" in message.lower():
            error_msg = "Este código já foi usado. Solicite um novo código de recuperação."
            error_code = "CODE_ALREADY_USED"
        elif "expirado" in message.lower():
            error_msg = "Código expirado. Solicite um novo código de recuperação."
            error_code = "CODE_EXPIRED"
        else:
            error_msg = "Erro ao verificar código. Tente novamente."
            error_code = "VERIFICATION_ERROR"
        
        return jsonify({
            "error": error_msg,
            "error_code": error_code,
            "suggestion": "Se o problema persistir, solicite um novo código."
        }), 400


@user_bp.route('/reset-password', methods=['POST'])
def reset_password_route():
    """Altera a senha usando email e código de reset"""
    data = request.get_json()
    email = data.get('email')
    reset_code = data.get('reset_code')
    new_password = data.get('new_password')
    
    if not email or not reset_code or not new_password:
        return jsonify({"error": "Email, código de recuperação e nova senha são obrigatórios"}), 400
    
    # Valida formato do código (6 dígitos)
    if not reset_code.isdigit() or len(reset_code) != 6:
        return jsonify({"error": "Código deve ter exatamente 6 dígitos"}), 400
    
    success, message = user_service.finalize_password_reset(email, reset_code, new_password)
    if success:
        return jsonify({
            "msg": "Senha redefinida com sucesso! Agora você pode fazer login com sua nova senha.",
            "success": True
        }), 200
    else:
        # Mensagens mais amigáveis baseadas no tipo de erro
        if "não encontrado" in message.lower():
            error_msg = "E-mail não encontrado. Verifique se digitou corretamente."
            error_code = "EMAIL_NOT_FOUND"
        elif "inválido" in message.lower():
            error_msg = "Código inválido. Verifique se digitou os 6 dígitos corretamente."
            error_code = "INVALID_CODE"
        elif "já foi utilizado" in message.lower():
            error_msg = "Este código já foi usado. Solicite um novo código de recuperação."
            error_code = "CODE_ALREADY_USED"
        elif "expirado" in message.lower():
            error_msg = "Código expirado. Solicite um novo código de recuperação."
            error_code = "CODE_EXPIRED"
        elif "senha" in message.lower() and ("fraca" in message.lower() or "forte" in message.lower()):
            error_msg = "A senha deve ter pelo menos 8 caracteres, incluindo letras maiúsculas, minúsculas, números e símbolos."
            error_code = "WEAK_PASSWORD"
        else:
            error_msg = "Erro ao redefinir senha. Tente novamente."
            error_code = "RESET_ERROR"
        
        return jsonify({
            "error": error_msg,
            "error_code": error_code,
            "suggestion": "Se o problema persistir, solicite um novo código de recuperação."
        }), 400


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
    """Retorna o perfil do usuário autenticado"""
    try:
        claims = get_jwt()
        user_id = int(claims.get('sub'))
        user = user_service.get_user_by_id(user_id)
        if user:
            return jsonify(user), 200
        return jsonify({"error": "Usuário não encontrado"}), 404
    except Exception as e:
        # ALTERAÇÃO: Usar logger ao invés de print() em código de produção
        logger.error(f"Erro ao buscar perfil do usuário: {e}", exc_info=True)
        # ALTERAÇÃO: Retornar erro 500 com mensagem genérica para evitar exposição de informações sensíveis
        return jsonify({"error": "Erro interno do servidor ao buscar perfil"}), 500


@user_bp.route('/', methods=['GET'])
@require_role('admin', 'manager')
def get_all_users_route():
    # ALTERAÇÃO: Parâmetros padronizados
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))  # Parâmetro padronizado
    per_page = int(request.args.get('per_page', page_size))  # Parâmetro legado
    limit = int(request.args.get('limit', page_size))  # Parâmetro legado (compatibilidade)
    # Usar page_size se fornecido, senão usar limit/per_page
    final_limit = page_size if request.args.get('page_size') else (limit if request.args.get('limit') else per_page)
    
    # Filtros
    filters = {}
    if request.args.get('name'):
        filters['name'] = request.args.get('name')
    if request.args.get('email'):
        filters['email'] = request.args.get('email')
    if request.args.get('search'):  # Busca geral (padronizado)
        filters['search'] = request.args.get('search')
    if request.args.get('role'):
        role = request.args.get('role')
        # ALTERAÇÃO: Mapear cargos do frontend para roles do backend
        role_map = {
            'atendente': 'attendant',
            'gerente': 'manager',
            'entregador': 'deliverer',
            'delivery': 'deliverer',
            'admin': 'admin',
            'cliente': 'customer'
        }
        # Se role está no mapeamento, usar valor mapeado; senão usar como está
        mapped_role = role_map.get(role.lower(), role)
        
        if mapped_role == 'all_staff':
            filters['role'] = ['admin', 'manager', 'attendant', 'deliverer']
        elif mapped_role == 'all_employees':
            filters['role'] = ['admin', 'manager', 'attendant', 'deliverer']
        else:
            filters['role'] = mapped_role
    
    # ALTERAÇÃO: Suportar status como string (padronizado: "ativo", "inativo") além de boolean (legado)
    status_param = request.args.get('status')
    if status_param is not None:
        if isinstance(status_param, str):
            status_lower = status_param.lower()
            if status_lower == 'ativo':
                filters['status'] = True
            elif status_lower == 'inativo':
                filters['status'] = False
            else:
                # Tentar interpretar como boolean (legado)
                filters['status'] = status_lower == 'true'
        else:
            # Se já é boolean, usar diretamente
            filters['status'] = bool(status_param)
    
    # Ordenação
    sort_by = request.args.get('sort_by', 'full_name')
    sort_order = request.args.get('sort_order', 'asc')
    
    result = user_service.get_users_paginated(page, final_limit, filters, sort_by, sort_order)
    return jsonify(result), 200


@user_bp.route('/', methods=['POST'])
@require_role('admin', 'manager')
def create_user_route():
    data = request.get_json()
    
    # Campos obrigatórios
    required_fields = ['full_name', 'email', 'password', 'role']
    if not all(k in data for k in required_fields):
        return jsonify({"error": "Campos obrigatórios: nome, email, senha e cargo"}), 400
    
    # Validação de cargo
    if data['role'] == 'delivery':
        data['role'] = 'deliverer'
    valid_roles = ['admin', 'manager', 'attendant', 'deliverer', 'customer']
    if data['role'] not in valid_roles:
        return jsonify({"error": "Cargo inválido. Cargos válidos: admin, manager, attendant, deliverer, customer"}), 400
    
    # Validação de data de nascimento se fornecida
    if 'date_of_birth' in data and data['date_of_birth']:
        is_valid_birth_date, birth_date_msg = validate_birth_date(data['date_of_birth'])
        if not is_valid_birth_date:
            return jsonify({"error": birth_date_msg}), 400
        # Converte para formato ISO para o banco de dados
        data['date_of_birth'] = convert_br_date_to_iso(data['date_of_birth'])
    
    # Campos opcionais com valores padrão
    if 'date_of_birth' not in data:
        data['date_of_birth'] = None
    if 'phone' not in data:
        data['phone'] = None
    if 'cpf' not in data:
        data['cpf'] = None
    
    new_user, error_code, error_message = user_service.create_user(data)
    if new_user:
        return jsonify({**new_user, "message": "Usuário registrado com sucesso"}), 201
    else:
        if error_code == "EMAIL_ALREADY_EXISTS":
            return jsonify({"error": "E-mail já cadastrado"}), 409
        elif error_code == "CPF_ALREADY_EXISTS":
            return jsonify({"error": "CPF já cadastrado"}), 409
        elif error_code in ["INVALID_EMAIL", "INVALID_PHONE", "INVALID_CPF", "WEAK_PASSWORD", "INVALID_DATE"]:
            return jsonify({"error": error_message}), 400
        elif error_code == "DATABASE_ERROR":
            return jsonify({"error": error_message}), 500
        else:
            return jsonify({"error": "Não foi possível criar o usuário."}), 500


@user_bp.route('/<int:user_id>/metrics', methods=['GET'])
@require_role('admin', 'manager')
def get_user_metrics_route(user_id):
    """Retorna métricas de performance de um funcionário específico."""
    metrics = user_service.get_user_metrics(user_id)
    if metrics is None:
        return jsonify({"error": "Usuário não encontrado ou não é um funcionário"}), 404
    return jsonify(metrics), 200


@user_bp.route('/<int:user_id>/status', methods=['PATCH'])
@require_role('admin', 'manager')
def update_user_status_route(user_id):
    """Ativa/desativa um usuário"""
    data = request.get_json()
    if not data or 'is_active' not in data:
        return jsonify({"error": "Campo 'is_active' é obrigatório"}), 400
    
    # Verifica se está tentando desativar o último admin ativo
    if data['is_active'] is False:
        if user_service.is_last_active_admin(user_id):
            return jsonify({"error": "Não é possível desativar o último administrador ativo do sistema"}), 409
    
    success, error_code, message = user_service.update_user_status(user_id, data['is_active'])
    if success:
        status_text = "ativado" if data['is_active'] else "desativado"
        return jsonify({"msg": f"Usuário {status_text} com sucesso"}), 200
    else:
        if error_code == "USER_NOT_FOUND":
            return jsonify({"error": "Usuário não encontrado"}), 404
        elif error_code == "DATABASE_ERROR":
            return jsonify({"error": "Erro interno do servidor"}), 500
        else:
            return jsonify({"error": message}), 400


@user_bp.route('/<int:user_id>/role', methods=['PATCH'])
@require_role('admin', 'manager')
def update_user_role_route(user_id):
    """Atualiza o cargo/role de um usuário"""
    data = request.get_json()
    if not data or 'role' not in data:
        return jsonify({"error": "Campo 'role' é obrigatório"}), 400
    
    if data['role'] == 'delivery':
        data['role'] = 'deliverer'
    valid_roles = ['admin', 'manager', 'attendant', 'deliverer', 'customer']
    if data['role'] not in valid_roles:
        return jsonify({"error": "Cargo inválido"}), 400
    
    # Verifica se está tentando alterar o role do último admin ativo
    if data['role'] != 'admin':
        if user_service.is_last_active_admin(user_id):
            return jsonify({"error": "Não é possível alterar o cargo do último administrador ativo do sistema"}), 409
    
    success, error_code, message = user_service.update_user_role(user_id, data['role'])
    if success:
        return jsonify({"msg": "Cargo atualizado com sucesso"}), 200
    else:
        if error_code == "USER_NOT_FOUND":
            return jsonify({"error": "Usuário não encontrado"}), 404
        elif error_code == "DATABASE_ERROR":
            return jsonify({"error": "Erro interno do servidor"}), 500
        else:
            return jsonify({"error": message}), 400


@user_bp.route('/<int:user_id>', methods=['GET'])
@require_role('admin', 'manager')
def get_user_by_id_route(user_id):
    user = user_service.get_user_by_id(user_id)
    if user:
        return jsonify(user), 200
    return jsonify({"error": "Usuário não encontrado"}), 404


@user_bp.route('/<int:user_id>', methods=['PUT'])
@require_role('admin', 'manager')
def update_user_route(user_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400
    
    # Validação de cargo se fornecido
    if 'role' in data:
        if data['role'] == 'delivery':
            data['role'] = 'deliverer'
        valid_roles = ['admin', 'manager', 'attendant', 'deliverer', 'customer']
        if data['role'] not in valid_roles:
            return jsonify({"error": "Cargo inválido"}), 400
    
    # Validação de data de nascimento se fornecida
    if 'date_of_birth' in data and data['date_of_birth']:
        is_valid_birth_date, birth_date_msg = validate_birth_date(data['date_of_birth'])
        if not is_valid_birth_date:
            return jsonify({"error": birth_date_msg}), 400
        # Converte para formato ISO para o banco de dados
        data['date_of_birth'] = convert_br_date_to_iso(data['date_of_birth'])
    
    # Verifica se está tentando desativar o último admin ativo
    if data.get('is_active') is False:
        if user_service.is_last_active_admin(user_id):
            return jsonify({"error": "Não é possível desativar o último administrador ativo do sistema"}), 409
    
    # Verifica se está tentando alterar o role do último admin ativo
    if data.get('role') and data.get('role') != 'admin':
        if user_service.is_last_active_admin(user_id):
            return jsonify({"error": "Não é possível alterar o cargo do último administrador ativo do sistema"}), 409
    
    success, error_code, message = user_service.update_user(user_id, data, is_admin_request=True)
    if success:
        return jsonify({"msg": "Dados atualizados com sucesso"}), 200
    if error_code == "USER_NOT_FOUND":
        return jsonify({"error": message}), 404
    elif error_code == "EMAIL_ALREADY_EXISTS":
        return jsonify({"error": message}), 409
    elif error_code in ["INVALID_EMAIL", "INVALID_PHONE", "INVALID_CPF", "INVALID_ROLE", "NO_VALID_FIELDS", "EMAIL_CHANGE_REQUIRES_VERIFICATION"]:
        return jsonify({"error": message}), 400
    elif error_code == "DATABASE_ERROR":
        return jsonify({"error": message}), 500
    else:
        return jsonify({"error": "Falha ao atualizar usuário"}), 500


@user_bp.route('/<int:user_id>', methods=['DELETE'])
@require_role('admin', 'manager')
def delete_user_route(user_id):
    # Verifica se está tentando desativar o último admin ativo
    if user_service.is_last_active_admin(user_id):
        return jsonify({"error": "Não é possível desativar o último administrador ativo do sistema"}), 409
    
    if user_service.deactivate_user(user_id):
        return jsonify({"msg": "Usuário desativado com sucesso"}), 200
    return jsonify({"error": "Falha ao desativar ou usuário não encontrado"}), 404


# Rotas específicas para administradores
@user_bp.route('/admins', methods=['POST'])
@require_role('admin')
def create_admin_route():
    data = request.get_json()
    if not all(k in data for k in ['full_name', 'email', 'password']):
        return jsonify({"error": "full_name, email e password são obrigatórios"}), 400
    
    # Validação de data de nascimento se fornecida
    if 'date_of_birth' in data and data['date_of_birth']:
        is_valid_birth_date, birth_date_msg = validate_birth_date(data['date_of_birth'])
        if not is_valid_birth_date:
            return jsonify({"error": birth_date_msg}), 400
        # Converte para formato ISO para o banco de dados
        data['date_of_birth'] = convert_br_date_to_iso(data['date_of_birth'])
    
    # Força o role como admin
    data['role'] = 'admin'
    
    new_user, error_code, error_message = user_service.create_user(data)
    if new_user:
        return jsonify({**new_user, "message": "Administrador registrado com sucesso"}), 201
    else:
        if error_code == "EMAIL_ALREADY_EXISTS":
            return jsonify({"error": "E-mail já cadastrado"}), 409
        elif error_code == "CPF_ALREADY_EXISTS":
            return jsonify({"error": "CPF já cadastrado"}), 409
        elif error_code in ["INVALID_EMAIL", "INVALID_PHONE", "INVALID_CPF", "WEAK_PASSWORD"]:
            return jsonify({"error": error_message}), 400
        elif error_code == "DATABASE_ERROR":
            return jsonify({"error": error_message}), 500
        else:
            return jsonify({"error": "Não foi possível criar o administrador."}), 500


@user_bp.route('/admins/<int:user_id>', methods=['PUT'])
@require_role('admin')
def update_admin_route(user_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400
    
    # Verifica se o usuário é realmente um admin
    user = user_service.get_user_by_id(user_id)
    if not user or user['role'] != 'admin':
        return jsonify({"error": "Administrador não encontrado"}), 404
    
    # Validação de data de nascimento se fornecida
    if 'date_of_birth' in data and data['date_of_birth']:
        is_valid_birth_date, birth_date_msg = validate_birth_date(data['date_of_birth'])
        if not is_valid_birth_date:
            return jsonify({"error": birth_date_msg}), 400
        # Converte para formato ISO para o banco de dados
        data['date_of_birth'] = convert_br_date_to_iso(data['date_of_birth'])
    
    # Verifica se está tentando desativar o último admin ativo
    if data.get('is_active') is False:
        if user_service.is_last_active_admin(user_id):
            return jsonify({"error": "Não é possível desativar o último administrador ativo do sistema"}), 409
    
    # Impede alteração do role de admin
    if data.get('role') and data.get('role') != 'admin':
        return jsonify({"error": "Não é possível alterar o cargo de um administrador"}), 400
    
    success, error_code, message = user_service.update_user(user_id, data, is_admin_request=True)
    if success:
        return jsonify({"msg": "Dados do administrador atualizados com sucesso"}), 200
    if error_code == "USER_NOT_FOUND":
        return jsonify({"error": message}), 404
    elif error_code == "EMAIL_ALREADY_EXISTS":
        return jsonify({"error": message}), 409
    elif error_code in ["INVALID_EMAIL", "INVALID_PHONE", "INVALID_CPF", "INVALID_ROLE", "NO_VALID_FIELDS", "EMAIL_CHANGE_REQUIRES_VERIFICATION"]:
        return jsonify({"error": message}), 400
    elif error_code == "DATABASE_ERROR":
        return jsonify({"error": message}), 500
    else:
        return jsonify({"error": "Falha ao atualizar administrador"}), 500


# Endpoints para gerenciamento completo de usuários
@user_bp.route('/metrics', methods=['GET'])
@require_role('admin', 'manager')
def get_users_metrics_route():
    """Retorna métricas gerais de usuários"""
    metrics = user_service.get_users_general_metrics()
    return jsonify(metrics), 200


@user_bp.route('/roles', methods=['GET'])
@require_role('admin', 'manager')
def get_available_roles_route():
    """Retorna os cargos/roles disponíveis"""
    roles = [
        {"value": "admin", "label": "Administrador"},
        {"value": "manager", "label": "Gerente"},
        {"value": "attendant", "label": "Atendente"},
        {"value": "deliverer", "label": "Entregador"},  # ALTERAÇÃO: alinhar com roles aceitos pelo backend
        {"value": "customer", "label": "Cliente"}
    ]
    return jsonify({"roles": roles}), 200


@user_bp.route('/check-email', methods=['GET'])
@require_role('admin', 'manager')
def check_email_availability_route():
    """Verifica se um email está disponível"""
    email = request.args.get('email')
    if not email:
        return jsonify({"error": "Parâmetro 'email' é obrigatório"}), 400
    
    is_available = user_service.check_email_availability(email)
    return jsonify({"available": is_available}), 200


@user_bp.route('/request-email-verification', methods=['POST'])
@rate_limit(max_requests=3, window_seconds=300)  # IMPLEMENTAÇÃO: Rate limiting - 3 tentativas por 5 minutos
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
        elif error_code == "NO_UNVERIFIED_USER":
            return jsonify({"error": message}), 404
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
        if error_code == "EMAIL_WARNING":
            return jsonify({
                "msg": "Novo código de verificação criado", 
                "warning": message
            }), 200
        else:
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
@rate_limit(max_requests=5, window_seconds=300)  # IMPLEMENTAÇÃO: Rate limiting - 5 tentativas por 5 minutos
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
        # ALTERAÇÃO: Logging estruturado ao invés de print
        logger.error(f"Erro na verificação 2FA: {e}", exc_info=True)
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
        # ALTERAÇÃO: Logging estruturado ao invés de print
        logger.error(f"Erro ao alterar 2FA: {e}", exc_info=True)
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
        # ALTERAÇÃO: Logging estruturado ao invés de print
        logger.error(f"Erro ao confirmar 2FA: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@user_bp.route('/2fa-status', methods=['GET'])
@jwt_required()
def get_2fa_status_route():
    try:
        user_id = get_jwt_identity()
        is_enabled = two_factor_service.is_2fa_enabled(user_id)
        
        return jsonify({"two_factor_enabled": is_enabled}), 200
        
    except Exception as e:
        # ALTERAÇÃO: Logging estruturado ao invés de print
        logger.error(f"Erro ao verificar status 2FA: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


# ===== ROTAS PARA MUDANÇA DE EMAIL COM VERIFICAÇÃO =====

@user_bp.route('/request-email-change', methods=['POST'])
@jwt_required()
def request_email_change_route():
    """
    Solicita mudança de email. Envia código de verificação para o novo email.
    """
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        new_email = data.get('new_email')
        
        if not new_email:
            return jsonify({"error": "O campo 'new_email' é obrigatório"}), 400
        
        success, error_code, message = pending_email_service.create_pending_email_change(user_id, new_email)
        
        if success:
            return jsonify({"msg": message}), 200
        else:
            if error_code == "USER_NOT_FOUND":
                return jsonify({"error": "Usuário não encontrado"}), 404
            elif error_code == "SAME_EMAIL":
                return jsonify({"error": "O novo email deve ser diferente do email atual"}), 400
            elif error_code == "EMAIL_ALREADY_EXISTS":
                return jsonify({"error": "Este email já está em uso por outra conta"}), 409
            elif error_code == "PENDING_CHANGE_EXISTS":
                return jsonify({"error": "Já existe uma solicitação de mudança de email pendente"}), 409
            elif error_code == "EMAIL_ERROR":
                return jsonify({"error": message}), 500
            elif error_code == "DATABASE_ERROR":
                return jsonify({"error": "Erro interno do servidor"}), 500
            else:
                return jsonify({"error": message}), 400
                
    except Exception as e:
        # ALTERAÇÃO: Logging estruturado ao invés de print
        logger.error(f"Erro ao solicitar mudança de email: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@user_bp.route('/verify-email-change', methods=['POST'])
@jwt_required()
def verify_email_change_route():
    """
    Verifica o código e efetua a mudança de email.
    """
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        code = data.get('code')
        
        if not code:
            return jsonify({"error": "O campo 'code' é obrigatório"}), 400
        
        if len(code) != 6 or not code.isdigit():
            return jsonify({"error": "Código deve ter exatamente 6 dígitos"}), 400
        
        success, error_code, message = pending_email_service.verify_pending_email_change(user_id, code)
        
        if success:
            return jsonify({"msg": message}), 200
        else:
            if error_code == "NO_PENDING_CHANGE":
                return jsonify({"error": "Nenhuma solicitação de mudança de email pendente"}), 404
            elif error_code == "CODE_EXPIRED":
                return jsonify({"error": "Código de verificação expirado"}), 400
            elif error_code == "INVALID_CODE":
                return jsonify({"error": "Código de verificação inválido"}), 400
            elif error_code == "EMAIL_ALREADY_EXISTS":
                return jsonify({"error": "Este email já está em uso por outra conta"}), 409
            elif error_code == "DATABASE_ERROR":
                return jsonify({"error": "Erro interno do servidor"}), 500
            else:
                return jsonify({"error": message}), 400
                
    except Exception as e:
        # ALTERAÇÃO: Logging estruturado ao invés de print
        logger.error(f"Erro ao verificar mudança de email: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@user_bp.route('/cancel-email-change', methods=['POST'])
@jwt_required()
def cancel_email_change_route():
    """
    Cancela uma solicitação de mudança de email pendente.
    """
    try:
        user_id = int(get_jwt_identity())
        
        success, error_code, message = pending_email_service.cancel_pending_email_change(user_id)
        
        if success:
            return jsonify({"msg": message}), 200
        else:
            if error_code == "NO_PENDING_CHANGE":
                return jsonify({"error": "Nenhuma solicitação de mudança de email pendente"}), 404
            elif error_code == "DATABASE_ERROR":
                return jsonify({"error": "Erro interno do servidor"}), 500
            else:
                return jsonify({"error": message}), 400
                
    except Exception as e:
        # ALTERAÇÃO: Logging estruturado ao invés de print
        logger.error(f"Erro ao cancelar mudança de email: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@user_bp.route('/pending-email-change', methods=['GET'])
@jwt_required()
def get_pending_email_change_route():
    """
    Retorna informações sobre uma mudança de email pendente.
    """
    try:
        user_id = int(get_jwt_identity())
        
        data, error_code, message = pending_email_service.get_pending_email_change(user_id)
        
        if data:
            return jsonify(data), 200
        else:
            if error_code == "NO_PENDING_CHANGE":
                return jsonify({"error": "Nenhuma solicitação de mudança de email pendente"}), 404
            elif error_code == "DATABASE_ERROR":
                return jsonify({"error": "Erro interno do servidor"}), 500
            else:
                return jsonify({"error": message}), 400
                
    except Exception as e:
        # ALTERAÇÃO: Logging estruturado ao invés de print
        logger.error(f"Erro ao buscar mudança de email pendente: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@user_bp.route('/cleanup-unverified', methods=['POST'])
@require_role('admin')
def cleanup_unverified_accounts_route():
    """
    Remove contas não verificadas antigas (apenas para administradores)
    """
    try:
        data = request.get_json() or {}
        days_old = data.get('days_old', 7)  # Padrão: 7 dias
        
        if not isinstance(days_old, int) or days_old < 1:
            return jsonify({"error": "days_old deve ser um número inteiro maior que 0"}), 400
        
        deleted_count = user_service.cleanup_unverified_accounts(days_old)
        
        return jsonify({
            "msg": f"Limpeza concluída. {deleted_count} contas não verificadas removidas.",
            "deleted_count": deleted_count,
            "days_old": days_old
        }), 200
        
    except Exception as e:
        # ALTERAÇÃO: Logging estruturado ao invés de print
        logger.error(f"Erro na limpeza de contas não verificadas: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@user_bp.route('/device-token', methods=['POST'])
@jwt_required()
def save_device_token_route():
    """
    Salva ou atualiza o token de push do dispositivo do usuário.
    Body: { "push_token": "ExponentPushToken[...]", "device_name": "iPhone de João" (opcional) }
    """
    try:
        claims = get_jwt()
        user_id = int(claims.get('sub'))
        data = request.get_json()
        
        if not data or 'push_token' not in data:
            return jsonify({"error": "O campo 'push_token' é obrigatório"}), 400
        
        push_token = data.get('push_token')
        device_name = data.get('device_name')
        
        if not push_token or not isinstance(push_token, str):
            return jsonify({"error": "push_token deve ser uma string não vazia"}), 400
        
        success = push_service.save_device_token(user_id, push_token, device_name)
        
        if success:
            return jsonify({"msg": "Token de dispositivo salvo com sucesso"}), 200
        else:
            return jsonify({"error": "Erro ao salvar token de dispositivo"}), 500
            
    except Exception as e:
        logger.error(f"Erro ao salvar token de dispositivo: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500