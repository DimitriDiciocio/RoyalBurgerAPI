import threading  
from flask import render_template, current_app  
from flask_mail import Message  

def send_async_email(app, msg):  
    with app.app_context():  
        mail_ext = app.extensions.get('mail')  
        if mail_ext:  
            mail_ext.send(msg)  

def send_email(to, subject, template, **kwargs):  
    app = current_app._get_current_object()  
    msg = Message(subject, recipients=[to])  
    msg.body = render_template(f'email/{template}.txt', **kwargs)  
    msg.html = render_template(f'email/{template}.html', **kwargs)  
    thr = threading.Thread(target=send_async_email, args=[app, msg], daemon=True)  
    thr.start()  
    return thr  
