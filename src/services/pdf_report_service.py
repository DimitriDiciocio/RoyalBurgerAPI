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
from ..utils.pdf_layout_config import (
    MARGIN_LEFT, MARGIN_RIGHT, MARGIN_TOP, MARGIN_BOTTOM,
    PADDING_SMALL, PADDING_MEDIUM, PADDING_LARGE,
    FONT_SIZE_TINY, FONT_SIZE_SMALL, FONT_SIZE_NORMAL, FONT_SIZE_MEDIUM,
    FONT_SIZE_LARGE, FONT_SIZE_XLARGE, FONT_SIZE_XXLARGE, FONT_SIZE_TITLE,
    LINE_HEIGHT_RATIO, CELL_PADDING_V, CELL_PADDING_H,
    CHART_WIDTH_RATIO, CHART_HEIGHT_BASE,
    CARD_MIN_WIDTH, CARD_MIN_HEIGHT, CARD_SPACING,
    TABLE_COL_MIN_WIDTH, TABLE_COL_MAX_WIDTH, TABLE_ANALYSIS_ROWS,
    PRIMARY_COLOR, ACCENT_COLOR, CARD_BG_COLOR, TABLE_HEADER_BG,
    TABLE_ROW_ALT_BG, FOOTER_TEXT_COLOR, SUCCESS_COLOR, ERROR_COLOR,
    CARDS_PER_ROW, CARDS_PER_PAGE, DATA_CARD_HEIGHT, METRIC_CARD_HEIGHT,
    METRIC_CARD_WIDTH_FULL, DATA_CARD_WIDTH, CARD_LINE_HEIGHT,
    CARD_GRID_SPACING_X, CARD_GRID_SPACING_Y, CARD_MARGIN_X, PAGE_START_Y,
    get_line_height, get_content_width, get_content_height,
    get_chart_width, get_chart_height, get_card_width,
    get_table_col_widths
)

# Importar constantes para uso direto
from ..utils import pdf_layout_config

logger = logging.getLogger(__name__)


class BaseReportPDF(FPDF):
    """
    Classe base para geração de relatórios em PDF com sistema de layout padronizado
    Contém elementos comuns a todos os relatórios
    """
    
    # Constantes de layout (importadas do config)
    MARGIN_LEFT = MARGIN_LEFT
    MARGIN_RIGHT = MARGIN_RIGHT
    MARGIN_TOP = MARGIN_TOP
    MARGIN_BOTTOM = MARGIN_BOTTOM
    PADDING_SMALL = PADDING_SMALL
    PADDING_MEDIUM = PADDING_MEDIUM
    PADDING_LARGE = PADDING_LARGE
    FONT_SIZE_TINY = FONT_SIZE_TINY
    FONT_SIZE_SMALL = FONT_SIZE_SMALL
    FONT_SIZE_NORMAL = FONT_SIZE_NORMAL
    FONT_SIZE_MEDIUM = FONT_SIZE_MEDIUM
    FONT_SIZE_LARGE = FONT_SIZE_LARGE
    FONT_SIZE_XLARGE = FONT_SIZE_XLARGE
    FONT_SIZE_XXLARGE = FONT_SIZE_XXLARGE
    FONT_SIZE_TITLE = FONT_SIZE_TITLE
    LINE_HEIGHT_RATIO = LINE_HEIGHT_RATIO
    CELL_PADDING_V = CELL_PADDING_V
    CELL_PADDING_H = CELL_PADDING_H
    
    def __init__(self, title="Relatório", orientation='P', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.title = title
        
        # Configura margens usando constantes
        self.set_margins(
            left=self.MARGIN_LEFT,
            top=self.MARGIN_TOP,
            right=self.MARGIN_RIGHT
        )
        self.set_auto_page_break(auto=True, margin=self.MARGIN_BOTTOM)
        
        # Habilita numeração de páginas (necessário para {nb} no rodapé)
        self.alias_nb_pages()
        
        # Usa fontes padrão do fpdf2 (sem dependência de arquivos externos)
        # self.add_font('DejaVu', '', 'DejaVuSansCondensed.ttf', uni=True)
        # self.add_font('DejaVu', 'B', 'DejaVuSansCondensed-Bold.ttf', uni=True)
    
    @property
    def content_width(self):
        """Largura útil do conteúdo"""
        return get_content_width(self.w, self.MARGIN_LEFT, self.MARGIN_RIGHT)
    
    @property
    def content_height(self):
        """Altura útil do conteúdo"""
        return get_content_height(self.h, self.MARGIN_TOP, self.MARGIN_BOTTOM)
    
    def get_line_height(self, font_size):
        """Calcula altura de linha baseada no tamanho da fonte"""
        return get_line_height(font_size)
    
    def add_spacing(self, size='medium'):
        """Adiciona espaçamento padronizado"""
        spacing_map = {
            'small': self.PADDING_SMALL,
            'medium': self.PADDING_MEDIUM,
            'large': self.PADDING_LARGE
        }
        self.ln(spacing_map.get(size, self.PADDING_MEDIUM))
    
    def add_section_title(self, title, level=1):
        """Adiciona título de seção com tamanho proporcional ao nível"""
        font_sizes = {
            1: self.FONT_SIZE_XLARGE,
            2: self.FONT_SIZE_LARGE,
            3: self.FONT_SIZE_MEDIUM
        }
        font_size = font_sizes.get(level, self.FONT_SIZE_LARGE)
        
        self.set_font('Arial', 'B', font_size)
        line_height = self.get_line_height(font_size)
        self.cell(0, line_height, title, 0, 1, 'L')
        self.add_spacing('small')
    
    def add_text(self, text, size='normal', style='', align='L'):
        """Adiciona texto com formatação padronizada"""
        font_sizes = {
            'tiny': self.FONT_SIZE_TINY,
            'small': self.FONT_SIZE_SMALL,
            'normal': self.FONT_SIZE_NORMAL,
            'medium': self.FONT_SIZE_MEDIUM,
            'large': self.FONT_SIZE_LARGE
        }
        font_size = font_sizes.get(size, self.FONT_SIZE_NORMAL)
        
        self.set_font('Arial', style, font_size)
        line_height = self.get_line_height(font_size)
        self.cell(0, line_height, str(text), 0, 1, align)
        
    def header(self):
        """Cabeçalho padrão para todos os relatórios com estilo melhorado"""
        # Logo e título usando constantes
        self.set_font('Arial', 'B', self.FONT_SIZE_TITLE)
        self.set_text_color(*PRIMARY_COLOR)
        line_height = self.get_line_height(self.FONT_SIZE_TITLE)
        self.cell(0, line_height, 'ROYAL BURGER', 0, 1, 'C')
        
        self.set_font('Arial', 'B', self.FONT_SIZE_XXLARGE)
        line_height = self.get_line_height(self.FONT_SIZE_XXLARGE)
        self.cell(0, line_height, self.title, 0, 1, 'C')
        
        # Data de geração
        self.set_font('Arial', '', self.FONT_SIZE_SMALL)
        self.set_text_color(100, 100, 100)
        self.cell(0, self.get_line_height(self.FONT_SIZE_SMALL), 
                 f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", 0, 1, 'C')
        
        # Linha separadora
        self.ln(2)
        self.set_draw_color(*PRIMARY_COLOR)
        self.set_line_width(0.5)
        self.line(self.MARGIN_LEFT, self.get_y(), self.w - self.MARGIN_RIGHT, self.get_y())
        self.ln(6)
        self.set_text_color(*PRIMARY_COLOR)  # Restaura cor padrão
        
    def footer(self):
        """Rodapé padrão para todos os relatórios com estilo melhorado"""
        # Posiciona o rodapé usando constante
        self.set_y(-15)
        
        # Data de emissão usando constante
        self.set_font('Arial', 'I', self.FONT_SIZE_SMALL)
        self.set_text_color(*FOOTER_TEXT_COLOR)
        line_height = self.get_line_height(self.FONT_SIZE_SMALL)
        self.cell(0, line_height, f'Emitido em: {datetime.now().strftime("%d/%m/%Y às %H:%M")}', 0, 0, 'L')
        
        # Número da página
        self.cell(0, line_height, f'Página {self.page_no()}/{{nb}}', 0, 0, 'C')
        
        # Restaura cor padrão
        self.set_text_color(*PRIMARY_COLOR)
        
    def add_summary_section(self, summary_data):
        """Adiciona seção de resumo no topo do relatório"""
        self.add_section_title('RESUMO', level=1)
        
        self.set_font('Arial', '', self.FONT_SIZE_MEDIUM)
        line_height = self.get_line_height(self.FONT_SIZE_MEDIUM)
        for key, value in summary_data.items():
            self.cell(70, line_height, f'{key}:', 0, 0, 'L')
            self.cell(0, line_height, str(value), 0, 1, 'L')
        
        self.add_spacing('large')
        
    def _calculate_table_widths(self, headers, data, total_width=None):
        """
        Calcula larguras de colunas proporcionais baseadas no conteúdo
        Usa função do config para padronização
        """
        if total_width is None:
            total_width = self.content_width
        return get_table_col_widths(headers, data, total_width)
    
    def add_table(self, headers, data, col_widths=None, header_style='B', data_style='', 
                  header_size='medium', data_size='normal', header_bg_color=None,
                  alternate_rows=False, aligns=None):
        """
        Adiciona uma tabela ao PDF com larguras ajustáveis, cores e espaçamentos padronizados
        
        Args:
            headers: Lista com os cabeçalhos das colunas
            data: Lista de listas com os dados das linhas
            col_widths: Lista com larguras das colunas (opcional, será calculada automaticamente)
            header_style: Estilo do cabeçalho ('B' para negrito, '' para normal)
            data_style: Estilo dos dados
            header_size: Tamanho da fonte do cabeçalho ('tiny', 'small', 'normal', 'medium', 'large')
            data_size: Tamanho da fonte dos dados
            header_bg_color: Cor de fundo do cabeçalho (tupla RGB) - padrão: TABLE_HEADER_BG
            alternate_rows: Se True, alterna cor de fundo das linhas
            aligns: Lista de alinhamentos ('L', 'C', 'R') - padrão: todos centralizados
        """
        if not data:
            self.add_text('Nenhum dado encontrado para os filtros aplicados.', 
                         size='normal', align='C')
            return
            
        # Calcula larguras das colunas se não fornecidas
        if not col_widths:
            col_widths = self._calculate_table_widths(headers, data, self.content_width)
        
        # Garante que a soma das larguras não exceda o total
        total_specified = sum(col_widths)
        if total_specified != self.content_width:
            ratio = self.content_width / total_specified if total_specified > 0 else 1
            col_widths = [int(w * ratio) for w in col_widths]
            col_widths[-1] = self.content_width - sum(col_widths[:-1])
        
        # Alinhamentos padrão (todos centralizados)
        if aligns is None:
            aligns = ['C'] * len(headers)
        
        # Cabeçalho com fundo colorido
        header_font_size = getattr(self, f'FONT_SIZE_{header_size.upper()}', self.FONT_SIZE_MEDIUM)
        self.set_font('Arial', header_style, header_font_size)
        header_height = self.get_line_height(header_font_size) + self.CELL_PADDING_V
        
        # Cor de fundo do cabeçalho
        bg_color = header_bg_color if header_bg_color else TABLE_HEADER_BG
        self.set_fill_color(*bg_color)
        self.set_text_color(40, 40, 40)  # Texto escuro no cabeçalho
        
        for i, header in enumerate(headers):
            header_text = str(header)
            if len(header_text) > 30:
                header_text = header_text[:27] + '...'
            align = aligns[i] if i < len(aligns) else 'C'
            self.cell(col_widths[i], header_height, header_text, 1, 0, align, fill=True)
        
        self.ln()
        self.set_text_color(*PRIMARY_COLOR)  # Restaura cor padrão
        
        # Dados usando constantes
        data_font_size = getattr(self, f'FONT_SIZE_{data_size.upper()}', self.FONT_SIZE_NORMAL)
        self.set_font('Arial', data_style, data_font_size)
        data_height = self.get_line_height(data_font_size) + self.CELL_PADDING_V
        
        for row_idx, row in enumerate(data):
            # Alterna cor de fundo se solicitado
            fill = False
            if alternate_rows and row_idx % 2 == 0:
                self.set_fill_color(*TABLE_ROW_ALT_BG)
                fill = True
            
            # Calcula altura máxima necessária para esta linha (para multi_cell)
            x_start = self.get_x()
            y_start = self.get_y()
            max_cell_height = data_height
            
            # Primeiro, calcula altura necessária para a primeira coluna se usar multi_cell
            first_cell_text = str(row[0]) if row else ""
            if first_cell_text:
                text_width = self.get_string_width(first_cell_text)
                if text_width > col_widths[0] - 4:
                    # Estima número de linhas necessárias
                    chars_per_line = int((col_widths[0] - 4) / (data_font_size * 0.5))
                    num_lines = max(1, (len(first_cell_text) // chars_per_line) + 1)
                    max_cell_height = (self.get_line_height(data_font_size) * num_lines) + (self.CELL_PADDING_V * 2)
            
            # IMPORTANTE: Verifica se há espaço suficiente na página ANTES de desenhar
            # Se não houver, quebra a página ANTES de desenhar qualquer célula
            if self.get_y() + max_cell_height > self.h - self.MARGIN_BOTTOM:
                self.add_page()
                x_start = self.MARGIN_LEFT
                y_start = self.get_y()
            
            # Desenha todas as células na mesma linha
            for i, cell in enumerate(row):
                if i >= len(col_widths):
                    break
                cell_text = str(cell)
                align = aligns[i] if i < len(aligns) else 'C'
                
                # Para a primeira coluna (geralmente texto), usa multi_cell se necessário
                if i == 0:
                    text_width = self.get_string_width(cell_text)
                    if text_width > col_widths[i] - 4:
                        # Usa quebra de linha manual para permitir texto completo sem quebrar página
                        # Desenha borda manualmente
                        self.set_xy(x_start, y_start)
                        self.rect(x_start, y_start, col_widths[i], max_cell_height)
                        if fill:
                            self.set_fill_color(*TABLE_ROW_ALT_BG)
                            self.rect(x_start, y_start, col_widths[i], max_cell_height, 'F')
                        
                        # Desenha texto com multi_cell (sem quebra de página automática)
                        # Usa split_only=False para evitar quebra de página
                        self.set_xy(x_start + 2, y_start + self.CELL_PADDING_V)
                        # Calcula quantas linhas serão necessárias
                        lines = []
                        words = cell_text.split(' ')
                        current_line = ''
                        for word in words:
                            test_line = current_line + (' ' if current_line else '') + word
                            test_width = self.get_string_width(test_line)
                            if test_width > col_widths[i] - 4 and current_line:
                                lines.append(current_line)
                                current_line = word
                            else:
                                current_line = test_line
                        if current_line:
                            lines.append(current_line)
                        
                        # Desenha cada linha manualmente para ter controle total
                        line_height = self.get_line_height(data_font_size)
                        for line_idx, line in enumerate(lines):
                            line_y = y_start + self.CELL_PADDING_V + (line_idx * line_height)
                            self.set_xy(x_start + 2, line_y)
                            self.cell(col_widths[i] - 4, line_height, line, 0, 0, align)
                        
                        x_start += col_widths[i]
                    else:
                        # Texto cabe, usa cell normal
                        self.set_xy(x_start, y_start)
                        self.cell(col_widths[i], max_cell_height, cell_text, 1, 0, align, fill=fill)
                        x_start += col_widths[i]
                else:
                    # Outras colunas: cell normal
                    self.set_xy(x_start, y_start)
                    self.cell(col_widths[i], max_cell_height, cell_text, 1, 0, align, fill=fill)
                    x_start += col_widths[i]
            
            # Move para próxima linha usando altura máxima
            self.set_xy(self.MARGIN_LEFT, y_start + max_cell_height)
        
        # Restaura cor de preenchimento
        self.set_fill_color(255, 255, 255)
        self.add_spacing('medium')
            
    def _format_filter_label(self, key):
        """Formata a chave do filtro para um rótulo legível em português"""
        labels = {
            'start_date': 'Data inicial',
            'end_date': 'Data final',
            'order_type': 'Tipo de pedido',
            'payment_method': 'Método de pagamento',
            'status': 'Status',
            'customer_id': 'Cliente',
            'product_id': 'Produto',
            'category_id': 'Categoria',
            'price_min': 'Preço mínimo',
            'price_max': 'Preço máximo',
            'type': 'Tipo',
            'category': 'Categoria',
            'payment_status': 'Status de pagamento',
        }
        return labels.get(key, key.replace('_', ' ').title())
    
    def _format_filter_value(self, key, value):
        """Formata o valor do filtro para exibição legível"""
        if value is None or value == '':
            return None
        
        # Formata datas
        if 'date' in key.lower():
            try:
                from datetime import datetime
                if isinstance(value, str):
                    # Tenta vários formatos de data
                    for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%d/%m/%Y', '%d-%m-%Y']:
                        try:
                            dt = datetime.strptime(value[:10], fmt)
                            return dt.strftime('%d/%m/%Y')
                        except:
                            continue
                return str(value)
            except:
                return str(value)
        
        # Formata tipos de pedido
        if key == 'order_type':
            type_map = {
                'delivery': 'Entrega',
                'pickup': 'Retirada',
                'on_site': 'No local'
            }
            return type_map.get(str(value).lower(), str(value).title())
        
        # Formata status
        if key == 'status':
            status_map = {
                'pending': 'Pendente',
                'confirmed': 'Confirmado',
                'preparing': 'Preparando',
                'ready': 'Pronto',
                'on_the_way': 'A caminho',
                'delivered': 'Entregue',
                'cancelled': 'Cancelado',
                'completed': 'Concluído',
                'active': 'Ativo',
                'inactive': 'Inativo'
            }
            return status_map.get(str(value).lower(), str(value).title())
        
        # Formata métodos de pagamento
        if key == 'payment_method':
            method_map = {
                'pix': 'PIX',
                'credit_card': 'Cartão de Crédito',
                'debit_card': 'Cartão de Débito',
                'cash': 'Dinheiro',
                'bank_transfer': 'Transferência Bancária'
            }
            return method_map.get(str(value).lower(), str(value).upper())
        
        # Formata status de pagamento
        if key == 'payment_status':
            return 'Pago' if str(value).lower() == 'paid' else 'Pendente'
        
        # Formata valores monetários
        if 'price' in key.lower() or 'min' in key.lower() or 'max' in key.lower():
            try:
                value_float = float(value)
                return f'R$ {value_float:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
            except:
                return str(value)
        
        return str(value)
            
    def add_filters_info(self, filters):
        """Adiciona informações sobre os filtros aplicados com formatação melhorada"""
        if not filters:
            return
            
        # Remove valores vazios
        filters = {k: v for k, v in filters.items() if v is not None and v != ''}
        if not filters:
            return
            
        self.add_section_title('FILTROS APLICADOS', level=2)
        
        # Trata intervalo de datas primeiro
        start_date = filters.get('start_date')
        end_date = filters.get('end_date')
        
        if start_date or end_date:
            start_formatted = self._format_filter_value('start_date', start_date) if start_date else 'Início'
            end_formatted = self._format_filter_value('end_date', end_date) if end_date else 'Fim'
            
            if start_date and end_date:
                self.add_text(f'Intervalo de tempo: {start_formatted} a {end_formatted}', size='normal')
            elif start_date:
                self.add_text(f'Data inicial: {start_formatted}', size='normal')
            elif end_date:
                self.add_text(f'Data final: {end_formatted}', size='normal')
        
        # Processa outros filtros (exceto datas que já foram processadas)
        for key, value in filters.items():
            if key not in ['start_date', 'end_date']:
                label = self._format_filter_label(key)
                formatted_value = self._format_filter_value(key, value)
                if formatted_value:
                    self.add_text(f'{label}: {formatted_value}', size='normal')
        
        self.add_spacing('large')
    
    def add_chart(self, chart_base64, width=None, height=None, title=None, is_pie_chart=False):
        """
        Adiciona gráfico ao PDF a partir de base64 com tamanhos calculados automaticamente
        
        Args:
            chart_base64: String base64 da imagem do gráfico
            width: Largura em mm (None = calculado automaticamente)
            height: Altura em mm (None = calculado automaticamente)
            title: Título opcional para o gráfico
            is_pie_chart: Se True, garante que seja quadrado (circular)
        """
        if not chart_base64:
            logger.warning("Tentativa de adicionar gráfico vazio ao PDF")
            return
        
        try:
            # Decodifica imagem base64
            image_data = base64.b64decode(chart_base64)
            image = Image.open(io.BytesIO(image_data))
            
            # Para gráfico de pizza, garante dimensões quadradas
            if is_pie_chart:
                # Calcula tamanho baseado na largura disponível
                available_width = get_chart_width(self.content_width, CHART_WIDTH_RATIO)
                # Para pizza, sempre usa dimensões quadradas
                # Usa a largura disponível como base, mas limita pela altura disponível também
                available_height = self.h - self.get_y() - self.MARGIN_BOTTOM - 20  # 20mm para título
                size = min(available_width, available_height, 120)  # Máximo 120mm para não ficar muito grande
                width = size
                height = size
            else:
                # Calcula largura e altura se não fornecidas
                if width is None:
                    width = get_chart_width(self.content_width, CHART_WIDTH_RATIO)
                if height is None:
                    height = get_chart_height(CHART_HEIGHT_BASE)
            
            # Verifica se precisa quebrar página
            if self.get_y() + height > self.h - self.MARGIN_BOTTOM:
                self.add_page()
            
            # Adiciona título se fornecido usando novo sistema
            if title:
                self.add_section_title(title, level=2)
            
            # Calcula posição X para centralizar
            x_position = (self.w - width) / 2
            
            # Adiciona imagem ao PDF
            self.image(image, x=x_position, y=self.get_y(), w=width, h=height)
            self.ln(height + self.PADDING_MEDIUM)
            
        except Exception as e:
            logger.error(f"Erro ao adicionar gráfico ao PDF: {e}", exc_info=True)
            # Adiciona mensagem de erro no PDF
            self.add_text(f'Erro ao carregar gráfico: {str(e)[:50]}', size='small', style='')
            self.set_text_color(255, 0, 0)
            self.set_text_color(0, 0, 0)
            self.add_spacing('small')
    
    def add_metric_card(self, label, value, comparison=None, comparison_label=None):
        """
        Adiciona card de métrica (KPI) ao PDF com fundo cinza e tamanhos fixos (estilo do outro projeto)
        
        Args:
            label: Rótulo da métrica (ex: "Total de Vendas")
            value: Valor da métrica (formatado como string)
            comparison: Valor de comparação opcional (ex: "+15.5%")
            comparison_label: Rótulo da comparação (ex: "vs. período anterior")
        """
        # Tamanhos fixos (estilo do outro projeto)
        card_height = METRIC_CARD_HEIGHT  # 70mm fixo
        card_width = METRIC_CARD_WIDTH_FULL  # 195mm fixo (largura total menos margens)
        card_margin_x = CARD_MARGIN_X  # 10mm
        line_height = CARD_LINE_HEIGHT  # 5mm fixo
        
        # Verifica se precisa quebrar página
        if self.get_y() + card_height > self.h - self.MARGIN_BOTTOM:
            self.add_page()
        
        x_start = self.get_x()
        y_start = self.get_y()
        
        # Ajusta largura se não couber (mas mantém proporção)
        available_width = self.content_width
        if card_width > available_width:
            card_width = available_width
        
        # Desenha card com fundo cinza (estilo do outro projeto)
        self.set_fill_color(*CARD_BG_COLOR)
        self.rect(x_start, y_start, card_width, card_height, 'F')
        
        # Borda do card
        self.set_draw_color(*PRIMARY_COLOR)
        self.rect(x_start, y_start, card_width, card_height)
            
        # Label (estilo do outro projeto)
        self.set_xy(x_start + 5, y_start + 5)
        self.set_font('Arial', '', self.FONT_SIZE_NORMAL)
        self.set_text_color(*PRIMARY_COLOR)
        self.cell(0, 6, str(label), 0, 1, 'L')
        
        # Valor (estilo do outro projeto)
        self.set_font('Arial', 'B', self.FONT_SIZE_XXLARGE)
        value_y = y_start + 14  # 5 (topo) + 6 (label) + 3 (espaço)
        self.set_xy(x_start + 5, value_y)
        self.cell(0, line_height, str(value), 0, 0, 'L')
        
        # Comparação se fornecida
        if comparison is not None:
            self.set_font('Arial', '', self.FONT_SIZE_SMALL)
            comparison_y = value_y + line_height + 1
            self.set_xy(x_start + 5, comparison_y)
            comparison_text = str(comparison)
            if comparison_label:
                comparison_text += f" {comparison_label}"
            self.cell(0, line_height, comparison_text, 0, 0, 'L')
        
        # Move para próxima linha (cards em linha única, um abaixo do outro)
        self.set_xy(self.MARGIN_LEFT, y_start + card_height + CARD_SPACING)
    
    def add_info_box(self, title, data_dict, width=None, height=None):
        """
        Adiciona uma caixa informativa com título e dados em colunas (estilo do outro projeto)
        
        Args:
            title: Título da caixa
            data_dict: Dicionário com {label: value} para exibir
            width: Largura da caixa (None = largura total)
            height: Altura da caixa (None = calculada automaticamente)
        """
        if width is None:
            width = self.content_width
        
        # Calcula altura se não fornecida
        if height is None:
            num_items = len(data_dict)
            num_rows = (num_items + 1) // 2  # 2 colunas
            title_height = self.get_line_height(self.FONT_SIZE_LARGE)
            line_height = self.get_line_height(self.FONT_SIZE_NORMAL)
            height = title_height + (line_height * num_rows) + (self.CELL_PADDING_V * 4) + self.PADDING_SMALL
        
        x_start = self.get_x()
        y_start = self.get_y()
        
        # Verifica se precisa quebrar página
        if self.get_y() + height > self.h - self.MARGIN_BOTTOM:
            self.add_page()
            x_start = self.MARGIN_LEFT
            y_start = self.get_y()
        
        # Desenha caixa com fundo cinza
        self.set_fill_color(*CARD_BG_COLOR)
        self.set_draw_color(*PRIMARY_COLOR)
        self.rect(x_start, y_start, width, height, 'F')
        self.rect(x_start, y_start, width, height)
        
        # Título
        self.set_font('Arial', 'B', self.FONT_SIZE_LARGE)
        self.set_text_color(*PRIMARY_COLOR)
        title_y = y_start + self.CELL_PADDING_V
        self.set_xy(x_start + self.CELL_PADDING_H, title_y)
        self.cell(width - (self.CELL_PADDING_H * 2), 
                 self.get_line_height(self.FONT_SIZE_LARGE), 
                 str(title), 0, 0, 'L')
        
        # Dados em 2 colunas
        col_width = (width - (self.CELL_PADDING_H * 4)) / 2
        col1_x = x_start + self.CELL_PADDING_H
        col2_x = col1_x + col_width + self.CELL_PADDING_H
        start_data_y = title_y + self.get_line_height(self.FONT_SIZE_LARGE) + self.PADDING_SMALL
        line_h = self.get_line_height(self.FONT_SIZE_NORMAL)
        
        items = list(data_dict.items())
        for i, (label, value) in enumerate(items):
            # Calcula posição: coluna e linha
            col = i % 2
            row = i // 2
            
            col_x = col1_x if col == 0 else col2_x
            y_pos = start_data_y + (row * (line_h + 1))
            
            self.set_xy(col_x, y_pos)
            self.set_font('Arial', '', self.FONT_SIZE_NORMAL)
            self.cell(30, line_h, f"{label}:", 0, 0, 'L')
            self.set_font('Arial', 'B', self.FONT_SIZE_NORMAL)
            self.cell(col_width - 30, line_h, str(value), 0, 0, 'L')
            
            # Move para próxima linha
        self.set_xy(self.MARGIN_LEFT, y_start + height + self.PADDING_MEDIUM)
        self.add_spacing('medium')
    
    def create_data_cards_grid(self, data_list, card_fields, cards_per_row=2, cards_per_page=8):
        """
        Cria cards em grid (estilo do outro projeto - como usuários em 2x4)
        
        Args:
            data_list: Lista de dicionários ou tuplas com os dados
            card_fields: Lista de tuplas (label, field_index ou key) para cada campo do card
            cards_per_row: Número de cards por linha (padrão: 2)
            cards_per_page: Número de cards por página (padrão: 8 para grid 2x4)
        """
        total_items = len(data_list)
        
        if total_items == 0:
            self.add_page()
            self.ln(10)
            self.add_text('Nenhum item encontrado para os critérios informados.', size='normal', align='C')
            self.ln(8)
            self.set_font('Arial', 'B', self.FONT_SIZE_XLARGE)
            self.cell(0, self.get_line_height(self.FONT_SIZE_XLARGE), 
                     f'Total: {total_items}', 0, 1, 'C')
            return
        
        # Tamanhos fixos (estilo do outro projeto)
        card_width = DATA_CARD_WIDTH  # 90mm fixo
        card_height = DATA_CARD_HEIGHT  # 50mm fixo
        card_margin_x = CARD_MARGIN_X  # 10mm
        card_spacing_x = CARD_GRID_SPACING_X  # 10mm
        card_spacing_y = CARD_GRID_SPACING_Y  # 10mm
        line_height = CARD_LINE_HEIGHT  # 5mm fixo
        
        for i, item in enumerate(data_list):
            # Nova página a cada N cards
            if i % cards_per_page == 0:
                self.add_page()
                self.current_page_y = PAGE_START_Y  # 35mm fixo (posição após header)
            
            # Calcula posição no grid (estilo do outro projeto)
            row = (i % cards_per_page) // cards_per_row
            col = (i % cards_per_page) % cards_per_row
            
            # Posição calculada com valores fixos
            card_x = card_margin_x + col * (card_width + card_spacing_x)
            card_y = self.current_page_y + row * (card_height + card_spacing_y)
            
            self._draw_data_card(item, card_fields, card_x, card_y, card_width, card_height, line_height)
        
        # Total no final
        self.set_y(-30)
        self.set_font('Arial', 'B', self.FONT_SIZE_XLARGE)
        self.cell(0, self.get_line_height(self.FONT_SIZE_XLARGE), 
                 f'Total: {total_items}', 0, 1, 'C')
    
    def _draw_data_card(self, data, fields, start_x, start_y, width, height, line_height):
        """Desenha um card de dados individual com tamanhos fixos (estilo do outro projeto)"""
        # Fundo cinza
        self.set_fill_color(*CARD_BG_COLOR)
        self.rect(start_x, start_y, width, height, 'F')
        
        # Borda
        self.set_draw_color(*PRIMARY_COLOR)
        self.rect(start_x, start_y, width, height)
        
        # Título do card (primeiro campo geralmente é o nome/título) - estilo do outro projeto
        if fields:
            first_field = fields[0]
            if isinstance(first_field, tuple):
                label, field_key = first_field
            else:
                field_key = first_field
            
            # Obtém valor
            if isinstance(data, dict):
                title_value = data.get(field_key, 'N/A') if isinstance(field_key, str) else data.get(field_key, 'N/A')
            elif isinstance(data, (list, tuple)):
                title_value = data[field_key] if field_key < len(data) else 'N/A'
            else:
                title_value = str(data)
            
            # Desenha título (estilo do outro projeto: 5mm do topo, fonte B 10pt)
            self.set_xy(start_x + 5, start_y + 5)
            self.set_font('Arial', 'B', self.FONT_SIZE_NORMAL)
            self.set_text_color(*PRIMARY_COLOR)
            title_text = str(title_value)
            # Trunca se necessário
            max_title_width = width - 10
            if self.get_string_width(title_text) > max_title_width:
                while self.get_string_width(title_text + '...') > max_title_width and len(title_text):
                    title_text = title_text[:-1]
                title_text += '...'
            self.cell(max_title_width, 6, title_text, 0, 1, 'L')
        
        # Campos restantes (estilo do outro projeto: 14mm do topo, linha a cada 6mm)
        y_pos = start_y + 14  # 5 (topo) + 6 (título) + 3 (espaço)
        
        for field in fields[1:]:  # Pula o primeiro que já foi usado como título
            if y_pos + line_height > start_y + height - 5:
                break  # Não cabe mais campos
            
            if isinstance(field, tuple):
                label, field_key = field
            else:
                label = str(field)
                field_key = field
            
            # Obtém valor
            if isinstance(data, dict):
                value = data.get(field_key, 'N/A') if isinstance(field_key, str) else data.get(field_key, 'N/A')
            elif isinstance(data, (list, tuple)):
                value = data[field_key] if field_key < len(data) else 'N/A'
            else:
                value = str(data)
            
            # Label (estilo do outro projeto: fonte normal 9pt, largura fixa 30mm)
            self.set_xy(start_x + 5, y_pos)
            self.set_font('Arial', '', 9)  # FONT_SIZE_SMALL = 9
            self.cell(30, line_height, f"{label}:", 0, 0, 'L')
            
            # Valor (estilo do outro projeto: fonte B 9pt)
            self.set_font('Arial', 'B', 9)
            value_text = str(value)
            max_value_width = width - 40  # 30 para label + 10 de margem
            if self.get_string_width(value_text) > max_value_width:
                while self.get_string_width(value_text + '...') > max_value_width and len(value_text):
                    value_text = value_text[:-1]
                value_text += '...'
            self.cell(max_value_width, line_height, value_text, 0, 0, 'L')
            
            y_pos += line_height + 1  # Espaçamento entre linhas
    
    def add_comparison_section(self, current_data, previous_data, title="Comparação de Períodos"):
        """
        Adiciona seção de comparação entre dois períodos usando novo sistema
        
        Args:
            current_data: dict com dados do período atual (ex: {"revenue": 50000, "orders": 500})
            previous_data: dict com dados do período anterior (ex: {"revenue": 43250, "orders": 450})
            title: Título da seção
        """
        # Título usando novo sistema
        self.add_section_title(title, level=1)
        
        # Prepara dados para tabela
        headers = ['Métrica', 'Período Atual', 'Período Anterior', 'Variação']
        table_data = []
        
        # Mapeia nomes de métricas para português
        metric_names = {
            'total_revenue': 'Receita Total',
            'total_orders': 'Total de Pedidos',
            'avg_ticket': 'Ticket Médio',
            'cancellation_rate': 'Taxa de Cancelamento',
            'revenue': 'Receita',
            'orders': 'Pedidos',
            'expenses': 'Despesas',
            'net': 'Líquido'
        }
        
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
            
            # Usa nome traduzido se disponível, senão formata a chave
            metric_name = metric_names.get(key, str(key).replace('_', ' ').title())
            
            table_data.append([
                metric_name,  # Nome completo sem truncamento
                current_str,
                previous_str,
                variation
            ])
        
        # Usa add_table com larguras fixas maiores para a coluna Métrica
        # Calcula larguras proporcionais, mas garante espaço mínimo para Métrica
        total_width = self.content_width
        metric_col_width = max(60, total_width * 0.3)  # Mínimo 60mm ou 30% da largura
        other_cols_width = (total_width - metric_col_width) / 3  # Divide o resto em 3 colunas
        
        col_widths = [
            metric_col_width,
            other_cols_width,
            other_cols_width,
            other_cols_width
        ]
        
        self.add_table(headers, table_data, col_widths=col_widths, aligns=['L', 'R', 'R', 'C'], alternate_rows=True)
    
    def add_trend_analysis(self, trend_data, title="Análise de Tendências"):
        """
        Adiciona análise de tendências ao PDF
        
        Args:
            trend_data: dict com dados de tendência (ex: {"metric": "Vendas", "trend": "crescente", "percentage": 15.5})
            title: Título da seção
        """
        # Verifica se precisa quebrar página
        if self.get_y() + 30 > self.h - 25:
            self.add_page()
        
        # Título da seção - aumentado
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, title, 0, 1, 'L')
        self.ln(4)
        
        # Análise de cada métrica - aumentado
        self.set_font('Arial', '', 11)
        if isinstance(trend_data, dict):
            trend_data = [trend_data]
        
        for item in trend_data:
            metric = item.get('metric', 'Métrica')
            trend = item.get('trend', 'estável')
            percentage = item.get('percentage', 0)
            
            # Determina cor e ícone baseado na tendência
            # CORREÇÃO: Substituir setas Unicode por caracteres compatíveis com latin-1
            if trend.lower() in ['crescente', 'aumento', 'up']:
                trend_text = f"[+] Crescente ({percentage:+.1f}%)"
            elif trend.lower() in ['decrescente', 'queda', 'down']:
                trend_text = f"[-] Decrescente ({percentage:+.1f}%)"
            else:
                trend_text = f"[=] Estavel ({percentage:+.1f}%)"
            
            # CORREÇÃO: Substituir bullet Unicode por caractere compatível com latin-1
            self.cell(0, 8, f"- {metric}: {trend_text}", 0, 1, 'L')
        
        self.ln(8)


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
            self.add_spacing('medium')
        
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
            self.add_section_title('Vendas por Tipo de Pedido', level=1)
            
            headers = ['Tipo', 'Pedidos', 'Receita']
            table_data = [
                [
                    str(item.get('type', 'N/A')),
                    str(item.get('orders', 0)),
                    format_currency(item.get('revenue', 0))
                ]
                for item in sales_by_type
            ]
            
            # Tabela com cabeçalho colorido e linhas alternadas
            self.add_table(headers, table_data, aligns=['L', 'C', 'R'], 
                          alternate_rows=True)
        
        # Gráfico: Métodos de pagamento (pizza)
        if report_data.get('charts', {}).get('payment_methods'):
            self.add_chart(
                report_data['charts']['payment_methods'],
                title="Vendas por Método de Pagamento",
                is_pie_chart=True
            )
        
        # Top 10 Produtos
        top_products = report_data.get('top_products', [])
        if top_products:
            self.add_section_title('Top 10 Produtos Mais Vendidos', level=1)
            
            if report_data.get('charts', {}).get('top_products'):
                self.add_chart(
                    report_data['charts']['top_products'],
                    title=None  # Título já foi adicionado acima
                )
            
            headers = ['Produto', 'Quantidade', 'Receita']
            table_data = [
                [
                    str(item.get('name', 'N/A'))[:35],
                    str(item.get('quantity', 0)),
                    format_currency(item.get('revenue', 0))
                ]
                for item in top_products[:10]
            ]
            
            # Tabela com cabeçalho colorido e linhas alternadas
            self.add_table(headers, table_data, aligns=['L', 'C', 'R'],
                          alternate_rows=True)
        
        # Top 10 Clientes
        top_customers = report_data.get('top_customers', [])
        if top_customers:
            self.add_section_title('Top 10 Clientes', level=1)
            
            headers = ['Cliente', 'Pedidos', 'Total Gasto']
            table_data = [
                [
                    str(item.get('name', 'N/A'))[:35],
                    str(item.get('orders', 0)),
                    format_currency(item.get('spent', 0))
                ]
                for item in top_customers[:10]
            ]
            
            # Tabela com cabeçalho colorido e linhas alternadas
            self.add_table(headers, table_data, aligns=['L', 'C', 'R'],
                          alternate_rows=True)


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
                    height=80,
                    is_pie_chart=True
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
                    height=80,
                    is_pie_chart=True
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
                    height=80,
                    is_pie_chart=True
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
                title="Distribuição de Ingredientes por Status",
                is_pie_chart=True
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
