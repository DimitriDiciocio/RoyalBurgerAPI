import re  # importa biblioteca de expressões regulares
from validate_docbr import CPF  # importa validador de CPF

def is_valid_cpf(cpf_string: str) -> bool:  # função para validar CPF
    if not cpf_string or not isinstance(cpf_string, str):  # valida entrada
        return False  # retorna falso se inválido
    cpf_validator = CPF()  # cria instância do validador
    return cpf_validator.validate(cpf_string)  # valida CPF e retorna resultado

def is_strong_password(password: str) -> (bool, str):  # função para validar força da senha
    if not password:  # verifica se senha não está vazia
        return (False, "A senha não pode estar em branco.")  # retorna erro
    if len(password) < 8:  # verifica tamanho mínimo
        return (False, "A senha deve ter no mínimo 8 caracteres.")  # retorna erro
    if not re.search(r"[a-z]", password):  # verifica letra minúscula
        return (False, "A senha deve conter pelo menos uma letra minúscula.")  # retorna erro
    if not re.search(r"[A-Z]", password):  # verifica letra maiúscula
        return (False, "A senha deve conter pelo menos uma letra maiúscula.")  # retorna erro
    if not re.search(r"[0-9]", password):  # verifica número
        return (False, "A senha deve conter pelo menos um número.")  # retorna erro
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?~`]", password):  # verifica caractere especial
        return (False, "A senha deve conter pelo menos um caractere especial (!@#$%^&*()_+-=[]{}|;':\",./<>?~`).")  # retorna erro
    return (True, "Senha válida.")  # retorna sucesso

def is_valid_email(email: str) -> (bool, str):  # função para validar email
    if not email or not isinstance(email, str):  # valida entrada
        return (False, "O e-mail não pode estar em branco.")  # retorna erro
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'  # regex para email
    if not re.match(email_pattern, email):  # verifica formato
        return (False, "Formato de e-mail inválido.")  # retorna erro
    if len(email) > 254:  # verifica tamanho máximo
        return (False, "E-mail muito longo (máximo 254 caracteres).")  # retorna erro
    return (True, "E-mail válido.")  # retorna sucesso

def is_valid_phone(phone: str) -> (bool, str):  # função para validar telefone brasileiro
    if not phone or not isinstance(phone, str):  # valida entrada
        return (False, "O telefone não pode estar em branco.")  # retorna erro
    phone_digits = re.sub(r'\D', '', phone)  # remove caracteres não numéricos
    if len(phone_digits) == 10:  # telefone fixo
        if not phone_digits.startswith(('11', '12', '13', '14', '15', '16', '17', '18', '19', '21', '22', '23', '24', '27', '28', '31', '32', '33', '34', '35', '37', '38', '41', '42', '43', '44', '45', '46', '47', '48', '49', '51', '53', '54', '55', '61', '62', '63', '64', '65', '66', '67', '68', '69', '71', '73', '74', '75', '77', '79', '81', '82', '83', '84', '85', '86', '87', '88', '89', '91', '92', '93', '94', '95', '96', '97', '98', '99')):  # verifica DDD válido
            return (False, "DDD inválido.")  # retorna erro
    elif len(phone_digits) == 11:  # celular
        if not phone_digits.startswith(('11', '12', '13', '14', '15', '16', '17', '18', '19', '21', '22', '23', '24', '27', '28', '31', '32', '33', '34', '35', '37', '38', '41', '42', '43', '44', '45', '46', '47', '48', '49', '51', '53', '54', '55', '61', '62', '63', '64', '65', '66', '67', '68', '69', '71', '73', '74', '75', '77', '79', '81', '82', '83', '84', '85', '86', '87', '88', '89', '91', '92', '93', '94', '95', '96', '97', '98', '99')):  # verifica DDD válido
            return (False, "DDD inválido.")  # retorna erro
        if not phone_digits[2] == '9':  # verifica se celular começa com 9
            return (False, "Número de celular deve começar com 9.")  # retorna erro
    else:  # tamanho inválido
        return (False, "Telefone deve ter 10 ou 11 dígitos (com DDD).")  # retorna erro
    return (True, "Telefone válido.")  # retorna sucesso