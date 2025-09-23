from flask import Blueprint, request, jsonify, g  # importa Blueprint, request, jsonify e g
from ..services import financial_service  # importa o serviço financeiro
from ..services.auth_service import require_role  # importa decorator de autorização por papel

financial_bp = Blueprint('financials', __name__)  # cria o blueprint financeiro

@financial_bp.route('/summary', methods=['GET'])  # define rota GET para resumo financeiro (KPIs)
@require_role('admin')  # restringe a administradores
def get_financial_summary_route():  # função handler do resumo
    period = request.args.get('period', 'this_month')  # extrai período da query string
    summary = financial_service.get_financial_summary(period)  # busca resumo no serviço
    return jsonify(summary), 200  # retorna resumo com status 200

@financial_bp.route('/transactions', methods=['GET'])  # define rota GET para listar transações
@require_role('admin')  # restringe a administradores
def get_financial_transactions_route():  # função handler da listagem de transações
    filters = {}  # inicia dicionário de filtros
    if request.args.get('start_date'):  # filtra por data inicial
        filters['start_date'] = request.args.get('start_date')  # adiciona filtro
    if request.args.get('end_date'):  # filtra por data final
        filters['end_date'] = request.args.get('end_date')  # adiciona filtro
    if request.args.get('type'):  # filtra por tipo
        filters['type'] = request.args.get('type')  # adiciona filtro
    transactions = financial_service.get_financial_transactions(filters)  # busca transações no serviço
    return jsonify(transactions), 200  # retorna lista com status 200

@financial_bp.route('/transactions', methods=['POST'])  # define rota POST para criar transação
@require_role('admin')  # restringe a administradores
def create_financial_transaction_route():  # função handler de criação de transação
    data = request.get_json()  # captura corpo JSON
    if not data:  # valida corpo não vazio
        return jsonify({"error": "Corpo da requisição não pode ser vazio"}), 400  # retorna 400
    user_id = g.current_user_id if hasattr(g, 'current_user_id') else None  # obtém ID do usuário do contexto
    if not user_id:  # valida autenticação
        return jsonify({"error": "Usuário não autenticado"}), 401  # retorna 401
    success, error_code, result = financial_service.create_financial_transaction(data, user_id)  # delega criação ao serviço
    if success:  # criado com sucesso
        return jsonify(result), 201  # retorna 201 com resultado
    elif error_code in ["INVALID_DESCRIPTION", "INVALID_AMOUNT", "INVALID_TYPE"]:  # validações
        return jsonify({"error": result}), 400  # retorna 400
    else:  # erro interno
        return jsonify({"error": "Erro interno do servidor"}), 500  # retorna 500
