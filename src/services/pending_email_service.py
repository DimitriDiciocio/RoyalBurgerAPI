import fdb
import random
import string
from datetime import datetime, timedelta
from ..database import get_db_connection
from . import email_service

def generate_verification_code():
    """Gera código de verificação de 6 dígitos"""
    return ''.join(random.choices(string.digits, k=6))

def create_pending_email_change(user_id, new_email):
    """
    Cria uma solicitação de mudança de email pendente de verificação.
    Retorna (sucesso, error_code, mensagem)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se o usuário existe e está ativo
        sql_check_user = "SELECT ID, FULL_NAME, EMAIL FROM USERS WHERE ID = ? AND IS_ACTIVE = TRUE"
        cur.execute(sql_check_user, (user_id,))
        user_data = cur.fetchone()
        
        if not user_data:
            return (False, "USER_NOT_FOUND", "Usuário não encontrado")
        
        user_id_db, full_name, current_email = user_data
        
        # Verifica se o novo email é diferente do atual
        if new_email.lower() == current_email.lower():
            return (False, "SAME_EMAIL", "O novo email deve ser diferente do email atual")
        
        # Verifica se o novo email já está em uso por uma conta verificada
        sql_check_email = "SELECT ID FROM USERS WHERE EMAIL = ? AND ID <> ? AND IS_EMAIL_VERIFIED = TRUE"
        cur.execute(sql_check_email, (new_email, user_id))
        if cur.fetchone():
            return (False, "EMAIL_ALREADY_EXISTS", "Este email já está em uso por outra conta verificada")
        
        # Verifica se já existe uma solicitação pendente para este usuário
        sql_check_pending = "SELECT ID FROM PENDING_EMAIL_CHANGES WHERE USER_ID = ? AND STATUS = 'pending'"
        cur.execute(sql_check_pending, (user_id,))
        if cur.fetchone():
            return (False, "PENDING_CHANGE_EXISTS", "Já existe uma solicitação de mudança de email pendente")
        
        # Gera código de verificação
        verification_code = generate_verification_code()
        expires_at = datetime.now() + timedelta(minutes=15)  # 15 minutos para verificar
        
        # Insere a solicitação pendente
        sql_insert = """
            INSERT INTO PENDING_EMAIL_CHANGES 
            (USER_ID, NEW_EMAIL, VERIFICATION_CODE, EXPIRES_AT, CREATED_AT, STATUS) 
            VALUES (?, ?, ?, ?, ?, 'pending')
        """
        created_at = datetime.now()
        cur.execute(sql_insert, (user_id, new_email, verification_code, expires_at, created_at))
        conn.commit()
        
        # Envia email de verificação para o novo email
        try:
            email_service.send_email(
                to=new_email,
                subject="Royal Burger - Confirmação de mudança de email",
                template="email_change_verification",
                user={"full_name": full_name, "current_email": current_email},
                verification_code=verification_code,
                new_email=new_email
            )
            return (True, None, f"Código de verificação enviado para {new_email}")
        except Exception as e:
            # Se falhou ao enviar email, remove a solicitação
            conn.rollback()
            return (False, "EMAIL_ERROR", f"Erro ao enviar email: {e}")
        
    except fdb.Error as e:
        print(f"Erro ao criar mudança de email pendente: {e}")
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()

def verify_pending_email_change(user_id, code):
    """
    Verifica o código e efetua a mudança de email.
    Retorna (sucesso, error_code, mensagem)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca a solicitação pendente
        sql_get_pending = """
            SELECT ID, NEW_EMAIL, VERIFICATION_CODE, EXPIRES_AT 
            FROM PENDING_EMAIL_CHANGES 
            WHERE USER_ID = ? AND STATUS = 'pending'
            ORDER BY CREATED_AT DESC
        """
        cur.execute(sql_get_pending, (user_id,))
        pending_data = cur.fetchone()
        
        if not pending_data:
            return (False, "NO_PENDING_CHANGE", "Nenhuma solicitação de mudança de email pendente")
        
        pending_id, new_email, stored_code, expires_at = pending_data
        
        # Verifica se o código expirou
        if datetime.now() > expires_at:
            # Marca como expirado
            sql_expire = "UPDATE PENDING_EMAIL_CHANGES SET STATUS = 'expired' WHERE ID = ?"
            cur.execute(sql_expire, (pending_id,))
            conn.commit()
            return (False, "CODE_EXPIRED", "Código de verificação expirado")
        
        # Verifica o código
        if stored_code != code:
            return (False, "INVALID_CODE", "Código de verificação inválido")
        
        # Verifica novamente se o email não está em uso por uma conta verificada (pode ter mudado desde a criação)
        sql_check_email = "SELECT ID FROM USERS WHERE EMAIL = ? AND ID <> ? AND IS_EMAIL_VERIFIED = TRUE"
        cur.execute(sql_check_email, (new_email, user_id))
        if cur.fetchone():
            # Marca como inválido
            sql_invalid = "UPDATE PENDING_EMAIL_CHANGES SET STATUS = 'invalid' WHERE ID = ?"
            cur.execute(sql_invalid, (pending_id,))
            conn.commit()
            return (False, "EMAIL_ALREADY_EXISTS", "Este email já está em uso por outra conta verificada")
        
        # Efetua a mudança de email
        sql_update_user = "UPDATE USERS SET EMAIL = ?, IS_EMAIL_VERIFIED = TRUE WHERE ID = ?"
        cur.execute(sql_update_user, (new_email, user_id))
        
        # Marca a solicitação como concluída
        sql_complete = "UPDATE PENDING_EMAIL_CHANGES SET STATUS = 'completed', COMPLETED_AT = ? WHERE ID = ?"
        cur.execute(sql_complete, (datetime.now(), pending_id))
        
        conn.commit()
        
        return (True, None, "Email alterado com sucesso")
        
    except fdb.Error as e:
        print(f"Erro ao verificar mudança de email: {e}")
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()

def cancel_pending_email_change(user_id):
    """
    Cancela uma solicitação de mudança de email pendente.
    Retorna (sucesso, error_code, mensagem)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql_cancel = "UPDATE PENDING_EMAIL_CHANGES SET STATUS = 'cancelled', COMPLETED_AT = ? WHERE USER_ID = ? AND STATUS = 'pending'"
        cur.execute(sql_cancel, (datetime.now(), user_id))
        
        if cur.rowcount == 0:
            return (False, "NO_PENDING_CHANGE", "Nenhuma solicitação de mudança de email pendente")
        
        conn.commit()
        return (True, None, "Solicitação de mudança de email cancelada")
        
    except fdb.Error as e:
        print(f"Erro ao cancelar mudança de email: {e}")
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()

def get_pending_email_change(user_id):
    """
    Retorna informações sobre uma mudança de email pendente.
    Retorna (dados, error_code, mensagem)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql_get = """
            SELECT NEW_EMAIL, CREATED_AT, EXPIRES_AT 
            FROM PENDING_EMAIL_CHANGES 
            WHERE USER_ID = ? AND STATUS = 'pending'
            ORDER BY CREATED_AT DESC
        """
        cur.execute(sql_get, (user_id,))
        result = cur.fetchone()
        
        if not result:
            return (None, "NO_PENDING_CHANGE", "Nenhuma solicitação de mudança de email pendente")
        
        new_email, created_at, expires_at = result
        
        return ({
            "new_email": new_email,
            "created_at": created_at,
            "expires_at": expires_at,
            "is_expired": datetime.now() > expires_at
        }, None, None)
        
    except fdb.Error as e:
        print(f"Erro ao buscar mudança de email pendente: {e}")
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()

def cleanup_expired_pending_changes():
    """
    Limpa solicitações de mudança de email expiradas.
    Função para ser executada periodicamente.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql_cleanup = "UPDATE PENDING_EMAIL_CHANGES SET STATUS = 'expired' WHERE STATUS = 'pending' AND EXPIRES_AT < ?"
        cur.execute(sql_cleanup, (datetime.now(),))
        
        conn.commit()
        return cur.rowcount
        
    except fdb.Error as e:
        print(f"Erro ao limpar mudanças expiradas: {e}")
        if conn: conn.rollback()
        return 0
    finally:
        if conn: conn.close()
