# src/services/settings_service.py

import fdb
from ..database import get_db_connection

# Cache em memória para as configurações
_settings_cache = {}

def _load_settings_into_cache():
    """Carrega todas as configurações do banco para o cache em memória."""
    global _settings_cache
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT SETTING_KEY, SETTING_VALUE FROM SETTINGS;")
        settings = {}
        for row in cur.fetchall():
            settings[row[0]] = row[1]
        _settings_cache = settings
        print("Cache de configurações carregado com sucesso.")
    except fdb.Error as e:
        print(f"Erro ao carregar configurações para o cache: {e}")
    finally:
        if conn:
            conn.close()

def get_setting(key, default=None):
    """
    Busca uma configuração, primeiro do cache, depois do banco.
    Converte para número (int/float) se possível.
    """
    if not _settings_cache:
        _load_settings_into_cache()

    value_str = _settings_cache.get(key, default)

    if value_str is None:
        return default

    # Tenta converter para um número
    try:
        if '.' in value_str:
            return float(value_str)
        return int(value_str)
    except (ValueError, TypeError):
        return value_str # Retorna como string se não for um número

def update_setting(key, new_value, user_id):
    """
    Atualiza uma configuração no banco de dados, registra no histórico e limpa o cache.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # --- Início da Transação ---

        # 1. Pega o valor antigo para o histórico
        cur.execute("SELECT SETTING_VALUE FROM SETTINGS WHERE SETTING_KEY = ?;", (key,))
        old_value_row = cur.fetchone()
        old_value = old_value_row[0] if old_value_row else None

        # 2. Atualiza (ou insere) a configuração principal
        # O MERGE é ótimo para isso: atualiza se existir, insere se não.
        sql_merge = """
            MERGE INTO SETTINGS s
            USING (SELECT ? AS key, ? AS value, ? AS user_id FROM RDB$DATABASE) AS new
            ON (s.SETTING_KEY = new.key)
            WHEN MATCHED THEN
                UPDATE SET s.SETTING_VALUE = new.value, s.LAST_UPDATED_BY = new.user_id, s.LAST_UPDATED_AT = CURRENT_TIMESTAMP
            WHEN NOT MATCHED THEN
                INSERT (SETTING_KEY, SETTING_VALUE, LAST_UPDATED_BY) VALUES (new.key, new.value, new.user_id);
        """
        cur.execute(sql_merge, (key, str(new_value), user_id))

        # 3. Insere o registro no histórico
        sql_history = """
            INSERT INTO SETTINGS_HISTORY (SETTING_KEY, OLD_VALUE, NEW_VALUE, UPDATED_BY)
            VALUES (?, ?, ?, ?);
        """
        cur.execute(sql_history, (key, old_value, str(new_value), user_id))

        conn.commit()

        # --- Fim da Transação ---

        # 4. Limpa o cache para forçar o recarregamento na próxima leitura
        global _settings_cache
        _settings_cache.clear()

        return True
    except fdb.Error as e:
        print(f"Erro ao atualizar configuração: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()