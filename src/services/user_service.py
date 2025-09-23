import fdb  # importa driver do Firebird
import bcrypt  # importa biblioteca de hash de senhas
from datetime import datetime, timedelta  # importa classes de data e tempo
from . import email_service  # importa serviço de e-mail
from ..database import get_db_connection  # importa função de conexão com banco
from ..utils import token_helper  # importa utilitários de token
from ..utils import validators  # importa validadores

def convert_date_format(date_string):  # função para converter formato de data
    if not date_string:  # verifica se string não está vazia
        return None  # retorna None se vazia
    try:  # tenta conversão
        if len(date_string) == 10 and date_string.count('-') == 2:  # valida formato DD-MM-YYYY
            day, month, year = date_string.split('-')  # separa componentes da data
            if len(day) == 2 and len(month) == 2 and len(year) == 4:  # valida tamanhos
                return f"{year}-{month}-{day}"  # retorna formato YYYY-MM-DD
    except:  # captura qualquer erro
        pass  # ignora erro
    return date_string  # retorna string original se inválida


def create_user(user_data):  # função para criar novo usuário
    full_name = user_data.get('full_name')  # extrai nome completo dos dados
    email = user_data.get('email')  # extrai e-mail dos dados
    password = user_data.get('password')  # extrai senha dos dados
    phone = user_data.get('phone')  # extrai telefone dos dados
    cpf = user_data.get('cpf')  # extrai CPF dos dados
    date_of_birth = convert_date_format(user_data.get('date_of_birth'))  # converte formato da data

    is_valid, message = validators.is_valid_email(email)  # valida formato do e-mail
    if not is_valid:  # se e-mail inválido
        return (None, "INVALID_EMAIL", message)  # retorna erro de e-mail inválido

    if date_of_birth:  # se data de nascimento fornecida
        try:  # tenta validar data
            datetime.strptime(date_of_birth, '%Y-%m-%d')  # valida formato da data
            birth_date = datetime.strptime(date_of_birth, '%Y-%m-%d')  # converte para datetime
            today = datetime.now()  # obtém data atual
            age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))  # calcula idade
            if age < 18:  # se menor de 18 anos
                return (None, "INVALID_DATE", "Você deve ter pelo menos 18 anos para se cadastrar.")  # retorna erro de idade
            if age > 120:  # se idade inválida
                return (None, "INVALID_DATE", "Data de nascimento inválida.")  # retorna erro de data
        except ValueError:  # captura erro de formato
            return (None, "INVALID_DATE", "Formato de data inválido. Use DD-MM-AAAA.")  # retorna erro de formato

    if phone:  # se telefone fornecido
        is_valid, message = validators.is_valid_phone(phone)  # valida formato do telefone
        if not is_valid:  # se telefone inválido
            return (None, "INVALID_PHONE", message)  # retorna erro de telefone inválido

    if cpf:  # se CPF fornecido
        if not validators.is_valid_cpf(cpf):  # valida CPF
            return (None, "INVALID_CPF", "O CPF fornecido é inválido.")  # retorna erro de CPF inválido

    is_strong, message = validators.is_strong_password(password)  # valida força da senha
    if not is_strong:  # se senha fraca
        return (None, "WEAK_PASSWORD", message)  # retorna erro de senha fraca

    role = user_data.get('role', 'customer')  # obtém papel do usuário ou define como cliente
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())  # gera hash da senha

    conn = None  # inicializa variável de conexão
    try:  # tenta operação no banco
        conn = get_db_connection()  # estabelece conexão com banco
        cur = conn.cursor()  # cria cursor para execução de queries

        sql_check_email = "SELECT ID FROM USERS WHERE EMAIL = ?;"  # query para verificar e-mail existente
        cur.execute(sql_check_email, (email,))  # executa verificação de e-mail
        if cur.fetchone():  # se e-mail já existe
            return (None, "EMAIL_ALREADY_EXISTS", "Este e-mail já está em uso por outra conta.")  # retorna erro de e-mail duplicado

        if phone:  # se telefone fornecido
            sql_check_phone = "SELECT ID FROM USERS WHERE PHONE = ?;"  # query para verificar telefone existente
            cur.execute(sql_check_phone, (phone,))  # executa verificação de telefone
            if cur.fetchone():  # se telefone já existe
                return (None, "PHONE_ALREADY_EXISTS", "Este telefone já está em uso por outra conta.")  # retorna erro de telefone duplicado

        if cpf:  # se CPF fornecido
            sql_check_cpf = "SELECT ID FROM USERS WHERE CPF = ?;"  # query para verificar CPF existente
            cur.execute(sql_check_cpf, (cpf,))  # executa verificação de CPF
            if cur.fetchone():  # se CPF já existe
                return (None, "CPF_ALREADY_EXISTS", "Este CPF já está em uso por outra conta.")  # retorna erro de CPF duplicado

        sql = """  # query para inserir novo usuário
            INSERT INTO USERS (FULL_NAME, EMAIL, PASSWORD_HASH, ROLE, DATE_OF_BIRTH, PHONE, CPF) 
            VALUES (?, ?, ?, ?, ?, ?, ?) 
            RETURNING ID;
        """
        cur.execute(sql, (full_name, email, hashed_password.decode('utf-8'), role, date_of_birth, phone, cpf))  # executa inserção
        new_user_id = cur.fetchone()[0]  # obtém ID do usuário criado
        conn.commit()  # confirma transação

        new_user = {  # cria dicionário com dados do usuário
            "id": new_user_id,  # ID do usuário
            "full_name": full_name,  # nome completo
            "email": email,  # e-mail
            "role": role,  # papel
            "date_of_birth": date_of_birth,  # data de nascimento
            "phone": phone,  # telefone
            "cpf": cpf  # CPF
        }

        if role == 'customer':  # se for cliente
            try:  # tenta enviar e-mail de boas-vindas
                email_service.send_email(  # chama serviço de e-mail
                    to=new_user['email'],  # destinatário
                    subject='Bem-vindo ao Royal Burger!',  # assunto
                    template='welcome',  # template
                    user=new_user  # dados do usuário
                )
            except Exception as e:  # captura erro no envio
                print(f"AVISO: Falha ao enviar e-mail de boas-vindas para {new_user['email']}. Erro: {e}")  # log do erro

        return (new_user, None, None)  # retorna sucesso com dados do usuário
    except fdb.Error as e:  # captura erro do banco
        print(f"Erro ao criar usuário: {e}")  # log do erro
        if conn: conn.rollback()  # desfaz transação
        return (None, "DATABASE_ERROR", "Erro interno do servidor")  # retorna erro de banco
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão


def verify_user_password(user_id, password):  # função para verificar senha do usuário
    conn = None  # inicializa variável de conexão
    try:  # tenta operação no banco
        conn = get_db_connection()  # estabelece conexão com banco
        cur = conn.cursor()  # cria cursor para execução de queries

        sql = "SELECT PASSWORD_HASH FROM USERS WHERE ID = ?;"  # query para buscar hash da senha
        cur.execute(sql, (user_id,))  # executa busca do hash
        row = cur.fetchone()  # obtém resultado da query

        if not row:  # se usuário não encontrado
            return False  # retorna falso

        stored_hash = row[0]  # extrai hash armazenado
        if not stored_hash:  # se hash não existe
            return False  # retorna falso

        return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))  # verifica senha com hash
    except fdb.Error as e:  # captura erro do banco
        print(f"Erro ao verificar senha do usuário: {e}")  # log do erro
        return False  # retorna falso em caso de erro
    finally:  # sempre executa
        if conn:  # se conexão existe
            conn.close()  # fecha conexão


def get_users_by_role(roles):  # função para buscar usuários por papel
    if isinstance(roles, str):  # se roles é string
        roles = [roles]  # converte para lista
    
    conn = None  # inicializa variável de conexão
    try:  # tenta operação no banco
        conn = get_db_connection()  # estabelece conexão com banco
        cur = conn.cursor()  # cria cursor para execução de queries
        placeholders = ', '.join(['?' for _ in roles])  # cria placeholders para query
        sql = f"SELECT ID, FULL_NAME, EMAIL, PHONE, CPF, ROLE FROM USERS WHERE ROLE IN ({placeholders}) AND IS_ACTIVE = TRUE ORDER BY FULL_NAME;"  # query para buscar usuários
        cur.execute(sql, tuple(roles))  # executa busca com parâmetros
        users = [{"id": row[0], "full_name": row[1], "email": row[2], "phone": row[3], "cpf": row[4], "role": row[5]} for row in cur.fetchall()]  # converte resultados para dicionários
        return users  # retorna lista de usuários
    except fdb.Error as e:  # captura erro do banco
        print(f"Erro ao buscar usuários por papel: {e}")  # log do erro
        return []  # retorna lista vazia em caso de erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def get_user_by_id(user_id):  # função para buscar usuário por ID
    conn = None  # inicializa variável de conexão
    try:  # tenta operação no banco
        conn = get_db_connection()  # estabelece conexão com banco
        cur = conn.cursor()  # cria cursor para execução de queries
        sql = "SELECT ID, FULL_NAME, EMAIL, PHONE, CPF, ROLE FROM USERS WHERE ID = ? AND IS_ACTIVE = TRUE;"  # query para buscar usuário
        cur.execute(sql, (user_id,))  # executa busca com ID
        row = cur.fetchone()  # obtém resultado da query
        if row:  # se usuário encontrado
            return {"id": row[0], "full_name": row[1], "email": row[2], "phone": row[3], "cpf": row[4], "role": row[5]}  # retorna dados do usuário
        return None  # retorna None se não encontrado
    except fdb.Error as e:  # captura erro do banco
        print(f"Erro ao buscar usuário por ID: {e}")  # log do erro
        return None  # retorna None em caso de erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão


def get_user_by_email(email):  # função para buscar usuário por e-mail
    conn = None  # inicializa variável de conexão
    try:  # tenta operação no banco
        conn = get_db_connection()  # estabelece conexão com banco
        cur = conn.cursor()  # cria cursor para execução de queries
        sql = "SELECT ID, FULL_NAME, EMAIL, PHONE, CPF, ROLE FROM USERS WHERE EMAIL = ? AND IS_ACTIVE = TRUE;"  # query para buscar usuário
        cur.execute(sql, (email,))  # executa busca com e-mail
        row = cur.fetchone()  # obtém resultado da query
        if row:  # se usuário encontrado
            return {"id": row[0], "full_name": row[1], "email": row[2], "phone": row[3], "cpf": row[4], "role": row[5]}  # retorna dados do usuário
        return None  # retorna None se não encontrado
    except fdb.Error as e:  # captura erro do banco
        print(f"Erro ao buscar usuário por e-mail: {e}")  # log do erro
        return None  # retorna None em caso de erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão


def update_user(user_id, update_data):  # função para atualizar dados do usuário
    conn = None  # inicializa variável de conexão
    try:  # tenta operação no banco
        conn = get_db_connection()  # estabelece conexão com banco
        cur = conn.cursor()  # cria cursor para execução de queries

        sql_check_exists = "SELECT 1 FROM USERS WHERE ID = ? AND IS_ACTIVE = TRUE;"  # query para verificar existência
        cur.execute(sql_check_exists, (user_id,))  # executa verificação de existência
        if not cur.fetchone():  # se usuário não encontrado
            return (False, "USER_NOT_FOUND", "Usuário não encontrado.")  # retorna erro de usuário não encontrado

        if 'email' in update_data:  # se e-mail está sendo atualizado
            new_email = update_data['email']  # extrai novo e-mail
            is_valid, message = validators.is_valid_email(new_email)  # valida formato do e-mail
            if not is_valid:  # se e-mail inválido
                return (False, "INVALID_EMAIL", message)  # retorna erro de e-mail inválido
            
            sql_check_email = "SELECT ID FROM USERS WHERE EMAIL = ? AND ID <> ?;"  # query para verificar e-mail duplicado
            cur.execute(sql_check_email, (new_email, user_id))  # executa verificação de e-mail duplicado
            if cur.fetchone():  # se e-mail já existe
                return (False, "EMAIL_ALREADY_EXISTS", "Este e-mail já está em uso por outra conta.")  # retorna erro de e-mail duplicado

        if 'phone' in update_data:  # se telefone está sendo atualizado
            new_phone = update_data['phone']  # extrai novo telefone
            if new_phone:  # se telefone fornecido
                is_valid, message = validators.is_valid_phone(new_phone)  # valida formato do telefone
                if not is_valid:  # se telefone inválido
                    return (False, "INVALID_PHONE", message)  # retorna erro de telefone inválido
                
                sql_check_phone = "SELECT ID FROM USERS WHERE PHONE = ? AND ID <> ?;"  # query para verificar telefone duplicado
                cur.execute(sql_check_phone, (new_phone, user_id))  # executa verificação de telefone duplicado
                if cur.fetchone():  # se telefone já existe
                    return (False, "PHONE_ALREADY_EXISTS", "Este telefone já está em uso por outra conta.")  # retorna erro de telefone duplicado

        if 'cpf' in update_data:  # se CPF está sendo atualizado
            new_cpf = update_data['cpf']  # extrai novo CPF
            if new_cpf and not validators.is_valid_cpf(new_cpf):  # se CPF fornecido e inválido
                return (False, "INVALID_CPF", "O CPF fornecido é inválido.")  # retorna erro de CPF inválido

        allowed_fields = ['full_name', 'date_of_birth', 'phone', 'cpf', 'email']  # lista de campos permitidos
        fields_to_update = {k: v for k, v in update_data.items() if k in allowed_fields}  # filtra campos válidos

        if not fields_to_update:  # se nenhum campo válido
            return (False, "NO_VALID_FIELDS", "Nenhum campo válido para atualização foi fornecido.")  # retorna erro de campos inválidos

        set_parts = [f"{key} = ?" for key in fields_to_update]  # cria partes SET da query
        values = list(fields_to_update.values())  # extrai valores dos campos
        values.append(user_id)  # adiciona ID do usuário aos valores

        sql_update = f"UPDATE USERS SET {', '.join(set_parts)} WHERE ID = ?;"  # monta query de atualização
        cur.execute(sql_update, tuple(values))  # executa atualização
        conn.commit()  # confirma transação

        return (True, None, "Dados atualizados com sucesso.")  # retorna sucesso

    except fdb.Error as e:  # captura erro do banco
        print(f"Erro ao atualizar usuário: {e}")  # log do erro
        if conn: conn.rollback()  # desfaz transação
        return (False, "DATABASE_ERROR", "Erro interno do servidor.")  # retorna erro de banco
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def deactivate_user(user_id):  # função para inativar usuário (soft delete)
    conn = None  # inicializa variável de conexão
    try:  # tenta operação no banco
        conn = get_db_connection()  # estabelece conexão com banco
        cur = conn.cursor()  # cria cursor para execução de queries

        sql_check = "SELECT 1 FROM USERS WHERE ID = ?;"  # query para verificar existência
        cur.execute(sql_check, (user_id,))  # executa verificação de existência
        if not cur.fetchone():  # se usuário não existe
            return False  # retorna falso

        sql_update = "UPDATE USERS SET IS_ACTIVE = FALSE WHERE ID = ?;"  # query para inativar usuário
        cur.execute(sql_update, (user_id,))  # executa inativação
        conn.commit()  # confirma transação

        return True  # retorna verdadeiro em caso de sucesso
        
    except fdb.Error as e:  # captura erro do banco
        print(f"Erro ao inativar usuário: {e}")  # log do erro
        if conn: conn.rollback()  # desfaz transação
        return False  # retorna falso em caso de erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def get_user_ids_by_roles(roles):  # função para buscar IDs de usuários por cargos
    conn = None  # inicializa variável de conexão
    try:  # tenta operação no banco
        conn = get_db_connection()  # estabelece conexão com banco
        cur = conn.cursor()  # cria cursor para execução de queries
        placeholders = ', '.join(['?' for _ in roles])  # cria placeholders para query
        sql = f"SELECT ID FROM USERS WHERE ROLE IN ({placeholders}) AND IS_ACTIVE = TRUE;"  # query para buscar IDs
        cur.execute(sql, tuple(roles))  # executa busca com parâmetros
        return [row[0] for row in cur.fetchall()]  # retorna lista de IDs
    except fdb.Error as e:  # captura erro do banco
        print(f"Erro ao buscar usuários por cargos: {e}")  # log do erro
        return []  # retorna lista vazia em caso de erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def initiate_password_reset(email):  # função para iniciar recuperação de senha
    conn = None  # inicializa variável de conexão
    try:  # tenta operação no banco
        conn = get_db_connection()  # estabelece conexão com banco
        cur = conn.cursor()  # cria cursor para execução de queries

        sql_find_user = "SELECT ID, FULL_NAME FROM USERS WHERE EMAIL = ? AND IS_ACTIVE = TRUE;"  # query para buscar usuário
        cur.execute(sql_find_user, (email,))  # executa busca do usuário
        user_record = cur.fetchone()  # obtém resultado da query

        if user_record:  # se usuário encontrado
            user_id, full_name = user_record  # extrai ID e nome do usuário

            token = token_helper.generate_secure_token()  # gera token seguro

            expires_at = datetime.now() + timedelta(hours=1)  # define expiração em 1 hora

            sql_save_token = "INSERT INTO PASSWORD_RESET_TOKENS (USER_ID, TOKEN, EXPIRES_AT) VALUES (?, ?, ?);"  # query para salvar token
            cur.execute(sql_save_token, (user_id, token, expires_at))  # executa inserção do token
            conn.commit()  # confirma transação

            reset_link = f"http://localhost:5173/reset-password?token={token}"  # monta link de recuperação

            email_service.send_email(  # envia e-mail de recuperação
                to=email,  # destinatário
                subject="Recuperação de Senha - Royal Burger",  # assunto
                template='password_reset',  # template
                user={"full_name": full_name},  # dados do usuário
                reset_link=reset_link  # link de recuperação
            )

        return True  # sempre retorna verdadeiro por segurança

    except fdb.Error as e:  # captura erro do banco
        print(f"Erro no banco de dados ao iniciar a recuperação de senha: {e}")  # log do erro
        if conn: conn.rollback()  # desfaz transação
        return False  # retorna falso em caso de erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def finalize_password_reset(token, new_password):  # função para finalizar recuperação de senha
    is_strong, message = validators.is_strong_password(new_password)  # valida força da nova senha
    if not is_strong:  # se senha fraca
        return (False, message)  # retorna erro de senha fraca

    conn = None  # inicializa variável de conexão
    try:  # tenta operação no banco
        conn = get_db_connection()  # estabelece conexão com banco
        cur = conn.cursor()  # cria cursor para execução de queries

        sql_find_token = """  # query para buscar token
            SELECT USER_ID, EXPIRES_AT, USED_AT
            FROM PASSWORD_RESET_TOKENS
            WHERE TOKEN = ?;
        """
        cur.execute(sql_find_token, (token,))  # executa busca do token
        token_record = cur.fetchone()  # obtém resultado da query

        if not token_record:  # se token não encontrado
            return (False, "Token inválido ou não encontrado.")  # retorna erro de token inválido

        user_id, expires_at, used_at = token_record  # extrai dados do token

        if used_at is not None:  # se token já foi usado
            return (False, "Este token de recuperação já foi utilizado.")  # retorna erro de token usado

        if datetime.now() > expires_at:  # se token expirado
            return (False, "Este token de recuperação expirou.")  # retorna erro de token expirado

        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())  # gera hash da nova senha
        sql_update_password = "UPDATE USERS SET PASSWORD_HASH = ? WHERE ID = ?;"  # query para atualizar senha
        cur.execute(sql_update_password, (hashed_password.decode('utf-8'), user_id))  # executa atualização da senha

        sql_invalidate_token = "UPDATE PASSWORD_RESET_TOKENS SET USED_AT = CURRENT_TIMESTAMP WHERE TOKEN = ?;"  # query para invalidar token
        cur.execute(sql_invalidate_token, (token,))  # executa invalidação do token

        conn.commit()  # confirma transação

        return (True, "Senha atualizada com sucesso.")  # retorna sucesso

    except fdb.Error as e:  # captura erro do banco
        print(f"Erro no banco de dados ao finalizar a recuperação de senha: {e}")  # log do erro
        if conn: conn.rollback()  # desfaz transação
        return (False, "Ocorreu um erro interno. Tente novamente mais tarde.")  # retorna erro interno
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def reactivate_user(user_id):  # função para reativar usuário
    conn = None  # inicializa variável de conexão
    try:  # tenta operação no banco
        conn = get_db_connection()  # estabelece conexão com banco
        cur = conn.cursor()  # cria cursor para execução de queries

        sql_check = "SELECT 1 FROM USERS WHERE ID = ?;"  # query para verificar existência
        cur.execute(sql_check, (user_id,))  # executa verificação de existência
        if not cur.fetchone():  # se usuário não existe
            return False  # retorna falso

        sql_update = "UPDATE USERS SET IS_ACTIVE = TRUE WHERE ID = ?;"  # query para reativar usuário
        cur.execute(sql_update, (user_id,))  # executa reativação
        conn.commit()  # confirma transação

        return True  # retorna verdadeiro em caso de sucesso
        
    except fdb.Error as e:  # captura erro do banco
        print(f"Erro ao reativar usuário: {e}")  # log do erro
        if conn: conn.rollback()  # desfaz transação
        return False  # retorna falso em caso de erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão


def get_user_metrics(user_id):  # função para buscar métricas do usuário
    conn = None  # inicializa variável de conexão
    try:  # tenta operação no banco
        conn = get_db_connection()  # estabelece conexão com banco
        cur = conn.cursor()  # cria cursor para execução de queries
        
        cur.execute("SELECT ROLE FROM USERS WHERE ID = ? AND IS_ACTIVE = TRUE", (user_id,))  # busca papel do usuário
        user_row = cur.fetchone()  # obtém resultado da query
        if not user_row:  # se usuário não encontrado
            return None  # retorna None
        
        user_role = user_row[0]  # extrai papel do usuário
        if user_role not in ['attendant', 'manager', 'admin']:  # se não for funcionário
            return None  # retorna None
        
        cur.execute("""  # query para contar pedidos concluídos
            SELECT COUNT(*) as total_orders,
                   SUM(TOTAL_AMOUNT) as total_revenue
            FROM ORDERS 
            WHERE ATTENDANT_ID = ? AND STATUS = 'delivered'
        """, (user_id,))  # executa contagem de pedidos
        
        order_stats = cur.fetchone()  # obtém estatísticas dos pedidos
        total_orders = order_stats[0] if order_stats and order_stats[0] else 0  # extrai total de pedidos
        total_revenue = float(order_stats[1]) if order_stats and order_stats[1] else 0.0  # extrai receita total
        
        cur.execute("""  # query para calcular tempo médio de atendimento
            SELECT AVG(EXTRACT(EPOCH FROM (UPDATED_AT - CREATED_AT))/60) as avg_service_time
            FROM ORDERS 
            WHERE ATTENDANT_ID = ? AND STATUS = 'delivered' AND UPDATED_AT IS NOT NULL
        """, (user_id,))  # executa cálculo de tempo médio
        
        avg_service_time = cur.fetchone()  # obtém tempo médio
        avg_service_time = round(float(avg_service_time[0]), 1) if avg_service_time and avg_service_time[0] else 0.0  # arredonda tempo médio
        
        cur.execute("""  # query para contar pedidos em andamento
            SELECT COUNT(*) 
            FROM ORDERS 
            WHERE ATTENDANT_ID = ? AND STATUS IN ('pending', 'confirmed', 'preparing', 'ready', 'out_for_delivery')
        """, (user_id,))  # executa contagem de pedidos em andamento
        
        ongoing_result = cur.fetchone()  # obtém resultado dos pedidos em andamento
        ongoing_orders = ongoing_result[0] if ongoing_result and ongoing_result[0] else 0  # extrai total de pedidos em andamento
        
        average_rating = 0.0  # define média de avaliações como 0 (não implementado)
        
        return {  # retorna dicionário com métricas
            "user_id": user_id,  # ID do usuário
            "role": user_role,  # papel do usuário
            "total_completed_orders": total_orders,  # total de pedidos concluídos
            "total_revenue": total_revenue,  # receita total
            "average_service_time_minutes": avg_service_time,  # tempo médio de atendimento
            "ongoing_orders": ongoing_orders,  # pedidos em andamento
            "average_rating": average_rating  # média de avaliações
        }
        
    except fdb.Error as e:  # captura erro do banco
        print(f"Erro ao buscar métricas do usuário: {e}")  # log do erro
        return None  # retorna None em caso de erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão