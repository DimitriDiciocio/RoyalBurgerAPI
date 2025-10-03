import fdb  
import bcrypt  
from datetime import datetime, timedelta  
from . import email_service
from . import loyalty_service
from ..database import get_db_connection  
from ..utils import token_helper  
from ..utils import validators  

def convert_date_format(date_string):
    """
    Converte data do formato DD-MM-YYYY (frontend) para YYYY-MM-DD (Firebird).
    Retorna a data convertida ou None se inválida.
    """
    if not date_string:
        return None
    
    try:
        if len(date_string) == 10 and date_string.count('-') == 2:
            day, month, year = date_string.split('-')
            if len(day) == 2 and len(month) == 2 and len(year) == 4:
                return f"{year}-{month}-{day}"
    except:
        pass
    
    return date_string

def create_user(user_data):
    full_name = user_data.get('full_name')
    email = user_data.get('email')
    password = user_data.get('password')
    phone = user_data.get('phone')
    cpf = user_data.get('cpf')
    date_of_birth = convert_date_format(user_data.get('date_of_birth'))
    
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
        
        sql_check_email = "SELECT ID FROM USERS WHERE EMAIL = ?;"
        cur.execute(sql_check_email, (email,))
        if cur.fetchone():
            return (None, "EMAIL_ALREADY_EXISTS", "Este e-mail já está em uso por outra conta.")

        if phone:
            sql_check_phone = "SELECT ID FROM USERS WHERE PHONE = ?;"
            cur.execute(sql_check_phone, (phone,))
            if cur.fetchone():
                return (None, "PHONE_ALREADY_EXISTS", "Este telefone já está em uso por outra conta.")

        if cpf:
            sql_check_cpf = "SELECT ID FROM USERS WHERE CPF = ?;"
            cur.execute(sql_check_cpf, (cpf,))
            if cur.fetchone():
                return (None, "CPF_ALREADY_EXISTS", "Este CPF já está em uso por outra conta.")

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
                print(f"Pontos de boas-vindas adicionados para o cliente {new_user_id}")
            except Exception as e:
                print(f"AVISO: Falha ao adicionar pontos de boas-vindas para o cliente {new_user_id}. Erro: {e}")
        
        # Commit de tudo junto (usuário + pontos)
        conn.commit()

        new_user = {
            "id": new_user_id,
            "full_name": full_name,
            "email": email,
            "role": role,
            "date_of_birth": date_of_birth,
            "phone": phone,
            "cpf": cpf
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
                print(f"AVISO: Falha ao enviar e-mail de boas-vindas para {new_user['email']}. Erro: {e}")

        return (new_user, None, None)
    except fdb.Error as e:
        print(f"Erro ao criar usuário: {e}")
        if conn: conn.rollback()
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
        print(f"Erro ao verificar senha do usuário: {e}")
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
        print(f"Erro ao buscar usuários por papel: {e}")
        return []
    finally:
        if conn: conn.close()

def get_user_by_id(user_id):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = (
            "SELECT ID, FULL_NAME, EMAIL, PHONE, CPF, ROLE, DATE_OF_BIRTH, IS_ACTIVE, CREATED_AT, "
            "IS_EMAIL_VERIFIED, TWO_FACTOR_ENABLED "
            "FROM USERS WHERE ID = ? AND IS_ACTIVE = TRUE;"
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
            }
        return None
    except fdb.Error as e:
        print(f"Erro ao buscar usuário por ID: {e}")
        return None
    finally:
        if conn: conn.close()

def get_user_by_email(email):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        sql = "SELECT ID, FULL_NAME, EMAIL, PHONE, CPF, ROLE FROM USERS WHERE EMAIL = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql, (email,))
        row = cur.fetchone()
        if row:
            return {"id": row[0], "full_name": row[1], "email": row[2], "phone": row[3], "cpf": row[4], "role": row[5]}
        return None
    except fdb.Error as e:
        print(f"Erro ao buscar usuário por e-mail: {e}")
        return None
    finally:
        if conn: conn.close()

def update_user(user_id, update_data):
    """
    Atualiza dados de um usuário com validações específicas para cada campo.
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

        if 'email' in update_data:
            new_email = update_data['email']
            
            is_valid, message = validators.is_valid_email(new_email)
            if not is_valid:
                return (False, "INVALID_EMAIL", message)
            
            sql_check_email = "SELECT ID FROM USERS WHERE EMAIL = ? AND ID <> ?;"
            cur.execute(sql_check_email, (new_email, user_id))
            if cur.fetchone():
                return (False, "EMAIL_ALREADY_EXISTS", "Este e-mail já está em uso por outra conta.")

        if 'phone' in update_data:
            new_phone = update_data['phone']
            if new_phone:
                is_valid, message = validators.is_valid_phone(new_phone)
                if not is_valid:
                    return (False, "INVALID_PHONE", message)
                
                sql_check_phone = "SELECT ID FROM USERS WHERE PHONE = ? AND ID <> ?;"
                cur.execute(sql_check_phone, (new_phone, user_id))
                if cur.fetchone():
                    return (False, "PHONE_ALREADY_EXISTS", "Este telefone já está em uso por outra conta.")

        if 'cpf' in update_data:
            new_cpf = update_data['cpf']
            if new_cpf and not validators.is_valid_cpf(new_cpf):
                return (False, "INVALID_CPF", "O CPF fornecido é inválido.")

        allowed_fields = ['full_name', 'date_of_birth', 'phone', 'cpf', 'email']
        fields_to_update = {k: v for k, v in update_data.items() if k in allowed_fields}

        if not fields_to_update:
            return (False, "NO_VALID_FIELDS", "Nenhum campo válido para atualização foi fornecido.")

        set_parts = [f"{key} = ?" for key in fields_to_update]
        values = list(fields_to_update.values())
        values.append(user_id)

        sql_update = f"UPDATE USERS SET {', '.join(set_parts)} WHERE ID = ?;"
        cur.execute(sql_update, tuple(values))
        conn.commit()

        return (True, None, "Dados atualizados com sucesso.")

    except fdb.Error as e:
        print(f"Erro ao atualizar usuário: {e}")
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
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        sql_find_user = "SELECT ID, FULL_NAME FROM USERS WHERE EMAIL = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql_find_user, (email,))
        user_record = cur.fetchone()

        if user_record:
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
                print(f"Erro ao enviar e-mail de recuperação: {e}")

        return True

    except fdb.Error as e:
        print(f"Erro no banco de dados ao iniciar a recuperação de senha: {e}")
        if conn: conn.rollback()
        
        return False
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
        print(f"Erro no banco de dados ao finalizar a recuperação de senha: {e}")
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
        print(f"Erro ao reativar usuário: {e}")
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
        return (True, None, "Senha alterada com sucesso")
        
    except fdb.Error as e:
        print(f"Erro ao alterar senha: {e}")
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
        
        cur.execute("""
            SELECT AVG(EXTRACT(EPOCH FROM (UPDATED_AT - CREATED_AT))/60) as avg_service_time
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
        print(f"Erro ao buscar métricas do usuário: {e}")
        return None
    finally:
        if conn: conn.close()