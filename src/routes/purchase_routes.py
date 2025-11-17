from flask import Blueprint, request, jsonify, g
from ..services import purchase_service
from ..services.auth_service import require_role
from ..utils.validators import is_valid_date_format, is_date_in_range, convert_br_date_to_iso

purchase_bp = Blueprint('purchases', __name__)

@purchase_bp.route('/invoices', methods=['POST'])
@require_role('admin', 'manager')
def create_purchase_invoice_route():
    """Cria uma nota fiscal de compra"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400
    
    user_id = g.current_user_id if hasattr(g, 'current_user_id') else None
    if not user_id:
        return jsonify({"error": "Usuário não autenticado"}), 401
    
    success, error_code, result = purchase_service.create_purchase_invoice(data, user_id)
    
    if success:
        return jsonify(result), 201
    else:
        return jsonify({"error": result}), 400


@purchase_bp.route('/invoices', methods=['GET'])
@require_role('admin', 'manager')
def get_purchase_invoices_route():
    """Lista notas fiscais de compra com filtros"""
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
    if request.args.get('supplier_name'):
        filters['supplier_name'] = request.args.get('supplier_name')
    if request.args.get('payment_status'):
        filters['payment_status'] = request.args.get('payment_status')
    
    invoices = purchase_service.get_purchase_invoices(filters)
    return jsonify(invoices), 200


@purchase_bp.route('/invoices/<int:invoice_id>', methods=['GET'])
@require_role('admin', 'manager')
def get_purchase_invoice_by_id_route(invoice_id):
    """Busca uma nota fiscal de compra por ID"""
    invoice = purchase_service.get_purchase_invoice_by_id(invoice_id)
    
    if invoice:
        return jsonify(invoice), 200
    else:
        return jsonify({"error": "Nota fiscal não encontrada"}), 404

