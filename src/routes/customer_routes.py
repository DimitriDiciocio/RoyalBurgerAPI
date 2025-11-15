from flask import Blueprint, request, jsonify  
from ..services import user_service, address_service  
from ..services.auth_service import require_role  
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from ..utils.validators import validate_birth_date, convert_br_date_to_iso  

customer_bp = Blueprint('customers', __name__)  

@customer_bp.route('/', methods=['POST'])  
def create_customer_route():  
    data = request.get_json()  
    guest_cart_id = data.get('guest_cart_id') if data else None

    required_fields = ['full_name', 'email', 'password', 'password_confirmation', 'date_of_birth', 'phone']  
    if not data or not all(field in data for field in required_fields):  
        return jsonify({"error": "Todos os campos são obrigatórios: nome completo, email, senha, confirmação de senha, data de nascimento e telefone."}), 400  

    password = data.get('password')  
    password_confirmation = data.get('password_confirmation')  

    if password != password_confirmation:  
        return jsonify({"error": "As senhas não conferem."}), 400  

    # Validação de data de nascimento
    if 'date_of_birth' in data and data['date_of_birth']:
        is_valid_birth_date, birth_date_msg = validate_birth_date(data['date_of_birth'])
        if not is_valid_birth_date:
            return jsonify({"error": birth_date_msg}), 400
        # Converte para formato ISO para o banco de dados
        data['date_of_birth'] = convert_br_date_to_iso(data['date_of_birth'])

    # Força o role como customer
    data['role'] = 'customer'

    new_user, error_code, error_message = user_service.create_user(data)  

    if new_user:  
        # Reivindica carrinho convidado, se houver
        if guest_cart_id and new_user.get('id'):
            try:
                from ..services import cart_service
                ok, err, msg = cart_service.claim_guest_cart(guest_cart_id, new_user['id'])
                # Não bloqueia o fluxo de registro; apenas adiciona aviso em caso de falha
                if not ok:
                    return jsonify({**new_user, "message": "Cliente registrado com sucesso", "cart_merge_warning": msg}), 201
            except Exception as e:
                print(f"Erro ao reivindicar carrinho convidado no registro: {e}")
                return jsonify({**new_user, "message": "Cliente registrado com sucesso", "cart_merge_warning": "Erro interno ao mesclar o carrinho"}), 201

        return jsonify({**new_user, "message": "Cliente registrado com sucesso"}), 201  
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
            return jsonify({"error": "Não foi possível criar o cliente."}), 500  

@customer_bp.route('/', methods=['GET'])  
@require_role('admin', 'manager')  
def get_all_customers_route():  
    # Parâmetros de paginação
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    
    # Filtros
    filters = {}
    if request.args.get('name'):
        filters['name'] = request.args.get('name')
    if request.args.get('email'):
        filters['email'] = request.args.get('email')
    if request.args.get('cpf'):
        filters['cpf'] = request.args.get('cpf')
    if request.args.get('status') is not None:
        filters['status'] = request.args.get('status').lower() == 'true'
    
    # Ordenação
    sort_by = request.args.get('sort_by', 'full_name')
    sort_order = request.args.get('sort_order', 'asc')
    
    result = user_service.get_customers_paginated(page, per_page, filters, sort_by, sort_order)
    return jsonify(result), 200  

@customer_bp.route('/<int:user_id>', methods=['GET'])  
@jwt_required()  
def get_customer_by_id_route(user_id):  
    claims = get_jwt()  
    if 'admin' not in claims.get('roles', []) and get_jwt_identity() != str(user_id):  
        return jsonify({"msg": "Acesso não autorizado"}), 403  

    user = user_service.get_user_by_id(user_id)  
    if user and user['role'] == 'customer':  
        return jsonify(user), 200  
    return jsonify({"msg": "Cliente não encontrado"}), 404  

@customer_bp.route('/<int:user_id>', methods=['PUT'])  
@jwt_required()  
def update_customer_route(user_id):  
    claims = get_jwt()  
    if 'admin' not in claims.get('roles', []) and get_jwt_identity() != str(user_id):  
        return jsonify({"msg": "Acesso não autorizado"}), 403  

    data = request.get_json()  
    if not data:  
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400  

    # Verifica se o usuário é realmente um customer
    user = user_service.get_user_by_id(user_id)
    if not user or user['role'] != 'customer':
        return jsonify({"error": "Cliente não encontrado"}), 404

    # Impede alteração do role de customer
    if data.get('role') and data.get('role') != 'customer':
        return jsonify({"error": "Não é possível alterar o cargo de um cliente"}), 400

    # Validação de data de nascimento se fornecida
    if 'date_of_birth' in data and data['date_of_birth']:
        is_valid_birth_date, birth_date_msg = validate_birth_date(data['date_of_birth'])
        if not is_valid_birth_date:
            return jsonify({"error": birth_date_msg}), 400
        # Converte para formato ISO para o banco de dados
        data['date_of_birth'] = convert_br_date_to_iso(data['date_of_birth'])

    success, error_code, message = user_service.update_user(user_id, data)  

    if success:  
        return jsonify({"msg": "Dados do cliente atualizados com sucesso"}), 200  
    else:  
        if error_code == "USER_NOT_FOUND":  
            return jsonify({"error": message}), 404  
        elif error_code == "EMAIL_ALREADY_EXISTS":  
            return jsonify({"error": message}), 409  
        elif error_code in ["INVALID_EMAIL", "INVALID_PHONE", "INVALID_CPF", "NO_VALID_FIELDS"]:  
            return jsonify({"error": message}), 400  
        elif error_code == "DATABASE_ERROR":  
            return jsonify({"error": message}), 500  
        else:  
            return jsonify({"error": "Falha ao atualizar dados do cliente"}), 500  

@customer_bp.route('/<int:user_id>/notification-preferences', methods=['GET'])
@jwt_required()
def get_notification_preferences_route(user_id):
    """
    Obtém as preferências de notificação do usuário.
    """
    claims = get_jwt()
    if 'admin' not in claims.get('roles', []) and get_jwt_identity() != str(user_id):
        return jsonify({"msg": "Acesso não autorizado"}), 403
    
    preferences = user_service.get_notification_preferences(user_id)
    if preferences is None:
        return jsonify({"error": "Usuário não encontrado"}), 404
    
    return jsonify(preferences), 200

@customer_bp.route('/<int:user_id>/notification-preferences', methods=['PUT'])
@jwt_required()
def update_notification_preferences_route(user_id):
    """
    Atualiza as preferências de notificação do usuário.
    Body esperado: { "notify_order_updates": true/false, "notify_promotions": true/false }
    """
    claims = get_jwt()
    if 'admin' not in claims.get('roles', []) and get_jwt_identity() != str(user_id):
        return jsonify({"msg": "Acesso não autorizado"}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400
    
    # Validar que pelo menos um campo foi fornecido
    if 'notify_order_updates' not in data and 'notify_promotions' not in data:
        return jsonify({"error": "Pelo menos uma preferência deve ser fornecida"}), 400
    
    # Validar tipos booleanos
    if 'notify_order_updates' in data and not isinstance(data['notify_order_updates'], bool):
        return jsonify({"error": "notify_order_updates deve ser um valor booleano (true/false)"}), 400
    
    if 'notify_promotions' in data and not isinstance(data['notify_promotions'], bool):
        return jsonify({"error": "notify_promotions deve ser um valor booleano (true/false)"}), 400
    
    success, error_code, message = user_service.update_notification_preferences(user_id, data)
    
    if success:
        return jsonify({"msg": message}), 200
    else:
        if error_code == "USER_NOT_FOUND":
            return jsonify({"error": message}), 404
        elif error_code == "NO_VALID_FIELDS":
            return jsonify({"error": message}), 400
        elif error_code == "DATABASE_ERROR":
            return jsonify({"error": message}), 500
        else:
            return jsonify({"error": "Falha ao atualizar preferências de notificação"}), 500

@customer_bp.route('/<int:user_id>', methods=['DELETE'])  
@jwt_required()  
def delete_customer_route(user_id):  
    claims = get_jwt()  
    if 'admin' not in claims.get('roles', []) and get_jwt_identity() != str(user_id):  
        return jsonify({"msg": "Acesso não autorizado"}), 403  

    if user_service.deactivate_user(user_id):  
        return jsonify({"msg": "Conta excluída com sucesso"}), 200  
    return jsonify({"error": "Falha ao excluir conta ou cliente não encontrado"}), 404  

@customer_bp.route('/delete-account', methods=['DELETE'])  
@jwt_required()  
def delete_my_account_route():  
    claims = get_jwt()  
    user_id = int(claims.get('sub'))  
    user_roles = claims.get('roles', [])  
    if 'customer' not in user_roles:  
        return jsonify({"error": "Apenas clientes podem deletar suas próprias contas"}), 403  
    if user_service.deactivate_user(user_id):  
        return jsonify({"msg": "Conta excluída com sucesso"}), 200  
    return jsonify({"error": "Falha ao excluir conta"}), 500  


@customer_bp.route('/<int:user_id>/addresses', methods=['POST'])  
@jwt_required()  
def add_address_route(user_id):  
    claims = get_jwt()  
    if int(claims.get('sub')) != user_id:  
        return jsonify({"msg": "Acesso não autorizado"}), 403  
    data = request.get_json()  
    # Validação de campos obrigatórios (number e complement são opcionais)
    required_fields = ['street', 'neighborhood', 'city', 'state', 'zip_code']
    if not data:
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400
    missing = [f for f in required_fields if not data.get(f)]
    if missing:
        return jsonify({"error": f"Campos obrigatórios ausentes: {', '.join(missing)}"}), 400
    # Validações de formato
    state = (data.get('state') or '').strip()
    if len(state) != 2:
        return jsonify({"error": "O campo state deve possuir 2 caracteres (UF)."}), 400
    # zip_code obrigatório: não aceitar vazio
    zip_code = (data.get('zip_code') or '').strip()
    if not zip_code:
        return jsonify({"error": "O campo zip_code é obrigatório."}), 400
    complement = data.get('complement')
    if complement is not None and isinstance(complement, str) and complement.strip() == "":
        data['complement'] = None
    # number é opcional: vazio vira null
    if 'number' in data and isinstance(data.get('number'), str) and data.get('number').strip() == "":
        data['number'] = None
    new_address = address_service.create_address(user_id, data)  
    if new_address:  
        return jsonify(new_address), 201  
    return jsonify({"error": "Não foi possível adicionar o endereço"}), 500

@customer_bp.route('/<int:user_id>/addresses', methods=['GET'])  
@jwt_required()  
def get_addresses_route(user_id):  
    claims = get_jwt()  
    if int(claims.get('sub')) != user_id:  
        return jsonify({"msg": "Acesso não autorizado"}), 403  
    addresses = address_service.get_addresses_by_user_id(user_id)  
    return jsonify(addresses), 200  

@customer_bp.route('/<int:user_id>/addresses/<int:address_id>', methods=['PUT'])  
@jwt_required()  
def update_address_route(user_id, address_id):  
    claims = get_jwt()  
    if int(claims.get('sub')) != user_id:  
        return jsonify({"msg": "Acesso não autorizado"}), 403  
    address = address_service.get_address_by_id(address_id)  
    if not address or address.get('user_id') != user_id or not address.get('is_active', True):  
        return jsonify({"msg": "Endereço não encontrado ou acesso não autorizado"}), 404  
    data = request.get_json()  
    if not data:  
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400  
    # Se qualquer campo essencial for enviado, exija todos (PUT semântico de substituição)
    # Campos essenciais: street, neighborhood, city, state, zip_code (number e complement são opcionais)
    core_fields = ['street', 'neighborhood', 'city', 'state', 'zip_code']
    any_core_present = any(k in data for k in core_fields)
    if any_core_present:
        missing = [f for f in core_fields if not data.get(f)]
        if missing:
            return jsonify({"error": f"Campos obrigatórios ausentes: {', '.join(missing)}"}), 400
        state = (data.get('state') or '').strip()
        if len(state) != 2:
            return jsonify({"error": "O campo state deve possuir 2 caracteres (UF)."}), 400
    # Normaliza opcionais vazios para null
    if 'complement' in data and isinstance(data.get('complement'), str) and data.get('complement').strip() == "":
        data['complement'] = None
    if 'number' in data and isinstance(data.get('number'), str) and data.get('number').strip() == "":
        data['number'] = None
    success, changed = address_service.update_address(address_id, data)  
    if success:
        if changed:
            return jsonify({"msg": "Endereço atualizado com sucesso"}), 200  
        else:
            return jsonify({"msg": "Nenhuma alteração aplicada"}), 200  
    return jsonify({"error": "Falha ao atualizar endereço"}), 500  

@customer_bp.route('/<int:user_id>/addresses/<int:address_id>', methods=['DELETE'])  
@jwt_required()  
def delete_address_route(user_id, address_id):  
    claims = get_jwt()  
    if int(claims.get('sub')) != user_id:  
        return jsonify({"msg": "Acesso não autorizado"}), 403  
    address = address_service.get_address_by_id(address_id)  
    if not address or address.get('user_id') != user_id or not address.get('is_active', True):  
        return jsonify({"msg": "Endereço não encontrado ou acesso não autorizado"}), 404  
    if address_service.delete_address(address_id):  
        return jsonify({"msg": "Endereço deletado com sucesso"}), 200  
    return jsonify({"error": "Falha ao deletar endereço"}), 500

@customer_bp.route('/<int:user_id>/addresses/<int:address_id>/set-default', methods=['PUT'])  
@jwt_required()  
def set_default_address_route(user_id, address_id):  
    """
    Define um endereço como padrão para o usuário.
    """
    claims = get_jwt()  
    if int(claims.get('sub')) != user_id:  
        return jsonify({"msg": "Acesso não autorizado"}), 403  
    
    success, message = address_service.set_default_address(user_id, address_id)
    
    if success:
        return jsonify({"msg": message}), 200  
    else:
        if "não encontrado" in message:
            return jsonify({"error": message}), 404
        else:
            return jsonify({"error": message}), 500  

# Endpoints de loyalty foram movidos para loyalty_routes.py
# Use /api/loyalty/balance/{user_id} e /api/loyalty/history/{user_id}  

@customer_bp.route('/<int:user_id>/reactivate', methods=['POST'])  
@jwt_required()  
def reactivate_customer_route(user_id):  
    claims = get_jwt()  
    if 'admin' not in claims.get('roles', []):  
        return jsonify({"msg": "Acesso não autorizado. Apenas administradores podem reativar contas."}), 403  
    if user_service.reactivate_user(user_id):  
        return jsonify({"msg": "Cliente reativado com sucesso"}), 200  
    else:  
        return jsonify({"error": "Falha ao reativar cliente ou cliente não encontrado"}), 404

