from flask import Blueprint, request, jsonify  
from ..services import product_service  
from ..services.auth_service import require_role  

menu_bp = Blueprint('menu', __name__)  

@menu_bp.route('/summary', methods=['GET'])  
@require_role('admin', 'manager')  
def get_menu_summary_route():  
    summary = product_service.get_menu_summary()  
    return jsonify(summary), 200  
