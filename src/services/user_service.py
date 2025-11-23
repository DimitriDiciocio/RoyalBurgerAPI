import fdb  
import bcrypt  
import logging
# ALTERAÇÃO: Adicionar date ao import para uso em validações de filtros
from datetime import datetime, timedelta, date  
from . import email_service
from . import loyalty_service
from ..database import get_db_connection  
from . import auth_service
# ALTERAÇÃO: Removido import não utilizado token_helper
from ..utils import validators

logger = logging.getLogger(__name__)  

def convert_date_format(date_string):
    """
    Converte data do formato DD-MM-YYYY ou DD-MM-YY (frontend) para YYYY-MM-DD (Firebird).
    Retorna a data convertida ou None se inválida.
    """
    if not date_string:
        return None
    
    try:
        if date_string.count('-') == 2:
            day, month, year = date_string.split('-')
            if len(day) == 2 and len(month) == 2 and len(year) in (2, 4):
                if len(year) == 2:
                    # Converte YY -> YYYY usando pivô 50 (00-50 => 2000-2050; 51-99 => 1951-1999)
                    yy = int(year)
                    full_year = 2000 + yy if yy <= 50 else 1900 + yy
                    year = str(full_year)
                return f"{year}-{month}-{day}"
    except (ValueError, AttributeError, IndexError) as e:
        # ALTERAÇÃO: Especificar exceções esperadas ao invés de catch-all genérico
        logger.debug(f"Erro ao converter formato de data '{date_string}': {e}")
        pass
    
    return date_string

def create_user(user_data):
    full_name = user_data.get('full_name')
    email = user_data.get('email')
    # Normaliza o email para minúsculas
    if email:
        email = email.lower().strip()
    password = user_data.get('password')
    phone = user_data.get('phone')
    cpf = user_data.get('cpf')
    
    # Processa a data de nascimento
    date_of_birth_raw = user_data.get('date_of_birth')
    if date_of_birth_raw and date_of_birth_raw.strip():
        # Se já está no formato ISO (YYYY-MM-DD), usa diretamente
        if len(date_of_birth_raw) == 10 and date_of_birth_raw.count('-') == 2:
            try:
                # Valida se é uma data válida no formato ISO
                datetime.strptime(date_of_birth_raw, '%Y-%m-%d')
                date_of_birth = date_of_birth_raw
            except ValueError:
                # Se não é válida, tenta converter do formato brasileiro
                date_of_birth = convert_date_format(date_of_birth_raw)
        else:
            # Se está no formato brasileiro (DD-MM-YYYY), converte
            date_of_birth = convert_date_format(date_of_birth_raw)
    else:
        date_of_birth = None
    
    is_valid, message = validators.is_valid_email(email)
    if not is_valid:
        return (None, "INVALID_EMAIL", message)

    if date_of_birth:
        try:
            datetime.strptime(date_of_birth, '%Y-%m-%d')
            
            birth_date = datetime.strptime(date_of_birth, '%Y-%m-%d')
            today = datetime.now()
            age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
            
            if age < 18:
                return (None, "INVALID_DATE", "Você deve ter pelo menos 18 anos para se cadastrar.")
            if age > 120:
                return (None, "INVALID_DATE", "Data de nascimento inválida.")
                
        except ValueError:
            return (None, "INVALID_DATE", "Formato de data inválido. Use DD-MM-AAAA.")

    if phone:
        is_valid, message = validators.is_valid_phone(phone)
        if not is_valid:
            return (None, "INVALID_PHONE", message)

    if cpf:
        if not validators.is_valid_cpf(cpf):
            return (None, "INVALID_CPF", "O CPF fornecido é inválido.")

    is_strong, message = validators.is_strong_password(password)
    if not is_strong:
        return (None, "WEAK_PASSWORD", message)

    role = user_data.get('role', 'customer')
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se o email já está em uso por uma conta com email verificado
        sql_check_email = "SELECT ID FROM USERS WHERE EMAIL = ? AND IS_EMAIL_VERIFIED = TRUE;"
        cur.execute(sql_check_email, (email,))
        if cur.fetchone():
            return (None, "EMAIL_ALREADY_EXISTS", "Este e-mail já está em uso por outra conta verificada.")

        # Telefone não precisa ser único - múltiplos usuários podem ter o mesmo telefone

        if cpf:
            sql_check_cpf = "SELECT ID FROM USERS WHERE CPF = ?;"
            cur.execute(sql_check_cpf, (cpf,))
            if cur.fetchone():
                return (None, "CPF_ALREADY_EXISTS", "Este CPF já está em uso por outra conta.")

        # Verifica se a data é válida antes de inserir
        if date_of_birth:
            try:
                # Tenta converter para datetime para validar
                datetime.strptime(date_of_birth, '%Y-%m-%d')
            except ValueError as ve:
                return (None, "INVALID_DATE", f"Data de nascimento inválida: {date_of_birth}")
        
        # query para inserir novo usuário
        sql = """
            INSERT INTO USERS (FULL_NAME, EMAIL, PASSWORD_HASH, ROLE, DATE_OF_BIRTH, PHONE, CPF) 
            VALUES (?, ?, ?, ?, ?, ?, ?) 
            RETURNING ID;
        """
        cur.execute(sql, (full_name, email, hashed_password.decode('utf-8'), role, date_of_birth, phone, cpf))
        new_user_id = cur.fetchone()[0]
        
        # Se for customer, adiciona pontos de boas-vindas ANTES do commit
        if role == 'customer':
            try:
                loyalty_service.add_welcome_points(new_user_id, cur)
            except Exception as e:
                # ALTERAÇÃO: Logar exceção ao invés de silenciar completamente
                # Falha em pontos de boas-vindas não deve impedir criação do usuário, mas deve ser registrada
                logger.warning(f"Falha ao adicionar pontos de boas-vindas para usuário {new_user_id}: {e}", exc_info=True)
                # Re-lança apenas para fazer rollback se necessário (mas não deve chegar aqui devido ao commit depois)
        
        # Commit de tudo junto (usuário + pontos)
        conn.commit()

        new_user = {
            "id": new_user_id,
            "full_name": full_name,
            "email": email,
            "role": role,
            "date_of_birth": date_of_birth,
            "phone": phone,
            "cpf": cpf,
            "is_active": True,
        }

        # Envia e-mail de boas-vindas após o commit (fora da transação)
        if role == 'customer':
            try:
                email_service.send_email(
                    to=new_user['email'],
                    subject='Bem-vindo ao Royal Burger!',
                    template='welcome',
                    user=new_user
                )
            except Exception as e:
                # ALTERAÇÃO: Logging estruturado ao invés de silenciar completamente
                # Falha no email não deve impedir criação do usuário, mas deve ser registrada
                logger.warning(f"Falha ao enviar e-mail de boas-vindas para {new_user.get('email', 'N/A')}: {e}", exc_info=True)

        return (new_user, None, None)
    except fdb.Error as e:
        if conn: conn.rollback()
        
        # Tratamento específico para erro de validação de data
        if "DATE_OF_BIRTH" in str(e) and "validation error" in str(e):
            return (None, "INVALID_DATE", "Data de nascimento inválida ou em formato incorreto")
        
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()

def verify_user_password(user_id, password):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        sql = "SELECT PASSWORD_HASH FROM USERS WHERE ID = ?;"
        cur.execute(sql, (user_id,))
        row = cur.fetchone()

        if not row:
            return False

        stored_hash = row[0]
        if not stored_hash:
            return False

        return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
    except fdb.Error as e:
        return False
    finally:
        if conn:
            conn.close()

def get_users_by_role(roles):
    if isinstance(roles, str):
        roles = [roles]
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        placeholders = ', '.join(['?' for _ in roles])
        sql = f"SELECT ID, FULL_NAME, EMAIL, PHONE, CPF, ROLE FROM USERS WHERE ROLE IN ({placeholders}) AND IS_ACTIVE = TRUE ORDER BY FULL_NAME;"
        cur.execute(sql, tuple(roles))
        users = [{"id": row[0], "full_name": row[1], "email": row[2], "phone": row[3], "cpf": row[4], "role": row[5]} for row in cur.fetchall()]
        return users
    except fdb.Error as e:
        return []
    finally:
        if conn: conn.close()

def get_notification_preferences(user_id):
    """
    Obtém as preferências de notificação do usuário.
    Retorna um dicionário com as preferências ou None se o usuário não for encontrado.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT NOTIFY_ORDER_UPDATES, NOTIFY_PROMOTIONS 
            FROM USERS 
            WHERE ID = ? AND IS_ACTIVE = TRUE;
        """
        cur.execute(sql, (user_id,))
        row = cur.fetchone()
        
        if not row:
            return None
        
        # Firebird retorna True/False como 1/0, converter para boolean
        notify_order_updates = bool(row[0]) if row[0] is not None else True
        notify_promotions = bool(row[1]) if row[1] is not None else True
        
        return {
            'notify_order_updates': notify_order_updates,
            'notify_promotions': notify_promotions
        }
    except fdb.Error as e:
        logger.error(f"Erro ao obter preferências de notificação: {e}")
        return None
    finally:
        if conn: conn.close()

def update_notification_preferences(user_id, preferences):
    """
    Atualiza as preferências de notificação do usuário.
    preferences: dict com 'notify_order_updates' e/ou 'notify_promotions' (boolean)
    Retorna (sucesso, error_code, mensagem)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verificar se o usuário existe
        sql_check = "SELECT 1 FROM USERS WHERE ID = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql_check, (user_id,))
        if not cur.fetchone():
            return (False, "USER_NOT_FOUND", "Usuário não encontrado.")
        
        # Validar e preparar campos para atualização
        updates = []
        values = []
        
        if 'notify_order_updates' in preferences:
            notify_order = bool(preferences['notify_order_updates'])
            updates.append("NOTIFY_ORDER_UPDATES = ?")
            values.append(notify_order)
        
        if 'notify_promotions' in preferences:
            notify_promo = bool(preferences['notify_promotions'])
            updates.append("NOTIFY_PROMOTIONS = ?")
            values.append(notify_promo)
        
        if not updates:
            return (False, "NO_VALID_FIELDS", "Nenhuma preferência válida fornecida.")
        
        values.append(user_id)
        sql_update = f"UPDATE USERS SET {', '.join(updates)} WHERE ID = ?;"
        cur.execute(sql_update, tuple(values))
        conn.commit()
        
        return (True, None, "Preferências de notificação atualizadas com sucesso.")
    
    except fdb.Error as e:
        if conn: conn.rollback()
        logger.error(f"Erro ao atualizar preferências de notificação: {e}")
        return (False, "DATABASE_ERROR", "Erro interno do servidor.")
    finally:
        if conn: conn.close()

def get_user_by_id(user_id):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = (
            "SELECT ID, FULL_NAME, EMAIL, PHONE, CPF, ROLE, DATE_OF_BIRTH, IS_ACTIVE, CREATED_AT, "
            "IS_EMAIL_VERIFIED, TWO_FACTOR_ENABLED, NOTIFY_ORDER_UPDATES, NOTIFY_PROMOTIONS "
            "FROM USERS WHERE ID = ?;"
        )
        cur.execute(sql, (user_id,))
        row = cur.fetchone()
        if row:
            return {
                "id": row[0],
                "full_name": row[1],
                "email": row[2],
                "phone": row[3],
                "cpf": row[4],
                "role": row[5],
                "date_of_birth": row[6].strftime('%Y-%m-%d') if row[6] else None,
                "is_active": bool(row[7]) if row[7] is not None else True,
                "created_at": row[8].strftime('%Y-%m-%d %H:%M:%S') if row[8] else None,
                "is_email_verified": bool(row[9]) if row[9] is not None else False,
                "two_factor_enabled": bool(row[10]) if row[10] is not None else False,
                "notify_order_updates": bool(row[11]) if row[11] is not None else True,
                "notify_promotions": bool(row[12]) if row[12] is not None else True,
            }
        return None
    except fdb.Error as e:
        # ALTERAÇÃO: Usar logger ao invés de print() em código de produção
        logger.error(f"Erro ao buscar usuário por ID {user_id} (fdb.Error): {e}", exc_info=True)
        raise  # Re-lança para tratamento na rota
    except Exception as e:
        # ALTERAÇÃO: Usar logger ao invés de print() e capturar outras exceções não esperadas
        logger.error(f"Erro inesperado ao buscar usuário por ID {user_id}: {e}", exc_info=True)
        raise  # Re-lança para tratamento na rota
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                # ALTERAÇÃO: Usar logger ao invés de print() para erros ao fechar conexão
                logger.warning(f"Erro ao fechar conexão ao buscar usuário por ID {user_id}: {e}", exc_info=True)

def get_user_by_email(email):
    conn = None
    try:
        # Normaliza o email para minúsculas
        email = email.lower().strip()
        
        conn = get_db_connection()
        cur = conn.cursor()
        sql = "SELECT ID, FULL_NAME, EMAIL, PHONE, CPF, ROLE FROM USERS WHERE EMAIL = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql, (email,))
        row = cur.fetchone()
        if row:
            return {"id": row[0], "full_name": row[1], "email": row[2], "phone": row[3], "cpf": row[4], "role": row[5]}
        return None
    except fdb.Error as e:
        return None
    finally:
        if conn: conn.close()

def update_user(user_id, update_data, is_admin_request=False):
    """
    Atualiza dados de um usuário com validações específicas para cada campo.
    Se is_admin_request=True, permite alteração direta de email (bypass da verificação).
    Retorna uma tupla: (sucesso, error_code, mensagem).
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        sql_check_exists = "SELECT 1 FROM USERS WHERE ID = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql_check_exists, (user_id,))
        if not cur.fetchone():
            return (False, "USER_NOT_FOUND", "Usuário não encontrado.")

        # Email só pode ser alterado diretamente por administradores
        email_changed = False
        if 'email' in update_data:
            if not is_admin_request:
                return (False, "EMAIL_CHANGE_REQUIRES_VERIFICATION", "Para alterar o email, use o endpoint específico que requer verificação.")
            
            # Verifica se o email está realmente mudando
            cur.execute("SELECT EMAIL FROM USERS WHERE ID = ?;", (user_id,))
            current_email = cur.fetchone()[0]
            new_email = update_data['email']
            # Normaliza o email para minúsculas
            new_email = new_email.lower().strip()
            
            if current_email != new_email:
                email_changed = True
                update_data['email'] = new_email
                
                is_valid, message = validators.is_valid_email(new_email)
                if not is_valid:
                    return (False, "INVALID_EMAIL", message)
                
                sql_check_email = "SELECT ID FROM USERS WHERE EMAIL = ? AND ID <> ? AND IS_EMAIL_VERIFIED = TRUE;"
                cur.execute(sql_check_email, (new_email, user_id))
                if cur.fetchone():
                    return (False, "EMAIL_ALREADY_EXISTS", "Este e-mail já está em uso por outra conta verificada.")

        if 'phone' in update_data:
            new_phone = update_data['phone']
            if new_phone:
                is_valid, message = validators.is_valid_phone(new_phone)
                if not is_valid:
                    return (False, "INVALID_PHONE", message)
                # Telefone não precisa ser único - múltiplos usuários podem ter o mesmo telefone

        if 'cpf' in update_data:
            new_cpf = update_data['cpf']
            if new_cpf and not validators.is_valid_cpf(new_cpf):
                return (False, "INVALID_CPF", "O CPF fornecido é inválido.")

        if 'role' in update_data:
            new_role = update_data['role']
            valid_roles = ['admin', 'manager', 'attendant', 'delivery', 'customer']
            if new_role not in valid_roles:
                return (False, "INVALID_ROLE", "Cargo inválido. Cargos válidos: admin, manager, attendant, delivery, customer")

        allowed_fields = ['full_name', 'date_of_birth', 'phone', 'cpf', 'notify_order_updates', 'notify_promotions']
        if is_admin_request:
            allowed_fields.extend(['email', 'role'])
        fields_to_update = {k: v for k, v in update_data.items() if k in allowed_fields}

        if not fields_to_update:
            return (False, "NO_VALID_FIELDS", "Nenhum campo válido para atualização foi fornecido.")

        # Se o email foi alterado por um admin, marca como não verificado
        if email_changed and is_admin_request:
            fields_to_update['is_email_verified'] = False

        set_parts = [f"{key.upper()} = ?" for key in fields_to_update]
        values = list(fields_to_update.values())
        values.append(user_id)

        sql_update = f"UPDATE USERS SET {', '.join(set_parts)} WHERE ID = ?;"
        cur.execute(sql_update, tuple(values))
        conn.commit()

        # Mensagem personalizada se o email foi alterado
        if email_changed and is_admin_request:
            return (True, None, "Dados atualizados com sucesso. O usuário precisará verificar o novo email para continuar usando a conta.")
        else:
            return (True, None, "Dados atualizados com sucesso.")

    except fdb.Error as e:
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor.")
    finally:
        if conn: conn.close()

def deactivate_user(user_id):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        sql_check = "SELECT 1 FROM USERS WHERE ID = ?;"
        cur.execute(sql_check, (user_id,))
        if not cur.fetchone():
            return False 

        sql_update = "UPDATE USERS SET IS_ACTIVE = FALSE WHERE ID = ?;"
        cur.execute(sql_update, (user_id,))
        conn.commit()

        return True
        
    except fdb.Error as e:
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
        
        placeholders = ', '.join(['?' for _ in roles])
        sql = f"SELECT ID FROM USERS WHERE ROLE IN ({placeholders}) AND IS_ACTIVE = TRUE;"
        cur.execute(sql, tuple(roles))
        return [row[0] for row in cur.fetchall()]
    except fdb.Error as e:
        return []
    finally:
        if conn: conn.close()

def initiate_password_reset(email):
    """
    Inicia o processo de recuperação de senha.
    Retorna (sucesso, mensagem) onde sucesso indica se o email existe.
    """
    conn = None
    try:
        # Normaliza o email para minúsculas
        email = email.lower().strip()
        
        conn = get_db_connection()
        cur = conn.cursor()

        sql_find_user = "SELECT ID, FULL_NAME FROM USERS WHERE EMAIL = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql_find_user, (email,))
        user_record = cur.fetchone()

        if not user_record:
            return (False, "Email não encontrado")

        user_id, full_name = user_record

        # Gera código de 6 dígitos
        import random
        reset_code = f"{random.randint(100000, 999999)}"

        expires_at = datetime.now() + timedelta(minutes=15)  # Código expira em 15 minutos

        # Remove códigos antigos do mesmo usuário
        sql_cleanup = "DELETE FROM PASSWORD_RESET WHERE USER_ID = ?;"
        cur.execute(sql_cleanup, (user_id,))

        # Salva o novo código
        sql_save_code = "INSERT INTO PASSWORD_RESET (USER_ID, VERIFICATION_CODE, EXPIRES_AT) VALUES (?, ?, ?);"
        cur.execute(sql_save_code, (user_id, reset_code, expires_at))
        conn.commit()

        from .email_service import send_email
        try:
            send_email(
                to=email,
                subject="Royal Burger - Código de recuperação de senha",
                template="password_reset_code",
                user={"full_name": full_name},
                reset_code=reset_code,
            )
        except Exception as e:
            # ALTERAÇÃO: Logging estruturado ao invés de silenciar completamente
            # Falha no email não impede geração do código, mas deve ser registrada para diagnóstico
            logger.warning(f"Falha ao enviar e-mail de recuperação de senha para {email}: {e}", exc_info=True)

        return (True, "Código enviado com sucesso")

    except fdb.Error as e:
        if conn: conn.rollback()
        return (False, "Erro interno do servidor")
    finally:
        if conn: conn.close()

def verify_reset_code(email, reset_code):
    """
    Verifica se o código de reset é válido.
    Retorna (sucesso, mensagem).
    """
    conn = None
    try:
        # Normaliza o email para minúsculas
        email = email.lower().strip()
        
        conn = get_db_connection()
        cur = conn.cursor()

        # Busca o usuário pelo email
        sql_find_user = "SELECT ID FROM USERS WHERE EMAIL = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql_find_user, (email,))
        user_record = cur.fetchone()

        if not user_record:
            return (False, "Usuário não encontrado.")

        user_id = user_record[0]

        # Busca o código de reset
        sql_find_code = """
            SELECT EXPIRES_AT, USED_AT
            FROM PASSWORD_RESET
            WHERE USER_ID = ? AND VERIFICATION_CODE = ?;
        """
        cur.execute(sql_find_code, (user_id, reset_code))
        code_record = cur.fetchone()

        if not code_record:
            return (False, "Código de recuperação inválido.")

        expires_at, used_at = code_record

        if used_at is not None:
            return (False, "Este código de recuperação já foi utilizado.")

        if datetime.now() > expires_at:
            return (False, "Este código de recuperação expirou.")

        return (True, "Código válido.")

    except fdb.Error as e:
        return (False, "Erro interno do servidor")
    finally:
        if conn: conn.close()

def finalize_password_reset(email, reset_code, new_password):
    """
    Finaliza a recuperação de senha usando email e código de 6 dígitos.
    Retorna uma tupla: (sucesso, mensagem).
    """
    is_strong, message = validators.is_strong_password(new_password)
    if not is_strong:
        return (False, message)

    conn = None
    try:
        # Normaliza o email para minúsculas
        email = email.lower().strip()
        
        conn = get_db_connection()
        cur = conn.cursor()

        # Busca o usuário pelo email
        sql_find_user = "SELECT ID FROM USERS WHERE EMAIL = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql_find_user, (email,))
        user_record = cur.fetchone()

        if not user_record:
            return (False, "Usuário não encontrado.")

        user_id = user_record[0]

        # Busca o código de reset
        sql_find_code = """
            SELECT EXPIRES_AT, USED_AT
            FROM PASSWORD_RESET
            WHERE USER_ID = ? AND VERIFICATION_CODE = ?;
        """
        cur.execute(sql_find_code, (user_id, reset_code))
        code_record = cur.fetchone()

        if not code_record:
            return (False, "Código de recuperação inválido.")

        expires_at, used_at = code_record

        if used_at is not None:
            return (False, "Este código de recuperação já foi utilizado.")

        if datetime.now() > expires_at:
            return (False, "Este código de recuperação expirou.")

        # Atualiza a senha
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        sql_update_password = "UPDATE USERS SET PASSWORD_HASH = ? WHERE ID = ?;"
        cur.execute(sql_update_password, (hashed_password.decode('utf-8'), user_id))

        # Invalida o código
        sql_invalidate_code = "UPDATE PASSWORD_RESET SET USED_AT = CURRENT_TIMESTAMP WHERE USER_ID = ? AND VERIFICATION_CODE = ?;"
        cur.execute(sql_invalidate_code, (user_id, reset_code))

        conn.commit()

        return (True, "Senha atualizada com sucesso.")

    except fdb.Error as e:
        if conn: conn.rollback()
        return (False, "Ocorreu um erro interno. Tente novamente mais tarde.")
    finally:
        if conn: conn.close()

def reactivate_user(user_id):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        sql_check = "SELECT 1 FROM USERS WHERE ID = ?;"
        cur.execute(sql_check, (user_id,))
        if not cur.fetchone():
            return False 

        sql_update = "UPDATE USERS SET IS_ACTIVE = TRUE WHERE ID = ?;"
        cur.execute(sql_update, (user_id,))
        conn.commit()

        return True
        
    except fdb.Error as e:
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

def change_user_password(user_id, current_password, new_password):
    """
    Altera a senha de um usuário autenticado.
    Valida a senha atual e aplica regras de segurança para a nova senha.
    Retorna uma tupla: (sucesso, error_code, mensagem).
    """
    if not current_password or not new_password:
        return (False, "MISSING_PASSWORDS", "Senha atual e nova senha são obrigatórias")
    
    if current_password == new_password:
        return (False, "SAME_PASSWORD", "A nova senha deve ser diferente da senha atual")
    
    is_strong, message = validators.is_strong_password(new_password)
    if not is_strong:
        return (False, "WEAK_PASSWORD", message)
    
    if not verify_user_password(user_id, current_password):
        return (False, "INVALID_CURRENT_PASSWORD", "Senha atual incorreta")
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        sql_update = "UPDATE USERS SET PASSWORD_HASH = ? WHERE ID = ? AND IS_ACTIVE = TRUE"
        cur.execute(sql_update, (hashed_password.decode('utf-8'), user_id))
        
        if cur.rowcount == 0:
            return (False, "USER_NOT_FOUND", "Usuário não encontrado")
        
        conn.commit()
        # Revoga todos os tokens do usuário (logout global)
        try:
            auth_service.revoke_all_tokens_for_user(user_id)
        except Exception as e:
            # ALTERAÇÃO: Logging estruturado ao invés de silenciar completamente
            # Falha na revogação não impede alteração de senha, mas deve ser registrada
            logger.warning(f"Falha ao revogar tokens do usuário {user_id} após alteração de senha: {e}", exc_info=True)
        return (True, None, "Senha alterada com sucesso. Você será desconectado em todos os dispositivos.")

    except fdb.Error as e:
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()

def get_user_metrics(user_id):
    """Retorna as métricas de performance de um funcionário específico."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT ROLE FROM USERS WHERE ID = ? AND IS_ACTIVE = TRUE", (user_id,))
        user_row = cur.fetchone()
        if not user_row:
            return None
        
        user_role = user_row[0]
        if user_role not in ['attendant', 'manager', 'admin']:
            return None
        
        cur.execute("""
            SELECT COUNT(*) as total_orders,
                   SUM(TOTAL_AMOUNT) as total_revenue
            FROM ORDERS 
            WHERE ATTENDANT_ID = ? AND STATUS = 'delivered'
        """, (user_id,))
        
        order_stats = cur.fetchone()
        total_orders = order_stats[0] if order_stats and order_stats[0] else 0
        total_revenue = float(order_stats[1]) if order_stats and order_stats[1] else 0.0
        
        # CORREÇÃO: Firebird não suporta EPOCH, usar DATEDIFF(SECOND, ...) e dividir por 60
        cur.execute("""
            SELECT CAST(COALESCE(AVG(DATEDIFF(SECOND, CREATED_AT, UPDATED_AT) / 60.0), 0) AS NUMERIC(18,2)) as avg_service_time
            FROM ORDERS 
            WHERE ATTENDANT_ID = ? AND STATUS = 'delivered' AND UPDATED_AT IS NOT NULL
        """, (user_id,))
        
        avg_service_time = cur.fetchone()
        avg_service_time = round(float(avg_service_time[0]), 1) if avg_service_time and avg_service_time[0] else 0.0
        
        cur.execute("""
            SELECT COUNT(*) 
            FROM ORDERS 
            WHERE ATTENDANT_ID = ? AND STATUS IN ('pending', 'confirmed', 'preparing', 'ready', 'out_for_delivery')
        """, (user_id,))
        
        ongoing_result = cur.fetchone()
        ongoing_orders = ongoing_result[0] if ongoing_result and ongoing_result[0] else 0
        
        average_rating = 0.0
        
        return {
            "user_id": user_id,
            "role": user_role,
            "total_completed_orders": total_orders,
            "total_revenue": total_revenue,
            "average_service_time_minutes": avg_service_time,
            "ongoing_orders": ongoing_orders,
            "average_rating": average_rating
        }
        
    except fdb.Error as e:
        return None
    finally:
        if conn: conn.close()

def is_last_active_admin(user_id):
    """Verifica se o usuário é o último administrador ativo no sistema."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se o usuário é admin
        cur.execute("SELECT ROLE FROM USERS WHERE ID = ? AND IS_ACTIVE = TRUE", (user_id,))
        user_row = cur.fetchone()
        if not user_row or user_row[0] != 'admin':
            return False
        
        # Conta quantos admins ativos existem
        cur.execute("SELECT COUNT(*) FROM USERS WHERE ROLE = 'admin' AND IS_ACTIVE = TRUE")
        admin_count = cur.fetchone()[0]
        
        return admin_count == 1
        
    except fdb.Error as e:
        return False
    finally:
        if conn: conn.close()

def get_users_paginated(page=1, per_page=20, filters=None, sort_by='full_name', sort_order='asc'):
    """Busca usuários com paginação, filtros e ordenação."""
    # OTIMIZAÇÃO: Usar validador centralizado de paginação
    from ..utils.validators import validate_pagination_params
    try:
        page, per_page, offset = validate_pagination_params(page, per_page, max_page_size=100)
    except ValueError:
        page, per_page, offset = 1, 20, 0
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Query base
        base_sql = """
            SELECT ID, FULL_NAME, EMAIL, PHONE, CPF, ROLE, IS_ACTIVE, 
                   CREATED_AT, IS_EMAIL_VERIFIED, TWO_FACTOR_ENABLED
            FROM USERS 
            WHERE 1=1
        """
        
        # Filtros
        conditions = []
        params = []
        
        if filters:
            if filters.get('name'):
                conditions.append("UPPER(FULL_NAME) LIKE UPPER(?)")
                params.append(f"%{filters['name']}%")
            
            if filters.get('email'):
                conditions.append("UPPER(EMAIL) LIKE UPPER(?)")
                params.append(f"%{filters['email']}%")
            
            if filters.get('search'):
                # ALTERAÇÃO: Busca geral em nome, email e telefone - melhorar tratamento de valores None
                search_term = filters['search']
                if search_term and str(search_term).strip():
                    search_term = f"%{str(search_term).strip()}%"
                    conditions.append("(UPPER(FULL_NAME) LIKE UPPER(?) OR UPPER(EMAIL) LIKE UPPER(?) OR UPPER(PHONE) LIKE UPPER(?))")
                    params.extend([search_term, search_term, search_term])
            
            if filters.get('role'):
                if isinstance(filters['role'], list):
                    placeholders = ', '.join(['?' for _ in filters['role']])
                    conditions.append(f"ROLE IN ({placeholders})")
                    params.extend(filters['role'])
                else:
                    conditions.append("ROLE = ?")
                    params.append(filters['role'])
            
            if filters.get('status') is not None:
                conditions.append("IS_ACTIVE = ?")
                params.append(bool(filters['status']))
            
            # OTIMIZAÇÃO: Converter datas para range queries (substitui DATE() por range para usar índices)
            if filters.get('created_after'):
                created_after = filters['created_after']
                if isinstance(created_after, str):
                    from datetime import datetime as dt
                    try:
                        created_after = dt.strptime(created_after, '%Y-%m-%d').date()
                    except (ValueError, TypeError) as e:
                        # ALTERAÇÃO: Especificar exceções esperadas ao invés de catch-all genérico
                        logger.debug(f"Erro ao converter created_after '{created_after}': {e}")
                        pass
                if isinstance(created_after, date) and not isinstance(created_after, datetime):
                    from datetime import datetime
                    created_after = datetime.combine(created_after, datetime.min.time())
                conditions.append("CREATED_AT >= ?")
                params.append(created_after)
            
            if filters.get('created_before'):
                created_before = filters['created_before']
                if isinstance(created_before, str):
                    from datetime import datetime as dt
                    try:
                        created_before = dt.strptime(created_before, '%Y-%m-%d').date()
                    except (ValueError, TypeError) as e:
                        # ALTERAÇÃO: Especificar exceções esperadas ao invés de catch-all genérico
                        logger.debug(f"Erro ao converter created_before '{created_before}': {e}")
                        pass
                if isinstance(created_before, date) and not isinstance(created_before, datetime):
                    from datetime import datetime, timedelta
                    created_before = datetime.combine(created_before + timedelta(days=1), datetime.min.time())
                conditions.append("CREATED_AT < ?")
                params.append(created_before)
        
        if conditions:
            base_sql += " AND " + " AND ".join(conditions)
        
        # ALTERAÇÃO: Contagem total ANTES de adicionar ORDER BY e ROWS
        # Construir query de contagem de forma explícita para evitar problemas com replace
        count_sql = "SELECT COUNT(*) FROM USERS WHERE 1=1"
        if conditions:
            count_sql += " AND " + " AND ".join(conditions)
        
        try:
            cur.execute(count_sql, params)
            count_result = cur.fetchone()
            # ALTERAÇÃO: Tratamento seguro para evitar erro quando fetchone() retorna None
            if count_result and len(count_result) > 0:
                total = count_result[0] if count_result[0] is not None else 0
            else:
                logger.warning(f"Query de contagem retornou resultado vazio. SQL: {count_sql[:200]}... Params: {params}")
                total = 0
        except Exception as count_error:
            logger.error(f"Erro ao executar query de contagem: {count_error}. SQL: {count_sql[:200]}... Params: {params}", exc_info=True)
            total = 0
        
        # Ordenação
        valid_sort_fields = ['full_name', 'email', 'role', 'created_at', 'is_active']
        if sort_by not in valid_sort_fields:
            sort_by = 'full_name'
        
        sort_order = 'ASC' if sort_order.lower() == 'asc' else 'DESC'
        base_sql += f" ORDER BY {sort_by} {sort_order}"
        
        # Paginação
        offset = (page - 1) * per_page
        base_sql += f" ROWS {offset + 1} TO {offset + per_page}"
        
        cur.execute(base_sql, params)
        users = []
        
        for row in cur.fetchall():
            users.append({
                "id": row[0],
                "full_name": row[1],
                "email": row[2],
                "phone": row[3],
                "cpf": row[4],
                "role": row[5],
                "is_active": bool(row[6]) if row[6] is not None else True,
                "created_at": row[7].strftime('%Y-%m-%d %H:%M:%S') if row[7] else None,
                "is_email_verified": bool(row[8]) if row[8] is not None else False,
                "two_factor_enabled": bool(row[9]) if row[9] is not None else False,
            })
        
        # ALTERAÇÃO: Retornar formato padronizado com total_pages, current_page, next, previous
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        
        return {
            "users": users,
            "pagination": {
                "total": total,
                "total_pages": total_pages,
                "current_page": page,
                "page_size": per_page,
                "per_page": per_page,  # Manter para compatibilidade
                "next": page + 1 if page < total_pages else None,
                "previous": page - 1 if page > 1 else None,
                "pages": total_pages  # Manter para compatibilidade
            }
        }
        
    except fdb.Error as e:
        logger.error(f"Erro ao buscar usuários paginados: {e}", exc_info=True)
        return {
            "users": [], 
            "pagination": {
                "total": 0,
                "total_pages": 1,
                "current_page": page,
                "page_size": per_page,
                "per_page": per_page,
                "next": None,
                "previous": None,
                "pages": 0
            }
        }
    finally:
        if conn: conn.close()

def get_customers_paginated(page=1, per_page=20, filters=None, sort_by='full_name', sort_order='asc'):
    """Busca clientes com paginação, filtros e ordenação."""
    # OTIMIZAÇÃO: Usar validador centralizado de paginação
    from ..utils.validators import validate_pagination_params
    try:
        page, per_page, offset = validate_pagination_params(page, per_page, max_page_size=100)
    except ValueError:
        page, per_page, offset = 1, 20, 0
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Query base
        base_sql = """
            SELECT ID, FULL_NAME, EMAIL, PHONE, CPF, DATE_OF_BIRTH, IS_ACTIVE, 
                   CREATED_AT, IS_EMAIL_VERIFIED, TWO_FACTOR_ENABLED
            FROM USERS 
            WHERE ROLE = 'customer'
        """
        
        # Filtros
        conditions = []
        params = []
        
        if filters:
            if filters.get('name'):
                conditions.append("UPPER(FULL_NAME) LIKE UPPER(?)")
                params.append(f"%{filters['name']}%")
            
            if filters.get('email'):
                conditions.append("UPPER(EMAIL) LIKE UPPER(?)")
                params.append(f"%{filters['email']}%")
            
            if filters.get('cpf'):
                conditions.append("CPF LIKE ?")
                params.append(f"%{filters['cpf']}%")
            
            if filters.get('status') is not None:
                conditions.append("IS_ACTIVE = ?")
                params.append(bool(filters['status']))
        
        if conditions:
            base_sql += " AND " + " AND ".join(conditions)
        
        # ALTERAÇÃO: Contagem total ANTES de adicionar ORDER BY e ROWS
        # Construir query de contagem de forma explícita para evitar problemas com replace
        count_sql = "SELECT COUNT(*) FROM USERS WHERE ROLE = 'customer'"
        if conditions:
            count_sql += " AND " + " AND ".join(conditions)
        
        try:
            cur.execute(count_sql, params)
            count_result = cur.fetchone()
            # ALTERAÇÃO: Tratamento seguro para evitar erro quando fetchone() retorna None
            if count_result and len(count_result) > 0:
                total = count_result[0] if count_result[0] is not None else 0
            else:
                logger.warning(f"Query de contagem de clientes retornou resultado vazio. SQL: {count_sql[:200]}... Params: {params}")
                total = 0
        except Exception as count_error:
            logger.error(f"Erro ao executar query de contagem de clientes: {count_error}. SQL: {count_sql[:200]}... Params: {params}", exc_info=True)
            total = 0
        
        # Ordenação
        valid_sort_fields = ['full_name', 'email', 'cpf', 'created_at', 'is_active']
        if sort_by not in valid_sort_fields:
            sort_by = 'full_name'
        
        sort_order = 'ASC' if sort_order.lower() == 'asc' else 'DESC'
        base_sql += f" ORDER BY {sort_by} {sort_order}"
        
        # Paginação (offset já calculado pelo validate_pagination_params)
        base_sql += f" ROWS {offset + 1} TO {offset + per_page}"
        
        cur.execute(base_sql, params)
        customers = []
        
        for row in cur.fetchall():
            customers.append({
                "id": row[0],
                "full_name": row[1],
                "email": row[2],
                "phone": row[3],
                "cpf": row[4],
                "date_of_birth": row[5].strftime('%Y-%m-%d') if row[5] else None,
                "is_active": bool(row[6]) if row[6] is not None else True,
                "created_at": row[7].strftime('%Y-%m-%d %H:%M:%S') if row[7] else None,
                "is_email_verified": bool(row[8]) if row[8] is not None else False,
                "two_factor_enabled": bool(row[9]) if row[9] is not None else False,
            })
        
        return {
            "customers": customers,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page
            }
        }
        
    except fdb.Error as e:
        logger.error(f"Erro ao buscar clientes paginados: {e}", exc_info=True)
        return {"customers": [], "pagination": {"page": page, "per_page": per_page, "total": 0, "pages": 0}}
    finally:
        if conn: conn.close()

def get_users_general_metrics():
    """Retorna métricas gerais de usuários."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Total de usuários
        cur.execute("SELECT COUNT(*) FROM USERS")
        total = cur.fetchone()[0] or 0
        
        # Usuários ativos
        cur.execute("SELECT COUNT(*) FROM USERS WHERE IS_ACTIVE = TRUE")
        ativos = cur.fetchone()[0] or 0
        
        # Usuários inativos
        inativos = total - ativos
        
        # Contagem por cargo
        cur.execute("""
            SELECT ROLE, COUNT(*) 
            FROM USERS 
            WHERE IS_ACTIVE = TRUE 
            GROUP BY ROLE
        """)
        roles_count = {}
        for row in cur.fetchall():
            roles_count[row[0]] = row[1]
        
        # Funcionários vs Clientes
        funcionarios = sum(roles_count.get(role, 0) for role in ['admin', 'manager', 'attendant', 'delivery'])
        clientes = roles_count.get('customer', 0)
        
        return {
            "total": total,
            "ativos": ativos,
            "inativos": inativos,
            "cargos": roles_count,
            "funcionarios": funcionarios,
            "clientes": clientes
        }
        
    except fdb.Error as e:
        return {
            "total": 0,
            "ativos": 0,
            "inativos": 0,
            "cargos": {},
            "funcionarios": 0,
            "clientes": 0
        }
    finally:
        if conn: conn.close()

def check_email_availability(email):
    """Verifica se um email está disponível (considerando apenas emails verificados)."""
    conn = None
    try:
        # Normaliza o email para minúsculas
        email = email.lower().strip()
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM USERS WHERE EMAIL = ? AND IS_EMAIL_VERIFIED = TRUE", (email,))
        count = cur.fetchone()[0]
        return count == 0
    except fdb.Error as e:
        return False
    finally:
        if conn: conn.close()

def cleanup_unverified_accounts(days_old=7):
    """
    Remove contas não verificadas que são mais antigas que o número de dias especificado.
    Útil para limpeza de contas criadas mas nunca verificadas.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Remove contas não verificadas criadas há mais de X dias
        sql_cleanup = """
            DELETE FROM USERS 
            WHERE IS_EMAIL_VERIFIED = FALSE 
            AND CREATED_AT < DATEADD(DAY, -?, CURRENT_DATE)
        """
        cur.execute(sql_cleanup, (days_old,))
        deleted_count = cur.rowcount
        
        conn.commit()
        
        return deleted_count
        
    except fdb.Error as e:
        if conn: conn.rollback()
        return 0
    finally:
        if conn: conn.close()

def update_user_status(user_id, is_active):
    """Ativa ou desativa um usuário."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se está tentando desativar o último admin ativo
        if not is_active and is_last_active_admin(user_id):
            return (False, "CANNOT_DEACTIVATE_LAST_ADMIN", "Não é possível desativar o último administrador ativo do sistema")
        
        cur.execute("UPDATE USERS SET IS_ACTIVE = ? WHERE ID = ?", (is_active, user_id))
        
        if cur.rowcount > 0:
            conn.commit()
            return (True, None, "Status do usuário atualizado com sucesso")
        else:
            return (False, "USER_NOT_FOUND", "Usuário não encontrado")
            
    except fdb.Error as e:
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()

def update_user_role(user_id, new_role):
    """Atualiza o cargo/role de um usuário."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se está tentando alterar o role do último admin ativo
        if new_role != 'admin' and is_last_active_admin(user_id):
            return (False, "CANNOT_CHANGE_LAST_ADMIN_ROLE", "Não é possível alterar o cargo do último administrador ativo do sistema")
        
        cur.execute("UPDATE USERS SET ROLE = ? WHERE ID = ?", (new_role, user_id))
        conn.commit()
        
        if cur.rowcount > 0:
            return (True, None, "Cargo do usuário atualizado com sucesso")
        else:
            return (False, "USER_NOT_FOUND", "Usuário não encontrado")
            
    except fdb.Error as e:
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()
