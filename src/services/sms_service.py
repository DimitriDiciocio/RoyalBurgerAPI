import requests
import os
from datetime import datetime

def send_sms(phone_number, message):
    """
    Envia SMS usando API externa (exemplo com Twilio)
    Para produção, configure as variáveis de ambiente necessárias
    """
    try:
        # Exemplo usando Twilio (você pode usar outro provedor)
        # Para este exemplo, vamos simular o envio
        
        # Em produção, use algo como:
        # account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        # auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        # client = Client(account_sid, auth_token)
        # 
        # message = client.messages.create(
        #     body=message,
        #     from_=os.getenv('TWILIO_PHONE_NUMBER'),
        #     to=phone_number
        # )
        
        # Para desenvolvimento, vamos simular o envio
        print(f"SMS enviado para {phone_number}: {message}")
        
        return (True, None, "SMS enviado com sucesso")
        
    except Exception as e:
        print(f"Erro ao enviar SMS: {e}")
        return (False, "SMS_ERROR", "Erro ao enviar SMS")

def send_2fa_sms(phone_number, code, user_name):
    """Envia código 2FA por SMS"""
    message = f"Royal Burger - Código de verificação: {code}. Válido por 10 minutos. Não compartilhe este código."
    return send_sms(phone_number, message)

def send_email_verification_sms(phone_number, code, user_name):
    """Envia código de verificação de email por SMS"""
    message = f"Royal Burger - Código de verificação de email: {code}. Válido por 15 minutos. Não compartilhe este código."
    return send_sms(phone_number, message)

def send_password_reset_sms(phone_number, code, user_name):
    """Envia código de recuperação de senha por SMS"""
    message = f"Royal Burger - Código de recuperação de senha: {code}. Válido por 60 minutos. Não compartilhe este código."
    return send_sms(phone_number, code)

def validate_phone_number(phone):
    """
    Valida e formata número de telefone brasileiro
    Retorna (is_valid, formatted_phone)
    """
    if not phone:
        return (False, None)
    
    # Remove caracteres não numéricos
    clean_phone = ''.join(filter(str.isdigit, phone))
    
    # Verifica se tem 10 ou 11 dígitos (com DDD)
    if len(clean_phone) == 10:
        # Formato: DDD + 8 dígitos (fixo)
        formatted = f"+55{clean_phone}"
        return (True, formatted)
    elif len(clean_phone) == 11:
        # Formato: DDD + 9 dígitos (celular)
        formatted = f"+55{clean_phone}"
        return (True, formatted)
    else:
        return (False, clean_phone)
