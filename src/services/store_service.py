import fdb  
from datetime import datetime  
from ..database import get_db_connection
from ..config import Config  

# Cache de horários em memória para melhor performance
_store_hours_cache = None
_cache_timestamp = None
_cache_ttl_seconds = 300  # 5 minutos de TTL

def _is_cache_valid():
    """Verifica se o cache ainda é válido"""
    global _cache_timestamp
    if _cache_timestamp is None:
        return False
    elapsed = (datetime.now() - _cache_timestamp).total_seconds()
    return elapsed < _cache_ttl_seconds

def _invalidate_cache():
    """Invalida o cache forçando refresh na próxima chamada"""
    global _store_hours_cache, _cache_timestamp
    _store_hours_cache = None
    _cache_timestamp = None

def _load_hours_into_cache(force_refresh=False):
    """Carrega horários no cache"""
    global _store_hours_cache, _cache_timestamp
    
    # Verifica cache se não for refresh forçado
    if not force_refresh and _is_cache_valid() and _store_hours_cache is not None:
        return
    
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        cur.execute("SELECT DAY_OF_WEEK, OPENING_TIME, CLOSING_TIME, IS_OPEN FROM STORE_HOURS ORDER BY DAY_OF_WEEK;")  
        hours = {row[0]: {"open": row[1], "close": row[2], "is_open": row[3]} for row in cur.fetchall()}  
        _store_hours_cache = hours
        _cache_timestamp = datetime.now()
        print("Cache de horários de funcionamento carregado.")  
    except fdb.Error as e:  
        print(f"Erro ao carregar horários para o cache: {e}")  
        _store_hours_cache = {}  
    finally:  
        if conn:
            conn.close()  

def is_store_open():  
    """Verifica se a loja está aberta no momento atual
    
    CORREÇÃO: Em modo DEV (DEV_MODE=True ou FLASK_ENV=development), ignora verificação
    de horário e sempre retorna que a loja está aberta.
    """
    # CORREÇÃO: Em modo dev, sempre retorna que a loja está aberta
    if Config.DEV_MODE:
        return (True, "Modo de desenvolvimento ativo - horário de funcionamento ignorado.")
    
    _load_hours_into_cache()
    
    if not _store_hours_cache:
        return (False, "Horários de funcionamento não disponíveis.")
    
    now = datetime.now()  
    day_of_week = (now.weekday() + 1) % 7  # 0=Domingo, 1=Segunda, ..., 6=Sábado
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

def get_store_hours():
    """
    Retorna todos os horários de funcionamento (com cache)
    
    Returns:
        list: Lista de dicionários com horários por dia da semana
    """
    _load_hours_into_cache()
    
    if not _store_hours_cache:
        return []
    
    # Nomes dos dias da semana para facilitar uso no frontend
    day_names = {
        0: "Domingo",
        1: "Segunda-feira",
        2: "Terça-feira",
        3: "Quarta-feira",
        4: "Quinta-feira",
        5: "Sexta-feira",
        6: "Sábado"
    }
    
    hours_list = []
    for day_of_week in sorted(_store_hours_cache.keys()):
        day_data = _store_hours_cache[day_of_week]
        opening_time = day_data['open']
        closing_time = day_data['close']
        
        hours_list.append({
            "day_of_week": day_of_week,
            "day_name": day_names[day_of_week],
            "opening_time": opening_time.strftime('%H:%M') if opening_time else None,
            "closing_time": closing_time.strftime('%H:%M') if closing_time else None,
            "is_open": day_data['is_open']
        })
    
    return hours_list

def update_store_hours(day_of_week, opening_time=None, closing_time=None, is_open=None):
    """
    Atualiza os horários de funcionamento de um dia específico
    
    Args:
        day_of_week: Dia da semana (0=Domingo, 1=Segunda, ..., 6=Sábado)
        opening_time: Horário de abertura (formato 'HH:MM')
        closing_time: Horário de fechamento (formato 'HH:MM')
        is_open: Se a loja está aberta neste dia (True/False)
    
    Returns:
        tuple: (success, message)
    """
    # Validação do dia da semana
    if not isinstance(day_of_week, int) or day_of_week < 0 or day_of_week > 6:
        return (False, "day_of_week deve ser um número entre 0 e 6 (0=Domingo, 6=Sábado)")
    
    # Validação de horários (formato HH:MM)
    if opening_time:
        try:
            datetime.strptime(opening_time, '%H:%M')
        except ValueError:
            return (False, "opening_time deve estar no formato 'HH:MM' (ex: '10:00')")
    
    if closing_time:
        try:
            datetime.strptime(closing_time, '%H:%M')
        except ValueError:
            return (False, "closing_time deve estar no formato 'HH:MM' (ex: '22:00')")
    
    # Validação de is_open
    if is_open is not None and not isinstance(is_open, bool):
        return (False, "is_open deve ser True ou False")
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se o registro existe
        cur.execute("SELECT DAY_OF_WEEK FROM STORE_HOURS WHERE DAY_OF_WEEK = ?;", (day_of_week,))
        exists = cur.fetchone()
        
        if exists:
            # Atualiza registro existente
            update_fields = []
            params = []
            
            if opening_time is not None:
                update_fields.append("OPENING_TIME = ?")
                params.append(opening_time)
            
            if closing_time is not None:
                update_fields.append("CLOSING_TIME = ?")
                params.append(closing_time)
            
            if is_open is not None:
                update_fields.append("IS_OPEN = ?")
                params.append(is_open)
            
            update_fields.append("UPDATED_AT = ?")
            params.append(datetime.now())
            params.append(day_of_week)
            
            sql = f"UPDATE STORE_HOURS SET {', '.join(update_fields)} WHERE DAY_OF_WEEK = ?;"
            cur.execute(sql, params)
        else:
            # Cria novo registro (caso não exista)
            sql = """
                INSERT INTO STORE_HOURS (DAY_OF_WEEK, OPENING_TIME, CLOSING_TIME, IS_OPEN, UPDATED_AT)
                VALUES (?, ?, ?, ?, ?);
            """
            cur.execute(sql, (day_of_week, opening_time, closing_time, is_open if is_open is not None else True, datetime.now()))
        
        conn.commit()
        
        # Invalida cache para forçar refresh
        _invalidate_cache()
        
        day_names = {0: "Domingo", 1: "Segunda", 2: "Terça", 3: "Quarta", 4: "Quinta", 5: "Sexta", 6: "Sábado"}
        return (True, f"Horários de {day_names.get(day_of_week, 'Dia ' + str(day_of_week))} atualizados com sucesso.")
        
    except fdb.Error as e:
        print(f"Erro ao atualizar horários: {e}")
        if conn:
            conn.rollback()
        return (False, f"Erro ao atualizar horários: {str(e)}")
    finally:
        if conn:
            conn.close()

def bulk_update_store_hours(hours_data):
    """
    Atualiza múltiplos dias de uma vez
    
    Args:
        hours_data: Lista de dicionários com dados de horários
                   Exemplo: [
                       {"day_of_week": 0, "opening_time": "10:00", "closing_time": "22:00", "is_open": True},
                       {"day_of_week": 1, "opening_time": "10:00", "closing_time": "22:00", "is_open": True},
                   ]
    
    Returns:
        tuple: (success_count, failed_count, errors)
    """
    success_count = 0
    failed_count = 0
    errors = []
    
    if not isinstance(hours_data, list):
        return (0, 0, ["hours_data deve ser uma lista"])
    
    for hour_data in hours_data:
        if not isinstance(hour_data, dict):
            failed_count += 1
            errors.append("Cada item deve ser um dicionário")
            continue
        
        day_of_week = hour_data.get('day_of_week')
        opening_time = hour_data.get('opening_time')
        closing_time = hour_data.get('closing_time')
        is_open = hour_data.get('is_open')
        
        success, message = update_store_hours(day_of_week, opening_time, closing_time, is_open)
        
        if success:
            success_count += 1
        else:
            failed_count += 1
            errors.append(f"Dia {day_of_week}: {message}")
    
    return (success_count, failed_count, errors)  
