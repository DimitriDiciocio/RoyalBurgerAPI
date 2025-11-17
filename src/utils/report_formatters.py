"""
Utilitários para formatação de dados em relatórios
Funções auxiliares para formatar valores monetários, datas, percentuais, etc.
"""

from datetime import datetime, date
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


def format_currency(value, show_symbol=True):
    """
    Formata valor como moeda brasileira (R$ X.XXX,XX)
    
    Args:
        value: Valor numérico (int, float, Decimal)
        show_symbol: Se True, inclui símbolo R$
    
    Returns:
        str: Valor formatado como moeda brasileira
    """
    try:
        # Converte para float se necessário
        if isinstance(value, Decimal):
            value = float(value)
        elif not isinstance(value, (int, float)):
            value = float(value) if value else 0.0
        
        # Formata com 2 casas decimais
        formatted = f"{value:,.2f}"
        # Substitui separadores: 1.234,56 -> 1.234,56 (já está correto)
        # Mas precisa trocar . por , e vice-versa
        parts = formatted.split('.')
        if len(parts) == 2:
            integer_part = parts[0].replace(',', 'X').replace('.', ',').replace('X', '.')
            decimal_part = parts[1]
            formatted = f"{integer_part},{decimal_part}"
        else:
            formatted = formatted.replace(',', '.')
        
        if show_symbol:
            return f"R$ {formatted}"
        return formatted
    except (ValueError, TypeError) as e:
        logger.warning(f"Erro ao formatar moeda: {value}, erro: {e}")
        return "R$ 0,00" if show_symbol else "0,00"


def format_percentage(value, decimals=2, show_symbol=True):
    """
    Formata valor como percentual
    
    Args:
        value: Valor numérico (0.155 = 15,5%)
        decimals: Número de casas decimais
        show_symbol: Se True, inclui símbolo %
    
    Returns:
        str: Valor formatado como percentual
    """
    try:
        if isinstance(value, Decimal):
            value = float(value)
        elif not isinstance(value, (int, float)):
            value = float(value) if value else 0.0
        
        # Multiplica por 100 para exibir como percentual
        percentage = value * 100
        formatted = f"{percentage:,.{decimals}f}"
        
        # Ajusta separadores para formato brasileiro
        if '.' in formatted:
            parts = formatted.split('.')
            integer_part = parts[0].replace(',', 'X').replace('.', ',').replace('X', '.')
            decimal_part = parts[1] if len(parts) > 1 else '0'
            formatted = f"{integer_part},{decimal_part}"
        else:
            formatted = formatted.replace(',', '.')
        
        if show_symbol:
            return f"{formatted}%"
        return formatted
    except (ValueError, TypeError) as e:
        logger.warning(f"Erro ao formatar percentual: {value}, erro: {e}")
        return "0,00%" if show_symbol else "0,00"


def format_date(date_value, format_str='%d/%m/%Y'):
    """
    Formata data para exibição
    
    Args:
        date_value: datetime, date ou string ISO
        format_str: Formato de saída (padrão: DD/MM/YYYY)
    
    Returns:
        str: Data formatada
    """
    try:
        if isinstance(date_value, str):
            # Tenta parsear string ISO
            try:
                date_value = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
            except:
                try:
                    date_value = datetime.strptime(date_value, '%Y-%m-%d')
                except:
                    return date_value  # Retorna original se não conseguir parsear
        
        if isinstance(date_value, (datetime, date)):
            return date_value.strftime(format_str)
        
        return str(date_value)
    except Exception as e:
        logger.warning(f"Erro ao formatar data: {date_value}, erro: {e}")
        return str(date_value)


def format_datetime(datetime_value, format_str='%d/%m/%Y %H:%M'):
    """
    Formata data e hora para exibição
    
    Args:
        datetime_value: datetime ou string ISO
        format_str: Formato de saída (padrão: DD/MM/YYYY HH:MM)
    
    Returns:
        str: Data e hora formatadas
    """
    try:
        if isinstance(datetime_value, str):
            # Tenta parsear string ISO
            try:
                datetime_value = datetime.fromisoformat(datetime_value.replace('Z', '+00:00'))
            except:
                try:
                    datetime_value = datetime.strptime(datetime_value, '%Y-%m-%d %H:%M:%S')
                except:
                    return datetime_value  # Retorna original se não conseguir parsear
        
        if isinstance(datetime_value, datetime):
            return datetime_value.strftime(format_str)
        
        return str(datetime_value)
    except Exception as e:
        logger.warning(f"Erro ao formatar data/hora: {datetime_value}, erro: {e}")
        return str(datetime_value)


def truncate_text(text, max_length=50, suffix='...'):
    """
    Trunca texto se exceder tamanho máximo
    
    Args:
        text: Texto a truncar
        max_length: Tamanho máximo
        suffix: Sufixo a adicionar se truncar
    
    Returns:
        str: Texto truncado
    """
    if not text:
        return ''
    
    text_str = str(text)
    if len(text_str) <= max_length:
        return text_str
    
    return text_str[:max_length - len(suffix)] + suffix


def calculate_growth_percentage(current, previous):
    """
    Calcula percentual de crescimento entre dois valores
    
    Args:
        current: Valor atual
        previous: Valor anterior
    
    Returns:
        float: Percentual de crescimento (pode ser negativo)
    """
    try:
        # Converte para float se necessário
        if isinstance(current, Decimal):
            current = float(current)
        if isinstance(previous, Decimal):
            previous = float(previous)
        
        if not isinstance(current, (int, float)):
            current = float(current) if current else 0.0
        if not isinstance(previous, (int, float)):
            previous = float(previous) if previous else 0.0
        
        # Se valor anterior é zero
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        
        # Calcula crescimento percentual
        growth = ((current - previous) / previous) * 100
        return round(growth, 2)
    except (ValueError, TypeError, ZeroDivisionError) as e:
        logger.warning(f"Erro ao calcular crescimento: current={current}, previous={previous}, erro: {e}")
        return 0.0


def format_number(value, decimals=0, thousand_separator=True):
    """
    Formata número com separadores de milhar
    
    Args:
        value: Valor numérico
        decimals: Número de casas decimais
        thousand_separator: Se True, usa separador de milhar
    
    Returns:
        str: Número formatado
    """
    try:
        if isinstance(value, Decimal):
            value = float(value)
        elif not isinstance(value, (int, float)):
            value = float(value) if value else 0.0
        
        if thousand_separator:
            formatted = f"{value:,.{decimals}f}"
            # Ajusta para formato brasileiro
            if '.' in formatted:
                parts = formatted.split('.')
                integer_part = parts[0].replace(',', 'X').replace('.', ',').replace('X', '.')
                decimal_part = parts[1] if len(parts) > 1 else '0'
                formatted = f"{integer_part},{decimal_part}"
            else:
                formatted = formatted.replace(',', '.')
        else:
            formatted = f"{value:.{decimals}f}"
            formatted = formatted.replace('.', ',')
        
        return formatted
    except (ValueError, TypeError) as e:
        logger.warning(f"Erro ao formatar número: {value}, erro: {e}")
        return "0" if decimals == 0 else "0,00"


def format_duration_minutes(minutes):
    """
    Formata duração em minutos para formato legível
    
    Args:
        minutes: Duração em minutos (int ou float)
    
    Returns:
        str: Duração formatada (ex: "1h 30min" ou "45min")
    """
    try:
        minutes = int(float(minutes))
        
        if minutes < 60:
            return f"{minutes}min"
        
        hours = minutes // 60
        remaining_minutes = minutes % 60
        
        if remaining_minutes == 0:
            return f"{hours}h"
        else:
            return f"{hours}h {remaining_minutes}min"
    except (ValueError, TypeError) as e:
        logger.warning(f"Erro ao formatar duração: {minutes}, erro: {e}")
        return "0min"


def safe_divide(numerator, denominator, default=0.0):
    """
    Divisão segura que evita ZeroDivisionError
    
    Args:
        numerator: Numerador
        denominator: Denominador
        default: Valor padrão se divisão por zero
    
    Returns:
        float: Resultado da divisão ou valor padrão
    """
    try:
        if isinstance(numerator, Decimal):
            numerator = float(numerator)
        if isinstance(denominator, Decimal):
            denominator = float(denominator)
        
        if not isinstance(numerator, (int, float)):
            numerator = float(numerator) if numerator else 0.0
        if not isinstance(denominator, (int, float)):
            denominator = float(denominator) if denominator else 0.0
        
        if denominator == 0:
            return default
        
        return numerator / denominator
    except (ValueError, TypeError) as e:
        logger.warning(f"Erro na divisão segura: {numerator}/{denominator}, erro: {e}")
        return default

