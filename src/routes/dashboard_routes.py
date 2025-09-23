from flask import Blueprint, request, jsonify  # importa Blueprint, request e jsonify do Flask
from ..services import dashboard_service  # importa o serviço de dashboard
from ..services.auth_service import require_role  # importa decorator de autorização por papel

dashboard_bp = Blueprint('dashboard', __name__)  # cria o blueprint de dashboard

@dashboard_bp.route('/metrics', methods=['GET'])  # define rota GET para métricas do dashboard
@require_role('admin', 'manager')  # restringe a admin/manager
def get_dashboard_metrics_route():  # função handler para métricas
    metrics = dashboard_service.get_dashboard_metrics()  # busca métricas no serviço
    return jsonify(metrics), 200  # retorna métricas com status 200
