# src/services/auth_service.py

import bcrypt
import fdb
from functools import wraps
from flask import jsonify
from ..database import get_db_connection
from flask_jwt_extended import create_access_token, jwt_required, get_jwt


def authenticate(email, password):
    """
    Autentica um usuário e retorna um token JWT se as credenciais forem válidas.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Busca o usuário e o hash da senha
        sql = "SELECT ID, PASSWORD_HASH, ROLE, FULL_NAME FROM USERS WHERE EMAIL = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql, (email,))
        user_record = cur.fetchone()

        if user_record:
            user_id, hashed_password, role, full_name = user_record

            # Verifica se a senha fornecida corresponde ao hash armazenado
            if bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8')):
                # --- A CORREÇÃO ESTÁ AQUI ---
                # 1. A 'identity' deve ser algo simples e único, como o ID do usuário.
                #    Convertemos para string por segurança.
                identity = str(user_id)

                # 2. Podemos adicionar outros dados úteis (como o cargo) como "claims" adicionais.
                additional_claims = {"roles": [role], "full_name": full_name}

                # 3. Criamos o token com a identidade correta e as claims.
                access_token = create_access_token(identity=identity, additional_claims=additional_claims)

                return access_token

        # Retorna None se o usuário não for encontrado ou a senha estiver incorreta
        return None

    except fdb.Error as e:
        print(f"Erro de banco de dados na autenticação: {e}")
        return None
    finally:
        if conn: conn.close()

def require_role(*roles):
    # ... (o código do decorator continua exatamente o mesmo) ...
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
    """Adiciona o JTI de um token à blacklist."""
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
        # Não lançamos um erro aqui para não quebrar o logout do usuário
    finally:
        if conn: conn.close()

def is_token_revoked(jwt_payload):
    """Verifica se um token (pelo seu JTI) está na blacklist."""
    jti = jwt_payload['jti']
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = "SELECT JTI FROM TOKEN_BLACKLIST WHERE JTI = ?;"
        cur.execute(sql, (jti,))
        return cur.fetchone() is not None # Retorna True se encontrou, False se não
    except fdb.Error as e:
        print(f"Erro ao verificar a blacklist de tokens: {e}")
        return False # Em caso de erro, por segurança, consideramos o token revogado
    finally:
        if conn: conn.close()