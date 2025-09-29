import fdb
import random
import string
from datetime import datetime, timedelta
from ..database import get_db_connection
from . import sms_service

def generate_verification_code():
    return ''.join(random.choices(string.digits, k=6))

def create_email_verification(email):
    user = get_user_by_email_for_verification(email)
    if not user:
        return (False, "USER_NOT_FOUND", "Usuário não encontrado")
    
    if user.get('is_email_verified', False):
        return (False, "EMAIL_ALREADY_VERIFIED", "Este email já foi verificado")
    
    verification_code = generate_verification_code()
    expires_at = datetime.now() + timedelta(minutes=15)
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql_delete_old = "DELETE FROM EMAIL_VERIFICATIONS WHERE EMAIL = ?"
        cur.execute(sql_delete_old, (email,))
        
        sql_insert = """
            INSERT INTO EMAIL_VERIFICATIONS (EMAIL, VERIFICATION_CODE, EXPIRES_AT, CREATED_AT) 
            VALUES (?, ?, ?, ?)
        """
        created_at = datetime.now()
        cur.execute(sql_insert, (email, verification_code, expires_at, created_at))
        conn.commit()
        
        # Busca telefone do usuário para enviar SMS
        sql_phone = "SELECT PHONE FROM USERS WHERE EMAIL = ?"
        cur.execute(sql_phone, (email,))
        phone_result = cur.fetchone()
        
        if phone_result and phone_result[0]:
            phone = phone_result[0]
            # Valida e formata o telefone
            is_valid, formatted_phone = sms_service.validate_phone_number(phone)
            if is_valid:
                success, error_code, message = sms_service.send_email_verification_sms(formatted_phone, verification_code, user['full_name'])
                if success:
                    return (True, None, "Código de verificação enviado por SMS")
                else:
                    return (False, "SMS_ERROR", "Erro ao enviar SMS")
            else:
                return (False, "INVALID_PHONE", "Número de telefone inválido")
        else:
            return (False, "NO_PHONE", "Usuário não possui telefone cadastrado")
        
    except fdb.Error as e:
        print(f"Erro ao criar verificação de email: {e}")
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()

def verify_email_code(email, code):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql_get_verification = """
            SELECT VERIFICATION_CODE, EXPIRES_AT 
            FROM EMAIL_VERIFICATIONS 
            WHERE EMAIL = ? AND CREATED_AT = (
                SELECT MAX(CREATED_AT) FROM EMAIL_VERIFICATIONS WHERE EMAIL = ?
            )
        """
        cur.execute(sql_get_verification, (email, email))
        result = cur.fetchone()
        
        if not result:
            return (False, "NO_VERIFICATION_FOUND", "Nenhum código de verificação encontrado para este email")
        
        stored_code, expires_at = result
        
        if datetime.now() > expires_at:
            return (False, "CODE_EXPIRED", "Código de verificação expirado")
        
        if stored_code != code:
            return (False, "INVALID_CODE", "Código de verificação inválido")
        
        sql_update_user = "UPDATE USERS SET IS_EMAIL_VERIFIED = TRUE WHERE EMAIL = ?"
        cur.execute(sql_update_user, (email,))
        
        sql_cleanup = "DELETE FROM EMAIL_VERIFICATIONS WHERE EMAIL = ?"
        cur.execute(sql_cleanup, (email,))
        
        conn.commit()
        
        return (True, None, "Email verificado com sucesso")
        
    except fdb.Error as e:
        print(f"Erro ao verificar código: {e}")
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()

def get_user_by_email_for_verification(email):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = "SELECT ID, FULL_NAME, EMAIL, IS_EMAIL_VERIFIED FROM USERS WHERE EMAIL = ? AND IS_ACTIVE = TRUE"
        cur.execute(sql, (email,))
        row = cur.fetchone()
        if row:
            return {
                "id": row[0], 
                "full_name": row[1], 
                "email": row[2], 
                "is_email_verified": bool(row[3]) if row[3] is not None else False
            }
        return None
    except fdb.Error as e:
        print(f"Erro ao buscar usuário para verificação: {e}")
        return None
    finally:
        if conn: conn.close()

def resend_verification_code(email):
    return create_email_verification(email)
