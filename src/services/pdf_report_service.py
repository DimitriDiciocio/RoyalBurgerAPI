"""
Serviço de Geração de Relatórios em PDF
Utiliza fpdf2 para criar relatórios dinâmicos e filtráveis
"""

from fpdf import FPDF
from datetime import datetime
import io


class BaseReportPDF(FPDF):
    """
    Classe base para geração de relatórios em PDF
    Contém elementos comuns a todos os relatórios
    """
    
    def __init__(self, title="Relatório", orientation='P', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.title = title
        self.set_auto_page_break(auto=True, margin=15)
        
        # Usa fontes padrão do fpdf2 (sem dependência de arquivos externos)
        # self.add_font('DejaVu', '', 'DejaVuSansCondensed.ttf', uni=True)
        # self.add_font('DejaVu', 'B', 'DejaVuSansCondensed-Bold.ttf', uni=True)
        
    def header(self):
        """Cabeçalho padrão para todos os relatórios"""
        # Logo e título
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'ROYAL BURGER', 0, 1, 'C')
        
        self.set_font('Arial', 'B', 14)
        self.cell(0, 8, self.title, 0, 1, 'C')
        
        # Linha separadora
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)
        
    def footer(self):
        """Rodapé padrão para todos os relatórios"""
        # Posiciona o rodapé a 15mm do final da página
        self.set_y(-15)
        
        # Data de emissão
        self.set_font('Arial', '', 8)
        self.cell(0, 5, f'Emitido em: {datetime.now().strftime("%d/%m/%Y às %H:%M")}', 0, 0, 'L')
        
        # Número da página
        self.cell(0, 5, f'Página {self.page_no()}', 0, 0, 'R')
        
    def add_summary_section(self, summary_data):
        """Adiciona seção de resumo no topo do relatório"""
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'RESUMO', 0, 1, 'L')
        
        self.set_font('Arial', '', 10)
        for key, value in summary_data.items():
            self.cell(60, 6, f'{key}:', 0, 0, 'L')
            self.cell(0, 6, str(value), 0, 1, 'L')
        
        self.ln(5)
        
    def add_table(self, headers, data, col_widths=None):
        """
        Adiciona uma tabela ao PDF
        
        Args:
            headers: Lista com os cabeçalhos das colunas
            data: Lista de listas com os dados das linhas
            col_widths: Lista com larguras das colunas (opcional)
        """
        if not data:
            self.set_font('Arial', '', 10)
            self.cell(0, 6, 'Nenhum dado encontrado para os filtros aplicados.', 0, 1, 'C')
            return
            
        # Calcula larguras das colunas se não fornecidas
        if not col_widths:
            total_width = 190  # Largura útil da página
            col_widths = [total_width // len(headers)] * len(headers)
        
        # Cabeçalho da tabela
        self.set_font('Arial', 'B', 10)
        for i, header in enumerate(headers):
            self.cell(col_widths[i], 8, str(header), 1, 0, 'C')
        self.ln()
        
        # Dados da tabela
        self.set_font('Arial', '', 9)
        for row in data:
            for i, cell in enumerate(row):
                # Trunca texto muito longo
                cell_text = str(cell)
                if len(cell_text) > 25:
                    cell_text = cell_text[:22] + '...'
                self.cell(col_widths[i], 6, cell_text, 1, 0, 'C')
            self.ln()
            
    def add_filters_info(self, filters):
        """Adiciona informações sobre os filtros aplicados"""
        if not filters:
            return
            
        self.set_font('Arial', 'B', 10)
        self.cell(0, 6, 'FILTROS APLICADOS:', 0, 1, 'L')
        
        self.set_font('Arial', '', 9)
        for key, value in filters.items():
            if value is not None and value != '':
                self.cell(0, 5, f'• {key}: {value}', 0, 1, 'L')
        
        self.ln(3)


class UsersReportPDF(BaseReportPDF):
    """Relatório específico para usuários do sistema"""
    
    def __init__(self):
        super().__init__("Relatório de Usuários do Sistema")
        
    def generate_report(self, users_data, filters=None, summary=None):
        """Gera o relatório completo de usuários"""
        self.add_page()
        
        # Adiciona informações de filtros se aplicáveis
        if filters:
            self.add_filters_info(filters)
            
        # Adiciona resumo se fornecido
        if summary:
            self.add_summary_section(summary)
            
        # Cabeçalhos da tabela
        headers = ['ID', 'Nome Completo', 'Email', 'CPF', 'Cargo', 'Status', 'Data Criação']
        col_widths = [15, 50, 50, 25, 20, 15, 25]
        
        # Prepara dados para a tabela
        table_data = []
        for user in users_data:
            table_data.append([
                user.get('id', ''),
                user.get('full_name', ''),
                user.get('email', ''),
                user.get('cpf', '') or 'N/A',
                user.get('role', ''),
                'Ativo' if user.get('is_active', True) else 'Inativo',
                user.get('created_at', '')[:10] if user.get('created_at') else 'N/A'
            ])
            
        self.add_table(headers, table_data, col_widths)


class IngredientsReportPDF(BaseReportPDF):
    """Relatório específico para ingredientes e estoque"""
    
    def __init__(self):
        super().__init__("Relatório de Ingredientes e Estoque")
        
    def generate_report(self, ingredients_data, filters=None, summary=None):
        """Gera o relatório completo de ingredientes"""
        self.add_page()
        
        # Adiciona informações de filtros se aplicáveis
        if filters:
            self.add_filters_info(filters)
            
        # Adiciona resumo se fornecido
        if summary:
            self.add_summary_section(summary)
            
        # Cabeçalhos da tabela
        headers = ['ID', 'Nome', 'Preço Custo', 'Estoque Atual', 'Unidade', 'Estoque Mín', 'Status']
        col_widths = [15, 40, 25, 25, 20, 25, 20]
        
        # Prepara dados para a tabela
        table_data = []
        for ingredient in ingredients_data:
            # Determina status do estoque
            current_stock = float(ingredient.get('current_stock', 0))
            min_threshold = float(ingredient.get('min_stock_threshold', 0))
            
            if current_stock == 0:
                status = 'Esgotado'
            elif current_stock <= min_threshold:
                status = 'Baixo'
            else:
                status = 'OK'
                
            table_data.append([
                ingredient.get('id', ''),
                ingredient.get('name', ''),
                f"R$ {float(ingredient.get('price', 0)):.2f}",
                f"{current_stock:.1f}",
                ingredient.get('stock_unit', ''),
                f"{min_threshold:.1f}",
                status
            ])
            
        self.add_table(headers, table_data, col_widths)


class ProductsReportPDF(BaseReportPDF):
    """Relatório específico para produtos e cardápio"""
    
    def __init__(self):
        super().__init__("Relatório de Produtos e Cardápio")
        
    def generate_report(self, products_data, filters=None, summary=None):
        """Gera o relatório completo de produtos"""
        self.add_page()
        
        # Adiciona informações de filtros se aplicáveis
        if filters:
            self.add_filters_info(filters)
            
        # Adiciona resumo se fornecido
        if summary:
            self.add_summary_section(summary)
            
        # Cabeçalhos da tabela
        headers = ['ID', 'Nome', 'Seção', 'Preço Venda', 'Preço Custo', 'Status']
        col_widths = [15, 50, 30, 25, 25, 20]
        
        # Prepara dados para a tabela
        table_data = []
        for product in products_data:
            table_data.append([
                product.get('id', ''),
                product.get('name', ''),
                product.get('category_name', 'N/A'),
                f"R$ {float(product.get('price', 0)):.2f}",
                f"R$ {float(product.get('cost_price', 0)):.2f}",
                'Disponível' if product.get('is_active', True) else 'Indisponível'
            ])
            
        self.add_table(headers, table_data, col_widths)


class OrdersReportPDF(BaseReportPDF):
    """Relatório específico para pedidos e vendas"""
    
    def __init__(self):
        super().__init__("Relatório de Pedidos e Vendas")
        
    def generate_report(self, orders_data, filters=None, summary=None):
        """Gera o relatório completo de pedidos"""
        self.add_page()
        
        # Adiciona informações de filtros se aplicáveis
        if filters:
            self.add_filters_info(filters)
            
        # Adiciona resumo se fornecido
        if summary:
            self.add_summary_section(summary)
            
        # Cabeçalhos da tabela
        headers = ['ID Pedido', 'Data/Hora', 'Cliente', 'Tipo', 'Status', 'Valor Total']
        col_widths = [20, 30, 50, 20, 25, 25]
        
        # Prepara dados para a tabela
        table_data = []
        for order in orders_data:
            # Formata data/hora
            created_at = order.get('created_at', '')
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    formatted_date = dt.strftime('%d/%m/%Y %H:%M')
                except:
                    formatted_date = created_at[:16]
            else:
                formatted_date = 'N/A'
                
            table_data.append([
                order.get('id', ''),
                formatted_date,
                order.get('customer_name', ''),
                order.get('order_type', 'Delivery'),
                order.get('status', '').title(),
                f"R$ {float(order.get('total_amount', 0)):.2f}"
            ])
            
        self.add_table(headers, table_data, col_widths)


def generate_pdf_report(report_type, data, filters=None, summary=None):
    """
    Função principal para gerar relatórios em PDF
    
    Args:
        report_type: Tipo do relatório ('users', 'ingredients', 'products', 'orders')
        data: Dados para o relatório
        filters: Filtros aplicados (opcional)
        summary: Resumo do relatório (opcional)
        
    Returns:
        bytes: Conteúdo do PDF em bytes
    """
    
    # Cria instância do relatório apropriado
    if report_type == 'users':
        pdf = UsersReportPDF()
    elif report_type == 'ingredients':
        pdf = IngredientsReportPDF()
    elif report_type == 'products':
        pdf = ProductsReportPDF()
    elif report_type == 'orders':
        pdf = OrdersReportPDF()
    else:
        raise ValueError(f"Tipo de relatório inválido: {report_type}")
    
    # Gera o relatório
    pdf.generate_report(data, filters, summary)
    
    # Retorna o PDF como bytes
    pdf_content = pdf.output(dest='S')
    if isinstance(pdf_content, str):
        pdf_content = pdf_content.encode('latin-1')
    elif isinstance(pdf_content, bytearray):
        pdf_content = bytes(pdf_content)
    
    # Garante que é bytes
    if not isinstance(pdf_content, bytes):
        pdf_content = str(pdf_content).encode('utf-8')
    
    return pdf_content
