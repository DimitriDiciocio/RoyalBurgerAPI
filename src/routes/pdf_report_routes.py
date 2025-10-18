"""
Rotas para geração de relatórios em PDF
Endpoints específicos para exportação de dados em formato PDF
"""

from flask import Blueprint, request, Response, jsonify
from ..services import reports_service
from ..services.auth_service import require_role
from ..utils.validators import is_valid_date_format, convert_br_date_to_iso

pdf_reports_bp = Blueprint('pdf_reports', __name__)


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
            "filters": ["role", "status", "created_after", "created_before", "search"]
        },
        {
            "type": "ingredients",
            "name": "Relatório de Ingredientes",
            "description": "Lista ingredientes e status do estoque com filtros por nome, status e preço",
            "endpoint": "/pdf_reports/ingredients",
            "filters": ["name", "stock_status", "min_price", "max_price"]
        },
        {
            "type": "products",
            "name": "Relatório de Produtos",
            "description": "Lista produtos do cardápio com filtros por seção, preço e status",
            "endpoint": "/pdf_reports/products",
            "filters": ["name", "section_id", "min_price", "max_price", "status", "include_inactive"]
        },
        {
            "type": "orders",
            "name": "Relatório de Pedidos",
            "description": "Lista pedidos e vendas com filtros por data, status e ordenação",
            "endpoint": "/pdf_reports/orders",
            "filters": ["start_date", "end_date", "status", "sort_by"]
        }
    ]
    
    return jsonify({
        "available_reports": available_reports,
        "total": len(available_reports)
    }), 200
