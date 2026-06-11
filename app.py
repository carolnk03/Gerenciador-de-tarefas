from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sua-chave-secreta-aqui'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gerenciador.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configurações de email (configure com suas credenciais)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'carol.n.k03@gmail.com'
app.config['MAIL_PASSWORD'] = 'gakm embn kepv zsfe'

db = SQLAlchemy(app)
mail = Mail(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Modelos do Banco de Dados
class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha = db.Column(db.String(200), nullable=False)
    projetos = db.relationship('Projeto', backref='criador', lazy=True)

class Projeto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    prazo = db.Column(db.DateTime)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    tarefas = db.relationship('Tarefa', backref='projeto', lazy=True, cascade='all, delete-orphan')

class Tarefa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text)
    prioridade = db.Column(db.String(20), default='media')  # alta, media, baixa
    status = db.Column(db.String(20), default='pendente')  # pendente, em_andamento, concluida
    prazo = db.Column(db.DateTime)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    projeto_id = db.Column(db.Integer, db.ForeignKey('projeto.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# Rotas de Autenticação
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        usuario_existente = Usuario.query.filter_by(email=email).first()
        if usuario_existente:
            flash('Email já cadastrado!', 'error')
            return redirect(url_for('registro'))
        
        hashed_senha = generate_password_hash(senha)
        novo_usuario = Usuario(nome=nome, email=email, senha=hashed_senha)
        
        db.session.add(novo_usuario)
        db.session.commit()
        
        flash('Conta criada com sucesso!', 'success')
        return redirect(url_for('login'))
    
    return render_template('registro.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        usuario = Usuario.query.filter_by(email=email).first()
        
        if usuario and check_password_hash(usuario.senha, senha):
            login_user(usuario)
            return redirect(url_for('dashboard'))
        else:
            flash('Email ou senha incorretos!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# Rotas do Dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    projetos = Projeto.query.filter_by(usuario_id=current_user.id).all()
    
    # Calcular estatísticas
    total_concluidas = 0
    total_pendentes = 0
    
    for projeto in projetos:
        for tarefa in projeto.tarefas:
            if tarefa.status == 'concluida':
                total_concluidas += 1
            else:
                total_pendentes += 1
    
    return render_template('dashboard.html', 
                         projetos=projetos, 
                         total_concluidas=total_concluidas, 
                         total_pendentes=total_pendentes)

# Rotas de Projetos
@app.route('/projeto/novo', methods=['GET', 'POST'])
@login_required
def novo_projeto():
    if request.method == 'POST':
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        prazo = datetime.strptime(request.form.get('prazo'), '%Y-%m-%d') if request.form.get('prazo') else None
        
        novo_projeto = Projeto(
            nome=nome,
            descricao=descricao,
            prazo=prazo,
            usuario_id=current_user.id
        )
        
        db.session.add(novo_projeto)
        db.session.commit()
        
        flash('Projeto criado com sucesso!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('novo_projeto.html')

@app.route('/projeto/<int:id>')
@login_required
def ver_projeto(id):
    projeto = Projeto.query.get_or_404(id)
    if projeto.usuario_id != current_user.id:
        flash('Acesso negado!', 'error')
        return redirect(url_for('dashboard'))
    
    tarefas = Tarefa.query.filter_by(projeto_id=id).all()
    return render_template('projeto.html', projeto=projeto, tarefas=tarefas)

@app.route('/projeto/<int:id>/excluir')
@login_required
def excluir_projeto(id):
    projeto = Projeto.query.get_or_404(id)
    if projeto.usuario_id != current_user.id:
        flash('Acesso negado!', 'error')
        return redirect(url_for('dashboard'))
    
    db.session.delete(projeto)
    db.session.commit()
    flash('Projeto excluído com sucesso!', 'success')
    return redirect(url_for('dashboard'))

# Rotas de Tarefas
@app.route('/projeto/<int:projeto_id>/tarefa/nova', methods=['GET', 'POST'])
@login_required
def nova_tarefa(projeto_id):
    projeto = Projeto.query.get_or_404(projeto_id)
    if projeto.usuario_id != current_user.id:
        flash('Acesso negado!', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        titulo = request.form.get('titulo')
        descricao = request.form.get('descricao')
        prioridade = request.form.get('prioridade')
        prazo = datetime.strptime(request.form.get('prazo'), '%Y-%m-%dT%H:%M') if request.form.get('prazo') else None
        
        nova_tarefa = Tarefa(
            titulo=titulo,
            descricao=descricao,
            prioridade=prioridade,
            prazo=prazo,
            projeto_id=projeto_id
        )
        
        db.session.add(nova_tarefa)
        db.session.commit()
        
        flash('Tarefa adicionada com sucesso!', 'success')
        return redirect(url_for('ver_projeto', id=projeto_id))
    
    return render_template('nova_tarefa.html', projeto=projeto)

@app.route('/tarefa/<int:id>/status', methods=['POST'])
@login_required
def atualizar_status(id):
    tarefa = Tarefa.query.get_or_404(id)
    projeto = Projeto.query.get(tarefa.projeto_id)
    
    if projeto.usuario_id != current_user.id:
        return jsonify({'error': 'Acesso negado'}), 403
    
    data = request.get_json()
    novo_status = data.get('status')
    
    if novo_status in ['pendente', 'em_andamento', 'concluida']:
        tarefa.status = novo_status
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'error': 'Status inválido'}), 400

@app.route('/tarefa/<int:id>/excluir')
@login_required
def excluir_tarefa(id):
    tarefa = Tarefa.query.get_or_404(id)
    projeto = Projeto.query.get(tarefa.projeto_id)
    
    if projeto.usuario_id != current_user.id:
        flash('Acesso negado!', 'error')
        return redirect(url_for('dashboard'))
    
    projeto_id = tarefa.projeto_id
    db.session.delete(tarefa)
    db.session.commit()
    
    flash('Tarefa excluída com sucesso!', 'success')
    return redirect(url_for('ver_projeto', id=projeto_id))

# Função de notificação por email
def verificar_prazos():
    with app.app_context():
        agora = datetime.utcnow()
        prazo_proximo = agora + timedelta(days=2)
        
        tarefas_proximas = Tarefa.query.filter(
            Tarefa.prazo <= prazo_proximo,
            Tarefa.prazo > agora,
            Tarefa.status != 'concluida'
        ).all()
        
        for tarefa in tarefas_proximas:
            projeto = Projeto.query.get(tarefa.projeto_id)
            usuario = Usuario.query.get(projeto.usuario_id)
            
            msg = Message(
                'Lembrete: Tarefa próxima do prazo!',
                sender=app.config['MAIL_USERNAME'],
                recipients=[usuario.email]
            )
            msg.body = f'''
            Olá {usuario.nome},
            
            A tarefa "{tarefa.titulo}" do projeto "{projeto.nome}" 
            está com prazo para {tarefa.prazo.strftime('%d/%m/%Y %H:%M')}.
            
            Prioridade: {tarefa.prioridade}
            Status atual: {tarefa.status}
            
            Acesse o sistema para mais detalhes.
            '''
            
            try:
                mail.send(msg)
            except Exception as e:
                print(f"Erro ao enviar email: {e}")

# Scheduler para verificar prazos
scheduler = BackgroundScheduler()
scheduler.add_job(func=verificar_prazos, trigger="interval", hours=24)
scheduler.start()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)