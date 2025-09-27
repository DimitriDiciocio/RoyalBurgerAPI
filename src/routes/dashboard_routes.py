from flask import Blueprint, request, jsonify  
from ..services import dashboard_service  
from ..services.auth_service import require_role  

dashboard_bp = Blueprint('dashboard', __name__)  

@dashboard_bp.route('/metrics', methods=['GET'])  
@require_role('admin', 'manager')  
def get_dashboard_metrics_route():  
    metrics = dashboard_service.get_dashboard_metrics()  
    return jsonify(metrics), 200  
