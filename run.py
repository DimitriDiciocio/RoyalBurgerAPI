# run.py

# Importamos o app e o socketio do nosso pacote src
from src import create_app, socketio
import os

app = create_app()

if __name__ == '__main__':
    # Host e porta configuráveis via variáveis de ambiente
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))

    # Log amigável mostrando a URL
    print(f"\n➡️  API iniciando em http://{host}:{port}/api (DEBUG={app.config['DEBUG']})")
    print("   - Emulador Android (AVD): http://10.0.2.2:5000/api")
    print("   - Dispositivo físico na mesma rede: use o IP da máquina, ex.: http://192.168.x.x:5000/api\n")

    # Inicia o servidor com suporte a WebSockets
    socketio.run(app, host=host, port=port, debug=app.config['DEBUG'])