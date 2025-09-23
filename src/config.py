import os  # importa utilitários do sistema operacional
import fdb  # importa driver do Firebird para conexão com banco

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # encontra caminho absoluto da raiz do projeto

class Config:  # classe de configuração da aplicação
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'uma-chave-secreta-muito-dificil-de-adivinhar'  # chave secreta do Flask
    DEBUG = True  # modo debug ativado
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'uma-outra-chave-jwt-muito-segura'  # chave para assinar tokens JWT
    JWT_ACCESS_TOKEN_EXPIRES = int(os.environ.get('JWT_ACCESS_TOKEN_EXPIRES', 7200))  # expiração do token em segundos (2h)
    DATABASE_PATH = os.path.join(PROJECT_ROOT, 'database', 'royalburger.fdb')  # caminho do arquivo do banco Firebird
    FIREBIRD_HOST = 'localhost'  # host do servidor Firebird
    FIREBIRD_PORT = 3050  # porta padrão do Firebird
    FIREBIRD_USER = 'SYSDBA'  # usuário administrador do Firebird
    FIREBIRD_PASSWORD = 'sysdba'  # senha do usuário administrador
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')  # servidor SMTP para envio de emails
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))  # porta do servidor SMTP
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', '1', 't']  # habilita TLS para SMTP
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')  # usuário do email
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')  # senha do email
    MAIL_DEFAULT_SENDER = ('Royal Burger', MAIL_USERNAME)  # remetente padrão dos emails