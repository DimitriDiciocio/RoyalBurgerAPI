from src import create_app, socketio  # importa factory do app e instância do SocketIO
import os  # importa utilitários do sistema operacional

app = create_app()  # cria instância da aplicação Flask

if __name__ == '__main__':  # executa apenas se for o arquivo principal
    host = os.environ.get('HOST', '0.0.0.0')  # obtém host das variáveis de ambiente
    port = int(os.environ.get('PORT', 5000))  # obtém porta das variáveis de ambiente
    print(f"\n➡️  API iniciando em http://{host}:{port}/api (DEBUG={app.config['DEBUG']})")  # exibe URL da API
    print("   - Emulador Android (AVD): http://10.0.2.2:5000/api")  # exibe URL para emulador
    print("   - Dispositivo físico na mesma rede: use o IP da máquina, ex.: http://192.168.x.x:5000/api\n")  # exibe URL para dispositivo físico
    socketio.run(app, host=host, port=port, debug=app.config['DEBUG'])  # inicia servidor com suporte a WebSockets