import threading  
from flask import render_template  
from flask_mail import Message  
from .. import mail, create_app  

def send_async_email(app, msg):  
    with app.app_context():  
        mail.send(msg)  

def send_email(to, subject, template, **kwargs):  
    app = create_app()  
    msg = Message(subject, recipients=[to])  
    msg.body = render_template(f'email/{template}.txt', **kwargs)  
    msg.html = render_template(f'email/{template}.html', **kwargs)  
    thr = threading.Thread(target=send_async_email, args=[app, msg])  
    thr.start()  
    return thr  
