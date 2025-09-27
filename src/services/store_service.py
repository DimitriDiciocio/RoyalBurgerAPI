import fdb  
from datetime import datetime  
from ..database import get_db_connection  

_store_hours_cache = None  

def _load_hours_into_cache():  
    global _store_hours_cache  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        cur.execute("SELECT DAY_OF_WEEK, OPENING_TIME, CLOSING_TIME, IS_OPEN FROM STORE_HOURS;")  
        hours = {row[0]: {"open": row[1], "close": row[2], "is_open": row[3]} for row in cur.fetchall()}  
        _store_hours_cache = hours  
        print("Cache de horários de funcionamento carregado.")  
    except fdb.Error as e:  
        print(f"Erro ao carregar horários para o cache: {e}")  
        _store_hours_cache = {}  
    finally:  
        if conn: conn.close()  

def is_store_open():  
    if _store_hours_cache is None:  
        _load_hours_into_cache()  
    now = datetime.now()  
    day_of_week = (now.weekday() + 1) % 7  
    current_time = now.time()  
    today_hours = _store_hours_cache.get(day_of_week)  
    if not today_hours or not today_hours['is_open']:  
        return (False, "A loja está fechada hoje.")  
    opening_time = today_hours['open']  
    closing_time = today_hours['close']  
    if opening_time and closing_time and opening_time <= current_time <= closing_time:  
        return (True, "A loja está aberta.")  
    else:  
        return (False, "A loja está fechada neste horário.")  
