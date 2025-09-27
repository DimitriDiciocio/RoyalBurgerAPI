import fdb  
from .config import Config  

def get_db_connection():  
    try:  
        conn = fdb.connect(  
            host=Config.FIREBIRD_HOST,  
            port=Config.FIREBIRD_PORT,  
            database=Config.DATABASE_PATH,  
            user=Config.FIREBIRD_USER,  
            password=Config.FIREBIRD_PASSWORD,  
            charset='UTF-8'  
        )
        return conn  
    except fdb.Error as e:  
        print(f"Erro ao conectar ao Firebird: {e}")  
        return None  
