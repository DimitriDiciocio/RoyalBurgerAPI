from flask import Blueprint, request, jsonify, g  
from ..services import financial_service  
from ..services.auth_service import require_role
from ..utils.validators import is_valid_date_format, is_date_in_range, convert_br_date_to_iso  

financial_bp = Blueprint('financials', __name__)  

@financial_bp.route('/summary', methods=['GET'])  
@require_role('admin')  
def get_financial_summary_route():  
    period = request.args.get('period', 'this_month')  
    summary = financial_service.get_financial_summary(period)  
    return jsonify(summary), 200  

@financial_bp.route('/transactions', methods=['GET'])  
@require_role('admin')  
def get_financial_transactions_route():  
    filters = {}  
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
    if request.args.get('type'):  
        filters['type'] = request.args.get('type')
    
    # Valida se start_date não é posterior a end_date
    if filters.get('start_date') and filters.get('end_date'):
        is_valid_range, range_msg = is_date_in_range(
            filters['start_date'], 
            max_date=filters['end_date']
        )
        if not is_valid_range:
            return jsonify({"error": f"Intervalo de datas inválido: {range_msg}"}), 400
    
    transactions = financial_service.get_financial_transactions(filters)  
    return jsonify(transactions), 200  

@financial_bp.route('/transactions', methods=['POST'])  
@require_role('admin')  
def create_financial_transaction_route():  
    data = request.get_json()  
    if not data:  
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400  
    user_id = g.current_user_id if hasattr(g, 'current_user_id') else None  
    if not user_id:  
        return jsonify({"error": "Usuário não autenticado"}), 401  
    success, error_code, result = financial_service.create_financial_transaction(data, user_id)  
    if success:  
        return jsonify(result), 201  
    elif error_code in ["INVALID_DESCRIPTION", "INVALID_AMOUNT", "INVALID_TYPE"]:  
        return jsonify({"error": result}), 400  
    else:  
        return jsonify({"error": "Erro interno do servidor"}), 500  
