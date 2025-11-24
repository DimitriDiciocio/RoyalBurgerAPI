"""
Configurações de layout para relatórios PDF
Todas as constantes podem ser ajustadas para personalizar o layout
"""

# ============================================================================
# MARGENS DA PÁGINA (em mm)
# ============================================================================
MARGIN_LEFT = 12
MARGIN_RIGHT = 12
MARGIN_TOP = 15
MARGIN_BOTTOM = 15

# ============================================================================
# ESPAÇAMENTOS (em mm)
# ============================================================================
# Espaçamento pequeno: entre elementos relacionados (ex: título e tabela)
PADDING_SMALL = 2

# Espaçamento médio: entre seções diferentes
PADDING_MEDIUM = 3

# Espaçamento grande: entre blocos principais
PADDING_LARGE = 5

# ============================================================================
# TAMANHOS DE FONTE
# ============================================================================
FONT_SIZE_TINY = 7       # Textos muito pequenos (rodapé, notas)
FONT_SIZE_SMALL = 8      # Textos pequenos (legendas, subtítulos)
FONT_SIZE_NORMAL = 9     # Texto padrão (corpo do relatório)
FONT_SIZE_MEDIUM = 10    # Textos médios (cabeçalhos de tabela)
FONT_SIZE_LARGE = 11     # Textos grandes (subtítulos de seção)
FONT_SIZE_XLARGE = 12    # Títulos de seção
FONT_SIZE_XXLARGE = 14   # Títulos principais
FONT_SIZE_TITLE = 16     # Título do relatório

# ============================================================================
# PROPORÇÕES E RATIOS
# ============================================================================
# Ratio de altura de linha (1.15 = 15% maior que a fonte - mais compacto)
LINE_HEIGHT_RATIO = 1.15

# Padding vertical em células de tabela
CELL_PADDING_V = 1.5

# Padding horizontal em células de tabela
CELL_PADDING_H = 2

# ============================================================================
# TAMANHOS DE GRÁFICOS (proporcionais)
# ============================================================================
# Largura do gráfico como proporção da largura útil (0.80 = 80% - mais compacto)
CHART_WIDTH_RATIO = 0.80

# Altura base dos gráficos (em mm) - reduzido para evitar sobreposição
CHART_HEIGHT_BASE = 80

# Altura mínima dos gráficos (em mm)
CHART_HEIGHT_MIN = 60

# Altura máxima dos gráficos (em mm)
CHART_HEIGHT_MAX = 100

# ============================================================================
# TAMANHOS DE CARDS DE MÉTRICAS
# ============================================================================
# Largura mínima de um card (em mm)
CARD_MIN_WIDTH = 70

# Altura mínima de um card (em mm)
CARD_MIN_HEIGHT = 25

# Espaçamento entre cards (em mm)
CARD_SPACING = 5

# ============================================================================
# CORES E ESTILOS
# ============================================================================
# Cores padrão
PRIMARY_COLOR = (56, 56, 56)  # Cinza escuro
ACCENT_COLOR = (220, 50, 50)  # Vermelho para destaques
CARD_BG_COLOR = (240, 240, 240)  # Cinza claro para fundo de cards
TABLE_HEADER_BG = (230, 215, 245)  # Roxo suave para cabeçalhos de tabela
TABLE_ROW_ALT_BG = (245, 245, 245)  # Cinza suave para linhas alternadas
FOOTER_TEXT_COLOR = (150, 150, 150)  # Cinza para rodapé
SUCCESS_COLOR = (0, 150, 0)  # Verde para receitas/sucesso
ERROR_COLOR = (200, 0, 0)  # Vermelho para despesas/erro

# ============================================================================
# LAYOUT DE CARDS EM GRID
# ============================================================================
# Cards por linha (padrão: 2)
CARDS_PER_ROW = 2

# Cards por página (padrão: 8 para grid 2x4)
CARDS_PER_PAGE = 8

# Altura padrão de card de dados (em mm) - reduzido para evitar sobreposição
DATA_CARD_HEIGHT = 35

# Altura padrão de card de métrica (em mm) - reduzido para evitar sobreposição
METRIC_CARD_HEIGHT = 45

# Largura fixa de card de métrica (em mm) - quando em linha única
METRIC_CARD_WIDTH_FULL = 180

# Largura fixa de card de dados em grid (em mm)
DATA_CARD_WIDTH = 85

# Altura de linha fixa para cards (em mm) - reduzido
CARD_LINE_HEIGHT = 4

# Espaçamento entre cards em grid (em mm) - reduzido
CARD_GRID_SPACING_X = 7
CARD_GRID_SPACING_Y = 7

# Margem lateral dos cards (em mm)
CARD_MARGIN_X = 8

# Posição Y inicial após header (em mm) - reduzido
PAGE_START_Y = 30

# ============================================================================
# TABELAS
# ============================================================================
# Largura mínima de uma coluna (em mm)
TABLE_COL_MIN_WIDTH = 15

# Largura máxima de uma coluna (em mm)
TABLE_COL_MAX_WIDTH = 100

# Número máximo de linhas a analisar para calcular larguras
TABLE_ANALYSIS_ROWS = 20

# ============================================================================
# MAPAS DE TRADUÇÃO (para filtros)
# ============================================================================
FILTER_LABELS = {
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

# Mapas de valores para tradução
ORDER_TYPE_MAP = {
    'delivery': 'Entrega',
    'pickup': 'Retirada',
    'on_site': 'No local'
}

STATUS_MAP = {
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

PAYMENT_METHOD_MAP = {
    'pix': 'PIX',
    'credit_card': 'Cartão de Crédito',
    'debit_card': 'Cartão de Débito',
    'cash': 'Dinheiro',
    'bank_transfer': 'Transferência Bancária'
}

# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

def get_line_height(font_size):
    """Calcula altura de linha baseada no tamanho da fonte"""
    return font_size * LINE_HEIGHT_RATIO


def get_content_width(page_width, margin_left, margin_right):
    """Calcula largura útil do conteúdo"""
    return page_width - margin_left - margin_right


def get_content_height(page_height, margin_top, margin_bottom):
    """Calcula altura útil do conteúdo"""
    return page_height - margin_top - margin_bottom


def get_chart_width(content_width, ratio=CHART_WIDTH_RATIO):
    """Calcula largura do gráfico baseada na largura útil"""
    return int(content_width * ratio)


def get_chart_height(base_height=CHART_HEIGHT_BASE, min_height=CHART_HEIGHT_MIN, max_height=CHART_HEIGHT_MAX):
    """Calcula altura do gráfico com limites"""
    return max(min_height, min(base_height, max_height))


def get_card_width(content_width, num_cards_per_row=2, spacing=CARD_SPACING):
    """Calcula largura de card baseada no espaço disponível"""
    if num_cards_per_row == 1:
        return content_width
    available_width = content_width - (spacing * (num_cards_per_row - 1))
    return int(available_width / num_cards_per_row)


def get_table_col_widths(headers, data, total_width, min_width=TABLE_COL_MIN_WIDTH, max_width=TABLE_COL_MAX_WIDTH):
    """
    Calcula larguras de colunas proporcionais baseadas no conteúdo
    
    Args:
        headers: Lista com os cabeçalhos das colunas
        data: Lista de listas com os dados das linhas
        total_width: Largura total disponível
        min_width: Largura mínima de uma coluna
        max_width: Largura máxima de uma coluna
    
    Returns:
        Lista com larguras de cada coluna
    """
    num_cols = len(headers)
    if num_cols == 0:
        return []
    
    # Calcula tamanho médio do texto em cada coluna
    col_sizes = []
    for i in range(num_cols):
        header_size = len(str(headers[i]))
        max_data_size = 0
        for row in data[:TABLE_ANALYSIS_ROWS]:
            if i < len(row):
                max_data_size = max(max_data_size, len(str(row[i])))
        col_sizes.append(max(header_size, max_data_size, 5))
    
    # Calcula proporção
    total_size = sum(col_sizes)
    if total_size == 0:
        return [total_width // num_cols] * num_cols
    
    # Calcula larguras proporcionais
    col_widths = []
    remaining_width = total_width
    
    for i, size in enumerate(col_sizes):
        if i == num_cols - 1:
            col_widths.append(remaining_width)
        else:
            width = int((size / total_size) * total_width)
            width = max(min_width, min(width, max_width))
            col_widths.append(width)
            remaining_width -= width
    
    return col_widths

