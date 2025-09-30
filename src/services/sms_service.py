import requests
import os

SMS_API_URL = "https://api.smsempresa.com.br/v1/send"

def _only_digits(number_str):
    return ''.join(ch for ch in str(number_str) if ch.isdigit())

def send_sms(phone_number, message):
    """
    Envia SMS usando o provedor smsempresa.
    Requer variável de ambiente SMS_EMPRESA_KEY.
    """
    try:
        api_key = os.getenv('SMS_EMPRESA_KEY')
        if not api_key:
            return (False, "CONFIG_ERROR", "Chave SMS_EMPRESA_KEY ausente nas variáveis de ambiente")

        sms_type = int(os.getenv('SMS_EMPRESA_TYPE', 9))
        number_digits = _only_digits(phone_number)
        if not number_digits:
            return (False, "INVALID_PHONE", "Número de telefone inválido")

        payload = [
            {
                "key": api_key,
                "type": sms_type,
                "number": int(number_digits),
                "msg": message,
            }
        ]

        resp = requests.post(SMS_API_URL, json=payload, timeout=10)
        if 200 <= resp.status_code < 300:
            return (True, None, "SMS enviado com sucesso")
        else:
            try:
                err_body = resp.json()
            except Exception:
                err_body = resp.text
            return (False, "SMS_PROVIDER_ERROR", f"Falha no provedor ({resp.status_code}): {err_body}")

    except Exception as e:
        return (False, "SMS_ERROR", f"Erro ao enviar SMS: {e}")

def send_2fa_sms(phone_number, code, user_name):
    """Envia código 2FA por SMS"""
    message = f"Royal Burger - Código 2FA: {code}. Válido por 10 minutos. Não compartilhe."
    return send_sms(phone_number, message)

def send_email_verification_sms(phone_number, code, user_name):
    """Envia código de verificação de email por SMS"""
    message = f"Royal Burger - Verificação de e-mail: {code}. Válido por 15 minutos. Não compartilhe."
    return send_sms(phone_number, message)

def send_password_reset_sms(phone_number, code, user_name):
    """Envia código de recuperação de senha por SMS"""
    message = f"Royal Burger - Recuperação de senha: {code}. Válido por 60 minutos. Não compartilhe."
    return send_sms(phone_number, message)

def validate_phone_number(phone):
    """
    Valida e formata número de telefone brasileiro
    Retorna (is_valid, formatted_phone)
    """
    if not phone:
        return (False, None)
    
    clean_phone = _only_digits(phone)
    
    # Verifica se tem 10 ou 11 dígitos (com DDD)
    if len(clean_phone) == 10:
        return (True, clean_phone)
    elif len(clean_phone) == 11:
        return (True, clean_phone)
    else:
        return (False, clean_phone)
