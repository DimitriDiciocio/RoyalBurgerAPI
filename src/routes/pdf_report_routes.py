"""
Rotas para geração de relatórios em PDF
Endpoints específicos para exportação de dados em formato PDF
"""

from flask import Blueprint, request, Response, jsonify
import logging
from ..services import reports_service, advanced_reports_service
from ..services.auth_service import require_role
from ..utils.validators import is_valid_date_format, convert_br_date_to_iso

pdf_reports_bp = Blueprint('pdf_reports', __name__)
logger = logging.getLogger(__name__)


@pdf_reports_bp.route('/users', methods=['GET'])
@require_role('admin')
def generate_users_pdf():
    """
    Gera relatório de usuários em PDF
    
    Parâmetros de Query (Filtros):
    - role: cargo do usuário (admin, manager, attendant, delivery, customer)
    - status: status do usuário (active, inactive)
    - created_after: data de criação (YYYY-MM-DD)
    - created_before: data de criação (YYYY-MM-DD)
    - search: busca geral por nome, email ou telefone
    """
    try:
        # Coleta filtros da query string
        filters = {}
        
        if request.args.get('role'):
            filters['role'] = request.args.get('role')
            
        if request.args.get('status'):
            status = request.args.get('status')
            if status in ['active', 'inactive']:
                filters['status'] = status == 'active'
                
        if request.args.get('created_after'):
            start_date = request.args.get('created_after')
            is_valid_format, format_msg = is_valid_date_format(start_date)
            if not is_valid_format:
                return jsonify({"error": f"Data de início inválida: {format_msg}"}), 400
            filters['created_after'] = convert_br_date_to_iso(start_date)
            
        if request.args.get('created_before'):
            end_date = request.args.get('created_before')
            is_valid_format, format_msg = is_valid_date_format(end_date)
            if not is_valid_format:
                return jsonify({"error": f"Data de fim inválida: {format_msg}"}), 400
            filters['created_before'] = convert_br_date_to_iso(end_date)
            
        if request.args.get('search'):
            filters['search'] = request.args.get('search')
        
        # Gera o PDF
        pdf_content = reports_service.generate_users_pdf_report(filters)
        
        # Retorna o PDF como resposta
        response = Response(
            pdf_content,
            mimetype='application/pdf'
        )
        response.headers['Content-Disposition'] = 'attachment; filename=relatorio_usuarios.pdf'
        return response
        
    except Exception as e:
        print(f"Erro ao gerar relatório de usuários: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500


@pdf_reports_bp.route('/ingredients', methods=['GET'])
@require_role('admin')
def generate_ingredients_pdf():
    """
    Gera relatório de ingredientes e estoque em PDF
    
    Parâmetros de Query (Filtros):
    - name: nome do ingrediente
    - stock_status: status do estoque (ok, low, out_of_stock, unavailable, available, overstock)
    - min_price: preço mínimo
    - max_price: preço máximo
    """
    try:
        # Coleta filtros da query string
        filters = {}
        
        if request.args.get('name'):
            filters['name'] = request.args.get('name')
            
        if request.args.get('stock_status'):
            filters['stock_status'] = request.args.get('stock_status')
            
        if request.args.get('min_price'):
            try:
                filters['min_price'] = float(request.args.get('min_price'))
            except ValueError:
                return jsonify({"error": "Preço mínimo deve ser um número válido"}), 400
                
        if request.args.get('max_price'):
            try:
                filters['max_price'] = float(request.args.get('max_price'))
            except ValueError:
                return jsonify({"error": "Preço máximo deve ser um número válido"}), 400
        
        # Gera o PDF
        pdf_content = reports_service.generate_ingredients_pdf_report(filters)
        
        # Retorna o PDF como resposta
        response = Response(
            pdf_content,
            mimetype='application/pdf'
        )
        response.headers['Content-Disposition'] = 'attachment; filename=relatorio_ingredientes.pdf'
        return response
        
    except Exception as e:
        print(f"Erro ao gerar relatório de ingredientes: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500


@pdf_reports_bp.route('/products', methods=['GET'])
@require_role('admin')
def generate_products_pdf():
    """
    Gera relatório de produtos e cardápio em PDF
    
    Parâmetros de Query (Filtros):
    - name: nome do produto
    - section_id: ID da seção/categoria
    - min_price: preço mínimo de venda
    - max_price: preço máximo de venda
    - status: status do produto (active, inactive)
    - include_inactive: incluir produtos inativos (true/false)
    """
    try:
        # Coleta filtros da query string
        filters = {}
        
        if request.args.get('name'):
            filters['name'] = request.args.get('name')
            
        if request.args.get('section_id'):
            try:
                filters['section_id'] = int(request.args.get('section_id'))
            except ValueError:
                return jsonify({"error": "ID da seção deve ser um número válido"}), 400
                
        if request.args.get('min_price'):
            try:
                filters['min_price'] = float(request.args.get('min_price'))
            except ValueError:
                return jsonify({"error": "Preço mínimo deve ser um número válido"}), 400
                
        if request.args.get('max_price'):
            try:
                filters['max_price'] = float(request.args.get('max_price'))
            except ValueError:
                return jsonify({"error": "Preço máximo deve ser um número válido"}), 400
                
        if request.args.get('status'):
            status = request.args.get('status')
            if status in ['active', 'inactive']:
                filters['status'] = status == 'active'
                
        if request.args.get('include_inactive'):
            filters['include_inactive'] = request.args.get('include_inactive').lower() == 'true'
        
        # Gera o PDF
        pdf_content = reports_service.generate_products_pdf_report(filters)
        
        # Retorna o PDF como resposta
        response = Response(
            pdf_content,
            mimetype='application/pdf'
        )
        response.headers['Content-Disposition'] = 'attachment; filename=relatorio_produtos.pdf'
        return response
        
    except Exception as e:
        print(f"Erro ao gerar relatório de produtos: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500


@pdf_reports_bp.route('/orders', methods=['GET'])
@require_role('admin')
def generate_orders_pdf():
    """
    Gera relatório de pedidos e vendas em PDF
    
    Parâmetros de Query (Filtros):
    - start_date: data de início (YYYY-MM-DD)
    - end_date: data de fim (YYYY-MM-DD)
    - status: status do pedido (pending, preparing, on_the_way, completed, cancelled)
    - sort_by: ordenação (date_desc, date_asc)
    """
    try:
        # Coleta filtros da query string
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
            
        if request.args.get('status'):
            filters['status'] = request.args.get('status')
            
        if request.args.get('sort_by'):
            sort_by = request.args.get('sort_by')
            if sort_by in ['date_desc', 'date_asc']:
                filters['sort_by'] = sort_by
        
        # Gera o PDF
        pdf_content = reports_service.generate_orders_pdf_report(filters)
        
        # Retorna o PDF como resposta
        response = Response(
            pdf_content,
            mimetype='application/pdf'
        )
        response.headers['Content-Disposition'] = 'attachment; filename=relatorio_pedidos.pdf'
        return response
        
    except Exception as e:
        print(f"Erro ao gerar relatório de pedidos: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500


@pdf_reports_bp.route('/sales/detailed', methods=['POST'])
@require_role('admin', 'manager')
def generate_detailed_sales_pdf():
    """
    Gera relatório de vendas detalhado com gráficos e análises
    
    Body (JSON):
    - start_date: data de início (YYYY-MM-DD) - opcional
    - end_date: data de fim (YYYY-MM-DD) - opcional
    - order_type: tipo de pedido (delivery, pickup, on_site) - opcional
    - payment_method: método de pagamento - opcional
    - status: status do pedido - opcional
    - customer_id: ID do cliente - opcional
    - product_id: ID do produto - opcional
    """
    try:
        filters = request.get_json() or {}
        
        # Gera o PDF
        pdf_content = advanced_reports_service.generate_detailed_sales_report(filters)
        
        # Retorna o PDF como resposta
        response = Response(
            pdf_content,
            mimetype='application/pdf'
        )
        response.headers['Content-Disposition'] = 'attachment; filename=relatorio_vendas_detalhado.pdf'
        return response
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Erro ao gerar relatório de vendas detalhado: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@pdf_reports_bp.route('/orders/performance', methods=['POST'])
@require_role('admin', 'manager')
def generate_orders_performance_pdf():
    """
    Gera relatório de performance de pedidos
    
    Body (JSON):
    - start_date: data de início (YYYY-MM-DD) - opcional
    - end_date: data de fim (YYYY-MM-DD) - opcional
    - attendant_id: ID do atendente - opcional
    - deliverer_id: ID do entregador - opcional
    - status: status do pedido - opcional
    - order_type: tipo de pedido - opcional
    """
    try:
        filters = request.get_json() or {}
        
        # Gera o PDF
        pdf_content = advanced_reports_service.generate_orders_performance_report(filters)
        
        # Retorna o PDF como resposta
        response = Response(
            pdf_content,
            mimetype='application/pdf'
        )
        response.headers['Content-Disposition'] = 'attachment; filename=relatorio_performance_pedidos.pdf'
        return response
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Erro ao gerar relatório de performance: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@pdf_reports_bp.route('/products/analysis', methods=['POST'])
@require_role('admin', 'manager')
def generate_products_analysis_pdf():
    """
    Gera relatório de análise de produtos
    
    Body (JSON):
    - start_date: data de início (YYYY-MM-DD) - opcional
    - end_date: data de fim (YYYY-MM-DD) - opcional
    - category_id: ID da categoria - opcional
    - product_id: ID do produto - opcional
    - price_min: preço mínimo - opcional
    - price_max: preço máximo - opcional
    - status: status (active, inactive) - opcional
    """
    try:
        filters = request.get_json() or {}
        
        # Gera o PDF
        pdf_content = advanced_reports_service.generate_products_analysis_report(filters)
        
        # Retorna o PDF como resposta
        response = Response(
            pdf_content,
            mimetype='application/pdf'
        )
        response.headers['Content-Disposition'] = 'attachment; filename=relatorio_analise_produtos.pdf'
        return response
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Erro ao gerar relatório de análise de produtos: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@pdf_reports_bp.route('/financial/complete', methods=['POST'])
@require_role('admin', 'manager')
def generate_complete_financial_pdf():
    """
    Gera relatório financeiro completo com gráficos e análises
    
    Body (JSON):
    - start_date: data de início (YYYY-MM-DD) - opcional
    - end_date: data de fim (YYYY-MM-DD) - opcional
    - type: tipo de movimentação (REVENUE, EXPENSE, CMV, TAX) - opcional
    - category: categoria - opcional
    - payment_status: status de pagamento (Pending, Paid) - opcional
    - payment_method: método de pagamento - opcional
    """
    try:
        filters = request.get_json() or {}
        
        # Gera o PDF
        pdf_content = advanced_reports_service.generate_complete_financial_report(filters)
        
        # Retorna o PDF como resposta
        response = Response(
            pdf_content,
            mimetype='application/pdf'
        )
        response.headers['Content-Disposition'] = 'attachment; filename=relatorio_financeiro_completo.pdf'
        return response
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Erro ao gerar relatório financeiro completo: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@pdf_reports_bp.route('/financial/cmv', methods=['POST'])
@require_role('admin', 'manager')
def generate_cmv_pdf():
    """
    Gera relatório de CMV (Custo das Mercadorias Vendidas)
    
    Body (JSON):
    - start_date: data de início (YYYY-MM-DD) - opcional
    - end_date: data de fim (YYYY-MM-DD) - opcional
    - category_id: ID da categoria - opcional
    - product_id: ID do produto - opcional
    """
    try:
        filters = request.get_json() or {}
        
        # Gera o PDF
        pdf_content = advanced_reports_service.generate_cmv_report_pdf(filters)
        
        # Retorna o PDF como resposta
        response = Response(
            pdf_content,
            mimetype='application/pdf'
        )
        response.headers['Content-Disposition'] = 'attachment; filename=relatorio_cmv.pdf'
        return response
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Erro ao gerar relatório de CMV: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@pdf_reports_bp.route('/financial/taxes', methods=['POST'])
@require_role('admin', 'manager')
def generate_taxes_pdf():
    """
    Gera relatório de impostos e taxas
    
    Body (JSON):
    - start_date: data de início (YYYY-MM-DD) - opcional
    - end_date: data de fim (YYYY-MM-DD) - opcional
    - category: categoria de imposto - opcional
    - status: status (Pending, Paid) - opcional
    """
    try:
        filters = request.get_json() or {}
        
        # Gera o PDF
        pdf_content = advanced_reports_service.generate_taxes_report_pdf(filters)
        
        # Retorna o PDF como resposta
        response = Response(
            pdf_content,
            mimetype='application/pdf'
        )
        response.headers['Content-Disposition'] = 'attachment; filename=relatorio_impostos.pdf'
        return response
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Erro ao gerar relatório de impostos: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@pdf_reports_bp.route('/stock/complete', methods=['POST'])
@require_role('admin', 'manager')
def generate_complete_stock_pdf():
    """Gera relatório completo de estoque"""
    try:
        filters = request.get_json() or {}
        pdf_content = advanced_reports_service.generate_complete_stock_report_pdf(filters)
        response = Response(pdf_content, mimetype='application/pdf')
        response.headers['Content-Disposition'] = 'attachment; filename=relatorio_estoque_completo.pdf'
        return response
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Erro ao gerar relatório de estoque: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@pdf_reports_bp.route('/purchases', methods=['POST'])
@require_role('admin', 'manager')
def generate_purchases_pdf():
    """Gera relatório de compras e fornecedores"""
    try:
        filters = request.get_json() or {}
        pdf_content = advanced_reports_service.generate_purchases_report_pdf(filters)
        response = Response(pdf_content, mimetype='application/pdf')
        response.headers['Content-Disposition'] = 'attachment; filename=relatorio_compras.pdf'
        return response
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Erro ao gerar relatório de compras: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@pdf_reports_bp.route('/customers/analysis', methods=['POST'])
@require_role('admin', 'manager')
def generate_customers_analysis_pdf():
    """Gera relatório de análise de clientes"""
    try:
        filters = request.get_json() or {}
        pdf_content = advanced_reports_service.generate_customers_analysis_report_pdf(filters)
        response = Response(pdf_content, mimetype='application/pdf')
        response.headers['Content-Disposition'] = 'attachment; filename=relatorio_analise_clientes.pdf'
        return response
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Erro ao gerar relatório de clientes: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@pdf_reports_bp.route('/loyalty', methods=['POST'])
@require_role('admin', 'manager')
def generate_loyalty_pdf():
    """Gera relatório de programa de fidelidade"""
    try:
        filters = request.get_json() or {}
        pdf_content = advanced_reports_service.generate_loyalty_report_pdf(filters)
        response = Response(pdf_content, mimetype='application/pdf')
        response.headers['Content-Disposition'] = 'attachment; filename=relatorio_fidelidade.pdf'
        return response
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Erro ao gerar relatório de fidelidade: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@pdf_reports_bp.route('/tables', methods=['POST'])
@require_role('admin', 'manager')
def generate_tables_pdf():
    """Gera relatório de mesas e salão"""
    try:
        filters = request.get_json() or {}
        pdf_content = advanced_reports_service.generate_tables_report_pdf(filters)
        response = Response(pdf_content, mimetype='application/pdf')
        response.headers['Content-Disposition'] = 'attachment; filename=relatorio_mesas.pdf'
        return response
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Erro ao gerar relatório de mesas: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@pdf_reports_bp.route('/executive/dashboard', methods=['POST'])
@require_role('admin', 'manager')
def generate_executive_dashboard_pdf():
    """Gera dashboard executivo"""
    try:
        filters = request.get_json() or {}
        pdf_content = advanced_reports_service.generate_executive_dashboard_pdf(filters)
        response = Response(pdf_content, mimetype='application/pdf')
        response.headers['Content-Disposition'] = 'attachment; filename=dashboard_executivo.pdf'
        return response
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Erro ao gerar dashboard executivo: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@pdf_reports_bp.route('/financial/reconciliation', methods=['POST'])
@require_role('admin', 'manager')
def generate_reconciliation_pdf():
    """Gera relatório de conciliação bancária"""
    try:
        filters = request.get_json() or {}
        pdf_content = advanced_reports_service.generate_reconciliation_report_pdf(filters)
        response = Response(pdf_content, mimetype='application/pdf')
        response.headers['Content-Disposition'] = 'attachment; filename=relatorio_conciliacao.pdf'
        return response
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Erro ao gerar relatório de conciliação: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@pdf_reports_bp.route('/available', methods=['GET'])
@require_role('admin')
def get_available_reports():
    """
    Retorna lista de relatórios disponíveis
    """
    available_reports = [
        {
            "type": "users",
            "name": "Relatório de Usuários",
            "description": "Lista todos os usuários do sistema com filtros por cargo, status e data",
            "endpoint": "/pdf_reports/users",
            "method": "GET",
            "filters": ["role", "status", "created_after", "created_before", "search"]
        },
        {
            "type": "ingredients",
            "name": "Relatório de Ingredientes",
            "description": "Lista ingredientes e status do estoque com filtros por nome, status e preço",
            "endpoint": "/pdf_reports/ingredients",
            "method": "GET",
            "filters": ["name", "stock_status", "min_price", "max_price"]
        },
        {
            "type": "products",
            "name": "Relatório de Produtos",
            "description": "Lista produtos do cardápio com filtros por seção, preço e status",
            "endpoint": "/pdf_reports/products",
            "method": "GET",
            "filters": ["name", "section_id", "min_price", "max_price", "status", "include_inactive"]
        },
        {
            "type": "orders",
            "name": "Relatório de Pedidos",
            "description": "Lista pedidos e vendas com filtros por data, status e ordenação",
            "endpoint": "/pdf_reports/orders",
            "method": "GET",
            "filters": ["start_date", "end_date", "status", "sort_by"]
        },
        {
            "type": "sales_detailed",
            "name": "Relatório de Vendas Detalhado",
            "description": "Relatório completo de vendas com gráficos, análises e métricas avançadas",
            "endpoint": "/pdf_reports/sales/detailed",
            "method": "POST",
            "filters": ["start_date", "end_date", "order_type", "payment_method", "status", "customer_id", "product_id"]
        },
        {
            "type": "orders_performance",
            "name": "Relatório de Performance de Pedidos",
            "description": "Análise de eficiência operacional com tempos médios e performance de funcionários",
            "endpoint": "/pdf_reports/orders/performance",
            "method": "POST",
            "filters": ["start_date", "end_date", "attendant_id", "deliverer_id", "status", "order_type"]
        },
        {
            "type": "products_analysis",
            "name": "Relatório de Análise de Produtos",
            "description": "Análise detalhada de produtos com margem de lucro, CMV e rankings",
            "endpoint": "/pdf_reports/products/analysis",
            "method": "POST",
            "filters": ["start_date", "end_date", "category_id", "product_id", "price_min", "price_max", "status"]
        },
        {
            "type": "financial_complete",
            "name": "Relatório Financeiro Completo",
            "description": "Relatório financeiro completo com fluxo de caixa, receitas, despesas e margens",
            "endpoint": "/pdf_reports/financial/complete",
            "method": "POST",
            "filters": ["start_date", "end_date", "type", "category", "payment_status", "payment_method"]
        },
        {
            "type": "cmv",
            "name": "Relatório de CMV",
            "description": "Análise detalhada de Custo das Mercadorias Vendidas por categoria e produto",
            "endpoint": "/pdf_reports/financial/cmv",
            "method": "POST",
            "filters": ["start_date", "end_date", "category_id", "product_id"]
        },
        {
            "type": "taxes",
            "name": "Relatório de Impostos e Taxas",
            "description": "Análise de impostos pagos, pendentes e impacto na receita",
            "endpoint": "/pdf_reports/financial/taxes",
            "method": "POST",
            "filters": ["start_date", "end_date", "category", "status"]
        },
        {
            "type": "stock_complete",
            "name": "Relatório Completo de Estoque",
            "description": "Análise detalhada de estoque com giro, valor e ingredientes mais utilizados",
            "endpoint": "/pdf_reports/stock/complete",
            "method": "POST",
            "filters": ["status", "category", "supplier", "price_min", "price_max"]
        },
        {
            "type": "purchases",
            "name": "Relatório de Compras e Fornecedores",
            "description": "Análise de compras por fornecedor, item e frequência",
            "endpoint": "/pdf_reports/purchases",
            "method": "POST",
            "filters": ["start_date", "end_date", "supplier", "payment_status"]
        },
        {
            "type": "customers_analysis",
            "name": "Relatório de Análise de Clientes",
            "description": "Análise RFV, top clientes e identificação de clientes inativos",
            "endpoint": "/pdf_reports/customers/analysis",
            "method": "POST",
            "filters": ["start_date", "end_date", "region", "min_orders", "min_spent"]
        },
        {
            "type": "loyalty",
            "name": "Relatório de Programa de Fidelidade",
            "description": "Análise de pontos acumulados, resgatados e top participantes",
            "endpoint": "/pdf_reports/loyalty",
            "method": "POST",
            "filters": ["start_date", "end_date", "user_id"]
        },
        {
            "type": "tables",
            "name": "Relatório de Mesas e Salão",
            "description": "Análise de ocupação, rotatividade e receita por mesa",
            "endpoint": "/pdf_reports/tables",
            "method": "POST",
            "filters": ["start_date", "end_date", "table_id", "attendant_id"]
        },
        {
            "type": "executive_dashboard",
            "name": "Dashboard Executivo",
            "description": "Visão geral consolidada com KPIs principais e alertas",
            "endpoint": "/pdf_reports/executive/dashboard",
            "method": "POST",
            "filters": ["start_date", "end_date"]
        },
        {
            "type": "reconciliation",
            "name": "Relatório de Conciliação Bancária",
            "description": "Análise de movimentações conciliadas vs. pendentes",
            "endpoint": "/pdf_reports/financial/reconciliation",
            "method": "POST",
            "filters": ["start_date", "end_date", "payment_gateway", "bank_account", "reconciled"]
        }
    ]
    
    return jsonify({
        "available_reports": available_reports,
        "total": len(available_reports)
    }), 200
