"""
Gerador de gráficos para relatórios PDF
Utiliza matplotlib para criar gráficos e converter para base64
"""

import matplotlib
# ALTERAÇÃO: Usar backend sem GUI para servidor
matplotlib.use('Agg')  # Backend sem GUI
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import io
import base64
import logging
from datetime import datetime, date
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# ALTERAÇÃO: Configurar estilo padrão para gráficos
plt.style.use('default')
# Configurações de fonte para suportar caracteres especiais
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False


def _encode_chart_to_base64(fig):
    """
    Converte figura matplotlib para base64
    
    Args:
        fig: Figura matplotlib
    
    Returns:
        str: Imagem em base64
    """
    try:
        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', dpi=100, bbox_inches='tight', 
                   facecolor='white', edgecolor='none')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        plt.close(fig)  # Fecha figura para liberar memória
        return image_base64
    except Exception as e:
        logger.error(f"Erro ao codificar gráfico em base64: {e}", exc_info=True)
        plt.close(fig)
        return None


def generate_line_chart(data, title, x_label='', y_label='', width=10, height=6):
    """
    Gera gráfico de linha (tendências temporais)
    
    Args:
        data: dict com 'dates' (lista de datas) e 'values' (lista de valores)
              ou lista de dicts com 'date' e 'value'
        title: Título do gráfico
        x_label: Rótulo do eixo X
        y_label: Rótulo do eixo Y
        width: Largura da figura em polegadas
        height: Altura da figura em polegadas
    
    Returns:
        str: Imagem em base64 ou None se erro
    """
    try:
        fig, ax = plt.subplots(figsize=(width, height))
        
        # Processa dados
        if isinstance(data, dict):
            dates = data.get('dates', [])
            values = data.get('values', [])
        elif isinstance(data, list):
            # Assume lista de dicts
            dates = [item.get('date') for item in data]
            values = [item.get('value', 0) for item in data]
        else:
            logger.error("Formato de dados inválido para gráfico de linha")
            return None
        
        # Converte datas se necessário
        if dates and isinstance(dates[0], str):
            dates = [datetime.fromisoformat(d.replace('Z', '+00:00')) if 'T' in d 
                    else datetime.strptime(d, '%Y-%m-%d') for d in dates]
        
        # Plota gráfico
        ax.plot(dates, values, marker='o', linewidth=2, markersize=4)
        ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
        ax.set_xlabel(x_label, fontsize=11)
        ax.set_ylabel(y_label, fontsize=11)
        ax.grid(True, alpha=0.3, linestyle='--')
        
        # Formata eixo X para datas
        if dates:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m/%Y'))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        plt.tight_layout()
        return _encode_chart_to_base64(fig)
    except Exception as e:
        logger.error(f"Erro ao gerar gráfico de linha: {e}", exc_info=True)
        return None


def generate_bar_chart(data, title, x_label='', y_label='', width=10, height=6, 
                       horizontal=False, color='#4CAF50'):
    """
    Gera gráfico de barras (comparações)
    
    Args:
        data: dict com 'labels' (lista de rótulos) e 'values' (lista de valores)
              ou lista de dicts com 'label' e 'value'
        title: Título do gráfico
        x_label: Rótulo do eixo X
        y_label: Rótulo do eixo Y
        width: Largura da figura em polegadas
        height: Altura da figura em polegadas
        horizontal: Se True, barras horizontais
        color: Cor das barras (padrão: verde)
    
    Returns:
        str: Imagem em base64 ou None se erro
    """
    try:
        fig, ax = plt.subplots(figsize=(width, height))
        
        # Processa dados
        if isinstance(data, dict):
            labels = data.get('labels', [])
            values = data.get('values', [])
        elif isinstance(data, list):
            # Assume lista de dicts
            labels = [str(item.get('label', '')) for item in data]
            values = [float(item.get('value', 0)) for item in data]
        else:
            logger.error("Formato de dados inválido para gráfico de barras")
            return None
        
        # Trunca labels muito longos
        labels = [label[:20] + '...' if len(label) > 20 else label for label in labels]
        
        # Plota gráfico
        if horizontal:
            ax.barh(labels, values, color=color)
        else:
            ax.bar(labels, values, color=color)
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
        ax.set_xlabel(x_label, fontsize=11)
        ax.set_ylabel(y_label, fontsize=11)
        ax.grid(True, alpha=0.3, linestyle='--', axis='y' if horizontal else 'x')
        
        plt.tight_layout()
        return _encode_chart_to_base64(fig)
    except Exception as e:
        logger.error(f"Erro ao gerar gráfico de barras: {e}", exc_info=True)
        return None


def generate_pie_chart(data, title, width=8, height=8, colors=None):
    """
    Gera gráfico de pizza (distribuições)
    
    Args:
        data: dict com 'labels' (lista de rótulos) e 'values' (lista de valores)
              ou lista de dicts com 'label' e 'value'
        title: Título do gráfico
        width: Largura da figura em polegadas
        height: Altura da figura em polegadas
        colors: Lista de cores (opcional)
    
    Returns:
        str: Imagem em base64 ou None se erro
    """
    try:
        fig, ax = plt.subplots(figsize=(width, height))
        
        # Processa dados
        if isinstance(data, dict):
            labels = data.get('labels', [])
            values = data.get('values', [])
        elif isinstance(data, list):
            # Assume lista de dicts
            labels = [str(item.get('label', '')) for item in data]
            values = [float(item.get('value', 0)) for item in data]
        else:
            logger.error("Formato de dados inválido para gráfico de pizza")
            return None
        
        # Cores padrão se não fornecidas
        if not colors:
            colors = ['#4CAF50', '#2196F3', '#FF9800', '#F44336', '#9C27B0', 
                     '#00BCD4', '#FFC107', '#795548', '#607D8B', '#E91E63']
        
        # Plota gráfico
        wedges, texts, autotexts = ax.pie(values, labels=labels, autopct='%1.1f%%',
                                          colors=colors[:len(values)], startangle=90)
        
        # Melhora legibilidade
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
        
        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
        
        plt.tight_layout()
        return _encode_chart_to_base64(fig)
    except Exception as e:
        logger.error(f"Erro ao gerar gráfico de pizza: {e}", exc_info=True)
        return None


def generate_multi_line_chart(data_series, title, x_label='', y_label='', 
                              width=10, height=6, legend_labels=None):
    """
    Gera gráfico de múltiplas linhas (comparação de séries)
    
    Args:
        data_series: Lista de dicts, cada um com 'dates' e 'values'
        title: Título do gráfico
        x_label: Rótulo do eixo X
        y_label: Rótulo do eixo Y
        width: Largura da figura em polegadas
        height: Altura da figura em polegadas
        legend_labels: Lista de rótulos para legenda
    
    Returns:
        str: Imagem em base64 ou None se erro
    """
    try:
        fig, ax = plt.subplots(figsize=(width, height))
        
        colors = ['#4CAF50', '#2196F3', '#FF9800', '#F44336', '#9C27B0']
        
        for idx, series in enumerate(data_series):
            dates = series.get('dates', [])
            values = series.get('values', [])
            
            # Converte datas se necessário
            if dates and isinstance(dates[0], str):
                dates = [datetime.fromisoformat(d.replace('Z', '+00:00')) if 'T' in d 
                        else datetime.strptime(d, '%Y-%m-%d') for d in dates]
            
            label = legend_labels[idx] if legend_labels and idx < len(legend_labels) else f'Série {idx+1}'
            ax.plot(dates, values, marker='o', linewidth=2, markersize=4, 
                   color=colors[idx % len(colors)], label=label)
        
        ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
        ax.set_xlabel(x_label, fontsize=11)
        ax.set_ylabel(y_label, fontsize=11)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.legend(loc='best')
        
        # Formata eixo X para datas
        if data_series and data_series[0].get('dates'):
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m/%Y'))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        plt.tight_layout()
        return _encode_chart_to_base64(fig)
    except Exception as e:
        logger.error(f"Erro ao gerar gráfico de múltiplas linhas: {e}", exc_info=True)
        return None


def generate_stacked_bar_chart(data, title, x_label='', y_label='', 
                               width=10, height=6, stack_labels=None):
    """
    Gera gráfico de barras empilhadas
    
    Args:
        data: dict com 'categories' (rótulos) e 'series' (lista de listas de valores)
        title: Título do gráfico
        x_label: Rótulo do eixo X
        y_label: Rótulo do eixo Y
        width: Largura da figura em polegadas
        height: Altura da figura em polegadas
        stack_labels: Lista de rótulos para cada série empilhada
    
    Returns:
        str: Imagem em base64 ou None se erro
    """
    try:
        fig, ax = plt.subplots(figsize=(width, height))
        
        categories = data.get('categories', [])
        series = data.get('series', [])
        
        if not categories or not series:
            logger.error("Dados insuficientes para gráfico de barras empilhadas")
            return None
        
        # Trunca labels
        categories = [cat[:15] + '...' if len(cat) > 15 else cat for cat in categories]
        
        colors = ['#4CAF50', '#2196F3', '#FF9800', '#F44336', '#9C27B0']
        
        # Plota barras empilhadas
        bottom = [0] * len(categories)
        for idx, serie in enumerate(series):
            label = stack_labels[idx] if stack_labels and idx < len(stack_labels) else f'Série {idx+1}'
            ax.bar(categories, serie, bottom=bottom, label=label, 
                  color=colors[idx % len(colors)])
            # Atualiza bottom para próxima série
            bottom = [bottom[i] + serie[i] for i in range(len(categories))]
        
        ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
        ax.set_xlabel(x_label, fontsize=11)
        ax.set_ylabel(y_label, fontsize=11)
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3, linestyle='--', axis='y')
        
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        plt.tight_layout()
        return _encode_chart_to_base64(fig)
    except Exception as e:
        logger.error(f"Erro ao gerar gráfico de barras empilhadas: {e}", exc_info=True)
        return None

