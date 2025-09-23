import bcrypt  # importa biblioteca para hash de senhas
import fdb  # importa driver do Firebird
from functools import wraps  # importa decorator wraps
from flask import jsonify  # importa jsonify do Flask
from ..database import get_db_connection  # importa função de conexão com banco
from flask_jwt_extended import create_access_token, jwt_required, get_jwt  # importa utilitários JWT

def authenticate(email, password):  # função para autenticar usuário
    conn = None  # inicializa conexão
    try:  # tenta autenticar
        conn = get_db_connection()  # abre conexão com banco
        cur = conn.cursor()  # cria cursor
        sql_check_user = "SELECT ID, PASSWORD_HASH, ROLE, FULL_NAME, IS_ACTIVE FROM USERS WHERE EMAIL = ?;"  # query para buscar usuário
        cur.execute(sql_check_user, (email,))  # executa query
        user_record = cur.fetchone()  # obtém resultado
        if not user_record:  # usuário não encontrado
            return (None, "USER_NOT_FOUND", "Usuário não encontrado")  # retorna erro
        user_id, hashed_password, role, full_name, is_active = user_record  # desempacota dados do usuário
        if not is_active:  # conta inativa
            return (None, "ACCOUNT_INACTIVE", "Sua conta está inativa. Entre em contato com o suporte para reativá-la.")  # retorna erro
        if not bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8')):  # verifica senha
            return (None, "INVALID_PASSWORD", "Senha incorreta")  # retorna erro
        identity = str(user_id)  # converte ID para string
        additional_claims = {"roles": [role], "full_name": full_name}  # monta claims adicionais
        access_token = create_access_token(identity=identity, additional_claims=additional_claims)  # cria token JWT
        return (access_token, None, None)  # retorna token de sucesso
    except fdb.Error as e:  # captura erros do banco
        print(f"Erro de banco de dados na autenticação: {e}")  # exibe erro
        return (None, "DATABASE_ERROR", "Erro interno do servidor")  # retorna erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def require_role(*roles):  # decorator para verificar papéis
    def decorator(f):  # decorator interno
        @wraps(f)  # preserva metadados da função
        @jwt_required()  # exige autenticação JWT
        def decorated_function(*args, **kwargs):  # função decorada
            claims = get_jwt()  # obtém claims do token
            user_roles = claims.get("roles", [])  # extrai papéis do usuário
            if any(role in user_roles for role in roles):  # verifica se tem papel necessário
                return f(*args, **kwargs)  # executa função original
            else:  # sem permissão
                return jsonify({"msg": "Acesso não autorizado para esta função."}), 403  # retorna erro 403
        return decorated_function  # retorna função decorada
    return decorator  # retorna decorator

def add_token_to_blacklist(jti, expires_at):  # função para adicionar token à blacklist
    conn = None  # inicializa conexão
    try:  # tenta adicionar à blacklist
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = "INSERT INTO TOKEN_BLACKLIST (JTI, EXPIRES_AT) VALUES (?, ?);"  # query de inserção
        cur.execute(sql, (jti, expires_at))  # executa query
        conn.commit()  # confirma transação
    except fdb.Error as e:  # captura erros
        print(f"Erro ao adicionar token à blacklist: {e}")  # exibe erro
        if conn: conn.rollback()  # desfaz transação
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def is_token_revoked(jwt_payload):  # função para verificar se token está revogado
    jti = jwt_payload['jti']  # extrai JTI do payload
    conn = None  # inicializa conexão
    try:  # tenta verificar blacklist
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        sql = "SELECT JTI FROM TOKEN_BLACKLIST WHERE JTI = ?;"  # query de verificação
        cur.execute(sql, (jti,))  # executa query
        return cur.fetchone() is not None  # retorna True se encontrou na blacklist
    except fdb.Error as e:  # captura erros
        print(f"Erro ao verificar a blacklist de tokens: {e}")  # exibe erro
        return False  # em caso de erro, considera token válido
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão