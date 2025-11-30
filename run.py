from src import create_app, socketio  # importa factory do app e instância do SocketIO
import os  # importa utilitários do sistema operacional

app = create_app()  # cria instância da aplicação Flask

if __name__ == '__main__':  # executa apenas se for o arquivo principal
    # CORREÇÃO: Definir variáveis de ambiente para modo dev antes de iniciar
    # Isso garante que FLASK_ENV esteja definido e o modo dev seja ativado
    if not os.environ.get('FLASK_ENV'):
        os.environ['FLASK_ENV'] = 'development'
    if not os.environ.get('DEV_MODE'):
        os.environ['DEV_MODE'] = 'true'
    
    host = os.environ.get('HOST', '0.0.0.0')  # obtém host das variáveis de ambiente
    port = int(os.environ.get('PORT', 5000))  # obtém porta das variáveis de ambiente
    
    print("=" * 60)
    print("🚀 Iniciando Royal Burger API em MODO DEV")
    print("=" * 60)
    print(f"📝 Modo: {os.environ.get('FLASK_ENV', 'development')}")
    print(f"🔧 DEV_MODE: {os.environ.get('DEV_MODE', 'true')}")
    print(f"⏰ Horário de funcionamento: IGNORADO (modo dev ativo)")
    print(f"🌐 Servidor: http://{host}:{port}")
    print("=" * 60)
    
    socketio.run(app, host=host, port=port, debug=True, allow_unsafe_werkzeug=True)  # inicia servidor com suporte a WebSockets