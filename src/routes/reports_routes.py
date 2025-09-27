from flask import Blueprint, request, jsonify  
from ..services import reports_service  
from ..services.auth_service import require_role  

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
