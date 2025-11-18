from flask import Blueprint, request, jsonify  
from ..services import reports_service  
from ..services.auth_service import require_role  
from ..utils.validators import is_valid_date_format, is_date_in_range, convert_br_date_to_iso
from datetime import datetime, date

reports_bp = Blueprint('reports', __name__)  


@reports_bp.route('/financial/detailed', methods=['GET', 'POST'])
@require_role('admin')
def get_detailed_financial_report_route():
    """
    Retorna relatório financeiro detalhado usando o novo sistema FINANCIAL_MOVEMENTS
    
    Aceita parâmetros via:
    - GET: query string (?start_date=DD-MM-YYYY&end_date=DD-MM-YYYY)
    - POST: body JSON ({"start_date": "DD-MM-YYYY", "end_date": "DD-MM-YYYY"})
    
    Formato de data: DD-MM-YYYY (formato brasileiro)
    """
    # Buscar datas da query string (GET) ou body JSON (POST)
    if request.method == 'GET':
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
    else:  # POST
        data = request.get_json() or {}
        start_date = data.get('start_date')
        end_date = data.get('end_date')
    
    if not start_date or not end_date:
        return jsonify({"error": "start_date e end_date são obrigatórios. Use o formato DD-MM-YYYY"}), 400
    
    # Validar formato das datas
    is_valid_start, format_msg_start = is_valid_date_format(start_date)
    if not is_valid_start:
        return jsonify({"error": f"Data de início inválida: {format_msg_start}. Use o formato DD-MM-YYYY"}), 400
    
    is_valid_end, format_msg_end = is_valid_date_format(end_date)
    if not is_valid_end:
        return jsonify({"error": f"Data de fim inválida: {format_msg_end}. Use o formato DD-MM-YYYY"}), 400
    
    # Validar intervalo ANTES de converter (is_date_in_range espera formato brasileiro)
    is_valid_range, range_msg = is_date_in_range(
        start_date,
        max_date=end_date
    )
    if not is_valid_range:
        return jsonify({"error": f"Intervalo de datas inválido: {range_msg}"}), 400
    
    # Converter para ISO após validação
    start_date_iso = convert_br_date_to_iso(start_date)
    end_date_iso = convert_br_date_to_iso(end_date)
    
    # Verificar se a conversão foi bem-sucedida
    if not start_date_iso or not end_date_iso:
        return jsonify({"error": "Erro ao converter datas para formato ISO"}), 400
    
    # Gerar relatório
    try:
        report = reports_service.get_detailed_financial_report(start_date_iso, end_date_iso)
        return jsonify(report), 200
    except Exception as e:
        return jsonify({"error": f"Erro ao gerar relatório: {str(e)}"}), 500  
