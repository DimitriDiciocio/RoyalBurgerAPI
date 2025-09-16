# Em api/src/utils/validators.py

import re
from validate_docbr import CPF


def is_valid_cpf(cpf_string: str) -> bool:
    # ... (função existente) ...
    if not cpf_string or not isinstance(cpf_string, str):
        return False
    cpf_validator = CPF()
    return cpf_validator.validate(cpf_string)


def is_strong_password(password: str) -> (bool, str):
    """
    Verifica a força de uma senha.
    Regras: Mínimo 8 caracteres, 1 minúscula, 1 maiúscula, 1 número, 1 caractere especial.
    Retorna uma tupla (True/False, "mensagem").
    """
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

    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?~`]", password):
        return (False, "A senha deve conter pelo menos um caractere especial (!@#$%^&*()_+-=[]{}|;':\",./<>?~`).")

    return (True, "Senha válida.")