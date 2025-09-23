import fdb  # importa driver do Firebird
from .config import Config  # importa configurações da aplicação

def get_db_connection():  # função para criar conexão com o banco
    try:  # tenta conectar ao banco
        conn = fdb.connect(  # cria conexão usando parâmetros separados
            host=Config.FIREBIRD_HOST,  # host do servidor
            port=Config.FIREBIRD_PORT,  # porta do servidor
            database=Config.DATABASE_PATH,  # caminho do arquivo do banco
            user=Config.FIREBIRD_USER,  # usuário de conexão
            password=Config.FIREBIRD_PASSWORD,  # senha de conexão
            charset='UTF-8'  # codificação de caracteres
        )
        return conn  # retorna conexão estabelecida
    except fdb.Error as e:  # captura erros do Firebird
        print(f"Erro ao conectar ao Firebird: {e}")  # exibe erro no console
        return None  # retorna None em caso de falha