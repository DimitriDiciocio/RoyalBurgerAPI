import bcrypt  
import fdb  
from functools import wraps  
from flask import jsonify  
from ..database import get_db_connection  
from flask_jwt_extended import create_access_token, jwt_required, get_jwt
from .two_factor_service import create_2fa_verification, verify_2fa_code, is_2fa_enabled  

def authenticate(email, password):  
    conn = None  
    try:  
        # Normaliza o email para minúsculas
        email = email.lower().strip()
        
        conn = get_db_connection()  
        cur = conn.cursor()  
        sql_check_user = (
            "SELECT ID, PASSWORD_HASH, ROLE, FULL_NAME, IS_ACTIVE, TWO_FACTOR_ENABLED, IS_EMAIL_VERIFIED "
            "FROM USERS WHERE EMAIL = ?;"
        )  
        cur.execute(sql_check_user, (email,))  
        user_record = cur.fetchone()  
        if not user_record:  
            return (None, "USER_NOT_FOUND", "Usuário não encontrado")  
        user_id, hashed_password, role, full_name, is_active, two_factor_enabled, is_email_verified = user_record  
        if not is_active:  
            return (None, "ACCOUNT_INACTIVE", "Sua conta está inativa. Entre em contato com o suporte para reativá-la.")  
        if not bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8')):  
            return (None, "INVALID_PASSWORD", "Senha incorreta")  
        # Bloqueia login se e-mail não verificado
        if not is_email_verified:
            return (None, "EMAIL_NOT_VERIFIED", "E-mail não verificado. Verifique seu e-mail para continuar.")
        
        # Se 2FA está habilitado, retorna status especial
        if two_factor_enabled:
            success, error_code, message = create_2fa_verification(user_id, email)
            if not success:
                return (None, error_code, message)
            
            return ({"requires_2fa": True, "user_id": user_id}, None, message)
        
        # Login normal sem 2FA
        identity = str(user_id)  
        additional_claims = {"roles": [role], "full_name": full_name}  
        access_token = create_access_token(identity=identity, additional_claims=additional_claims)  
        return (access_token, None, None)  
    except fdb.Error as e:  
        print(f"Erro de banco de dados na autenticação: {e}")  
        return (None, "DATABASE_ERROR", "Erro interno do servidor")  
    finally:  
        if conn: conn.close()  

def require_role(*roles):  
    def decorator(f):  
        @wraps(f)  
        @jwt_required()  
        def decorated_function(*args, **kwargs):  
            claims = get_jwt()  
            user_roles = claims.get("roles", [])  
            if any(role in user_roles for role in roles):  
                return f(*args, **kwargs)  
            else:  
                return jsonify({"msg": "Acesso não autorizado para esta função."}), 403  
        return decorated_function  
    return decorator  

def add_token_to_blacklist(jti, expires_at):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        sql = "INSERT INTO TOKEN_BLACKLIST (JTI, EXPIRES_AT) VALUES (?, ?);"  
        cur.execute(sql, (jti, expires_at))  
        conn.commit()  
    except fdb.Error as e:  
        print(f"Erro ao adicionar token à blacklist: {e}")  
        if conn: conn.rollback()  
    finally:  
        if conn: conn.close()  

def verify_2fa_and_login(user_id, code):
    """Verifica código 2FA e retorna token de acesso"""
    success, error_code, message = verify_2fa_code(user_id, code)
    
    if not success:
        return (None, error_code, message)
    
    # Busca dados do usuário para criar token
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = "SELECT ROLE, FULL_NAME FROM USERS WHERE ID = ?"
        cur.execute(sql, (user_id,))
        user_data = cur.fetchone()
        
        if not user_data:
            return (None, "USER_NOT_FOUND", "Usuário não encontrado")
        
        role, full_name = user_data
        identity = str(user_id)
        additional_claims = {"roles": [role], "full_name": full_name}
        access_token = create_access_token(identity=identity, additional_claims=additional_claims)
        
        return (access_token, None, None)
        
    except fdb.Error as e:
        print(f"Erro ao criar token após 2FA: {e}")
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()

def is_token_revoked(jwt_payload):  
    jti = jwt_payload['jti']  
    user_sub = jwt_payload.get('sub')  
    token_iat = jwt_payload.get('iat')  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        # 1) Blacklist por JTI
        sql = "SELECT 1 FROM TOKEN_BLACKLIST WHERE JTI = ?;"  
        cur.execute(sql, (jti,))  
        if cur.fetchone() is not None:
            return True
        # 2) Revogação global por usuário (se existir tabela USER_TOKEN_BLACKLIST)
        try:
            cur.execute("SELECT REVOKED_AFTER FROM USER_TOKEN_BLACKLIST WHERE USER_ID = ?;", (int(user_sub),))
            row = cur.fetchone()
            if row and row[0] is not None and token_iat is not None:
                # token_iat é epoch seconds; compara com REVOKED_AFTER
                from datetime import datetime, timezone
                revoked_after = row[0]
                token_time = datetime.fromtimestamp(int(token_iat), tz=timezone.utc)
                # Se token é anterior ao momento de revogação, considerar revogado
                if token_time <= revoked_after.replace(tzinfo=timezone.utc):
                    return True
        except fdb.Error:
            # Se a tabela não existir, ignora verificação de usuário
            pass
        return False  
    except fdb.Error as e:  
        print(f"Erro ao verificar a blacklist de tokens: {e}")  
        return False  
    finally:  
        if conn: conn.close()  


def revoke_all_tokens_for_user(user_id):
    """Marca todos os tokens do usuário como revogados a partir de agora.
    Requer tabela USER_TOKEN_BLACKLIST (USER_ID INTEGER PRIMARY KEY, REVOKED_AFTER TIMESTAMP).
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Upsert (em Firebird: tenta update, se 0 linhas, faz insert)
        cur.execute("UPDATE USER_TOKEN_BLACKLIST SET REVOKED_AFTER = CURRENT_TIMESTAMP WHERE USER_ID = ?;", (user_id,))
        if cur.rowcount == 0:
            cur.execute("INSERT INTO USER_TOKEN_BLACKLIST (USER_ID, REVOKED_AFTER) VALUES (?, CURRENT_TIMESTAMP);", (user_id,))
        conn.commit()
        return True
    except fdb.Error as e:
        print(f"Erro ao revogar tokens do usuário {user_id}: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()
