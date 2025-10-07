import fdb
import random
import string
import hashlib
from datetime import datetime, timedelta
from ..database import get_db_connection
from . import email_service

def generate_verification_code():
    return ''.join(random.choices(string.digits, k=6))

def generate_user_data_hash(user_data):
    """
    Gera um hash único baseado nos dados do usuário para associar o código de verificação
    aos dados específicos do cadastro.
    """
    # Cria uma string com os dados relevantes do usuário
    data_string = f"{user_data.get('email', '').lower().strip()}|{user_data.get('full_name', '')}|{user_data.get('phone', '')}|{user_data.get('cpf', '')}|{user_data.get('date_of_birth', '')}"
    
    # Gera hash SHA-256
    return hashlib.sha256(data_string.encode('utf-8')).hexdigest()

def create_email_verification(email):
    # Normaliza o email para minúsculas
    email = email.lower().strip()
    
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
        
        # Remove TODOS os códigos antigos para este email (garante que apenas o mais recente seja válido)
        sql_delete_old = "DELETE FROM EMAIL_VERIFICATIONS WHERE EMAIL = ?"
        cur.execute(sql_delete_old, (email,))
        
        # Insere novo código (sem hash de dados do usuário)
        sql_insert = """
            INSERT INTO EMAIL_VERIFICATIONS (EMAIL, VERIFICATION_CODE, EXPIRES_AT, CREATED_AT) 
            VALUES (?, ?, ?, ?)
        """
        created_at = datetime.now()
        cur.execute(sql_insert, (email, verification_code, expires_at, created_at))
        conn.commit()
        
        # Envia por E-MAIL (novo padrão)
        try:
            email_service.send_email(
                to=email,
                subject="Royal Burger - Verificação de e-mail",
                template="email_verification",
                user={"full_name": user['full_name']},
                verification_code=verification_code,
            )
            return (True, None, "Código de verificação enviado por e-mail")
        except Exception as e:
            # Mesmo se o email falhar, o código foi salvo no banco
            print(f"Erro ao enviar email de verificação: {e}")
            return (True, "EMAIL_WARNING", f"Código criado, mas erro ao enviar e-mail: {e}")
        
    except fdb.Error as e:
        print(f"Erro ao criar verificação de email: {e}")
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()

def verify_email_code(email, code):
    conn = None
    try:
        # Normaliza o email para minúsculas
        email = email.lower().strip()
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca o código de verificação mais recente para este email
        sql_get_verification = """
            SELECT VERIFICATION_CODE, EXPIRES_AT, CREATED_AT
            FROM EMAIL_VERIFICATIONS 
            WHERE EMAIL = ? AND CREATED_AT = (
                SELECT MAX(CREATED_AT) FROM EMAIL_VERIFICATIONS WHERE EMAIL = ?
            )
        """
        cur.execute(sql_get_verification, (email, email))
        result = cur.fetchone()
        
        if not result:
            return (False, "NO_VERIFICATION_FOUND", "Nenhum código de verificação encontrado para este email")
        
        stored_code, expires_at, created_at = result
        
        if datetime.now() > expires_at:
            return (False, "CODE_EXPIRED", "Código de verificação expirado")
        
        if stored_code != code:
            return (False, "INVALID_CODE", "Código de verificação inválido")
        
        # Atualiza apenas o usuário mais recente (não verificado) para este email
        sql_update_user = """
            UPDATE USERS 
            SET IS_EMAIL_VERIFIED = TRUE 
            WHERE EMAIL = ? AND IS_EMAIL_VERIFIED = FALSE
            AND ID = (
                SELECT ID FROM USERS 
                WHERE EMAIL = ? AND IS_EMAIL_VERIFIED = FALSE
                ORDER BY ID DESC 
                ROWS 1
            )
        """
        cur.execute(sql_update_user, (email, email))
        
        if cur.rowcount == 0:
            return (False, "NO_UNVERIFIED_USER", "Nenhum usuário não verificado encontrado para este email")
        
        # Remove todos os códigos de verificação para este email
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
        # Normaliza o email para minúsculas
        email = email.lower().strip()
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca o usuário mais recente (não verificado) para este email
        sql = """
            SELECT ID, FULL_NAME, EMAIL, IS_EMAIL_VERIFIED 
            FROM USERS 
            WHERE EMAIL = ? AND IS_ACTIVE = TRUE 
            ORDER BY ID DESC 
            ROWS 1
        """
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
