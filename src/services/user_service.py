# src/services/user_service.py

import fdb
import bcrypt
from datetime import datetime, timedelta
from . import email_service
from ..database import get_db_connection
from ..utils import token_helper
from ..utils import validators


def create_user(user_data):
    """Cria um novo usuário (cliente ou interno) e envia e-mail de boas-vindas."""
    full_name = user_data.get('full_name')
    email = user_data.get('email')
    password = user_data.get('password')
    phone = user_data.get('phone')
    # NOVO: Coleta a data de nascimento
    date_of_birth = user_data.get('date_of_birth')

    # Validação de e-mail
    is_valid, message = validators.is_valid_email(email)
    if not is_valid:
        return (None, message)

    # Validação de telefone (se fornecido)
    if phone:
        is_valid, message = validators.is_valid_phone(phone)
        if not is_valid:
            return (None, message)

    # Validação de senha
    is_strong, message = validators.is_strong_password(password)
    if not is_strong:
        return (None, message)

    role = user_data.get('role', 'customer')
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # NOVO: Adiciona DATE_OF_BIRTH ao SQL
        sql = """
            INSERT INTO USERS (FULL_NAME, EMAIL, PASSWORD_HASH, ROLE, DATE_OF_BIRTH) 
            VALUES (?, ?, ?, ?, ?) 
            RETURNING ID;
        """
        # NOVO: Passa date_of_birth como parâmetro
        cur.execute(sql, (full_name, email, hashed_password.decode('utf-8'), role, date_of_birth))
        new_user_id = cur.fetchone()[0]
        conn.commit()

        # Adicionamos a data de nascimento ao objeto retornado
        new_user = {
            "id": new_user_id,
            "full_name": full_name,
            "email": email,
            "role": role,
            "date_of_birth": date_of_birth
        }

        if role == 'customer':
            try:
                email_service.send_email(
                    to=new_user['email'],
                    subject='Bem-vindo ao Royal Burger!',
                    template='welcome',
                    user=new_user
                )
            except Exception as e:
                print(f"AVISO: Falha ao enviar e-mail de boas-vindas para {new_user['email']}. Erro: {e}")

        # Retorna o novo usuário e None para a mensagem de erro
        return (new_user, None)
    except fdb.Error as e:
        print(f"Erro ao criar usuário: {e}")
        if conn: conn.rollback()
        # Retorna None para o usuário e uma mensagem de erro genérica
        return (None, "O e-mail fornecido já pode estar em uso.")
    finally:
        if conn: conn.close()


def get_users_by_role(roles):
    """Busca todos os usuários ativos de determinados papéis."""
    if isinstance(roles, str):
        roles = [roles]
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        placeholders = ', '.join(['?' for _ in roles])
        sql = f"SELECT ID, FULL_NAME, EMAIL, PHONE, CPF, ROLE FROM USERS WHERE ROLE IN ({placeholders}) AND IS_ACTIVE = TRUE ORDER BY FULL_NAME;"
        cur.execute(sql, tuple(roles))
        users = [{"id": row[0], "full_name": row[1], "email": row[2], "phone": row[3], "cpf": row[4], "role": row[5]} for row in
                 cur.fetchall()]
        return users
    except fdb.Error as e:
        print(f"Erro ao buscar usuários por papel: {e}")
        return []
    finally:
        if conn: conn.close()


def get_user_by_id(user_id):
    """Busca um único usuário ativo pelo ID."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = "SELECT ID, FULL_NAME, EMAIL, PHONE, CPF, ROLE FROM USERS WHERE ID = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql, (user_id,))
        row = cur.fetchone()
        if row:
            return {"id": row[0], "full_name": row[1], "email": row[2], "phone": row[3], "cpf": row[4], "role": row[5]}
        return None
    except fdb.Error as e:
        print(f"Erro ao buscar usuário por ID: {e}")
        return None
    finally:
        if conn: conn.close()


def update_user(user_id, update_data):
    """
    Atualiza dados de um usuário com validações específicas para cada campo.
    Retorna uma tupla: (sucesso, mensagem).
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # --- NOVA ETAPA: Verificação de Existência ---
        # Primeiro, garantimos que o usuário que estamos tentando editar realmente existe.
        sql_check_exists = "SELECT 1 FROM USERS WHERE ID = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql_check_exists, (user_id,))
        if not cur.fetchone():
            return (False, "Usuário não encontrado.")

        # --- Validações Específicas ---
        if 'email' in update_data:
            new_email = update_data['email']
            # Validação de formato de e-mail
            is_valid, message = validators.is_valid_email(new_email)
            if not is_valid:
                return (False, message)
            
            sql_check_email = "SELECT ID FROM USERS WHERE EMAIL = ? AND ID <> ?;"
            cur.execute(sql_check_email, (new_email, user_id))
            if cur.fetchone():
                return (False, "Este e-mail já está em uso por outra conta.")

        if 'phone' in update_data:
            new_phone = update_data['phone']
            if new_phone:
                # Validação de formato de telefone
                is_valid, message = validators.is_valid_phone(new_phone)
                if not is_valid:
                    return (False, message)
                
                sql_check_phone = "SELECT ID FROM USERS WHERE PHONE = ? AND ID <> ?;"
                cur.execute(sql_check_phone, (new_phone, user_id))
                if cur.fetchone():
                    return (False, "Este telefone já está em uso por outra conta.")

        if 'cpf' in update_data:
            new_cpf = update_data['cpf']
            if new_cpf and not validators.is_valid_cpf(new_cpf):
                return (False, "O CPF fornecido é inválido.")

        # --- Construção da Query de Update (continua igual) ---
        allowed_fields = ['full_name', 'date_of_birth', 'phone', 'cpf', 'email']
        fields_to_update = {k: v for k, v in update_data.items() if k in allowed_fields}

        if not fields_to_update:
            return (False, "Nenhum campo válido para atualização foi fornecido.")

        set_parts = [f"{key} = ?" for key in fields_to_update]
        values = list(fields_to_update.values())
        values.append(user_id)

        sql_update = f"UPDATE USERS SET {', '.join(set_parts)} WHERE ID = ?;"
        cur.execute(sql_update, tuple(values))
        conn.commit()

        # --- LÓGICA DE RETORNO CORRIGIDA ---
        # Se chegamos até aqui sem erros, a operação foi um sucesso.
        # Não dependemos mais do rowcount.
        return (True, "Dados atualizados com sucesso.")

    except fdb.Error as e:
        print(f"Erro ao atualizar usuário: {e}")
        if conn: conn.rollback()
        return (False, "Ocorreu um erro interno no servidor.")
    finally:
        if conn: conn.close()

def deactivate_user(user_id):
    """'Deleta' um usuário (na verdade, apenas o inativa - Soft Delete)."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = "UPDATE USERS SET IS_ACTIVE = FALSE WHERE ID = ?;"
        cur.execute(sql, (user_id,))
        conn.commit()
        return cur.rowcount > 0
    except fdb.Error as e:
        print(f"Erro ao inativar usuário: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

def get_user_ids_by_roles(roles):
    """Busca os IDs de todos os usuários ativos com os cargos especificados."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # O 'IN' do SQL não funciona bem com placeholders, então formatamos a string com segurança.
        placeholders = ', '.join(['?' for _ in roles])
        sql = f"SELECT ID FROM USERS WHERE ROLE IN ({placeholders}) AND IS_ACTIVE = TRUE;"
        cur.execute(sql, tuple(roles))
        return [row[0] for row in cur.fetchall()]
    except fdb.Error as e:
        print(f"Erro ao buscar usuários por cargos: {e}")
        return []
    finally:
        if conn: conn.close()

def initiate_password_reset(email):
    """
    Inicia o fluxo de recuperação de senha para um e-mail.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # 1. Encontra o usuário pelo e-mail
        sql_find_user = "SELECT ID, FULL_NAME FROM USERS WHERE EMAIL = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql_find_user, (email,))
        user_record = cur.fetchone()

        if user_record:
            user_id, full_name = user_record

            # 2. Gera um token seguro
            token = token_helper.generate_secure_token()

            # 3. Define o prazo de validade (1 hora a partir de agora)
            expires_at = datetime.now() + timedelta(hours=1)

            # 4. Salva o token no banco de dados
            sql_save_token = "INSERT INTO PASSWORD_RESET_TOKENS (USER_ID, TOKEN, EXPIRES_AT) VALUES (?, ?, ?);"
            cur.execute(sql_save_token, (user_id, token, expires_at))
            conn.commit()

            # 5. Envia o e-mail de recuperação
            # O link aponta para a rota do nosso frontend React
            reset_link = f"http://localhost:5173/reset-password?token={token}"

            email_service.send_email(
                to=email,
                subject="Recuperação de Senha - Royal Burger",
                template='password_reset',
                user={"full_name": full_name},
                reset_link=reset_link
            )

        # Sempre retorna True para não vazar informação sobre e-mails existentes
        return True

    except fdb.Error as e:
        print(f"Erro no banco de dados ao iniciar a recuperação de senha: {e}")
        if conn: conn.rollback()
        # Mesmo com erro de DB, não retornamos o erro para o usuário final por segurança
        return False
    finally:
        if conn: conn.close()

def finalize_password_reset(token, new_password):
    """
    Valida um token de recuperação e, se válido, redefine a senha do usuário.
    Retorna uma tupla: (sucesso, mensagem_de_erro).
    """
    is_strong, message = validators.is_strong_password(new_password)
    if not is_strong:
        return (False, message)

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # --- Início da Transação ---

        # 1. Encontra o token e verifica sua validade
        sql_find_token = """
            SELECT USER_ID, EXPIRES_AT, USED_AT
            FROM PASSWORD_RESET_TOKENS
            WHERE TOKEN = ?;
        """
        cur.execute(sql_find_token, (token,))
        token_record = cur.fetchone()

        if not token_record:
            return (False, "Token inválido ou não encontrado.")

        user_id, expires_at, used_at = token_record

        if used_at is not None:
            return (False, "Este token de recuperação já foi utilizado.")

        if datetime.now() > expires_at:
            return (False, "Este token de recuperação expirou.")

        # 2. Se o token é válido, atualiza a senha do usuário
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        sql_update_password = "UPDATE USERS SET PASSWORD_HASH = ? WHERE ID = ?;"
        cur.execute(sql_update_password, (hashed_password.decode('utf-8'), user_id))

        # 3. Marca o token como utilizado para invalidá-lo
        sql_invalidate_token = "UPDATE PASSWORD_RESET_TOKENS SET USED_AT = CURRENT_TIMESTAMP WHERE TOKEN = ?;"
        cur.execute(sql_invalidate_token, (token,))

        conn.commit()

        # --- Fim da Transação ---

        return (True, "Senha atualizada com sucesso.")

    except fdb.Error as e:
        print(f"Erro no banco de dados ao finalizar a recuperação de senha: {e}")
        if conn: conn.rollback()
        return (False, "Ocorreu um erro interno. Tente novamente mais tarde.")
    finally:
        if conn: conn.close()