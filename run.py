from src import create_app, socketio  # importa factory do app e instância do SocketIO
import os  # importa utilitários do sistema operacional

app = create_app()  # cria instância da aplicação Flask

if __name__ == '__main__':  # executa apenas se for o arquivo principal
    host = os.environ.get('HOST', '0.0.0.0')  # obtém host das variáveis de ambiente
    port = int(os.environ.get('PORT', 5000))  # obtém porta das variáveis de ambiente
    socketio.run(app, host=host, port=port, debug=app.config['DEBUG'])  # inicia servidor com suporte a WebSockets