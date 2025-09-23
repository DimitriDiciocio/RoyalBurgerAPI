from flask import Blueprint, request, jsonify  # importa Blueprint, request e jsonify do Flask
from ..services import reports_service  # importa o serviço de relatórios
from ..services.auth_service import require_role  # importa decorator de autorização por papel

reports_bp = Blueprint('reports', __name__)  # cria o blueprint de relatórios

@reports_bp.route('/', methods=['GET'])  # define rota GET para relatórios e analytics
@require_role('admin')  # restringe a administradores
def get_reports_route():  # função handler dos relatórios
    report_type = request.args.get('type', 'sales')  # extrai tipo do relatório
    period = request.args.get('period', 'last_7_days')  # extrai período
    valid_types = ['sales', 'financial', 'performance', 'employees']  # tipos válidos
    valid_periods = ['last_7_days', 'last_30_days', 'this_month']  # períodos válidos
    if report_type not in valid_types:  # valida tipo
        return jsonify({"error": "Tipo de relatório inválido. Use: sales, financial, performance, employees"}), 400  # retorna 400
    if period not in valid_periods:  # valida período
        return jsonify({"error": "Período inválido. Use: last_7_days, last_30_days, this_month"}), 400  # retorna 400
    report_data = reports_service.get_reports(report_type, period)  # busca relatório no serviço
    if "error" in report_data:  # erro no serviço
        return jsonify(report_data), 500  # retorna 500
    return jsonify(report_data), 200  # retorna dados com status 200
