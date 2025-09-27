import re  
from validate_docbr import CPF  

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
