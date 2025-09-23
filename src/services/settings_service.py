import fdb  # importa driver do Firebird
from ..database import get_db_connection  # importa função de conexão com o banco

_settings_cache = {}  # cache em memória para as configurações

def _load_settings_into_cache():  # carrega configurações do banco para o cache
    global _settings_cache  # acessa cache global
    conn = None  # inicializa conexão
    try:  # tenta carregar configurações
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        cur.execute("SELECT SETTING_KEY, SETTING_VALUE FROM SETTINGS;")  # busca todas as configurações
        settings = {}  # dicionário de configurações
        for row in cur.fetchall():  # itera resultados
            settings[row[0]] = row[1]  # mapeia chave-valor
        _settings_cache = settings  # atualiza cache global
        print("Cache de configurações carregado com sucesso.")  # log de sucesso
    except fdb.Error as e:  # captura erros
        print(f"Erro ao carregar configurações para o cache: {e}")  # exibe erro
    finally:  # sempre executa
        if conn:  # se conexão existe
            conn.close()  # fecha conexão

def get_setting(key, default=None):  # busca configuração por chave
    if not _settings_cache:  # se cache vazio
        _load_settings_into_cache()  # recarrega cache
    value_str = _settings_cache.get(key, default)  # busca valor no cache
    if value_str is None:  # se valor não encontrado
        return default  # retorna padrão
    try:  # tenta converter para número
        if '.' in value_str:  # se contém ponto decimal
            return float(value_str)  # converte para float
        return int(value_str)  # converte para int
    except (ValueError, TypeError):  # se conversão falhar
        return value_str  # retorna como string

def update_setting(key, new_value, user_id):  # atualiza configuração
    conn = None  # inicializa conexão
    try:  # tenta atualizar
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        cur.execute("SELECT SETTING_VALUE FROM SETTINGS WHERE SETTING_KEY = ?;", (key,))  # busca valor antigo
        old_value_row = cur.fetchone()  # obtém linha
        old_value = old_value_row[0] if old_value_row else None  # extrai valor antigo
        sql_merge = """
            MERGE INTO SETTINGS s
            USING (SELECT ? AS key, ? AS value, ? AS user_id FROM RDB$DATABASE) AS new
            ON (s.SETTING_KEY = new.key)
            WHEN MATCHED THEN
                UPDATE SET s.SETTING_VALUE = new.value, s.LAST_UPDATED_BY = new.user_id, s.LAST_UPDATED_AT = CURRENT_TIMESTAMP
            WHEN NOT MATCHED THEN
                INSERT (SETTING_KEY, SETTING_VALUE, LAST_UPDATED_BY) VALUES (new.key, new.value, new.user_id);
        """  # SQL de merge (atualiza ou insere)
        cur.execute(sql_merge, (key, str(new_value), user_id))  # executa merge
        sql_history = """
            INSERT INTO SETTINGS_HISTORY (SETTING_KEY, OLD_VALUE, NEW_VALUE, UPDATED_BY)
            VALUES (?, ?, ?, ?);
        """  # SQL de histórico
        cur.execute(sql_history, (key, old_value, str(new_value), user_id))  # registra histórico
        conn.commit()  # confirma transação
        global _settings_cache  # acessa cache global
        _settings_cache.clear()  # limpa cache para recarregar
        return True  # retorna sucesso
    except fdb.Error as e:  # captura erros
        print(f"Erro ao atualizar configuração: {e}")  # exibe erro
        if conn:  # se conexão existe
            conn.rollback()  # desfaz transação
        return False  # retorna falha
    finally:  # sempre executa
        if conn:  # se conexão existe
            conn.close()  # fecha conexão