# run.py

# Importamos o app e o socketio do nosso pacote src
from src import create_app, socketio

app = create_app()

if __name__ == '__main__':
    # Usamos o socketio.run() para iniciar o servidor
    # Isso inicia um servidor (eventlet) que suporta tanto HTTP quanto WebSockets
    socketio.run(app, debug=app.config['DEBUG'])