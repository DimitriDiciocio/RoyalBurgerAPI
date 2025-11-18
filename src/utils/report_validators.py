"""
Utilitários para validação de filtros e parâmetros de relatórios
Valida datas, IDs, strings, e outros parâmetros de entrada
"""

from datetime import datetime, date, timedelta
import logging
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Limites padrão
MAX_PERIOD_DAYS = 365  # Máximo de 1 ano
MIN_PERIOD_DAYS = 1    # Mínimo de 1 dia
MAX_STRING_LENGTH = 255
MAX_ID_VALUE = 2147483647  # INT_MAX do Firebird


def validate_date_range(start_date: Optional[str], end_date: Optional[str], 
                       max_days: int = MAX_PERIOD_DAYS) -> Tuple[bool, Optional[str], Optional[datetime], Optional[datetime]]:
    """
    Valida range de datas
    
    Args:
        start_date: Data inicial (string ISO ou YYYY-MM-DD)
        end_date: Data final (string ISO ou YYYY-MM-DD)
        max_days: Número máximo de dias permitido no range
    
    Returns:
        tuple: (is_valid, error_message, start_datetime, end_datetime)
    """
    start_dt = None
    end_dt = None
    
    # Parse de start_date
    if start_date:
        try:
            if 'T' in start_date:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            else:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        except (ValueError, TypeError) as e:
            return (False, f"Data inicial inválida: {start_date}. Formato esperado: YYYY-MM-DD", None, None)
    else:
        # Se não fornecida, usa 30 dias atrás como padrão
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=30)
    
    # Parse de end_date
    if end_date:
        try:
            if 'T' in end_date:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            else:
                end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        except (ValueError, TypeError) as e:
            return (False, f"Data final inválida: {end_date}. Formato esperado: YYYY-MM-DD", None, None)
    else:
        # Se não fornecida, usa hoje como padrão
        end_dt = datetime.now()
        if not start_date:
            start_dt = end_dt - timedelta(days=30)
    
    # Valida que start_date <= end_date
    if start_dt > end_dt:
        return (False, "Data inicial deve ser anterior ou igual à data final", None, None)
    
    # Valida range máximo
    days_diff = (end_dt - start_dt).days
    if days_diff > max_days:
        return (False, f"Período muito longo. Máximo permitido: {max_days} dias", None, None)
    
    if days_diff < MIN_PERIOD_DAYS:
        return (False, f"Período muito curto. Mínimo permitido: {MIN_PERIOD_DAYS} dia(s)", None, None)
    
    return (True, None, start_dt, end_dt)


def validate_id(id_value: Any, field_name: str = "ID") -> Tuple[bool, Optional[str], Optional[int]]:
    """
    Valida ID (deve ser inteiro positivo)
    
    Args:
        id_value: Valor do ID
        field_name: Nome do campo (para mensagem de erro)
    
    Returns:
        tuple: (is_valid, error_message, id_int)
    """
    if id_value is None:
        return (True, None, None)
    
    try:
        id_int = int(id_value)
        if id_int <= 0:
            return (False, f"{field_name} deve ser um número positivo", None)
        if id_int > MAX_ID_VALUE:
            return (False, f"{field_name} excede o valor máximo permitido", None)
        return (True, None, id_int)
    except (ValueError, TypeError):
        return (False, f"{field_name} deve ser um número inteiro válido", None)


def validate_string(value: Any, field_name: str, max_length: int = MAX_STRING_LENGTH, 
                   required: bool = False, allow_empty: bool = True) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Valida string
    
    Args:
        value: Valor a validar
        field_name: Nome do campo
        max_length: Tamanho máximo
        required: Se True, campo é obrigatório
        allow_empty: Se False, não permite string vazia
    
    Returns:
        tuple: (is_valid, error_message, sanitized_value)
    """
    if value is None:
        if required:
            return (False, f"{field_name} é obrigatório", None)
        return (True, None, None)
    
    if not isinstance(value, str):
        value = str(value)
    
    # Remove espaços em branco no início e fim
    sanitized = value.strip()
    
    if not allow_empty and len(sanitized) == 0:
        return (False, f"{field_name} não pode estar vazio", None)
    
    if len(sanitized) > max_length:
        return (False, f"{field_name} excede o tamanho máximo de {max_length} caracteres", None)
    
    return (True, None, sanitized)


def validate_enum(value: Any, field_name: str, allowed_values: list, 
                  required: bool = False) -> Tuple[bool, Optional[str], Optional[Any]]:
    """
    Valida valor enum (deve estar na lista de valores permitidos)
    
    Args:
        value: Valor a validar
        field_name: Nome do campo
        allowed_values: Lista de valores permitidos
        required: Se True, campo é obrigatório
    
    Returns:
        tuple: (is_valid, error_message, validated_value)
    """
    if value is None:
        if required:
            return (False, f"{field_name} é obrigatório", None)
        return (True, None, None)
    
    # CORREÇÃO: Aceitar booleanos quando os valores permitidos são ['true', 'false']
    if isinstance(value, bool) and set(allowed_values) == {'true', 'false'}:
        # Converter booleano para string correspondente
        value_str = 'true' if value else 'false'
        return (True, None, value_str)
    
    if value not in allowed_values:
        return (False, f"{field_name} deve ser um dos seguintes valores: {', '.join(map(str, allowed_values))}", None)
    
    return (True, None, value)


def validate_filters(filters: Dict[str, Any], allowed_filters: Dict[str, dict]) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """
    Valida dicionário de filtros completo
    
    Args:
        filters: Dicionário de filtros a validar
        allowed_filters: Dicionário com definição dos filtros permitidos
                        Ex: {
                            "start_date": {"type": "date", "required": False},
                            "end_date": {"type": "date", "required": False},
                            "status": {"type": "enum", "values": ["pending", "confirmed"], "required": False},
                            "user_id": {"type": "id", "required": False}
                        }
    
    Returns:
        tuple: (is_valid, error_message, validated_filters)
    """
    if not isinstance(filters, dict):
        return (False, "Filtros devem ser um dicionário", None)
    
    validated = {}
    
    # Valida cada filtro permitido
    for filter_name, filter_config in allowed_filters.items():
        filter_type = filter_config.get('type')
        required = filter_config.get('required', False)
        value = filters.get(filter_name)
        
        if filter_type == 'date':
            # Validação de data será feita junto com end_date no validate_date_range
            if value:
                validated[filter_name] = value
        elif filter_type == 'id':
            is_valid, error, id_int = validate_id(value, filter_name)
            if not is_valid:
                return (False, error, None)
            if id_int:
                validated[filter_name] = id_int
        elif filter_type == 'string':
            max_length = filter_config.get('max_length', MAX_STRING_LENGTH)
            allow_empty = filter_config.get('allow_empty', True)
            is_valid, error, sanitized = validate_string(value, filter_name, max_length, required, allow_empty)
            if not is_valid:
                return (False, error, None)
            if sanitized:
                validated[filter_name] = sanitized
        elif filter_type == 'enum':
            allowed_values = filter_config.get('values', [])
            is_valid, error, validated_value = validate_enum(value, filter_name, allowed_values, required)
            if not is_valid:
                return (False, error, None)
            if validated_value:
                validated[filter_name] = validated_value
        elif filter_type == 'number':
            try:
                if value is not None:
                    num_value = float(value)
                    min_value = filter_config.get('min')
                    max_value = filter_config.get('max')
                    if min_value is not None and num_value < min_value:
                        return (False, f"{filter_name} deve ser maior ou igual a {min_value}", None)
                    if max_value is not None and num_value > max_value:
                        return (False, f"{filter_name} deve ser menor ou igual a {max_value}", None)
                    validated[filter_name] = num_value
            except (ValueError, TypeError):
                return (False, f"{filter_name} deve ser um número válido", None)
    
    # Valida range de datas se ambas estiverem presentes
    if 'start_date' in validated or 'end_date' in validated:
        start_date = validated.get('start_date')
        end_date = validated.get('end_date')
        max_days = allowed_filters.get('start_date', {}).get('max_days', MAX_PERIOD_DAYS)
        
        is_valid, error, start_dt, end_dt = validate_date_range(start_date, end_date, max_days)
        if not is_valid:
            return (False, error, None)
    
    return (True, None, validated)


def sanitize_search_string(search_string: str, max_length: int = 100) -> str:
    """
    Sanitiza string de busca (remove caracteres perigosos)
    
    Args:
        search_string: String a sanitizar
        max_length: Tamanho máximo
    
    Returns:
        str: String sanitizada
    """
    if not search_string:
        return ""
    
    # Remove caracteres especiais perigosos (mantém apenas alfanuméricos, espaços e alguns especiais)
    import re
    sanitized = re.sub(r'[^\w\s\-\.]', '', search_string)
    
    # Limita tamanho
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    
    return sanitized.strip()

