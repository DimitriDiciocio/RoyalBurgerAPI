import requests
import json
import logging
from ..database import get_db_connection
import fdb

logger = logging.getLogger(__name__)

def get_user_tokens(user_id):
    """
    Busca todos os tokens de push do usuário na tabela USER_DEVICES.
    
    Args:
        user_id: ID do usuário
        
    Returns:
        Lista de tokens (strings) ou lista vazia se não houver tokens
    """
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            logger.error("Não foi possível obter conexão com o banco de dados")
            return []
            
        cur = conn.cursor()
        sql = "SELECT PUSH_TOKEN FROM USER_DEVICES WHERE USER_ID = ?"
        cur.execute(sql, (user_id,))
        tokens = [row[0] for row in cur.fetchall()]
        return tokens
    except fdb.Error as e:
        logger.error(f"Erro ao buscar tokens do usuário {user_id}: {e}")
        return []
    except Exception as e:
        logger.error(f"Erro inesperado ao buscar tokens: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()

def save_device_token(user_id, push_token, device_name=None):
    """
    Salva ou atualiza o token de push do dispositivo do usuário.
    
    Args:
        user_id: ID do usuário
        push_token: Token Expo Push (ex: "ExponentPushToken[xxxxxxxx]")
        device_name: Nome opcional do dispositivo
        
    Returns:
        bool: True se salvou/atualizou com sucesso, False caso contrário
    """
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            logger.error("Não foi possível obter conexão com o banco de dados")
            return False
            
        cur = conn.cursor()
        
        # Verifica se o token já existe
        check_sql = "SELECT ID FROM USER_DEVICES WHERE PUSH_TOKEN = ?"
        cur.execute(check_sql, (push_token,))
        existing = cur.fetchone()
        
        if existing:
            # Token já existe, atualiza LAST_USED e USER_ID (caso o usuário tenha mudado)
            update_sql = """
                UPDATE USER_DEVICES 
                SET USER_ID = ?, LAST_USED = CURRENT_TIMESTAMP, DEVICE_NAME = ?
                WHERE PUSH_TOKEN = ?
            """
            cur.execute(update_sql, (user_id, device_name, push_token))
        else:
            # Token não existe, insere novo
            insert_sql = """
                INSERT INTO USER_DEVICES (USER_ID, PUSH_TOKEN, DEVICE_NAME, LAST_USED)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """
            cur.execute(insert_sql, (user_id, push_token, device_name))
        
        conn.commit()
        return True
    except fdb.Error as e:
        logger.error(f"Erro ao salvar token do dispositivo: {e}")
        if conn:
            conn.rollback()
        return False
    except Exception as e:
        logger.error(f"Erro inesperado ao salvar token: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def send_push_to_user(user_id, title, body, data=None):
    """
    Busca os tokens do usuário e envia a notificação via Expo API.
    
    Args:
        user_id: ID do usuário
        title: Título da notificação
        body: Corpo da notificação
        data: Dados adicionais (dict) que serão enviados junto com a notificação
        
    Returns:
        bool: True se enviou com sucesso, False caso contrário
    """
    # 1. Buscar tokens do usuário no banco
    tokens = get_user_tokens(user_id)
    
    if not tokens:
        logger.debug(f"Nenhum token de push encontrado para o usuário {user_id}")
        return False
    
    # 2. Preparar payload para o Expo
    messages = []
    for token in tokens:
        messages.append({
            "to": token,
            "sound": "default",
            "title": title,
            "body": body,
            "data": data or {}
        })
    
    # 3. Enviar requisição HTTP
    try:
        response = requests.post(
            'https://exp.host/--/api/v2/push/send',
            headers={
                'Accept': 'application/json',
                'Accept-encoding': 'gzip, deflate',
                'Content-Type': 'application/json'
            },
            data=json.dumps(messages),
            timeout=10  # Timeout de 10 segundos
        )
        
        if response.status_code == 200:
            result = response.json()
            # Expo retorna um array de resultados, verifica se todos foram bem-sucedidos
            if isinstance(result, dict) and result.get('data'):
                results = result['data']
            elif isinstance(result, list):
                results = result
            else:
                results = [result]
            
            # Verifica se algum envio falhou
            failed = [r for r in results if r.get('status') == 'error']
            if failed:
                logger.warning(f"Alguns push notifications falharam: {failed}")
            
            success_count = len([r for r in results if r.get('status') == 'ok'])
            logger.info(f"Push notifications enviados: {success_count}/{len(messages)} para usuário {user_id}")
            return success_count > 0
        else:
            logger.error(f"Erro ao enviar push notification: Status {response.status_code}, Response: {response.text}")
            return False
    except requests.exceptions.Timeout:
        logger.error("Timeout ao enviar push notification para Expo API")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro de requisição ao enviar push notification: {e}")
        return False
    except Exception as e:
        logger.error(f"Erro inesperado ao enviar push notification: {e}", exc_info=True)
        return False

