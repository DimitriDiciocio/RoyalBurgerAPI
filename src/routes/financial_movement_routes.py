from flask import Blueprint, request, jsonify, g
from ..services import financial_movement_service, recurring_tax_service
from ..services.auth_service import require_role
from ..utils.validators import is_valid_date_format, is_date_in_range, convert_br_date_to_iso

financial_movement_bp = Blueprint('financial_movements', __name__)

@financial_movement_bp.route('/movements', methods=['GET'])
@require_role('admin', 'manager')
def get_financial_movements_route():
    """Lista movimentações financeiras com filtros"""
    filters = {}
    
    # Filtro por data
    if request.args.get('start_date'):
        start_date = request.args.get('start_date')
        is_valid_format, format_msg = is_valid_date_format(start_date)
        if not is_valid_format:
            return jsonify({"error": f"Data de início inválida: {format_msg}"}), 400
        filters['start_date'] = convert_br_date_to_iso(start_date)
    
    if request.args.get('end_date'):
        end_date = request.args.get('end_date')
        is_valid_format, format_msg = is_valid_date_format(end_date)
        if not is_valid_format:
            return jsonify({"error": f"Data de fim inválida: {format_msg}"}), 400
        filters['end_date'] = convert_br_date_to_iso(end_date)
    
    # Valida intervalo de datas
    if filters.get('start_date') and filters.get('end_date'):
        is_valid_range, range_msg = is_date_in_range(
            filters['start_date'],
            max_date=filters['end_date']
        )
        if not is_valid_range:
            return jsonify({"error": f"Intervalo de datas inválido: {range_msg}"}), 400
    
    # Outros filtros
    if request.args.get('type'):
        filters['type'] = request.args.get('type')
    if request.args.get('category'):
        filters['category'] = request.args.get('category')
    if request.args.get('payment_status'):
        filters['payment_status'] = request.args.get('payment_status')
    if request.args.get('related_entity_type'):
        filters['related_entity_type'] = request.args.get('related_entity_type')
    if request.args.get('related_entity_id'):
        try:
            filters['related_entity_id'] = int(request.args.get('related_entity_id'))
        except ValueError:
            return jsonify({"error": "related_entity_id deve ser um número"}), 400
    
    # ALTERAÇÃO: Adicionar filtro reconciled (compatível com frontend)
    if request.args.get('reconciled') is not None:
        reconciled_value = request.args.get('reconciled').lower()
        if reconciled_value in ['true', '1', 'yes']:
            filters['reconciled'] = True
        elif reconciled_value in ['false', '0', 'no']:
            filters['reconciled'] = False
    
    movements = financial_movement_service.get_financial_movements(filters)
    return jsonify(movements), 200


@financial_movement_bp.route('/movements', methods=['POST'])
@require_role('admin', 'manager')
def create_financial_movement_route():
    """Cria uma nova movimentação financeira"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400
    
    user_id = g.current_user_id if hasattr(g, 'current_user_id') else None
    if not user_id:
        return jsonify({"error": "Usuário não autenticado"}), 401
    
    success, error_code, result = financial_movement_service.create_financial_movement(data, user_id)
    
    if success:
        return jsonify(result), 201
    elif error_code in ["INVALID_TYPE", "INVALID_VALUE", "INVALID_CATEGORY", "INVALID_DESCRIPTION"]:
        return jsonify({"error": result}), 400
    else:
        return jsonify({"error": "Erro interno do servidor"}), 500


@financial_movement_bp.route('/movements/<int:movement_id>', methods=['GET'])
@require_role('admin', 'manager')
def get_financial_movement_by_id_route(movement_id):
    """Busca uma movimentação financeira por ID"""
    # ALTERAÇÃO: Novo endpoint adicionado para integração com frontend
    movement = financial_movement_service.get_financial_movement_by_id(movement_id)
    
    if movement:
        return jsonify(movement), 200
    else:
        return jsonify({"error": "Movimentação não encontrada"}), 404


@financial_movement_bp.route('/movements/<int:movement_id>', methods=['PATCH'])
@require_role('admin', 'manager')
def update_financial_movement_route(movement_id):
    """Atualiza uma movimentação financeira (campos gerais)"""
    # ALTERAÇÃO: Novo endpoint adicionado para integração com frontend
    data = request.get_json()
    if not data:
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400
    
    user_id = g.current_user_id if hasattr(g, 'current_user_id') else None
    
    success, error_code, result = financial_movement_service.update_financial_movement(
        movement_id, data, user_id
    )
    
    if success:
        return jsonify(result), 200
    elif error_code == "NOT_FOUND":
        return jsonify({"error": "Movimentação não encontrada"}), 404
    elif error_code in ["INVALID_TYPE", "INVALID_VALUE", "INVALID_STATUS", "INVALID_DATE", "NO_UPDATES"]:
        return jsonify({"error": result}), 400
    else:
        return jsonify({"error": "Erro interno do servidor"}), 500


@financial_movement_bp.route('/movements/<int:movement_id>/payment-status', methods=['PATCH'])
@require_role('admin', 'manager')
def update_payment_status_route(movement_id):
    """Atualiza status de pagamento de uma movimentação"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400
    
    payment_status = data.get('payment_status')
    if not payment_status:
        return jsonify({"error": "payment_status é obrigatório"}), 400
    
    movement_date = data.get('movement_date')
    user_id = g.current_user_id if hasattr(g, 'current_user_id') else None
    
    success, error_code, result = financial_movement_service.update_payment_status(
        movement_id, payment_status, movement_date, user_id
    )
    
    if success:
        return jsonify(result), 200
    elif error_code == "NOT_FOUND":
        return jsonify({"error": "Movimentação não encontrada"}), 404
    elif error_code == "INVALID_STATUS":
        return jsonify({"error": result}), 400
    else:
        return jsonify({"error": "Erro interno do servidor"}), 500


@financial_movement_bp.route('/summary', methods=['GET'])
@require_role('admin', 'manager')
def get_cash_flow_summary_route():
    """Retorna resumo do fluxo de caixa"""
    period = request.args.get('period', 'this_month')
    include_pending = request.args.get('include_pending', 'false').lower() == 'true'
    
    summary = financial_movement_service.get_cash_flow_summary(period, include_pending)
    return jsonify(summary), 200


@financial_movement_bp.route('/pending', methods=['GET'])
@require_role('admin', 'manager')
def get_pending_payments_route():
    """Lista contas a pagar (movimentações pendentes)"""
    filters = {
        'payment_status': 'Pending'
    }
    
    # Filtro opcional por tipo
    if request.args.get('type'):
        filters['type'] = request.args.get('type')
    
    movements = financial_movement_service.get_financial_movements(filters)
    return jsonify(movements), 200


@financial_movement_bp.route('/recurring-taxes', methods=['GET'])
@require_role('admin', 'manager')
def get_recurring_taxes_route():
    """Lista impostos recorrentes"""
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    taxes = recurring_tax_service.get_recurring_taxes(active_only)
    return jsonify(taxes), 200


@financial_movement_bp.route('/recurring-taxes', methods=['POST'])
@require_role('admin', 'manager')
def create_recurring_tax_route():
    """Cria um imposto recorrente"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400
    
    user_id = g.current_user_id if hasattr(g, 'current_user_id') else None
    if not user_id:
        return jsonify({"error": "Usuário não autenticado"}), 401
    
    success, error_code, result = recurring_tax_service.create_recurring_tax(data, user_id)
    
    if success:
        return jsonify(result), 201
    else:
        return jsonify({"error": result}), 400


@financial_movement_bp.route('/recurring-taxes/<int:tax_id>', methods=['PATCH'])
@require_role('admin', 'manager')
def update_recurring_tax_route(tax_id):
    """Atualiza um imposto recorrente"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400
    
    user_id = g.current_user_id if hasattr(g, 'current_user_id') else None
    
    success, error_code, result = recurring_tax_service.update_recurring_tax(tax_id, data, user_id)
    
    if success:
        return jsonify(result), 200
    elif error_code == "NOT_FOUND":
        return jsonify({"error": "Imposto recorrente não encontrado"}), 404
    elif error_code in ["INVALID_VALUE", "INVALID_PAYMENT_DAY", "NO_UPDATES"]:
        return jsonify({"error": result}), 400
    else:
        return jsonify({"error": "Erro interno do servidor"}), 500


@financial_movement_bp.route('/recurring-taxes/<int:tax_id>', methods=['DELETE'])
@require_role('admin', 'manager')
def delete_recurring_tax_route(tax_id):
    """Desativa um imposto recorrente"""
    success, error_code, message = recurring_tax_service.delete_recurring_tax(tax_id)
    
    if success:
        return jsonify({"message": message}), 200
    elif error_code == "NOT_FOUND":
        return jsonify({"error": "Imposto recorrente não encontrado"}), 404
    else:
        return jsonify({"error": "Erro interno do servidor"}), 500


@financial_movement_bp.route('/recurring-taxes/generate', methods=['POST'])
@require_role('admin', 'manager')
def generate_monthly_taxes_route():
    """Gera movimentações para impostos recorrentes do mês"""
    data = request.get_json() or {}
    year = data.get('year')
    month = data.get('month')
    
    # Validar ano e mês se fornecidos
    if year is not None:
        try:
            year = int(year)
            if year < 2000 or year > 2100:
                return jsonify({"error": "Ano deve estar entre 2000 e 2100"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Ano deve ser um número válido"}), 400
    
    if month is not None:
        try:
            month = int(month)
            if month < 1 or month > 12:
                return jsonify({"error": "Mês deve estar entre 1 e 12"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Mês deve ser um número válido"}), 400
    
    success, count, errors = recurring_tax_service.generate_monthly_taxes(year, month)
    
    if success:
        return jsonify({
            "success": True,
            "generated_count": count,
            "errors": errors
        }), 200
    else:
        return jsonify({
            "success": False,
            "generated_count": count,
            "errors": errors
        }), 500


@financial_movement_bp.route('/movements/<int:movement_id>/reconcile', methods=['PATCH'])
@require_role('admin', 'manager')
def reconcile_financial_movement_route(movement_id):
    """Marca uma movimentação financeira como reconciliada ou não"""
    data = request.get_json() or {}
    reconciled = data.get('reconciled', True)
    
    user_id = g.current_user_id if hasattr(g, 'current_user_id') else None
    
    success, error_code, result = financial_movement_service.reconcile_financial_movement(
        movement_id, reconciled, user_id
    )
    
    if success:
        return jsonify(result), 200
    elif error_code == "NOT_FOUND":
        return jsonify({"error": "Movimentação não encontrada"}), 404
    else:
        return jsonify({"error": "Erro interno do servidor"}), 500


@financial_movement_bp.route('/movements/<int:movement_id>/gateway-info', methods=['PATCH'])
@require_role('admin', 'manager')
def update_gateway_info_route(movement_id):
    """Atualiza informações de gateway de uma movimentação financeira"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400
    
    user_id = g.current_user_id if hasattr(g, 'current_user_id') else None
    
    success, error_code, result = financial_movement_service.update_financial_movement_gateway_info(
        movement_id, data, user_id
    )
    
    if success:
        return jsonify(result), 200
    elif error_code == "NOT_FOUND":
        return jsonify({"error": "Movimentação não encontrada"}), 404
    elif error_code == "NO_UPDATES":
        return jsonify({"error": result}), 400
    else:
        return jsonify({"error": "Erro interno do servidor"}), 500


@financial_movement_bp.route('/reconciliation-report', methods=['GET'])
@require_role('admin', 'manager')
def get_reconciliation_report_route():
    """Gera relatório de conciliação bancária"""
    filters = {}
    
    # Filtro por data
    if request.args.get('start_date'):
        start_date = request.args.get('start_date')
        is_valid_format, format_msg = is_valid_date_format(start_date)
        if not is_valid_format:
            return jsonify({"error": f"Data de início inválida: {format_msg}"}), 400
        filters['start_date'] = convert_br_date_to_iso(start_date)
    
    if request.args.get('end_date'):
        end_date = request.args.get('end_date')
        is_valid_format, format_msg = is_valid_date_format(end_date)
        if not is_valid_format:
            return jsonify({"error": f"Data de fim inválida: {format_msg}"}), 400
        filters['end_date'] = convert_br_date_to_iso(end_date)
    
    # Valida intervalo de datas
    if filters.get('start_date') and filters.get('end_date'):
        is_valid_range, range_msg = is_date_in_range(
            filters['start_date'],
            max_date=filters['end_date']
        )
        if not is_valid_range:
            return jsonify({"error": f"Intervalo de datas inválido: {range_msg}"}), 400
    
    # Outros filtros
    if request.args.get('reconciled') is not None:
        filters['reconciled'] = request.args.get('reconciled').lower() == 'true'
    
    if request.args.get('payment_gateway_id'):
        filters['payment_gateway_id'] = request.args.get('payment_gateway_id')
    
    report = financial_movement_service.get_reconciliation_report(
        start_date=filters.get('start_date'),
        end_date=filters.get('end_date'),
        reconciled=filters.get('reconciled'),
        payment_gateway_id=filters.get('payment_gateway_id')
    )
    
    return jsonify(report), 200

