import fdb
import random
import string
from datetime import datetime, timedelta
from ..database import get_db_connection
from . import sms_service

def generate_2fa_code():
    """Gera código de 6 dígitos para 2FA"""
    return ''.join(random.choices(string.digits, k=6))

def create_2fa_verification(user_id, email):
    """Cria código de verificação 2FA e envia por SMS"""
    verification_code = generate_2fa_code()
    expires_at = datetime.now() + timedelta(minutes=10)  # 10 minutos para 2FA
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Remove códigos antigos do usuário
        sql_delete_old = "DELETE FROM TWO_FACTOR_VERIFICATIONS WHERE USER_ID = ?"
        cur.execute(sql_delete_old, (user_id,))
        
        # Insere novo código
        sql_insert = """
            INSERT INTO TWO_FACTOR_VERIFICATIONS (USER_ID, VERIFICATION_CODE, EXPIRES_AT, CREATED_AT) 
            VALUES (?, ?, ?, ?)
        """
        created_at = datetime.now()
        cur.execute(sql_insert, (user_id, verification_code, expires_at, created_at))
        conn.commit()
        
        # Busca dados do usuário para o SMS
        sql_user = "SELECT FULL_NAME, PHONE FROM USERS WHERE ID = ?"
        cur.execute(sql_user, (user_id,))
        user_data = cur.fetchone()
        
        if user_data:
            full_name, phone = user_data
            if phone:
                # Valida e formata o telefone
                is_valid, formatted_phone = sms_service.validate_phone_number(phone)
                if is_valid:
                    success, error_code, message = sms_service.send_2fa_sms(formatted_phone, verification_code, full_name)
                    if success:
                        return (True, None, "Código de verificação enviado por SMS")
                    else:
                        return (False, "SMS_ERROR", "Erro ao enviar SMS")
                else:
                    return (False, "INVALID_PHONE", "Número de telefone inválido")
            else:
                return (False, "NO_PHONE", "Usuário não possui telefone cadastrado")
        
        return (False, "USER_NOT_FOUND", "Usuário não encontrado")
        
    except fdb.Error as e:
        print(f"Erro ao criar verificação 2FA: {e}")
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()

def verify_2fa_code(user_id, code):
    """Verifica código 2FA do usuário"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql_get_verification = """
            SELECT VERIFICATION_CODE, EXPIRES_AT, USED 
            FROM TWO_FACTOR_VERIFICATIONS 
            WHERE USER_ID = ? AND CREATED_AT = (
                SELECT MAX(CREATED_AT) FROM TWO_FACTOR_VERIFICATIONS WHERE USER_ID = ?
            )
        """
        cur.execute(sql_get_verification, (user_id, user_id))
        result = cur.fetchone()
        
        if not result:
            return (False, "NO_VERIFICATION_FOUND", "Nenhum código de verificação encontrado")
        
        stored_code, expires_at, used = result
        
        if used:
            return (False, "CODE_ALREADY_USED", "Código já foi utilizado")
        
        if datetime.now() > expires_at:
            return (False, "CODE_EXPIRED", "Código de verificação expirado")
        
        if stored_code != code:
            return (False, "INVALID_CODE", "Código de verificação inválido")
        
        # Marca código como usado
        sql_mark_used = "UPDATE TWO_FACTOR_VERIFICATIONS SET USED = TRUE WHERE USER_ID = ? AND VERIFICATION_CODE = ?"
        cur.execute(sql_mark_used, (user_id, code))
        
        # Remove códigos antigos
        sql_cleanup = "DELETE FROM TWO_FACTOR_VERIFICATIONS WHERE USER_ID = ? AND USED = TRUE"
        cur.execute(sql_cleanup, (user_id,))
        
        conn.commit()
        
        return (True, None, "Código verificado com sucesso")
        
    except fdb.Error as e:
        print(f"Erro ao verificar código 2FA: {e}")
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()

def toggle_2fa(user_id, enable):
    """Ativa ou desativa 2FA para o usuário"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql_update = "UPDATE USERS SET TWO_FACTOR_ENABLED = ? WHERE ID = ?"
        cur.execute(sql_update, (enable, user_id))
        conn.commit()
        
        return (True, None, "2FA atualizado com sucesso")
        
    except fdb.Error as e:
        print(f"Erro ao atualizar 2FA: {e}")
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()

def is_2fa_enabled(user_id):
    """Verifica se 2FA está habilitado para o usuário"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = "SELECT TWO_FACTOR_ENABLED FROM USERS WHERE ID = ?"
        cur.execute(sql, (user_id,))
        result = cur.fetchone()
        
        return bool(result[0]) if result else False
        
    except fdb.Error as e:
        print(f"Erro ao verificar 2FA: {e}")
        return False
    finally:
        if conn: conn.close()
