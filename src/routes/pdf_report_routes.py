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


@pdf_reports_bp.route('/test', methods=['GET'])
def test_reports_page():
    """
    Página de teste para acessar todos os relatórios sem autenticação
    ATENÇÃO: Esta rota é apenas para desenvolvimento/teste. Remover em produção!
    """
    html_content = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Teste de Relatórios PDF - Royal Burger</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            padding: 30px;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 2em;
        }
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 0.9em;
        }
        .warning {
            background: #fff3cd;
            border: 1px solid #ffc107;
            border-radius: 5px;
            padding: 15px;
            margin-bottom: 30px;
            color: #856404;
        }
        .warning strong {
            display: block;
            margin-bottom: 5px;
        }
        .report-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        .report-card {
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            padding: 20px;
            transition: all 0.3s ease;
            background: #f9f9f9;
        }
        .report-card:hover {
            border-color: #667eea;
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.3);
            transform: translateY(-2px);
        }
        .report-card h3 {
            color: #333;
            margin-bottom: 10px;
            font-size: 1.2em;
        }
        .report-card p {
            color: #666;
            font-size: 0.9em;
            margin-bottom: 15px;
            line-height: 1.5;
        }
        .report-card .btn {
            display: inline-block;
            padding: 10px 20px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            transition: background 0.3s ease;
            font-weight: bold;
            margin-right: 10px;
            margin-bottom: 5px;
        }
        .report-card .btn:hover {
            background: #5568d3;
        }
        .report-card .btn-secondary {
            background: #6c757d;
        }
        .report-card .btn-secondary:hover {
            background: #5a6268;
        }
        .loading {
            display: none;
            text-align: center;
            padding: 20px;
            color: #667eea;
        }
        .loading.active {
            display: block;
        }
        .date-inputs {
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #e0e0e0;
        }
        .date-inputs label {
            display: block;
            margin-bottom: 5px;
            color: #333;
            font-weight: bold;
            font-size: 0.85em;
        }
        .date-inputs input {
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            margin-bottom: 10px;
            font-size: 0.9em;
        }
        .date-inputs button {
            width: 100%;
            padding: 10px;
            background: #28a745;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-weight: bold;
            margin-top: 5px;
        }
        .date-inputs button:hover {
            background: #218838;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Teste de Relatórios PDF</h1>
        <p class="subtitle">Royal Burger - Sistema de Relatórios</p>
        
        <div class="warning">
            <strong>⚠️ ATENÇÃO: Rota de Teste</strong>
            Esta página é apenas para desenvolvimento e testes. Em produção, esta rota deve ser removida ou protegida com autenticação.
        </div>
        
        <div class="loading" id="loading">
            <p>⏳ Gerando relatório... Aguarde...</p>
        </div>
        
        <div class="report-grid" id="reports-grid">
            <!-- Relatórios serão inseridos aqui via JavaScript -->
        </div>
    </div>
    
    <script>
        // Função para obter data formatada
        function getDate(daysAgo = 0) {
            const date = new Date();
            date.setDate(date.getDate() - daysAgo);
            return date.toISOString().split('T')[0];
        }
        
        // Função para gerar relatório
        function generateReport(endpoint, method, filters = {}) {
            const loading = document.getElementById('loading');
            loading.classList.add('active');
            
            const url = `/api/pdf_reports/test${endpoint}`;
            const body = JSON.stringify(filters);
            
            fetch(url, {
                method: method,
                headers: {
                    'Content-Type': 'application/json'
                },
                body: method === 'POST' ? body : null
            })
            .then(response => {
                if (response.ok) {
                    return response.blob();
                }
                throw new Error(`Erro ${response.status}: ${response.statusText}`);
            })
            .then(blob => {
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = endpoint.split('/').pop() + '.pdf';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                loading.classList.remove('active');
                alert('Relatório gerado com sucesso!');
            })
            .catch(error => {
                loading.classList.remove('active');
                alert('Erro ao gerar relatório: ' + error.message);
                console.error('Erro:', error);
            });
        }
        
        // Função para gerar com datas customizadas
        function generateWithDates(endpoint, method, cardId) {
            const startDate = document.getElementById(`start-${cardId}`).value;
            const endDate = document.getElementById(`end-${cardId}`).value;
            
            if (!startDate || !endDate) {
                alert('Por favor, preencha ambas as datas');
                return;
            }
            
            generateReport(endpoint, method, {
                start_date: startDate,
                end_date: endDate
            });
        }
        
        // Lista de relatórios
        const reports = [
            {
                id: 'sales-detailed',
                title: 'Relatório de Vendas Detalhado',
                description: 'Relatório completo de vendas com gráficos de linha, pizza e barras. Inclui análise de tendências, métodos de pagamento e top produtos.',
                endpoint: '/sales/detailed',
                method: 'POST',
                hasDates: true
            },
            {
                id: 'products-analysis',
                title: 'Análise de Produtos',
                description: 'Análise detalhada de produtos com gráficos de barras mostrando top produtos por quantidade e receita.',
                endpoint: '/products/analysis',
                method: 'POST',
                hasDates: true
            },
            {
                id: 'financial-complete',
                title: 'Relatório Financeiro Completo',
                description: 'Relatório financeiro completo com múltiplos gráficos de fluxo de caixa, receitas e despesas por categoria.',
                endpoint: '/financial/complete',
                method: 'POST',
                hasDates: true
            },
            {
                id: 'orders-performance',
                title: 'Performance de Pedidos',
                description: 'Análise de eficiência operacional com tempos médios e performance de funcionários.',
                endpoint: '/orders/performance',
                method: 'POST',
                hasDates: true
            },
            {
                id: 'executive-dashboard',
                title: 'Dashboard Executivo',
                description: 'Dashboard executivo consolidado com KPIs principais e múltiplos gráficos de tendências.',
                endpoint: '/executive/dashboard',
                method: 'POST',
                hasDates: true
            },
            {
                id: 'cmv',
                title: 'Relatório de CMV',
                description: 'Análise detalhada de Custo das Mercadorias Vendidas por categoria e produto.',
                endpoint: '/financial/cmv',
                method: 'POST',
                hasDates: true
            },
            {
                id: 'taxes',
                title: 'Relatório de Impostos',
                description: 'Análise de impostos pagos, pendentes e impacto na receita.',
                endpoint: '/financial/taxes',
                method: 'POST',
                hasDates: true
            },
            {
                id: 'stock-complete',
                title: 'Relatório Completo de Estoque',
                description: 'Análise detalhada de estoque com giro, valor e ingredientes mais utilizados.',
                endpoint: '/stock/complete',
                method: 'POST',
                hasDates: false
            },
            {
                id: 'purchases',
                title: 'Relatório de Compras',
                description: 'Análise de compras por fornecedor, item e frequência.',
                endpoint: '/purchases',
                method: 'POST',
                hasDates: true
            },
            {
                id: 'customers-analysis',
                title: 'Análise de Clientes',
                description: 'Análise RFV, top clientes e identificação de clientes inativos.',
                endpoint: '/customers/analysis',
                method: 'POST',
                hasDates: true
            },
            {
                id: 'loyalty',
                title: 'Programa de Fidelidade',
                description: 'Análise de pontos acumulados, resgatados e top participantes.',
                endpoint: '/loyalty',
                method: 'POST',
                hasDates: true
            },
            {
                id: 'tables',
                title: 'Relatório de Mesas',
                description: 'Análise de ocupação, rotatividade e receita por mesa.',
                endpoint: '/tables',
                method: 'POST',
                hasDates: true
            }
        ];
        
        // Renderizar relatórios
        const grid = document.getElementById('reports-grid');
        reports.forEach((report, index) => {
            const card = document.createElement('div');
            card.className = 'report-card';
            card.innerHTML = `
                <h3>${report.title}</h3>
                <p>${report.description}</p>
                <a href="#" class="btn" onclick="generateReport('${report.endpoint}', '${report.method}', {}); return false;">
                    📄 Gerar (Últimos 30 dias)
                </a>
                ${report.hasDates ? `
                <div class="date-inputs">
                    <label>Data Início:</label>
                    <input type="date" id="start-${report.id}" value="${getDate(30)}">
                    <label>Data Fim:</label>
                    <input type="date" id="end-${report.id}" value="${getDate(0)}">
                    <button onclick="generateWithDates('${report.endpoint}', '${report.method}', '${report.id}')">
                        📅 Gerar com Datas
                    </button>
                </div>
                ` : ''}
            `;
            grid.appendChild(card);
        });
    </script>
</body>
</html>
    """
    return html_content, 200, {'Content-Type': 'text/html; charset=utf-8'}


@pdf_reports_bp.route('/test/<path:report_type>', methods=['GET', 'POST'])
def test_report_direct(report_type):
    """
    Rota de teste direta para gerar relatórios sem autenticação
    ATENÇÃO: Esta rota é apenas para desenvolvimento/teste. Remover em produção!
    
    Exemplos:
    - GET /api/pdf_reports/test/sales/detailed
    - GET /api/pdf_reports/test/products/analysis?start_date=2024-01-01&end_date=2024-01-31
    """
    try:
        # Mapeamento de tipos de relatório
        report_map = {
            'sales/detailed': ('generate_detailed_sales_report', {}),
            'products/analysis': ('generate_products_analysis_report', {}),
            'financial/complete': ('generate_complete_financial_report', {}),
            'orders/performance': ('generate_orders_performance_report', {}),
            'executive/dashboard': ('generate_executive_dashboard_pdf', {}),
            'financial/cmv': ('generate_cmv_report_pdf', {}),
            'financial/taxes': ('generate_taxes_report_pdf', {}),
            'stock/complete': ('generate_complete_stock_report_pdf', {}),
            'purchases': ('generate_purchases_report_pdf', {}),
            'customers/analysis': ('generate_customers_analysis_report_pdf', {}),
            'loyalty': ('generate_loyalty_report_pdf', {}),
            'tables': ('generate_tables_report_pdf', {})
        }
        
        # Verificar se o tipo de relatório existe
        if report_type not in report_map:
            return jsonify({
                "error": f"Tipo de relatório '{report_type}' não encontrado",
                "available_types": list(report_map.keys())
            }), 404
        
        # Obter função e filtros padrão
        function_name, default_filters = report_map[report_type]
        
        # Obter filtros da query string ou body
        if request.method == 'GET':
            filters = dict(request.args)
        else:
            filters = request.get_json() or {}
        
        # Mesclar com filtros padrão
        filters = {**default_filters, **filters}
        
        # Se não houver datas, usar últimos 30 dias
        if 'start_date' not in filters and 'end_date' not in filters:
            from datetime import datetime, timedelta
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            filters['start_date'] = start_date.strftime('%Y-%m-%d')
            filters['end_date'] = end_date.strftime('%Y-%m-%d')
        
        # Importar e chamar função
        func = getattr(advanced_reports_service, function_name)
        pdf_content = func(filters)
        
        # Retornar PDF
        response = Response(
            pdf_content,
            mimetype='application/pdf'
        )
        response.headers['Content-Disposition'] = f'attachment; filename=relatorio_{report_type.replace("/", "_")}.pdf'
        return response
        
    except AttributeError as e:
        logger.error(f"Função de relatório não encontrada: {e}", exc_info=True)
        return jsonify({"error": f"Função de relatório não encontrada: {function_name}"}), 500
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Erro ao gerar relatório de teste: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor ao gerar relatório"}), 500