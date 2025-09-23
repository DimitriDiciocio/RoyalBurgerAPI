import threading  # importa threading para envio assíncrono
from flask import render_template  # importa render_template para templates de e-mail
from flask_mail import Message  # importa Message para compor e-mails
from .. import mail, create_app  # importa instância do mail e factory da app

def send_async_email(app, msg):  # função para enviar e-mail em thread separada
    with app.app_context():  # usa contexto da aplicação
        mail.send(msg)  # envia mensagem

def send_email(to, subject, template, **kwargs):  # função genérica de envio de e-mails
    app = create_app()  # cria app para obter contexto
    msg = Message(subject, recipients=[to])  # cria mensagem com assunto e destinatário
    msg.body = render_template(f'email/{template}.txt', **kwargs)  # renderiza corpo texto
    msg.html = render_template(f'email/{template}.html', **kwargs)  # renderiza corpo HTML
    thr = threading.Thread(target=send_async_email, args=[app, msg])  # prepara thread de envio
    thr.start()  # inicia envio assíncrono
    return thr  # retorna thread criada