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
            user_role = claims.get("role")
            if user_role in roles:
                return f(*args, **kwargs)
            else:
                return jsonify({"msg": "Acesso não autorizado para esta função."}), 403
        return decorated_function
    return decorator