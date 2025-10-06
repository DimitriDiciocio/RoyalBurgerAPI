import re  
from validate_docbr import CPF
from datetime import datetime, date
from dateutil.relativedelta import relativedelta  

def is_valid_cpf(cpf_string: str) -> bool:  
    if not cpf_string or not isinstance(cpf_string, str):  
        return False  
    cpf_validator = CPF()  
    return cpf_validator.validate(cpf_string)  

def is_strong_password(password: str) -> (bool, str):  
    if not password:  
        return (False, "A senha não pode estar em branco.")  
    if len(password) < 8:  
        return (False, "A senha deve ter no mínimo 8 caracteres.")  
    if not re.search(r"[a-z]", password):  
        return (False, "A senha deve conter pelo menos uma letra minúscula.")  
    if not re.search(r"[A-Z]", password):  
        return (False, "A senha deve conter pelo menos uma letra maiúscula.")  
    if not re.search(r"[0-9]", password):  
        return (False, "A senha deve conter pelo menos um número.")  
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return (False, "A senha deve conter pelo menos um caractere especial (!@#$%^&*(),.?\":{}|<>)")
    return (True, "Senha válida.")  

def is_valid_email(email: str) -> (bool, str):  
    if not email or not isinstance(email, str):  
        return (False, "O e-mail não pode estar em branco.")  
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'  
    if not re.match(email_pattern, email):  
        return (False, "Formato de e-mail inválido.")  
    if len(email) > 254:  
        return (False, "E-mail muito longo (máximo 254 caracteres).")  
    return (True, "E-mail válido.")  

def is_valid_phone(phone: str) -> (bool, str):  
    if not phone or not isinstance(phone, str):  
        return (False, "O telefone não pode estar em branco.")  
    phone_digits = re.sub(r'\D', '', phone)  
    if len(phone_digits) == 10:  
        if not phone_digits.startswith(('11', '12', '13', '14', '15', '16', '17', '18', '19', '21', '22', '23', '24', '27', '28', '31', '32', '33', '34', '35', '37', '38', '41', '42', '43', '44', '45', '46', '47', '48', '49', '51', '53', '54', '55', '61', '62', '63', '64', '65', '66', '67', '68', '69', '71', '73', '74', '75', '77', '79', '81', '82', '83', '84', '85', '86', '87', '88', '89', '91', '92', '93', '94', '95', '96', '97', '98', '99')):  
            return (False, "DDD inválido.")  
    elif len(phone_digits) == 11:  
        if not phone_digits.startswith(('11', '12', '13', '14', '15', '16', '17', '18', '19', '21', '22', '23', '24', '27', '28', '31', '32', '33', '34', '35', '37', '38', '41', '42', '43', '44', '45', '46', '47', '48', '49', '51', '53', '54', '55', '61', '62', '63', '64', '65', '66', '67', '68', '69', '71', '73', '74', '75', '77', '79', '81', '82', '83', '84', '85', '86', '87', '88', '89', '91', '92', '93', '94', '95', '96', '97', '98', '99')):  
            return (False, "DDD inválido.")  
        if not phone_digits[2] == '9':  
            return (False, "Número de celular deve começar com 9.")  
    else:  
        return (False, "Telefone deve ter 10 ou 11 dígitos (com DDD).")  
    return (True, "Telefone válido.")


def is_valid_date_format(date_string: str) -> (bool, str):
    """
    Valida se a string de data está em formato válido (DD-MM-AAAA)
    """
    if not date_string or not isinstance(date_string, str):
        return (False, "Data não pode estar em branco.")
    
    try:
        # Tenta fazer o parse da data no formato brasileiro
        parsed_date = datetime.strptime(date_string, '%d-%m-%Y').date()
        return (True, "Formato de data válido.")
    except ValueError:
        return (False, "Formato de data inválido. Use DD-MM-AAAA.")


def is_valid_date(date_string: str) -> (bool, str):
    """
    Valida se a data é válida (ex: não permite 30 de fevereiro)
    """
    if not date_string or not isinstance(date_string, str):
        return (False, "Data não pode estar em branco.")
    
    try:
        # Tenta fazer o parse da data no formato brasileiro
        parsed_date = datetime.strptime(date_string, '%d-%m-%Y').date()
        
        # Verifica se a data parseada é igual à string original
        # Isso garante que não há datas inválidas como 30/02
        if parsed_date.strftime('%d-%m-%Y') != date_string:
            return (False, "Data inválida (ex: 30 de fevereiro não existe).")
        
        return (True, "Data válida.")
    except ValueError:
        return (False, "Data inválida (ex: 30 de fevereiro não existe).")


def is_date_not_future(date_string: str) -> (bool, str):
    """
    Valida se a data não é posterior ao dia atual
    """
    if not date_string or not isinstance(date_string, str):
        return (False, "Data não pode estar em branco.")
    
    try:
        parsed_date = datetime.strptime(date_string, '%d-%m-%Y').date()
        today = date.today()
        
        if parsed_date > today:
            return (False, "Data não pode ser posterior ao dia atual.")
        
        return (True, "Data válida.")
    except ValueError:
        return (False, "Data inválida.")


def is_date_not_past(date_string: str) -> (bool, str):
    """
    Valida se a data não é anterior ao dia atual
    """
    if not date_string or not isinstance(date_string, str):
        return (False, "Data não pode estar em branco.")
    
    try:
        parsed_date = datetime.strptime(date_string, '%d-%m-%Y').date()
        today = date.today()
        
        if parsed_date < today:
            return (False, "Data não pode ser anterior ao dia atual.")
        
        return (True, "Data válida.")
    except ValueError:
        return (False, "Data inválida.")


def is_age_valid(date_string: str, min_age: int = 18, max_age: int = None) -> (bool, str):
    """
    Valida se a idade está dentro dos limites especificados
    """
    if not date_string or not isinstance(date_string, str):
        return (False, "Data não pode estar em branco.")
    
    try:
        birth_date = datetime.strptime(date_string, '%d-%m-%Y').date()
        today = date.today()
        
        # Calcula a idade usando relativedelta para maior precisão
        age = relativedelta(today, birth_date).years
        
        if age < min_age:
            return (False, f"Idade mínima permitida: {min_age} anos.")
        
        if max_age is not None and age > max_age:
            return (False, f"Idade máxima permitida: {max_age} anos.")
        
        return (True, "Idade válida.")
    except ValueError:
        return (False, "Data inválida.")


def is_date_in_range(date_string: str, min_date: str = None, max_date: str = None) -> (bool, str):
    """
    Valida se a data está dentro de um intervalo específico
    """
    if not date_string or not isinstance(date_string, str):
        return (False, "Data não pode estar em branco.")
    
    try:
        parsed_date = datetime.strptime(date_string, '%d-%m-%Y').date()
        
        if min_date:
            min_parsed = datetime.strptime(min_date, '%d-%m-%Y').date()
            if parsed_date < min_parsed:
                return (False, f"Data deve ser posterior ou igual a {min_date}.")
        
        if max_date:
            max_parsed = datetime.strptime(max_date, '%d-%m-%Y').date()
            if parsed_date > max_parsed:
                return (False, f"Data deve ser anterior ou igual a {max_date}.")
        
        return (True, "Data dentro do intervalo válido.")
    except ValueError:
        return (False, "Data inválida.")


def validate_birth_date(date_string: str) -> (bool, str):
    """
    Validação específica para data de nascimento:
    - Formato válido (DD-MM-AAAA)
    - Data válida (não permite datas inexistentes)
    - Não pode ser futura
    - Idade mínima de 18 anos
    """
    if not date_string:
        return (True, "Data de nascimento é opcional.")
    
    # Valida formato
    is_valid_format, format_msg = is_valid_date_format(date_string)
    if not is_valid_format:
        return (False, format_msg)
    
    # Valida se a data existe
    is_valid_date_check, date_msg = is_valid_date(date_string)
    if not is_valid_date_check:
        return (False, date_msg)
    
    # Valida se não é futura
    is_not_future, future_msg = is_date_not_future(date_string)
    if not is_not_future:
        return (False, future_msg)
    
    # Valida idade mínima
    is_age_ok, age_msg = is_age_valid(date_string, min_age=18)
    if not is_age_ok:
        return (False, age_msg)
    
    return (True, "Data de nascimento válida.")


def convert_br_date_to_iso(date_string: str) -> str:
    """
    Converte data do formato brasileiro (DD-MM-AAAA) para ISO (AAAA-MM-DD)
    """
    if not date_string:
        return None
    
    try:
        parsed_date = datetime.strptime(date_string, '%d-%m-%Y').date()
        return parsed_date.strftime('%Y-%m-%d')
    except ValueError:
        return None


def convert_iso_date_to_br(date_string: str) -> str:
    """
    Converte data do formato ISO (AAAA-MM-DD) para brasileiro (DD-MM-AAAA)
    """
    if not date_string:
        return None
    
    try:
        parsed_date = datetime.strptime(date_string, '%Y-%m-%d').date()
        return parsed_date.strftime('%d-%m-%Y')
    except ValueError:
        return None  
