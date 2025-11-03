import threading  
import logging
from flask import render_template, current_app  
from flask_mail import Message  

logger = logging.getLogger(__name__)

def send_async_email(app, msg):  
    with app.app_context():  
        mail_ext = app.extensions.get('mail')  
        if mail_ext:  
            try:
                mail_ext.send(msg)
            except Exception as e:
                logger.error(f"Erro ao enviar email: {e}", exc_info=True)

def send_email(to, subject, template, **kwargs):  
    app = current_app._get_current_object()  
    try:
        msg = Message(subject, recipients=[to])  
        try:
            msg.body = render_template(f'email/{template}.txt', **kwargs)  
        except Exception as e:
            logger.warning(f"Erro ao renderizar template de texto {template}.txt: {e}")
            msg.body = f"Olá, {kwargs.get('user', {}).get('full_name', 'Cliente')}!\n\n{subject}\n\nPara mais detalhes, acesse o sistema."
        
        try:
            msg.html = render_template(f'email/{template}.html', **kwargs)  
        except Exception as e:
            logger.warning(f"Erro ao renderizar template HTML {template}.html: {e}")
            msg.html = None
        
        thr = threading.Thread(target=send_async_email, args=[app, msg], daemon=True)  
        thr.start()  
        return thr
    except Exception as e:
        logger.error(f"Erro ao preparar email para {to}: {e}", exc_info=True)
        # Retorna None para indicar que houve erro, mas não lança exceção
        return None  
