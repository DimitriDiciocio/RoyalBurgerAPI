import fdb  # importa driver do Firebird
from datetime import datetime  # importa classe de data/hora
from ..database import get_db_connection  # importa função de conexão com o banco

_store_hours_cache = None  # cache para horários de funcionamento

def _load_hours_into_cache():  # carrega horários do banco para o cache
    global _store_hours_cache  # acessa cache global
    conn = None  # inicializa conexão
    try:  # tenta carregar horários
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        cur.execute("SELECT DAY_OF_WEEK, OPENING_TIME, CLOSING_TIME, IS_OPEN FROM STORE_HOURS;")  # busca horários
        hours = {row[0]: {"open": row[1], "close": row[2], "is_open": row[3]} for row in cur.fetchall()}  # mapeia horários
        _store_hours_cache = hours  # atualiza cache global
        print("Cache de horários de funcionamento carregado.")  # log de sucesso
    except fdb.Error as e:  # captura erros
        print(f"Erro ao carregar horários para o cache: {e}")  # exibe erro
        _store_hours_cache = {}  # evita recarregar em caso de erro
    finally:  # sempre executa
        if conn: conn.close()  # fecha conexão

def is_store_open():  # verifica se a loja está aberta
    if _store_hours_cache is None:  # se cache não carregado
        _load_hours_into_cache()  # carrega cache
    now = datetime.now()  # data/hora atual
    day_of_week = (now.weekday() + 1) % 7  # converte weekday para nossa convenção (Dom=0, Sab=6)
    current_time = now.time()  # hora atual
    today_hours = _store_hours_cache.get(day_of_week)  # busca horários do dia
    if not today_hours or not today_hours['is_open']:  # se não há horários ou loja fechada
        return (False, "A loja está fechada hoje.")  # retorna fechada
    opening_time = today_hours['open']  # horário de abertura
    closing_time = today_hours['close']  # horário de fechamento
    if opening_time and closing_time and opening_time <= current_time <= closing_time:  # se dentro do horário
        return (True, "A loja está aberta.")  # retorna aberta
    else:  # fora do horário
        return (False, "A loja está fechada neste horário.")  # retorna fechada