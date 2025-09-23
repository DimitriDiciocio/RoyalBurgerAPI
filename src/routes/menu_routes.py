from flask import Blueprint, request, jsonify  # importa Blueprint, request e jsonify do Flask
from ..services import product_service  # importa serviço de produtos (KPIs do cardápio)
from ..services.auth_service import require_role  # importa decorator de autorização por papel

menu_bp = Blueprint('menu', __name__)  # cria o blueprint de menu

@menu_bp.route('/summary', methods=['GET'])  # define rota GET para KPIs do cardápio
@require_role('admin', 'manager')  # restringe a admin/manager
def get_menu_summary_route():  # função handler do resumo do cardápio
    summary = product_service.get_menu_summary()  # busca métricas no serviço de produtos
    return jsonify(summary), 200  # retorna métricas com status 200
