from flask import Blueprint, request, jsonify  
from ..services import reports_service  
from ..services.auth_service import require_role  
from ..utils.validators import is_valid_date_format, is_date_in_range, convert_br_date_to_iso
from datetime import datetime, date

reports_bp = Blueprint('reports', __name__)  

@reports_bp.route('/', methods=['GET'])  
@require_role('admin')  
def get_reports_route():  
    report_type = request.args.get('type', 'sales')  
    period = request.args.get('period', 'last_7_days')  
    valid_types = ['sales', 'financial', 'performance', 'employees']  
    valid_periods = ['last_7_days', 'last_30_days', 'this_month']  
    if report_type not in valid_types:  
        return jsonify({"error": "Tipo de relatório inválido. Use: sales, financial, performance, employees"}), 400  
    if period not in valid_periods:  
        return jsonify({"error": "Período inválido. Use: last_7_days, last_30_days, this_month"}), 400  
    report_data = reports_service.get_reports(report_type, period)  
    if "error" in report_data:  
        return jsonify(report_data), 500  
    return jsonify(report_data), 200


@reports_bp.route('/financial/detailed', methods=['GET'])
@require_role('admin')
def get_detailed_financial_report_route():
    """Retorna relatório financeiro detalhado usando o novo sistema FINANCIAL_MOVEMENTS"""
    # Validar datas
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date or not end_date:
        return jsonify({"error": "start_date e end_date são obrigatórios"}), 400
    
    # Validar formato das datas
    is_valid_start, format_msg_start = is_valid_date_format(start_date)
    if not is_valid_start:
        return jsonify({"error": f"Data de início inválida: {format_msg_start}"}), 400
    
    is_valid_end, format_msg_end = is_valid_date_format(end_date)
    if not is_valid_end:
        return jsonify({"error": f"Data de fim inválida: {format_msg_end}"}), 400
    
    # Converter para ISO
    start_date_iso = convert_br_date_to_iso(start_date)
    end_date_iso = convert_br_date_to_iso(end_date)
    
    # Validar intervalo
    is_valid_range, range_msg = is_date_in_range(
        start_date_iso,
        max_date=end_date_iso
    )
    if not is_valid_range:
        return jsonify({"error": f"Intervalo de datas inválido: {range_msg}"}), 400
    
    # Gerar relatório
    try:
        report = reports_service.get_detailed_financial_report(start_date_iso, end_date_iso)
        return jsonify(report), 200
    except Exception as e:
        return jsonify({"error": f"Erro ao gerar relatório: {str(e)}"}), 500  
