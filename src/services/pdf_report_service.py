"""
Serviço de Geração de Relatórios em PDF
Utiliza fpdf2 para criar relatórios dinâmicos e filtráveis
"""

from fpdf import FPDF
from datetime import datetime
import io
import base64
import logging
from PIL import Image

logger = logging.getLogger(__name__)


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
    
    def add_chart(self, chart_base64, width=190, height=100, title=None):
        """
        Adiciona gráfico ao PDF a partir de base64
        
        Args:
            chart_base64: String base64 da imagem do gráfico
            width: Largura em mm (padrão: 190mm - largura útil da página)
            height: Altura em mm (padrão: 100mm)
            title: Título opcional para o gráfico
        """
        if not chart_base64:
            logger.warning("Tentativa de adicionar gráfico vazio ao PDF")
            return
        
        try:
            # Decodifica imagem base64
            image_data = base64.b64decode(chart_base64)
            image = Image.open(io.BytesIO(image_data))
            
            # Verifica se precisa quebrar página
            if self.get_y() + height > self.h - 20:
                self.add_page()
            
            # Adiciona título se fornecido
            if title:
                self.set_font('Arial', 'B', 11)
                self.cell(0, 6, title, 0, 1, 'L')
                self.ln(2)
            
            # Calcula posição X para centralizar (se necessário)
            x_position = (self.w - width) / 2
            
            # Adiciona imagem ao PDF
            self.image(image, x=x_position, y=self.get_y(), w=width, h=height)
            self.ln(height + 5)
            
        except Exception as e:
            logger.error(f"Erro ao adicionar gráfico ao PDF: {e}", exc_info=True)
            # Adiciona mensagem de erro no PDF
            self.set_font('Arial', '', 9)
            self.set_text_color(255, 0, 0)
            self.cell(0, 6, f'Erro ao carregar gráfico: {str(e)[:50]}', 0, 1, 'L')
            self.set_text_color(0, 0, 0)
            self.ln(2)
    
    def add_metric_card(self, label, value, comparison=None, comparison_label=None):
        """
        Adiciona card de métrica (KPI) ao PDF
        
        Args:
            label: Rótulo da métrica (ex: "Total de Vendas")
            value: Valor da métrica (formatado como string)
            comparison: Valor de comparação opcional (ex: "+15.5%")
            comparison_label: Rótulo da comparação (ex: "vs. período anterior")
        """
        # Verifica se precisa quebrar página
        if self.get_y() + 15 > self.h - 20:
            self.add_page()
        
        # Desenha borda do card
        x_start = self.get_x()
        y_start = self.get_y()
        card_width = 90  # Largura do card (2 por linha)
        card_height = 20
        
        # Verifica se há espaço para 2 cards na mesma linha
        if x_start + card_width * 2 <= self.w - 10:
            # Card na esquerda
            self.rect(x_start, y_start, card_width, card_height)
            
            # Label
            self.set_font('Arial', '', 9)
            self.set_xy(x_start + 3, y_start + 2)
            self.cell(card_width - 6, 5, str(label), 0, 0, 'L')
            
            # Valor
            self.set_font('Arial', 'B', 12)
            self.set_xy(x_start + 3, y_start + 8)
            self.cell(card_width - 6, 7, str(value), 0, 0, 'L')
            
            # Comparação se fornecida
            if comparison is not None:
                self.set_font('Arial', '', 8)
                self.set_xy(x_start + 3, y_start + 15)
                comparison_text = str(comparison)
                if comparison_label:
                    comparison_text += f" {comparison_label}"
                self.cell(card_width - 6, 4, comparison_text, 0, 0, 'L')
            
            # Move para próximo card (direita)
            self.set_xy(x_start + card_width + 5, y_start)
        else:
            # Card único (ocupa linha inteira)
            card_width = 190
            self.rect(x_start, y_start, card_width, card_height)
            
            # Label
            self.set_font('Arial', '', 9)
            self.set_xy(x_start + 3, y_start + 2)
            self.cell(card_width - 6, 5, str(label), 0, 0, 'L')
            
            # Valor
            self.set_font('Arial', 'B', 12)
            self.set_xy(x_start + 3, y_start + 8)
            self.cell(card_width - 6, 7, str(value), 0, 0, 'L')
            
            # Comparação se fornecida
            if comparison is not None:
                self.set_font('Arial', '', 8)
                self.set_xy(x_start + 3, y_start + 15)
                comparison_text = str(comparison)
                if comparison_label:
                    comparison_text += f" {comparison_label}"
                self.cell(card_width - 6, 4, comparison_text, 0, 0, 'L')
            
            # Move para próxima linha
            self.set_xy(10, y_start + card_height + 5)
        
        self.ln(2)
    
    def add_comparison_section(self, current_data, previous_data, title="Comparação de Períodos"):
        """
        Adiciona seção de comparação entre dois períodos
        
        Args:
            current_data: dict com dados do período atual (ex: {"revenue": 50000, "orders": 500})
            previous_data: dict com dados do período anterior (ex: {"revenue": 43250, "orders": 450})
            title: Título da seção
        """
        # Verifica se precisa quebrar página
        if self.get_y() + 30 > self.h - 20:
            self.add_page()
        
        # Título da seção
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, title, 0, 1, 'L')
        self.ln(2)
        
        # Cabeçalho da tabela de comparação
        self.set_font('Arial', 'B', 10)
        col_widths = [60, 50, 50, 30]
        headers = ['Métrica', 'Período Atual', 'Período Anterior', 'Variação']
        for i, header in enumerate(headers):
            self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
        self.ln()
        
        # Dados de comparação
        self.set_font('Arial', '', 9)
        for key in current_data.keys():
            current_value = current_data.get(key, 0)
            previous_value = previous_data.get(key, 0)
            
            # Calcula variação percentual
            try:
                if previous_value == 0:
                    variation = "+100%" if current_value > 0 else "0%"
                else:
                    variation_pct = ((current_value - previous_value) / previous_value) * 100
                    sign = "+" if variation_pct >= 0 else ""
                    variation = f"{sign}{variation_pct:.1f}%"
            except:
                variation = "N/A"
            
            # Formata valores
            if isinstance(current_value, (int, float)):
                current_str = f"{current_value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                previous_str = f"{previous_value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            else:
                current_str = str(current_value)
                previous_str = str(previous_value)
            
            # Trunca valores longos
            current_str = current_str[:20] + '...' if len(current_str) > 20 else current_str
            previous_str = previous_str[:20] + '...' if len(previous_str) > 20 else previous_str
            
            # Adiciona linha
            self.cell(col_widths[0], 6, str(key).replace('_', ' ').title(), 1, 0, 'L')
            self.cell(col_widths[1], 6, current_str, 1, 0, 'C')
            self.cell(col_widths[2], 6, previous_str, 1, 0, 'C')
            self.cell(col_widths[3], 6, variation, 1, 0, 'C')
            self.ln()
        
        self.ln(5)
    
    def add_trend_analysis(self, trend_data, title="Análise de Tendências"):
        """
        Adiciona análise de tendências ao PDF
        
        Args:
            trend_data: dict com dados de tendência (ex: {"metric": "Vendas", "trend": "crescente", "percentage": 15.5})
            title: Título da seção
        """
        # Verifica se precisa quebrar página
        if self.get_y() + 20 > self.h - 20:
            self.add_page()
        
        # Título da seção
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, title, 0, 1, 'L')
        self.ln(2)
        
        # Análise de cada métrica
        self.set_font('Arial', '', 10)
        if isinstance(trend_data, dict):
            trend_data = [trend_data]
        
        for item in trend_data:
            metric = item.get('metric', 'Métrica')
            trend = item.get('trend', 'estável')
            percentage = item.get('percentage', 0)
            
            # Determina cor e ícone baseado na tendência
            if trend.lower() in ['crescente', 'aumento', 'up']:
                trend_text = f"↑ Crescente ({percentage:+.1f}%)"
            elif trend.lower() in ['decrescente', 'queda', 'down']:
                trend_text = f"↓ Decrescente ({percentage:+.1f}%)"
            else:
                trend_text = f"→ Estável ({percentage:+.1f}%)"
            
            self.cell(0, 6, f"• {metric}: {trend_text}", 0, 1, 'L')
        
        self.ln(5)


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


class DetailedSalesReportPDF(BaseReportPDF):
    """Relatório detalhado de vendas com gráficos e análises"""
    
    def __init__(self):
        super().__init__("Relatório de Vendas Detalhado")
    
    def generate_report(self, report_data):
        """Gera o relatório completo de vendas detalhado"""
        from ..utils.report_formatters import format_currency, format_percentage, format_date
        
        self.add_page()
        
        # Filtros
        if report_data.get('filters'):
            self.add_filters_info(report_data['filters'])
        
        # Resumo executivo com cards de métricas
        summary = report_data.get('summary', {})
        if summary:
            self.add_metric_card(
                "Total de Vendas",
                format_currency(summary.get('total_revenue', 0)),
                comparison=f"{summary.get('revenue_growth', 0):+.1f}%",
                comparison_label="vs. período anterior"
            )
            self.add_metric_card(
                "Total de Pedidos",
                str(summary.get('total_orders', 0)),
                comparison=f"{summary.get('orders_growth', 0):+.1f}%",
                comparison_label="vs. período anterior"
            )
            self.add_metric_card(
                "Ticket Médio",
                format_currency(summary.get('avg_ticket', 0))
            )
            self.add_metric_card(
                "Taxa de Cancelamento",
                format_percentage(summary.get('cancellation_rate', 0) / 100)
            )
            self.ln(5)
        
        # Comparação com período anterior
        if summary and summary.get('previous_period'):
            prev = summary['previous_period']
            self.add_comparison_section(
                current_data={
                    'Receita Total': summary.get('total_revenue', 0),
                    'Total de Pedidos': summary.get('total_orders', 0)
                },
                previous_data={
                    'Receita Total': prev.get('total_revenue', 0),
                    'Total de Pedidos': prev.get('total_orders', 0)
                }
            )
        
        # Gráfico: Vendas por data
        if report_data.get('charts', {}).get('sales_timeline'):
            self.add_chart(
                report_data['charts']['sales_timeline'],
                title="Evolução de Vendas"
            )
        
        # Vendas por tipo de pedido
        sales_by_type = report_data.get('sales_by_type', [])
        if sales_by_type:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Vendas por Tipo de Pedido', 0, 1, 'L')
            self.ln(2)
            
            headers = ['Tipo', 'Pedidos', 'Receita']
            col_widths = [60, 50, 80]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in sales_by_type:
                self.cell(col_widths[0], 6, str(item.get('type', 'N/A')), 1, 0, 'L')
                self.cell(col_widths[1], 6, str(item.get('orders', 0)), 1, 0, 'C')
                self.cell(col_widths[2], 6, format_currency(item.get('revenue', 0)), 1, 0, 'R')
                self.ln()
            self.ln(5)
        
        # Gráfico: Métodos de pagamento
        if report_data.get('charts', {}).get('payment_methods'):
            self.add_chart(
                report_data['charts']['payment_methods'],
                title="Vendas por Método de Pagamento"
            )
        
        # Top 10 Produtos
        top_products = report_data.get('top_products', [])
        if top_products:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Top 10 Produtos Mais Vendidos', 0, 1, 'L')
            self.ln(2)
            
            if report_data.get('charts', {}).get('top_products'):
                self.add_chart(
                    report_data['charts']['top_products'],
                    height=80
                )
            
            headers = ['Produto', 'Quantidade', 'Receita']
            col_widths = [100, 40, 50]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in top_products[:10]:
                name = str(item.get('name', 'N/A'))[:35]
                self.cell(col_widths[0], 6, name, 1, 0, 'L')
                self.cell(col_widths[1], 6, str(item.get('quantity', 0)), 1, 0, 'C')
                self.cell(col_widths[2], 6, format_currency(item.get('revenue', 0)), 1, 0, 'R')
                self.ln()
            self.ln(5)
        
        # Top 10 Clientes
        top_customers = report_data.get('top_customers', [])
        if top_customers:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Top 10 Clientes', 0, 1, 'L')
            self.ln(2)
            
            headers = ['Cliente', 'Pedidos', 'Total Gasto']
            col_widths = [100, 40, 50]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in top_customers[:10]:
                name = str(item.get('name', 'N/A'))[:35]
                self.cell(col_widths[0], 6, name, 1, 0, 'L')
                self.cell(col_widths[1], 6, str(item.get('orders', 0)), 1, 0, 'C')
                self.cell(col_widths[2], 6, format_currency(item.get('spent', 0)), 1, 0, 'R')
                self.ln()
            self.ln(5)


class OrdersPerformanceReportPDF(BaseReportPDF):
    """Relatório de performance de pedidos"""
    
    def __init__(self):
        super().__init__("Relatório de Performance de Pedidos")
    
    def generate_report(self, report_data):
        """Gera o relatório completo de performance"""
        from ..utils.report_formatters import format_currency, format_percentage, format_duration_minutes
        
        self.add_page()
        
        # Filtros
        if report_data.get('filters'):
            self.add_filters_info(report_data['filters'])
        
        # Resumo executivo
        summary = report_data.get('summary', {})
        if summary:
            self.add_metric_card(
                "Total de Pedidos",
                str(summary.get('total_orders', 0))
            )
            self.add_metric_card(
                "Taxa de Cancelamento",
                format_percentage(summary.get('cancellation_rate', 0) / 100)
            )
            self.add_metric_card(
                "Tempo Médio de Preparo",
                format_duration_minutes(summary.get('avg_prep_time', 0))
            )
            self.ln(5)
        
        # Performance por Atendente
        attendants = report_data.get('attendants_performance', [])
        if attendants:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Performance por Atendente', 0, 1, 'L')
            self.ln(2)
            
            headers = ['Atendente', 'Pedidos', 'Receita Gerada', 'Tempo Médio']
            col_widths = [70, 30, 50, 40]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in attendants:
                name = str(item.get('name', 'N/A'))[:30]
                self.cell(col_widths[0], 6, name, 1, 0, 'L')
                self.cell(col_widths[1], 6, str(item.get('orders', 0)), 1, 0, 'C')
                self.cell(col_widths[2], 6, format_currency(item.get('revenue', 0)), 1, 0, 'R')
                self.cell(col_widths[3], 6, format_duration_minutes(item.get('avg_time', 0)), 1, 0, 'C')
                self.ln()
            self.ln(5)
        
        # Performance por Entregador
        deliverers = report_data.get('deliverers_performance', [])
        if deliverers:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Performance por Entregador', 0, 1, 'L')
            self.ln(2)
            
            headers = ['Entregador', 'Entregas', 'Tempo Médio']
            col_widths = [100, 40, 50]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in deliverers:
                name = str(item.get('name', 'N/A'))[:40]
                self.cell(col_widths[0], 6, name, 1, 0, 'L')
                self.cell(col_widths[1], 6, str(item.get('deliveries', 0)), 1, 0, 'C')
                self.cell(col_widths[2], 6, format_duration_minutes(item.get('avg_time', 0)), 1, 0, 'C')
                self.ln()
            self.ln(5)


class ProductsAnalysisReportPDF(BaseReportPDF):
    """Relatório de análise de produtos"""
    
    def __init__(self):
        super().__init__("Relatório de Análise de Produtos")
    
    def generate_report(self, report_data):
        """Gera o relatório completo de análise de produtos"""
        from ..utils.report_formatters import format_currency, format_percentage
        
        self.add_page()
        
        # Filtros
        if report_data.get('filters'):
            self.add_filters_info(report_data['filters'])
        
        # Top Produtos por Quantidade
        top_qty = report_data.get('top_products_by_quantity', [])
        if top_qty:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Top 20 Produtos Mais Vendidos (Quantidade)', 0, 1, 'L')
            self.ln(2)
            
            if report_data.get('charts', {}).get('top_products_qty'):
                self.add_chart(
                    report_data['charts']['top_products_qty'],
                    height=80
                )
            
            headers = ['Produto', 'Qtd', 'Receita', 'Lucro', 'Margem']
            col_widths = [70, 25, 35, 35, 25]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in top_qty[:20]:
                name = str(item.get('name', 'N/A'))[:30]
                self.cell(col_widths[0], 6, name, 1, 0, 'L')
                self.cell(col_widths[1], 6, str(item.get('quantity', 0)), 1, 0, 'C')
                self.cell(col_widths[2], 6, format_currency(item.get('revenue', 0)), 1, 0, 'R')
                self.cell(col_widths[3], 6, format_currency(item.get('profit', 0)), 1, 0, 'R')
                self.cell(col_widths[4], 6, format_percentage(item.get('margin', 0) / 100), 1, 0, 'R')
                self.ln()
            self.ln(5)
        
        # Top Produtos por Receita
        top_revenue = report_data.get('top_products_by_revenue', [])
        if top_revenue:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Top 20 Produtos por Receita', 0, 1, 'L')
            self.ln(2)
            
            if report_data.get('charts', {}).get('top_products_revenue'):
                self.add_chart(
                    report_data['charts']['top_products_revenue'],
                    height=80
                )
            
            headers = ['Produto', 'Qtd', 'Receita', 'Lucro', 'Margem']
            col_widths = [70, 25, 35, 35, 25]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in top_revenue[:20]:
                name = str(item.get('name', 'N/A'))[:30]
                self.cell(col_widths[0], 6, name, 1, 0, 'L')
                self.cell(col_widths[1], 6, str(item.get('quantity', 0)), 1, 0, 'C')
                self.cell(col_widths[2], 6, format_currency(item.get('revenue', 0)), 1, 0, 'R')
                self.cell(col_widths[3], 6, format_currency(item.get('profit', 0)), 1, 0, 'R')
                self.cell(col_widths[4], 6, format_percentage(item.get('margin', 0) / 100), 1, 0, 'R')
                self.ln()
            self.ln(5)


class CompleteFinancialReportPDF(BaseReportPDF):
    """Relatório financeiro completo com gráficos e análises"""
    
    def __init__(self):
        super().__init__("Relatório Financeiro Completo")
    
    def generate_report(self, report_data):
        """Gera o relatório completo financeiro"""
        from ..utils.report_formatters import format_currency, format_percentage
        
        self.add_page()
        
        # Filtros
        if report_data.get('filters'):
            self.add_filters_info(report_data['filters'])
        
        # Resumo executivo com cards
        summary = report_data.get('summary', {})
        if summary:
            self.add_metric_card(
                "Receita Total",
                format_currency(summary.get('total_revenue', 0)),
                comparison=f"{summary.get('revenue_growth', 0):+.1f}%",
                comparison_label="vs. período anterior"
            )
            self.add_metric_card(
                "Lucro Bruto",
                format_currency(summary.get('gross_profit', 0))
            )
            self.add_metric_card(
                "Lucro Líquido",
                format_currency(summary.get('net_profit', 0))
            )
            self.add_metric_card(
                "Margem Líquida",
                format_percentage(summary.get('net_margin', 0) / 100)
            )
            self.ln(5)
        
        # Comparação com período anterior
        if summary and summary.get('previous_period'):
            prev = summary['previous_period']
            self.add_comparison_section(
                current_data={
                    'Receita Total': summary.get('total_revenue', 0),
                    'Despesas Totais': summary.get('total_expense', 0)
                },
                previous_data={
                    'Receita Total': prev.get('total_revenue', 0),
                    'Despesas Totais': prev.get('total_expense', 0)
                }
            )
        
        # Gráfico: Fluxo de caixa
        if report_data.get('charts', {}).get('cashflow_timeline'):
            self.add_chart(
                report_data['charts']['cashflow_timeline'],
                title="Fluxo de Caixa Diário"
            )
        
        # Receitas por categoria
        revenue_by_category = report_data.get('revenue_by_category', [])
        if revenue_by_category:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Receitas por Categoria', 0, 1, 'L')
            self.ln(2)
            
            if report_data.get('charts', {}).get('revenue_by_category'):
                self.add_chart(
                    report_data['charts']['revenue_by_category'],
                    height=80
                )
            
            headers = ['Categoria', 'Total']
            col_widths = [140, 50]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in revenue_by_category:
                self.cell(col_widths[0], 6, str(item.get('category', 'N/A'))[:50], 1, 0, 'L')
                self.cell(col_widths[1], 6, format_currency(item.get('total', 0)), 1, 0, 'R')
                self.ln()
            self.ln(5)
        
        # Despesas por categoria
        expenses_by_category = report_data.get('expenses_by_category', [])
        if expenses_by_category:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Despesas por Categoria', 0, 1, 'L')
            self.ln(2)
            
            if report_data.get('charts', {}).get('expenses_by_category'):
                self.add_chart(
                    report_data['charts']['expenses_by_category'],
                    height=80
                )
            
            headers = ['Categoria', 'Total']
            col_widths = [140, 50]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in expenses_by_category:
                self.cell(col_widths[0], 6, str(item.get('category', 'N/A'))[:50], 1, 0, 'L')
                self.cell(col_widths[1], 6, format_currency(item.get('total', 0)), 1, 0, 'R')
                self.ln()
            self.ln(5)
        
        # Contas a pagar
        if summary and (summary.get('pending_expenses', 0) > 0 or summary.get('pending_taxes', 0) > 0):
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Contas a Pagar (Pendentes)', 0, 1, 'L')
            self.ln(2)
            
            self.set_font('Arial', '', 10)
            if summary.get('pending_expenses', 0) > 0:
                self.cell(0, 6, f"Despesas Pendentes: {format_currency(summary.get('pending_expenses', 0))}", 0, 1, 'L')
            if summary.get('pending_taxes', 0) > 0:
                self.cell(0, 6, f"Impostos Pendentes: {format_currency(summary.get('pending_taxes', 0))}", 0, 1, 'L')
            self.ln(5)


class CMVReportPDF(BaseReportPDF):
    """Relatório de CMV (Custo das Mercadorias Vendidas)"""
    
    def __init__(self):
        super().__init__("Relatório de CMV - Custo das Mercadorias Vendidas")
    
    def generate_report(self, report_data):
        """Gera o relatório completo de CMV"""
        from ..utils.report_formatters import format_currency, format_percentage
        
        self.add_page()
        
        # Filtros
        if report_data.get('filters'):
            self.add_filters_info(report_data['filters'])
        
        # Resumo executivo
        summary = report_data.get('summary', {})
        if summary:
            self.add_metric_card(
                "CMV Total",
                format_currency(summary.get('total_cmv', 0))
            )
            self.add_metric_card(
                "CMV sobre Receita",
                format_percentage(summary.get('cmv_percentage', 0) / 100)
            )
            self.add_metric_card(
                "Receita Total",
                format_currency(summary.get('revenue_total', 0))
            )
            self.add_metric_card(
                "Total de Movimentações",
                str(summary.get('total_movements', 0))
            )
            self.ln(5)
        
        # CMV por categoria
        cmv_by_category = report_data.get('cmv_by_category', [])
        if cmv_by_category:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'CMV por Categoria', 0, 1, 'L')
            self.ln(2)
            
            if report_data.get('charts', {}).get('cmv_by_category'):
                self.add_chart(
                    report_data['charts']['cmv_by_category'],
                    height=80
                )
            
            headers = ['Categoria', 'CMV Total']
            col_widths = [140, 50]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in cmv_by_category:
                self.cell(col_widths[0], 6, str(item.get('category', 'N/A'))[:50], 1, 0, 'L')
                self.cell(col_widths[1], 6, format_currency(item.get('total', 0)), 1, 0, 'R')
                self.ln()
            self.ln(5)
        
        # CMV por produto
        cmv_by_product = report_data.get('cmv_by_product', [])
        if cmv_by_product:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Top 20 Produtos por CMV', 0, 1, 'L')
            self.ln(2)
            
            if report_data.get('charts', {}).get('cmv_by_product'):
                self.add_chart(
                    report_data['charts']['cmv_by_product'],
                    height=80
                )
            
            headers = ['Produto', 'Quantidade', 'CMV Total']
            col_widths = [100, 40, 50]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in cmv_by_product[:20]:
                name = str(item.get('product', 'N/A'))[:40]
                self.cell(col_widths[0], 6, name, 1, 0, 'L')
                self.cell(col_widths[1], 6, str(item.get('quantity', 0)), 1, 0, 'C')
                self.cell(col_widths[2], 6, format_currency(item.get('cmv', 0)), 1, 0, 'R')
                self.ln()
            self.ln(5)


class TaxesReportPDF(BaseReportPDF):
    """Relatório de impostos e taxas"""
    
    def __init__(self):
        super().__init__("Relatório de Impostos e Taxas")
    
    def generate_report(self, report_data):
        """Gera o relatório completo de impostos"""
        from ..utils.report_formatters import format_currency, format_percentage
        
        self.add_page()
        
        # Filtros
        if report_data.get('filters'):
            self.add_filters_info(report_data['filters'])
        
        # Resumo executivo
        summary = report_data.get('summary', {})
        if summary:
            self.add_metric_card(
                "Total de Impostos",
                format_currency(summary.get('total_taxes', 0))
            )
            self.add_metric_card(
                "Impostos Pagos",
                format_currency(summary.get('paid_taxes', 0))
            )
            self.add_metric_card(
                "Impostos Pendentes",
                format_currency(summary.get('pending_taxes', 0))
            )
            self.add_metric_card(
                "Impacto na Receita",
                format_percentage(summary.get('tax_impact', 0) / 100)
            )
            self.ln(5)
        
        # Impostos por categoria
        taxes_by_category = report_data.get('taxes_by_category', [])
        if taxes_by_category:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Impostos por Categoria', 0, 1, 'L')
            self.ln(2)
            
            if report_data.get('charts', {}).get('taxes_by_category'):
                self.add_chart(
                    report_data['charts']['taxes_by_category'],
                    height=80
                )
            
            headers = ['Categoria', 'Total', 'Quantidade']
            col_widths = [100, 50, 40]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in taxes_by_category:
                self.cell(col_widths[0], 6, str(item.get('category', 'N/A'))[:40], 1, 0, 'L')
                self.cell(col_widths[1], 6, format_currency(item.get('total', 0)), 1, 0, 'R')
                self.cell(col_widths[2], 6, str(item.get('count', 0)), 1, 0, 'C')
                self.ln()
            self.ln(5)
        
        # Impostos recorrentes
        recurring_taxes = report_data.get('recurring_taxes', [])
        if recurring_taxes:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Impostos Recorrentes', 0, 1, 'L')
            self.ln(2)
            
            headers = ['Nome', 'Valor', 'Frequência', 'Status']
            col_widths = [80, 40, 40, 30]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in recurring_taxes:
                self.cell(col_widths[0], 6, str(item.get('name', 'N/A'))[:35], 1, 0, 'L')
                self.cell(col_widths[1], 6, format_currency(item.get('amount', 0)), 1, 0, 'R')
                self.cell(col_widths[2], 6, str(item.get('frequency', 'N/A'))[:15], 1, 0, 'C')
                self.cell(col_widths[3], 6, 'Ativo' if item.get('is_active') else 'Inativo', 1, 0, 'C')
                self.ln()
            self.ln(5)


class CompleteStockReportPDF(BaseReportPDF):
    """Relatório completo de estoque"""
    
    def __init__(self):
        super().__init__("Relatório Completo de Estoque")
    
    def generate_report(self, report_data):
        """Gera o relatório completo de estoque"""
        from ..utils.report_formatters import format_currency
        
        self.add_page()
        
        # Filtros
        if report_data.get('filters'):
            self.add_filters_info(report_data['filters'])
        
        # Resumo executivo
        summary = report_data.get('summary', {})
        if summary:
            self.add_metric_card(
                "Total de Ingredientes",
                str(summary.get('total_ingredients', 0))
            )
            self.add_metric_card(
                "Valor Total do Estoque",
                format_currency(summary.get('total_value', 0))
            )
            self.add_metric_card(
                "Esgotados",
                str(summary.get('out_of_stock', 0))
            )
            self.add_metric_card(
                "Estoque Baixo",
                str(summary.get('low_stock', 0))
            )
            self.ln(5)
        
        # Distribuição por status
        if report_data.get('charts', {}).get('status_distribution'):
            self.add_chart(
                report_data['charts']['status_distribution'],
                title="Distribuição de Ingredientes por Status"
            )
        
        # Ingredientes por status
        ingredients_by_status = report_data.get('ingredients_by_status', [])
        if ingredients_by_status:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Ingredientes por Status', 0, 1, 'L')
            self.ln(2)
            
            headers = ['Status', 'Quantidade', 'Valor Total']
            col_widths = [60, 50, 80]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in ingredients_by_status:
                self.cell(col_widths[0], 6, str(item.get('status', 'N/A')), 1, 0, 'L')
                self.cell(col_widths[1], 6, str(item.get('count', 0)), 1, 0, 'C')
                self.cell(col_widths[2], 6, format_currency(item.get('total_value', 0)), 1, 0, 'R')
                self.ln()
            self.ln(5)
        
        # Ingredientes mais utilizados
        if report_data.get('charts', {}).get('most_used'):
            self.add_chart(
                report_data['charts']['most_used'],
                title="Top 10 Ingredientes Mais Utilizados"
            )
        
        # Ingredientes parados
        inactive = report_data.get('inactive_ingredients', [])
        if inactive:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Ingredientes Sem Movimentação (Últimos 30 dias)', 0, 1, 'L')
            self.ln(2)
            
            headers = ['Ingrediente', 'Estoque', 'Valor']
            col_widths = [100, 40, 50]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in inactive:
                self.cell(col_widths[0], 6, str(item.get('name', 'N/A'))[:40], 1, 0, 'L')
                self.cell(col_widths[1], 6, f"{item.get('stock', 0):.2f}", 1, 0, 'C')
                self.cell(col_widths[2], 6, format_currency(item.get('value', 0)), 1, 0, 'R')
                self.ln()
            self.ln(5)


class PurchasesReportPDF(BaseReportPDF):
    """Relatório de compras e fornecedores"""
    
    def __init__(self):
        super().__init__("Relatório de Compras e Fornecedores")
    
    def generate_report(self, report_data):
        """Gera o relatório completo de compras"""
        from ..utils.report_formatters import format_currency
        
        self.add_page()
        
        # Filtros
        if report_data.get('filters'):
            self.add_filters_info(report_data['filters'])
        
        # Resumo executivo
        summary = report_data.get('summary', {})
        if summary:
            self.add_metric_card(
                "Total de Notas Fiscais",
                str(summary.get('total_invoices', 0))
            )
            self.add_metric_card(
                "Valor Total",
                format_currency(summary.get('total_amount', 0))
            )
            self.add_metric_card(
                "Valor Médio",
                format_currency(summary.get('avg_amount', 0))
            )
            self.add_metric_card(
                "Pendentes",
                format_currency(summary.get('pending_amount', 0))
            )
            self.ln(5)
        
        # Compras por fornecedor
        if report_data.get('charts', {}).get('purchases_by_supplier'):
            self.add_chart(
                report_data['charts']['purchases_by_supplier'],
                title="Top 10 Fornecedores por Valor"
            )
        
        purchases_by_supplier = report_data.get('purchases_by_supplier', [])
        if purchases_by_supplier:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Compras por Fornecedor', 0, 1, 'L')
            self.ln(2)
            
            headers = ['Fornecedor', 'Notas', 'Total', 'Média']
            col_widths = [80, 30, 50, 30]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in purchases_by_supplier:
                self.cell(col_widths[0], 6, str(item.get('supplier', 'N/A'))[:35], 1, 0, 'L')
                self.cell(col_widths[1], 6, str(item.get('invoice_count', 0)), 1, 0, 'C')
                self.cell(col_widths[2], 6, format_currency(item.get('total_amount', 0)), 1, 0, 'R')
                self.cell(col_widths[3], 6, format_currency(item.get('avg_amount', 0)), 1, 0, 'R')
                self.ln()
            self.ln(5)
        
        # Itens mais comprados
        if report_data.get('charts', {}).get('most_purchased'):
            self.add_chart(
                report_data['charts']['most_purchased'],
                title="Top 10 Itens Mais Comprados"
            )
        
        most_purchased = report_data.get('most_purchased_items', [])
        if most_purchased:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Top 20 Itens Mais Comprados', 0, 1, 'L')
            self.ln(2)
            
            headers = ['Ingrediente', 'Quantidade', 'Total Gasto', 'Preço Médio']
            col_widths = [80, 40, 40, 30]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in most_purchased[:20]:
                self.cell(col_widths[0], 6, str(item.get('ingredient', 'N/A'))[:35], 1, 0, 'L')
                self.cell(col_widths[1], 6, f"{item.get('quantity', 0):.2f}", 1, 0, 'C')
                self.cell(col_widths[2], 6, format_currency(item.get('total_spent', 0)), 1, 0, 'R')
                self.cell(col_widths[3], 6, format_currency(item.get('avg_price', 0)), 1, 0, 'R')
                self.ln()
            self.ln(5)


class CustomersAnalysisReportPDF(BaseReportPDF):
    """Relatório de análise de clientes"""
    
    def __init__(self):
        super().__init__("Relatório de Análise de Clientes")
    
    def generate_report(self, report_data):
        """Gera o relatório completo de análise de clientes"""
        from ..utils.report_formatters import format_currency, format_date
        
        self.add_page()
        
        # Filtros
        if report_data.get('filters'):
            self.add_filters_info(report_data['filters'])
        
        # Resumo executivo
        summary = report_data.get('summary', {})
        if summary:
            self.add_metric_card(
                "Total de Clientes",
                str(summary.get('total_customers', 0))
            )
            self.add_metric_card(
                "Clientes Ativos",
                str(summary.get('active_customers', 0))
            )
            self.add_metric_card(
                "Clientes Inativos",
                str(summary.get('inactive_customers', 0))
            )
            self.ln(5)
        
        # Top clientes
        if report_data.get('charts', {}).get('top_customers'):
            self.add_chart(
                report_data['charts']['top_customers'],
                title="Top 10 Clientes por Valor Gasto"
            )
        
        top_customers = report_data.get('top_customers', [])
        if top_customers:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Top 50 Clientes por Valor Gasto', 0, 1, 'L')
            self.ln(2)
            
            headers = ['Cliente', 'Pedidos', 'Total Gasto', 'Ticket Médio', 'Último Pedido (dias)']
            col_widths = [70, 25, 35, 30, 30]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in top_customers[:50]:
                name = str(item.get('name', 'N/A'))[:30]
                self.cell(col_widths[0], 6, name, 1, 0, 'L')
                self.cell(col_widths[1], 6, str(item.get('total_orders', 0)), 1, 0, 'C')
                self.cell(col_widths[2], 6, format_currency(item.get('total_spent', 0)), 1, 0, 'R')
                self.cell(col_widths[3], 6, format_currency(item.get('avg_ticket', 0)), 1, 0, 'R')
                self.cell(col_widths[4], 6, str(item.get('days_since_last_order', 0)), 1, 0, 'C')
                self.ln()
            self.ln(5)
        
        # Clientes inativos
        inactive = report_data.get('inactive_customers', [])
        if inactive:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Clientes Inativos (Último pedido há mais de 30 dias)', 0, 1, 'L')
            self.ln(2)
            
            headers = ['Cliente', 'Email', 'Último Pedido', 'Total de Pedidos']
            col_widths = [70, 60, 40, 20]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in inactive[:50]:
                self.cell(col_widths[0], 6, str(item.get('name', 'N/A'))[:30], 1, 0, 'L')
                self.cell(col_widths[1], 6, str(item.get('email', 'N/A'))[:35], 1, 0, 'L')
                self.cell(col_widths[2], 6, format_date(item.get('last_order_date'))[:10] if item.get('last_order_date') else 'N/A', 1, 0, 'C')
                self.cell(col_widths[3], 6, str(item.get('total_orders', 0)), 1, 0, 'C')
                self.ln()
            self.ln(5)


class LoyaltyReportPDF(BaseReportPDF):
    """Relatório de programa de fidelidade"""
    
    def __init__(self):
        super().__init__("Relatório de Programa de Fidelidade")
    
    def generate_report(self, report_data):
        """Gera o relatório completo de fidelidade"""
        from ..utils.report_formatters import format_currency, format_number
        
        self.add_page()
        
        # Filtros
        if report_data.get('filters'):
            self.add_filters_info(report_data['filters'])
        
        # Resumo executivo
        summary = report_data.get('summary', {})
        if summary:
            self.add_metric_card(
                "Total de Participantes",
                str(summary.get('total_participants', 0))
            )
            self.add_metric_card(
                "Pontos Acumulados",
                format_number(summary.get('total_earned', 0))
            )
            self.add_metric_card(
                "Pontos Resgatados",
                format_number(summary.get('total_redeemed', 0))
            )
            self.add_metric_card(
                "Total de Resgates",
                str(summary.get('total_redemptions', 0))
            )
            self.ln(5)
        
        # Top participantes
        if report_data.get('charts', {}).get('top_participants'):
            self.add_chart(
                report_data['charts']['top_participants'],
                title="Top 10 Participantes por Pontos Ganhos"
            )
        
        top_participants = report_data.get('top_participants', [])
        if top_participants:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Top 20 Participantes', 0, 1, 'L')
            self.ln(2)
            
            headers = ['Cliente', 'Pontos Ganhos', 'Pontos Resgatados', 'Saldo Atual']
            col_widths = [80, 40, 40, 30]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in top_participants[:20]:
                self.cell(col_widths[0], 6, str(item.get('name', 'N/A'))[:35], 1, 0, 'L')
                self.cell(col_widths[1], 6, format_number(item.get('total_earned', 0)), 1, 0, 'C')
                self.cell(col_widths[2], 6, format_number(item.get('total_redeemed', 0)), 1, 0, 'C')
                self.cell(col_widths[3], 6, format_number(item.get('current_balance', 0)), 1, 0, 'C')
                self.ln()
            self.ln(5)


class TablesReportPDF(BaseReportPDF):
    """Relatório de mesas e salão"""
    
    def __init__(self):
        super().__init__("Relatório de Mesas e Salão")
    
    def generate_report(self, report_data):
        """Gera o relatório completo de mesas"""
        from ..utils.report_formatters import format_currency, format_percentage, format_duration_minutes
        
        self.add_page()
        
        # Filtros
        if report_data.get('filters'):
            self.add_filters_info(report_data['filters'])
        
        # Resumo executivo
        summary = report_data.get('summary', {})
        if summary:
            self.add_metric_card(
                "Total de Mesas",
                str(summary.get('total_tables', 0))
            )
            self.add_metric_card(
                "Taxa de Ocupação",
                format_percentage(summary.get('occupancy_rate', 0) / 100)
            )
            self.add_metric_card(
                "Total de Pedidos",
                str(summary.get('total_orders', 0))
            )
            self.add_metric_card(
                "Tempo Médio",
                format_duration_minutes(summary.get('avg_duration', 0))
            )
            self.ln(5)
        
        # Performance por mesa
        if report_data.get('charts', {}).get('tables_revenue'):
            self.add_chart(
                report_data['charts']['tables_revenue'],
                title="Top 10 Mesas por Receita"
            )
        
        tables_performance = report_data.get('tables_performance', [])
        if tables_performance:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Performance por Mesa', 0, 1, 'L')
            self.ln(2)
            
            headers = ['Mesa', 'Pedidos', 'Receita', 'Tempo Médio']
            col_widths = [60, 30, 50, 50]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in tables_performance:
                self.cell(col_widths[0], 6, str(item.get('name', 'N/A'))[:25], 1, 0, 'L')
                self.cell(col_widths[1], 6, str(item.get('order_count', 0)), 1, 0, 'C')
                self.cell(col_widths[2], 6, format_currency(item.get('revenue', 0)), 1, 0, 'R')
                self.cell(col_widths[3], 6, format_duration_minutes(item.get('avg_duration', 0)), 1, 0, 'C')
                self.ln()
            self.ln(5)


class ExecutiveDashboardPDF(BaseReportPDF):
    """Dashboard executivo consolidado"""
    
    def __init__(self):
        super().__init__("Dashboard Executivo")
    
    def generate_report(self, report_data):
        """Gera o dashboard executivo"""
        from ..utils.report_formatters import format_currency, format_percentage
        
        self.add_page()
        
        # Filtros
        if report_data.get('filters'):
            self.add_filters_info(report_data['filters'])
        
        # KPIs principais (cards grandes)
        summary = report_data.get('summary', {})
        if summary:
            self.add_metric_card(
                "Receita Total",
                format_currency(summary.get('total_revenue', 0)),
                comparison=f"{summary.get('revenue_growth', 0):+.1f}%",
                comparison_label="vs. período anterior"
            )
            self.add_metric_card(
                "Total de Pedidos",
                str(summary.get('total_orders', 0))
            )
            self.add_metric_card(
                "Ticket Médio",
                format_currency(summary.get('avg_ticket', 0))
            )
            self.add_metric_card(
                "Lucro Líquido",
                format_currency(summary.get('net_profit', 0))
            )
            self.ln(5)
        
        # Alertas
        if summary and summary.get('low_stock_alerts', 0) > 0:
            self.set_font('Arial', 'B', 12)
            self.set_text_color(255, 0, 0)
            self.cell(0, 8, f'⚠ ALERTA: {summary.get("low_stock_alerts", 0)} ingredientes com estoque baixo', 0, 1, 'L')
            self.set_text_color(0, 0, 0)
            self.ln(2)
        
        # Top 5 Produtos
        top_products = report_data.get('top_products', [])
        if top_products:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Top 5 Produtos Mais Vendidos', 0, 1, 'L')
            self.ln(2)
            
            headers = ['Produto', 'Quantidade Vendida']
            col_widths = [140, 50]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in top_products:
                self.cell(col_widths[0], 6, str(item.get('name', 'N/A'))[:50], 1, 0, 'L')
                self.cell(col_widths[1], 6, str(item.get('quantity', 0)), 1, 0, 'C')
                self.ln()
            self.ln(5)
        
        # Top 5 Clientes
        top_customers = report_data.get('top_customers', [])
        if top_customers:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Top 5 Clientes', 0, 1, 'L')
            self.ln(2)
            
            headers = ['Cliente', 'Total Gasto']
            col_widths = [140, 50]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 9)
            for item in top_customers:
                self.cell(col_widths[0], 6, str(item.get('name', 'N/A'))[:50], 1, 0, 'L')
                self.cell(col_widths[1], 6, format_currency(item.get('spent', 0)), 1, 0, 'R')
                self.ln()
            self.ln(5)


class ReconciliationReportPDF(BaseReportPDF):
    """Relatório de conciliação bancária"""
    
    def __init__(self):
        super().__init__("Relatório de Conciliação Bancária")
    
    def generate_report(self, report_data):
        """Gera o relatório completo de conciliação"""
        from ..utils.report_formatters import format_currency, format_date
        
        self.add_page()
        
        # Filtros
        if report_data.get('filters'):
            self.add_filters_info(report_data['filters'])
        
        # Resumo executivo
        summary = report_data.get('summary', {})
        if summary:
            self.add_metric_card(
                "Total de Movimentações",
                str(summary.get('total_movements', 0))
            )
            self.add_metric_card(
                "Concilidadas",
                str(summary.get('reconciled_count', 0))
            )
            self.add_metric_card(
                "Pendentes",
                str(summary.get('pending_count', 0))
            )
            self.add_metric_card(
                "Valor Pendente",
                format_currency(summary.get('pending_amount', 0))
            )
            self.ln(5)
        
        # Movimentações pendentes
        pending = report_data.get('pending_movements', [])
        if pending:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Movimentações Pendentes de Conciliação', 0, 1, 'L')
            self.ln(2)
            
            headers = ['ID', 'Tipo', 'Valor', 'Data', 'Gateway', 'Conta']
            col_widths = [20, 30, 35, 35, 35, 35]
            self.set_font('Arial', 'B', 10)
            for i, header in enumerate(headers):
                self.cell(col_widths[i], 7, str(header), 1, 0, 'C')
            self.ln()
            
            self.set_font('Arial', '', 8)
            for item in pending[:50]:
                self.cell(col_widths[0], 6, str(item.get('id', 'N/A')), 1, 0, 'C')
                self.cell(col_widths[1], 6, str(item.get('type', 'N/A'))[:12], 1, 0, 'C')
                self.cell(col_widths[2], 6, format_currency(item.get('value', 0)), 1, 0, 'R')
                self.cell(col_widths[3], 6, format_date(item.get('movement_date'))[:10] if item.get('movement_date') else 'N/A', 1, 0, 'C')
                self.cell(col_widths[4], 6, str(item.get('gateway_id', 'N/A'))[:15], 1, 0, 'L')
                self.cell(col_widths[5], 6, str(item.get('bank_account', 'N/A'))[:15], 1, 0, 'L')
                self.ln()
            self.ln(5)


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
