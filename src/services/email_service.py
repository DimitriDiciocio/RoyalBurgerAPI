# src/services/email_service.py

import threading
from flask import render_template
from flask_mail import Message
from .. import mail, create_app  # Importamos a instância do mail e o create_app


# O envio de e-mail pode ser lento. Para não travar a aplicação,
# vamos enviá-lo em uma thread separada (de forma assíncrona).
def send_async_email(app, msg):
    with app.app_context():
        mail.send(msg)


def send_email(to, subject, template, **kwargs):
    """
    Função genérica para enviar e-mails.
    'to': Destinatário
    'subject': Assunto
    'template': Nome do arquivo de template (ex: 'welcome.html')
    '**kwargs': Dados para passar para o template (ex: user=user_obj)
    """
    # Criamos um app context para a thread poder acessar as configurações
    app = create_app()
    msg = Message(subject, recipients=[to])

    # Renderiza o corpo do e-mail usando um template HTML e um de texto puro
    msg.body = render_template(f'email/{template}.txt', **kwargs)
    msg.html = render_template(f'email/{template}.html', **kwargs)

    # Inicia a thread para envio assíncrono
    thr = threading.Thread(target=send_async_email, args=[app, msg])
    thr.start()
    return thr