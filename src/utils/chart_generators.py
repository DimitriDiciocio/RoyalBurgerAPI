"""
Gerador de gráficos para relatórios PDF
Utiliza SVG para criar gráficos simples sem dependências pesadas
"""

import io
import base64
import logging
import math
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Cores padrão para gráficos
DEFAULT_COLORS = ['#4CAF50', '#2196F3', '#FF9800', '#F44336', '#9C27B0', 
                  '#00BCD4', '#FFC107', '#795548', '#607D8B', '#E91E63']


def _hex_to_rgb(hex_color):
    """Converte cor hexadecimal para RGB"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def _encode_image_to_base64(image):
    """
    Converte imagem PIL para base64
    
    Args:
        image: Imagem PIL
    
    Returns:
        str: Imagem em base64 ou None se erro
    """
    try:
        buffer = io.BytesIO()
        image.save(buffer, format='PNG', dpi=(100, 100))
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        return image_base64
    except Exception as e:
        logger.error(f"Erro ao codificar imagem em base64: {e}", exc_info=True)
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
        width: Largura da figura em polegadas (convertido para pixels)
        height: Altura da figura em polegadas (convertido para pixels)
    
    Returns:
        str: Imagem em base64 ou None se erro
    """
    try:
        # Converte polegadas para pixels (100 DPI)
        img_width = int(width * 100)
        img_height = int(height * 100)
        
        # Margens
        margin_top = 60
        margin_bottom = 50
        margin_left = 70
        margin_right = 30
        
        chart_width = img_width - margin_left - margin_right
        chart_height = img_height - margin_top - margin_bottom
        
        # Cria imagem
        img = Image.new('RGB', (img_width, img_height), color='white')
        draw = ImageDraw.Draw(img)
        
        # Processa dados
        if isinstance(data, dict):
            dates = data.get('dates', [])
            values = data.get('values', [])
        elif isinstance(data, list):
            dates = [item.get('date') for item in data]
            values = [item.get('value', 0) for item in data]
        else:
            logger.error("Formato de dados inválido para gráfico de linha")
            return None
        
        if not dates or not values or len(dates) != len(values):
            logger.error("Dados insuficientes ou incompatíveis para gráfico de linha")
            return None
        
        # Converte valores para float
        values = [float(v) for v in values]
        
        # Calcula ranges
        min_val = min(values) if values else 0
        max_val = max(values) if values else 1
        val_range = max_val - min_val if max_val != min_val else 1
        
        # Desenha título
        try:
            font_title = ImageFont.truetype("arial.ttf", 16)
            font_label = ImageFont.truetype("arial.ttf", 11)
            font_axis = ImageFont.truetype("arial.ttf", 9)
        except:
            font_title = ImageFont.load_default()
            font_label = ImageFont.load_default()
            font_axis = ImageFont.load_default()
        
        # Título
        title_bbox = draw.textbbox((0, 0), title, font=font_title)
        title_width = title_bbox[2] - title_bbox[0]
        draw.text(((img_width - title_width) // 2, 15), title, fill='black', font=font_title)
        
        # Labels dos eixos
        if x_label:
            x_label_bbox = draw.textbbox((0, 0), x_label, font=font_label)
            x_label_width = x_label_bbox[2] - x_label_bbox[0]
            draw.text(((img_width - x_label_width) // 2, img_height - 35), x_label, fill='black', font=font_label)
        
        if y_label:
            # Rotaciona label do eixo Y (vertical)
            y_label_text = y_label
            y_label_bbox = draw.textbbox((0, 0), y_label_text, font=font_label)
            draw.text((15, (img_height - y_label_bbox[3]) // 2), y_label_text, fill='black', font=font_label)
        
        # Desenha eixos
        axis_color = (100, 100, 100)
        # Eixo Y
        draw.line([(margin_left, margin_top), (margin_left, margin_top + chart_height)], fill=axis_color, width=2)
        # Eixo X
        draw.line([(margin_left, margin_top + chart_height), (margin_left + chart_width, margin_top + chart_height)], fill=axis_color, width=2)
        
        # Grid e labels do eixo Y
        num_ticks = 5
        for i in range(num_ticks + 1):
            y_pos = margin_top + chart_height - (i * chart_height // num_ticks)
            val = min_val + (val_range * i / num_ticks)
            label = f"{val:.1f}"
            label_bbox = draw.textbbox((0, 0), label, font=font_axis)
            label_width = label_bbox[2] - label_bbox[0]
            draw.text((margin_left - label_width - 5, y_pos - 5), label, fill='black', font=font_axis)
            if i > 0 and i < num_ticks:
                draw.line([(margin_left, y_pos), (margin_left + chart_width, y_pos)], fill=(200, 200, 200), width=1)
        
        # Desenha linha do gráfico
        points = []
        for i, val in enumerate(values):
            x = margin_left + (i * chart_width / (len(values) - 1)) if len(values) > 1 else margin_left + chart_width // 2
            y = margin_top + chart_height - ((val - min_val) / val_range * chart_height)
            points.append((x, y))
        
        # Desenha linha
        if len(points) > 1:
            for i in range(len(points) - 1):
                draw.line([points[i], points[i+1]], fill='#2196F3', width=3)
        
        # Desenha pontos
        for point in points:
            draw.ellipse([point[0] - 4, point[1] - 4, point[0] + 4, point[1] + 4], fill='#2196F3', outline='white', width=1)
        
        # Labels do eixo X (datas)
        if dates:
            num_x_labels = min(len(dates), 10)  # Máximo 10 labels
            step = max(1, len(dates) // num_x_labels)
            for i in range(0, len(dates), step):
                x = margin_left + (i * chart_width / (len(values) - 1)) if len(values) > 1 else margin_left + chart_width // 2
                date_str = str(dates[i])[:10] if len(str(dates[i])) > 10 else str(dates[i])
                date_str = date_str.replace('-', '/')
                label_bbox = draw.textbbox((0, 0), date_str, font=font_axis)
                label_width = label_bbox[2] - label_bbox[0]
                draw.text((x - label_width // 2, margin_top + chart_height + 5), date_str, fill='black', font=font_axis)
        
        return _encode_image_to_base64(img)
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
        img_width = int(width * 100)
        img_height = int(height * 100)
        
        margin_top = 60
        margin_bottom = 50
        margin_left = 70
        margin_right = 30
        
        chart_width = img_width - margin_left - margin_right
        chart_height = img_height - margin_top - margin_bottom
        
        img = Image.new('RGB', (img_width, img_height), color='white')
        draw = ImageDraw.Draw(img)
        
        # Processa dados
        if isinstance(data, dict):
            labels = data.get('labels', [])
            values = data.get('values', [])
        elif isinstance(data, list):
            labels = [str(item.get('label', '')) for item in data]
            values = [float(item.get('value', 0)) for item in data]
        else:
            logger.error("Formato de dados inválido para gráfico de barras")
            return None
        
        if not labels or not values or len(labels) != len(values):
            logger.error("Dados insuficientes para gráfico de barras")
            return None
        
        # Trunca labels
        labels = [label[:15] + '...' if len(label) > 15 else label for label in labels]
        
        try:
            font_title = ImageFont.truetype("arial.ttf", 16)
            font_label = ImageFont.truetype("arial.ttf", 11)
            font_axis = ImageFont.truetype("arial.ttf", 9)
        except:
            font_title = ImageFont.load_default()
            font_label = ImageFont.load_default()
            font_axis = ImageFont.load_default()
        
        # Título
        title_bbox = draw.textbbox((0, 0), title, font=font_title)
        title_width = title_bbox[2] - title_bbox[0]
        draw.text(((img_width - title_width) // 2, 15), title, fill='black', font=font_title)
        
        # Labels dos eixos - posicionamento correto baseado na orientação
        if horizontal:
            # Para barras horizontais:
            # x_label vai no eixo horizontal (embaixo)
            # y_label vai no eixo vertical (esquerda, mas não desenhamos aqui para evitar conflito)
            if x_label:
                x_label_bbox = draw.textbbox((0, 0), x_label, font=font_label)
                x_label_width = x_label_bbox[2] - x_label_bbox[0]
                draw.text(((img_width - x_label_width) // 2, img_height - 35), x_label, fill='black', font=font_label)
            # y_label não desenhamos aqui para gráficos horizontais (os labels dos produtos já são desenhados)
        else:
            # Para barras verticais:
            # x_label vai no eixo horizontal (embaixo)
            # y_label vai no eixo vertical (esquerda)
            if x_label:
                x_label_bbox = draw.textbbox((0, 0), x_label, font=font_label)
                x_label_width = x_label_bbox[2] - x_label_bbox[0]
                draw.text(((img_width - x_label_width) // 2, img_height - 35), x_label, fill='black', font=font_label)
            
            if y_label:
                y_label_bbox = draw.textbbox((0, 0), y_label, font=font_label)
                # Posiciona verticalmente no centro, mas com margem adequada
                y_label_y = (img_height - y_label_bbox[3]) // 2
                # Rotaciona 90 graus (simulado com posicionamento)
                draw.text((15, y_label_y), y_label, fill='black', font=font_label)
        
        # Calcula ranges
        max_val = max(values) if values else 1
        min_val = min(0, min(values)) if values else 0
        val_range = max_val - min_val if max_val != min_val else 1
        
        bar_color = _hex_to_rgb(color)
        axis_color = (100, 100, 100)
        
        if horizontal:
            # Barras horizontais
            # Aumenta margem esquerda para dar espaço aos labels dos produtos
            margin_left_labels = 100  # Mais espaço para labels longos
            chart_width_adj = img_width - margin_left_labels - margin_right
            
            bar_height = chart_height / len(labels) * 0.7
            bar_spacing = chart_height / len(labels)
            
            # Eixo Y (vertical, à esquerda)
            draw.line([(margin_left_labels, margin_top), (margin_left_labels, margin_top + chart_height)], fill=axis_color, width=2)
            # Eixo X (horizontal, embaixo)
            draw.line([(margin_left_labels, margin_top + chart_height), (margin_left_labels + chart_width_adj, margin_top + chart_height)], fill=axis_color, width=2)
            
            # Grid e labels do eixo X (valores numéricos)
            num_ticks = 5
            for i in range(num_ticks + 1):
                x_pos = margin_left_labels + (i * chart_width_adj / num_ticks)
                val = min_val + (val_range * i / num_ticks)
                label = f"{val:.1f}"
                label_bbox = draw.textbbox((0, 0), label, font=font_axis)
                label_width = label_bbox[2] - label_bbox[0]
                draw.text((x_pos - label_width // 2, margin_top + chart_height + 5), label, fill='black', font=font_axis)
                if i > 0:
                    draw.line([(x_pos, margin_top), (x_pos, margin_top + chart_height)], fill=(200, 200, 200), width=1)
            
            # Desenha barras
            for i, (label, value) in enumerate(zip(labels, values)):
                y = margin_top + (i * bar_spacing) + (bar_spacing - bar_height) / 2
                bar_width = (value - min_val) / val_range * chart_width_adj
                
                # Barra
                draw.rectangle([margin_left_labels, y, margin_left_labels + bar_width, y + bar_height], fill=bar_color, outline='white', width=1)
                
                # Label do produto (à esquerda da barra)
                label_bbox = draw.textbbox((0, 0), label, font=font_axis)
                label_height = label_bbox[3] - label_bbox[1]
                # Trunca label se muito longo
                max_label_width = margin_left_labels - 10
                if label_bbox[2] - label_bbox[0] > max_label_width:
                    # Calcula quantos caracteres cabem
                    char_width = (label_bbox[2] - label_bbox[0]) / len(label)
                    max_chars = int(max_label_width / char_width) - 3
                    label = label[:max_chars] + '...' if max_chars > 0 else label[:3]
                    label_bbox = draw.textbbox((0, 0), label, font=font_axis)
                draw.text((margin_left_labels - 5, y + (bar_height - label_height) // 2), label, fill='black', font=font_axis, anchor='rm')
        else:
            # Barras verticais
            # Aumenta margem inferior para evitar sobreposição de labels
            margin_bottom_labels = 80  # Mais espaço para labels rotacionados
            chart_height_adj = img_height - margin_top - margin_bottom_labels
            
            bar_width = chart_width / len(labels) * 0.6  # Reduz largura para dar mais espaço
            bar_spacing = chart_width / len(labels)
            
            # Eixo Y
            draw.line([(margin_left, margin_top), (margin_left, margin_top + chart_height_adj)], fill=axis_color, width=2)
            # Eixo X
            draw.line([(margin_left, margin_top + chart_height_adj), (margin_left + chart_width, margin_top + chart_height_adj)], fill=axis_color, width=2)
            
            # Grid e labels do eixo Y
            num_ticks = 5
            for i in range(num_ticks + 1):
                y_pos = margin_top + chart_height_adj - (i * chart_height_adj // num_ticks)
                val = min_val + (val_range * i / num_ticks)
                label = f"{val:.1f}"
                label_bbox = draw.textbbox((0, 0), label, font=font_axis)
                label_width = label_bbox[2] - label_bbox[0]
                draw.text((margin_left - label_width - 5, y_pos - 5), label, fill='black', font=font_axis)
                if i > 0 and i < num_ticks:
                    draw.line([(margin_left, y_pos), (margin_left + chart_width, y_pos)], fill=(200, 200, 200), width=1)
            
            # Desenha barras
            # Lista para rastrear posições dos labels e evitar sobreposição
            label_positions = []
            
            for i, (label, value) in enumerate(zip(labels, values)):
                x = margin_left + (i * bar_spacing) + (bar_spacing - bar_width) / 2
                bar_height = (value - min_val) / val_range * chart_height_adj
                
                # Barra
                draw.rectangle([x, margin_top + chart_height_adj - bar_height, x + bar_width, margin_top + chart_height_adj], 
                             fill=bar_color, outline='white', width=1)
                
                # Label - calcula tamanho máximo baseado no espaçamento disponível
                max_label_width = int(bar_spacing * 0.9)  # 90% do espaçamento
                label_bbox = draw.textbbox((0, 0), label, font=font_axis)
                label_width_original = label_bbox[2] - label_bbox[0]
                
                # Trunca label se necessário
                if label_width_original > max_label_width:
                    # Calcula quantos caracteres cabem
                    char_width = label_width_original / len(label)
                    max_chars = int(max_label_width / char_width) - 3  # -3 para "..."
                    short_label = label[:max_chars] + '...' if max_chars > 0 else label[:3]
                else:
                    short_label = label
                
                # Recalcula largura do label truncado
                label_bbox = draw.textbbox((0, 0), short_label, font=font_axis)
                label_width = label_bbox[2] - label_bbox[0]
                
                # Calcula posição do label (centralizado na barra)
                label_x = x + bar_width // 2
                label_y = margin_top + chart_height_adj + 8
                
                # Verifica sobreposição com labels anteriores
                overlap = False
                for prev_x, prev_width in label_positions:
                    # Verifica se há sobreposição horizontal
                    if abs(label_x - prev_x) < (label_width // 2 + prev_width // 2 + 3):
                        overlap = True
                        break
                
                # Se houver sobreposição, move o label ou trunca mais
                if overlap and i > 0:
                    # Tenta mover para a direita
                    new_x = label_x + (label_width // 2) + 5
                    if new_x + label_width // 2 < margin_left + chart_width:
                        label_x = new_x
                else:
                        # Se não couber, trunca mais agressivamente
                        short_label = label[:4] + '...' if len(label) > 4 else label
                        label_bbox = draw.textbbox((0, 0), short_label, font=font_axis)
                        label_width = label_bbox[2] - label_bbox[0]
                
                # Desenha label
                draw.text((label_x - label_width // 2, label_y), short_label, fill='black', font=font_axis)
                
                # Registra posição do label para próximas verificações
                label_positions.append((label_x, label_width))
        
        return _encode_image_to_base64(img)
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
        # Garante que seja quadrado para gráfico circular (não oval)
        size = min(width, height)  # Usa o menor valor
        img_width = int(size * 100)
        img_height = int(size * 100)
        
        img = Image.new('RGB', (img_width, img_height), color='white')
        draw = ImageDraw.Draw(img)
        
        # Processa dados
        if isinstance(data, dict):
            labels = data.get('labels', [])
            values = data.get('values', [])
        elif isinstance(data, list):
            labels = [str(item.get('label', '')) for item in data]
            values = [float(item.get('value', 0)) for item in data]
        else:
            logger.error("Formato de dados inválido para gráfico de pizza")
            return None
        
        if not labels or not values or len(labels) != len(values):
            logger.error("Dados insuficientes para gráfico de pizza")
            return None
        
        # Remove valores zero ou negativos
        filtered_data = [(l, v) for l, v in zip(labels, values) if v > 0]
        if not filtered_data:
            logger.error("Nenhum valor positivo para gráfico de pizza")
            return None
        
        labels, values = zip(*filtered_data)
        labels = list(labels)
        values = list(values)
        
        # Cores padrão
        if not colors:
            colors = DEFAULT_COLORS
        
        # Calcula totais e percentuais
        total = sum(values)
        percentages = [v / total * 100 for v in values]
        
        try:
            font_title = ImageFont.truetype("arial.ttf", 16)
            font_label = ImageFont.truetype("arial.ttf", 10)
            font_percent = ImageFont.truetype("arial.ttf", 9)
        except:
            font_title = ImageFont.load_default()
            font_label = ImageFont.load_default()
            font_percent = ImageFont.load_default()
        
        # Título
        title_bbox = draw.textbbox((0, 0), title, font=font_title)
        title_width = title_bbox[2] - title_bbox[0]
        draw.text(((img_width - title_width) // 2, 15), title, fill='black', font=font_title)
        
        # Área do gráfico
        center_x = img_width // 2
        center_y = img_height // 2 + 20
        radius = min(img_width, img_height) // 3
        
        # Desenha pizza
        start_angle = -90  # Começa no topo
        current_angle = start_angle
        
        for i, (label, value, percent, color) in enumerate(zip(labels, values, percentages, colors[:len(labels)])):
            # Calcula ângulo da fatia
            angle = 360 * (value / total)
            
            # Desenha fatia
            rgb_color = _hex_to_rgb(color)
            
            # Usa elipse para desenhar fatia (simplificado)
            end_angle = current_angle + angle
            
            # Desenha arco e preenche
            bbox = [center_x - radius, center_y - radius, center_x + radius, center_y + radius]
            
            # Desenha fatia usando polígono aproximado
            points = [(center_x, center_y)]
            num_points = max(3, int(angle / 5))  # Pontos para suavizar
            for j in range(num_points + 1):
                angle_rad = math.radians(current_angle + (j * angle / num_points))
                x = center_x + radius * math.cos(angle_rad)
                y = center_y + radius * math.sin(angle_rad)
                points.append((x, y))
            
            draw.polygon(points, fill=rgb_color, outline='white', width=2)
            
            # Label e percentual (fora do gráfico)
            mid_angle = current_angle + angle / 2
            mid_angle_rad = math.radians(mid_angle)
            label_x = center_x + (radius + 30) * math.cos(mid_angle_rad)
            label_y = center_y + (radius + 30) * math.sin(mid_angle_rad)
            
            label_text = f"{label}: {percent:.1f}%"
            label_bbox = draw.textbbox((0, 0), label_text, font=font_label)
            label_width = label_bbox[2] - label_bbox[0]
            label_height = label_bbox[3] - label_bbox[1]
            
            # Desenha retângulo de fundo para legenda
            padding = 3
            draw.rectangle([label_x - label_width // 2 - padding, label_y - label_height // 2 - padding,
                           label_x + label_width // 2 + padding, label_y + label_height // 2 + padding],
                          fill='white', outline=rgb_color, width=1)
            draw.text((label_x - label_width // 2, label_y - label_height // 2), label_text, fill='black', font=font_label)
            
            current_angle = end_angle
        
        return _encode_image_to_base64(img)
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
        if not data_series:
            logger.error("Nenhuma série de dados fornecida")
            return None
        
        # Usa a primeira série como base para o gráfico de linha
        # Para múltiplas linhas, combina os dados
        all_dates = []
        for series in data_series:
            dates = series.get('dates', [])
            all_dates.extend(dates)
        
        # Remove duplicatas e ordena
        unique_dates = sorted(list(set(all_dates)))
        
        # Cria estrutura combinada
        combined_data = {
            'dates': unique_dates,
            'values': []
        }
        
        # Para simplificar, usa apenas a primeira série
        # Em uma implementação completa, desenharia múltiplas linhas
        first_series = data_series[0]
        combined_data['values'] = first_series.get('values', [])
        
        # Gera gráfico de linha simples
        return generate_line_chart(combined_data, title, x_label, y_label, width, height)
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
        categories = data.get('categories', [])
        series = data.get('series', [])
        
        if not categories or not series:
            logger.error("Dados insuficientes para gráfico de barras empilhadas")
            return None
        
        # Para simplificar, soma as séries e cria gráfico de barras simples
        total_values = []
        for i in range(len(categories)):
            total = sum(s[i] if i < len(s) else 0 for s in series)
            total_values.append(total)
        
        # Cria gráfico de barras simples com totais
        bar_data = {
            'labels': [cat[:15] + '...' if len(cat) > 15 else cat for cat in categories],
            'values': total_values
        }
        
        return generate_bar_chart(bar_data, title, x_label, y_label, width, height, horizontal=False)
    except Exception as e:
        logger.error(f"Erro ao gerar gráfico de barras empilhadas: {e}", exc_info=True)
        return None
