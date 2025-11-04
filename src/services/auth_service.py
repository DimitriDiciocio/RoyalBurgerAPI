import bcrypt  
import fdb  
from functools import wraps  
from flask import jsonify  
from datetime import datetime, timezone, timedelta
import threading
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
        # Verifica conta inativa PRIMEIRO
        if not is_active:  
            return (None, "ACCOUNT_INACTIVE", "Sua conta está inativa. Entre em contato com o suporte para reativá-la.")  
        # Verifica email ANTES da senha para dar feedback mais específico
        if not is_email_verified:
            return (None, "EMAIL_NOT_VERIFIED", "E-mail não verificado. Verifique seu e-mail para continuar.")
        # Por último, verifica a senha
        if not bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8')):  
            return (None, "INVALID_PASSWORD", "Senha incorreta")
        
        # Se 2FA está habilitado, retorna status especial
        if two_factor_enabled:
            success, error_code, message = create_2fa_verification(user_id, email)
            if not success:
                return (None, error_code, message)
            
            return ({"requires_2fa": True, "user_id": user_id}, None, message)
        
        # Login normal sem 2FA
        # Remove tokens de revogação antigos quando o usuário faz login
        clear_user_revoke_tokens(user_id)
        
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
        # OTIMIZAÇÃO: Invalida cache quando token é adicionado à blacklist
        _invalidate_token_cache(jti=jti)
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
        # Remove tokens de revogação antigos quando o usuário faz login via 2FA
        clear_user_revoke_tokens(user_id)
        
        identity = str(user_id)
        additional_claims = {"roles": [role], "full_name": full_name}
        access_token = create_access_token(identity=identity, additional_claims=additional_claims)
        
        return (access_token, None, None)
        
    except fdb.Error as e:
        print(f"Erro ao criar token após 2FA: {e}")
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()

# Cache em memória para tokens revogados (usando apenas Python padrão)
_token_cache = {}
_cache_lock = threading.Lock()
_cache_ttl = timedelta(minutes=5)
_max_cache_size = 1000  # Limite para evitar consumo excessivo de memória

def _clean_expired_cache():
    """Remove entradas expiradas do cache"""
    now = datetime.now()
    expired_keys = [
        key for key, (_, cached_time) in _token_cache.items()
        if now - cached_time >= _cache_ttl
    ]
    for key in expired_keys:
        _token_cache.pop(key, None)

def _invalidate_token_cache(user_id=None, jti=None):
    """Invalida cache de tokens para um usuário ou token específico"""
    with _cache_lock:
        if user_id:
            # Remove todas as entradas do cache para este usuário
            keys_to_remove = [key for key in _token_cache.keys() if key.endswith(f"_{user_id}")]
            for key in keys_to_remove:
                _token_cache.pop(key, None)
        elif jti:
            # Remove entrada específica do cache
            keys_to_remove = [key for key in _token_cache.keys() if key.startswith(f"{jti}_")]
            for key in keys_to_remove:
                _token_cache.pop(key, None)

def is_token_revoked(jwt_payload):  
    jti = jwt_payload['jti']  
    user_sub = jwt_payload.get('sub')  
    token_iat = jwt_payload.get('iat')  
    
    # Verificar cache primeiro
    cache_key = f"{jti}_{user_sub}"
    with _cache_lock:
        # Limpa cache expirado periodicamente
        if len(_token_cache) > _max_cache_size:
            _clean_expired_cache()
        
        if cache_key in _token_cache:
            cached_result, cached_time = _token_cache[cache_key]
            if datetime.now() - cached_time < _cache_ttl:
                return cached_result
    
    # Se não estiver em cache, verificar banco
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        
        # 1) Blacklist por JTI (token específico)
        sql = "SELECT 1 FROM TOKEN_BLACKLIST WHERE JTI = ?;"  
        cur.execute(sql, (jti,))  
        if cur.fetchone() is not None:
            with _cache_lock:
                _token_cache[cache_key] = (True, datetime.now())
            return True
            
        # 2) Revogação global por usuário (verifica token especial de revogação)
        if user_sub:
            try:
                # Verifica se existe um token de revogação global para este usuário
                # OTIMIZAÇÃO: Usar FIRST 1 ao invés de LIKE sem limite
                cur.execute("SELECT FIRST 1 JTI FROM TOKEN_BLACKLIST WHERE JTI LIKE ?", (f"REVOKE_USER_{user_sub}_%",))
                revoke_token = cur.fetchone()
                
                if revoke_token and token_iat is not None:
                    # Extrai o timestamp do token de revogação
                    revoke_jti = revoke_token[0]
                    # Formato: "REVOKE_USER_{USER_ID}_{TIMESTAMP}"
                    try:
                        revoke_timestamp_str = revoke_jti.split('_')[-1]
                        revoke_timestamp = datetime.strptime(revoke_timestamp_str, "%Y%m%d%H%M%S")
                        
                        # Converte token_iat (epoch seconds) para datetime
                        token_time = datetime.fromtimestamp(int(token_iat), tz=timezone.utc)
                        
                        # Se o token foi criado antes da revogação, considera revogado
                        if token_time <= revoke_timestamp.replace(tzinfo=timezone.utc):
                            with _cache_lock:
                                _token_cache[cache_key] = (True, datetime.now())
                            return True
                        else:
                            # Token válido, cachear como não revogado
                            with _cache_lock:
                                _token_cache[cache_key] = (False, datetime.now())
                            return False
                            
                    except (ValueError, IndexError) as e:
                        print(f"Erro ao processar timestamp de revogação: {e}")
                        # Se não conseguir extrair o timestamp, considera revogado por segurança
                        with _cache_lock:
                            _token_cache[cache_key] = (True, datetime.now())
                        return True
                        
            except fdb.Error as e:
                print(f"Erro ao verificar revogação global do usuário {user_sub}: {e}")
                # Em caso de erro, não considera revogado para não bloquear usuários
                pass
        
        # Token não revogado, cachear resultado
        with _cache_lock:
            _token_cache[cache_key] = (False, datetime.now())
        return False  
    except fdb.Error as e:  
        print(f"Erro ao verificar a blacklist de tokens: {e}")  
        # Em caso de erro, não considera revogado para não bloquear usuários
        return False  
    finally:  
        if conn: conn.close()  


def revoke_all_tokens_for_user(user_id):
    """Marca todos os tokens do usuário como revogados a partir de agora.
    Usa a tabela TOKEN_BLACKLIST existente com um token especial para marcar a revogação global.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Cria um token especial para marcar a revogação global do usuário
        # Formato: "REVOKE_USER_{USER_ID}_{TIMESTAMP}"
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        special_jti = f"REVOKE_USER_{user_id}_{timestamp}"
        
        # Adiciona o token especial à blacklist com expiração longa (1 ano)
        expires_at = datetime.now().replace(year=datetime.now().year + 1)
        
        # Verifica se já existe um token de revogação para este usuário
        cur.execute("SELECT FIRST 1 JTI FROM TOKEN_BLACKLIST WHERE JTI LIKE ?", (f"REVOKE_USER_{user_id}_%",))
        existing_revoke = cur.fetchone()
        
        if existing_revoke:
            # Remove o token de revogação antigo
            cur.execute("DELETE FROM TOKEN_BLACKLIST WHERE JTI = ?", (existing_revoke[0],))
            print(f"Token de revogação antigo removido: {existing_revoke[0]}")
        
        # OTIMIZAÇÃO: Invalida cache de tokens deste usuário antes de adicionar novo token de revogação
        _invalidate_token_cache(user_id=user_id)
        
        # Adiciona o novo token de revogação
        cur.execute("INSERT INTO TOKEN_BLACKLIST (JTI, EXPIRES_AT) VALUES (?, ?)", (special_jti, expires_at))
        
        conn.commit()
        print(f"Tokens do usuário {user_id} revogados com sucesso. Token de revogação: {special_jti}")
        return True
    except fdb.Error as e:
        print(f"Erro ao revogar tokens do usuário {user_id}: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

def clear_user_revoke_tokens(user_id):
    """Remove tokens de revogação antigos quando o usuário faz login novamente."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Remove todos os tokens de revogação para este usuário
        cur.execute("DELETE FROM TOKEN_BLACKLIST WHERE JTI LIKE ?", (f"REVOKE_USER_{user_id}_%",))
        deleted_count = cur.rowcount
        
        if deleted_count > 0:
            conn.commit()
            print(f"Removidos {deleted_count} tokens de revogação antigos para o usuário {user_id}")
        
        return True
    except fdb.Error as e:
        print(f"Erro ao limpar tokens de revogação do usuário {user_id}: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()
