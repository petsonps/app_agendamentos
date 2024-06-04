from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from dateutil import parser
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from dotenv import load_dotenv
import os
import re

load_dotenv()  # Carrega as variáveis de ambiente do arquivo .env

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///appointments.db'
app.config['SECRET_KEY'] = 'very-secret-key'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    date_time = db.Column(db.DateTime, nullable=False)
    seller = db.Column(db.String(100), nullable=False)
    notificado = db.Column(db.String(20), nullable=False, default='Não enviado')

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        name = request.form['name']
        phone = format_phone_number(request.form['phone'])
        email = request.form['email']
        date_time = parser.isoparse(request.form['date_time'])
        seller = request.form['seller']

        if not validate_phone(phone):
            flash('Número de telefone inválido. Use o formato +551234567890.', 'danger')
            return redirect(url_for('index'))

        # Verificar se já existe um agendamento para o mesmo cliente no mesmo dia
        existing_appointment = Appointment.query.filter(
            Appointment.name == name,
            Appointment.phone == phone,
            Appointment.email == email,
            db.func.date(Appointment.date_time) == date_time.date()
        ).first()

        if existing_appointment:
            flash('Já existe um agendamento para este cliente no mesmo dia. Deseja substituir o agendamento anterior?', 'warning')
            session['new_appointment'] = {
                'name': name,
                'phone': phone,
                'email': email,
                'date_time': date_time.isoformat(),
                'seller': seller
            }
            return render_template('confirm.html', existing_appointment=existing_appointment)

        new_appointment = Appointment(name=name, phone=phone, email=email, date_time=date_time, seller=seller)
        db.session.add(new_appointment)
        db.session.commit()

        # Enviar mensagem via WhatsApp e atualizar o status de notificação
        notificado_status = send_whatsapp_message(phone, date_time)
        new_appointment.notificado = notificado_status
        db.session.commit()

        flash('Agendamento confirmado com sucesso!', 'success')
        return redirect(url_for('index'))
    appointments = Appointment.query.all()
    return render_template('index.html', appointments=appointments)

@app.route('/confirm_replace', methods=['POST'])
def confirm_replace():
    new_appointment = session.pop('new_appointment', None)
    if not new_appointment:
        flash('Erro ao processar a solicitação.', 'danger')
        return redirect(url_for('index'))

    # Excluir o agendamento anterior
    existing_appointment = Appointment.query.filter(
        Appointment.name == new_appointment['name'],
        Appointment.phone == new_appointment['phone'],
        Appointment.email == new_appointment['email'],
        db.func.date(Appointment.date_time) == parser.isoparse(new_appointment['date_time']).date()
    ).first()
    db.session.delete(existing_appointment)

    # Adicionar o novo agendamento
    new_appointment = Appointment(
        name=new_appointment['name'],
        phone=new_appointment['phone'],
        email=new_appointment['email'],
        date_time=parser.isoparse(new_appointment['date_time']),
        seller=new_appointment['seller']
    )
    db.session.add(new_appointment)
    db.session.commit()

    # Enviar mensagem via WhatsApp e atualizar o status de notificação
    notificado_status = send_whatsapp_message(new_appointment.phone, new_appointment.date_time)
    new_appointment.notificado = notificado_status
    db.session.commit()

    flash('Agendamento substituído com sucesso!', 'success')
    return redirect(url_for('index'))

@app.route('/api/events')
def get_events():
    appointments = Appointment.query.all()
    events = []
    for appointment in appointments:
        events.append({
            'title': f'Agendado: {appointment.name}',
            'start': appointment.date_time.isoformat(),
            'end': (appointment.date_time + timedelta(minutes=30)).isoformat(),  # Assuming 30-minute slots
            'color': 'red'  # Highlighting the event in red to indicate it's booked
        })
    return jsonify(events)

@app.route('/delete_appointment/<int:appointment_id>', methods=['POST'])
def delete_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    db.session.delete(appointment)
    db.session.commit()
    flash('Agendamento deletado com sucesso!', 'success')
    return redirect(url_for('index'))

def format_phone_number(phone):
    # Remove non-digit characters
    phone = re.sub(r'\D', '', phone)
    
    # Ensure the phone number starts with +55
    if not phone.startswith('55'):
        phone = '55' + phone
    
    # Check if the phone number has an extra '9' after the DDD
    if phone.startswith('55') and len(phone) == 13 and phone[4] == '9':
        phone = phone[:4] + phone[5:]

    return '+' + phone

def send_whatsapp_message(phone, date_time):
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    client = Client(account_sid, auth_token)

    try:
        message = client.messages.create(
            body=f'Olá, esta é uma mensagem de confirmação de agendamento da sua biopedância na Plenapharma às {date_time.strftime("%H:%M")} do dia {date_time.strftime("%d/%m/%Y")}. Não precisa responder essa mensagem. Lembre que o contato com a Plenapharma é no número https://wa.me/+5579999790047.',
            from_='whatsapp:+14155238886',
            to=f'whatsapp:{phone}'
        )
        return 'Enviado'
    except TwilioRestException as e:
        print(f'Error: {e}')
        return 'Erro no envio'

def validate_phone(phone):
    pattern = re.compile(r'^\+?[1-9]\d{1,14}$')
    return pattern.match(phone)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = os.environ.get("PORT", 5000)
    app.run(debug=False, host="0.0.0.0", port=port)