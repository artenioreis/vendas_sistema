from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from database import DatabaseManager
from config import Config
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)
app.config['SECRET_KEY'] = 'sua_chave_secreta_aqui_muito_segura'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username, role, codigo=None):
        self.id = id         # ID do banco (PK da tabela usuarios)
        self.username = username
        self.role = role
        self.codigo = codigo # Código do vendedor na tabela VENDE

    def get_id(self):
        return str(self.id)

@login_manager.user_loader
def load_user(user_id):
    if not check_database_config():
        return None
    
    db = DatabaseManager()
    user_data = db.get_user_by_id(user_id)
    
    if user_data:
        return User(
            id=user_data['id'], 
            username=user_data['username'], 
            role=user_data['role'], 
            codigo=user_data['codigo_vendedor']
        )
    return None

def check_database_config():
    """Verifica se as configurações do banco estão definidas"""
    return all([
        os.getenv('DB_SERVER'),
        os.getenv('DB_NAME'),
        os.getenv('DB_USER'),
        os.getenv('DB_PASSWORD')
    ])

@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    
    if not check_database_config():
        return redirect(url_for('configurar_banco'))
    
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    else:
        return redirect(url_for('vendedor_dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Se as configs de banco não existirem, permitir configuração
        if not check_database_config():
             # Backdoor temporário apenas para primeira configuração se necessário, 
             # mas idealmente deve-se configurar o .env primeiro.
             pass

        try:
            db = DatabaseManager()
            user_data = db.get_user_by_username(username)
            
            if user_data and check_password_hash(user_data['password_hash'], password):
                user = User(
                    id=user_data['id'],
                    username=user_data['username'],
                    role=user_data['role'],
                    codigo=user_data['codigo_vendedor']
                )
                login_user(user)
                return redirect(url_for('index'))
            
            flash('Usuário ou senha incorretos!', 'error')
        except Exception as e:
            flash(f'Erro ao tentar login: {str(e)}', 'error')
    
    return render_template('login.html')

@app.route('/configurar-banco', methods=['GET', 'POST'])
def configurar_banco():
    if request.method == 'POST':
        config_data = {
            'DB_SERVER': request.form['server'],
            'DB_NAME': request.form['database'],
            'DB_USER': request.form['username'],
            'DB_PASSWORD': request.form['password']
        }
        
        try:
            db = DatabaseManager(config_data)
            conn = db.get_connection()
            if conn:
                flash('Conexão bem sucedida! Configurações salvas.', 'success')
                with open('.env', 'w') as f:
                    for key, value in config_data.items():
                        f.write(f"{key}={value}\n")
                
                for key, value in config_data.items():
                    os.environ[key] = value
                
                return redirect(url_for('login'))
            else:
                flash('Falha na conexão com o banco de dados.', 'error')
        except Exception as e:
            flash(f'Erro: {str(e)}', 'error')
    
    return render_template('config.html')

@app.route('/dashboard')
@login_required
def vendedor_dashboard():
    if not check_database_config():
        return redirect(url_for('configurar_banco'))
    
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))

    try:
        db = DatabaseManager()
        query = """
        Select v.Codigo, v.Nome_Guerra, v.Cod_EstabeOpe, v.Vlr_Objetivo, Vlr_Realizado = IsNull(n.Vlr_Realizado,0), 
               v.Cod_Supervisor, Vlr_Comissao = IsNull(n.Vlr_Comissao,0),
             v.Email, CPF_CNPJ = v.Cgc, 
             Situacao = Case When v.Bloqueado = 0 Then 'INATIVO' Else 'ATIVO' End
        From VENDE v Left Outer Join 
             ( Select x.Cod_Vendedor, 
                      Vlr_Realizado = SUM(x.Vlr_Realizado), 
                      Vlr_Comissao = SUM(x.Vlr_Comissao)
               From ( Select cb.Cod_Vendedor, cb.Cod_Estabe, cb.Ser_Nota, cb.Num_Nota,  
                             Vlr_Realizado = ROUND(SUM(it.Vlr_LiqItem-it.Vlr_SubsTrib-it.Vlr_SbtRes-it.Vlr_RecSbt-it.Vlr_SubsTribEmb-it.Vlr_DespRateada),2),
                             Vlr_Comissao = ROUND(SUM(it.Vlr_Comissao),2)
                      From NFSCB cb Inner Join 
                           NFSIT it on cb.Cod_Estabe = it.Cod_Estabe and cb.Ser_Nota = it.Ser_Nota And cb.Num_Nota = it.Num_Nota  
                      Where cb.Status = 'F' 
                      And cb.Tip_Saida = 'V' 
                      And cb.Dat_Emissao >= DATEADD(mm, DATEDIFF(m,0,GETDATE()),0)
                      And cb.Dat_Emissao <= DATEADD(s,-1,DATEADD(mm, DATEDIFF(m,0,GETDATE())+1,0))
                      Group by cb.Cod_Vendedor, cb.Cod_Estabe, cb.Ser_Nota, cb.Num_Nota ) x
               Group by x.Cod_Vendedor ) n On (v.Codigo = n.Cod_Vendedor)
        Where v.Cod_TipVenBas <> 'TLM'
        And v.Flg_Export = 1 
        AND v.Codigo = ?
        """
        
        data = db.execute_query(query, (current_user.codigo,))
        
        if data:
            vendedor = data[0]
            meta = float(vendedor['Vlr_Objetivo']) if vendedor['Vlr_Objetivo'] else 0
            realizado = float(vendedor['Vlr_Realizado']) if vendedor['Vlr_Realizado'] else 0
            comissao = float(vendedor['Vlr_Comissao']) if vendedor['Vlr_Comissao'] else 0
            
            percentual = (realizado / meta * 100) if meta > 0 else 0
            
            chart_data = {
                'labels': ['Meta', 'Realizado', 'Comissão'],
                'values': [meta, realizado, comissao],
                'colors': ['#3498db', '#2ecc71', '#f39c12']
            }
            
            return render_template('vendedor.html', 
                                 vendedor=vendedor,
                                 meta=meta,
                                 realizado=realizado,
                                 comissao=comissao,
                                 percentual=percentual,
                                 chart_data=chart_data)
        else:
            flash('Dados do vendedor não encontrados (Código não vinculado ou inexistente).', 'error')
            return render_template('vendedor.html')
            
    except Exception as e:
        flash(f'Erro ao buscar dados: {str(e)}', 'error')
        return render_template('vendedor.html')

@app.route('/admin-dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('vendedor_dashboard'))
    
    if not check_database_config():
        return redirect(url_for('configurar_banco'))
    
    # Parâmetro para mostrar inativos (padrão é False)
    mostrar_inativos = request.args.get('mostrar_inativos') == '1'
    
    try:
        db = DatabaseManager()
        
        # Construção dinâmica da query
        base_query = """
        Select v.Codigo, v.Nome_Guerra, v.Cod_EstabeOpe, v.Vlr_Objetivo, Vlr_Realizado = IsNull(n.Vlr_Realizado,0), 
               v.Cod_Supervisor, Vlr_Comissao = IsNull(n.Vlr_Comissao,0),
             v.Email, CPF_CNPJ = v.Cgc, 
             Situacao = Case When v.Bloqueado = 0 Then 'INATIVO' Else 'ATIVO' End
        From VENDE v Left Outer Join 
             ( Select x.Cod_Vendedor, 
                      Vlr_Realizado = SUM(x.Vlr_Realizado), 
                      Vlr_Comissao = SUM(x.Vlr_Comissao)
               From ( Select cb.Cod_Vendedor, cb.Cod_Estabe, cb.Ser_Nota, cb.Num_Nota,  
                             Vlr_Realizado = ROUND(SUM(it.Vlr_LiqItem-it.Vlr_SubsTrib-it.Vlr_SbtRes-it.Vlr_RecSbt-it.Vlr_SubsTribEmb-it.Vlr_DespRateada),2),
                             Vlr_Comissao = ROUND(SUM(it.Vlr_Comissao),2)
                      From NFSCB cb Inner Join 
                           NFSIT it on cb.Cod_Estabe = it.Cod_Estabe and cb.Ser_Nota = it.Ser_Nota And cb.Num_Nota = it.Num_Nota  
                      Where cb.Status = 'F' 
                      And cb.Tip_Saida = 'V' 
                      And cb.Dat_Emissao >= DATEADD(mm, DATEDIFF(m,0,GETDATE()),0)
                      And cb.Dat_Emissao <= DATEADD(s,-1,DATEADD(mm, DATEDIFF(m,0,GETDATE())+1,0))
                      Group by cb.Cod_Vendedor, cb.Cod_Estabe, cb.Ser_Nota, cb.Num_Nota ) x
               Group by x.Cod_Vendedor ) n On (v.Codigo = n.Cod_Vendedor)
        Where v.Cod_TipVenBas <> 'TLM'
        And v.Flg_Export = 1 
        """
        
        # Filtro de ativos/inativos
        # Nota: A query original diz 'Case When v.Bloqueado = 0 Then 'INATIVO' Else 'ATIVO''.
        # Logo, ATIVO é quando Bloqueado != 0 (ou seja, 1).
        if not mostrar_inativos:
            base_query += " And v.Bloqueado <> 0 "
            
        base_query += " Order by v.Nome_Guerra"
        
        vendedores = db.execute_query(base_query)
        
        total_meta = sum(float(v['Vlr_Objetivo'] or 0) for v in vendedores)
        total_realizado = sum(float(v['Vlr_Realizado'] or 0) for v in vendedores)
        total_comissao = sum(float(v['Vlr_Comissao'] or 0) for v in vendedores)
        
        chart_data = {
            'total_meta': total_meta,
            'total_realizado': total_realizado,
            'total_comissao': total_comissao,
            'vendedores': [
                {
                    'nome': v['Nome_Guerra'],
                    'meta': float(v['Vlr_Objetivo'] or 0),
                    'realizado': float(v['Vlr_Realizado'] or 0),
                    'comissao': float(v['Vlr_Comissao'] or 0)
                }
                for v in vendedores
            ]
        }
        
        return render_template('admin.html', 
                             vendedores=vendedores,
                             chart_data=chart_data,
                             mostrar_inativos=mostrar_inativos)
            
    except Exception as e:
        flash(f'Erro ao buscar dados: {str(e)}', 'error')
        return render_template('admin.html', mostrar_inativos=mostrar_inativos)

@app.route('/usuarios')
@login_required
def gerenciar_usuarios():
    if current_user.role != 'admin':
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    
    db = DatabaseManager()
    usuarios = db.get_all_users()
    return render_template('usuarios.html', usuarios=usuarios)

@app.route('/usuarios/adicionar', methods=['POST'])
@login_required
def adicionar_usuario():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    username = request.form['username']
    password = request.form['password']
    role = request.form['role']
    codigo = request.form.get('codigo') # Pode ser vazio se for admin
    
    if not codigo and role == 'vendedor':
        flash('Vendedor precisa de um código vinculado.', 'error')
        return redirect(url_for('gerenciar_usuarios'))
        
    password_hash = generate_password_hash(password)
    
    db = DatabaseManager()
    # Verifica se usuário já existe
    if db.get_user_by_username(username):
        flash('Nome de usuário já existe.', 'error')
    else:
        db.create_user(username, password_hash, role, codigo if codigo else None)
        flash('Usuário criado com sucesso!', 'success')
        
    return redirect(url_for('gerenciar_usuarios'))

@app.route('/usuarios/deletar/<int:user_id>')
@login_required
def deletar_usuario(user_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    if str(user_id) == str(current_user.id):
        flash('Você não pode deletar seu próprio usuário.', 'error')
        return redirect(url_for('gerenciar_usuarios'))
        
    db = DatabaseManager()
    db.delete_user(user_id)
    flash('Usuário removido.', 'success')
    return redirect(url_for('gerenciar_usuarios'))

@app.route('/api/vendedor-dados/<int:codigo>')
@login_required
def get_vendedor_dados(codigo):
    if current_user.role != 'admin':
        return jsonify({'error': 'Não autorizado'}), 403
    
    try:
        db = DatabaseManager()
        query = """
        SELECT 
            MONTH(cb.Dat_Emissao) as Mes,
            SUM(it.Vlr_LiqItem-it.Vlr_SubsTrib-it.Vlr_SbtRes-it.Vlr_RecSbt-it.Vlr_SubsTribEmb-it.Vlr_DespRateada) as Realizado,
            SUM(it.Vlr_Comissao) as Comissao
        FROM NFSCB cb 
        INNER JOIN NFSIT it ON cb.Cod_Estabe = it.Cod_Estabe 
            AND cb.Ser_Nota = it.Ser_Nota 
            AND cb.Num_Nota = it.Num_Nota
        WHERE cb.Status = 'F' 
            AND cb.Tip_Saida = 'V' 
            AND cb.Cod_Vendedor = ?
            AND cb.Dat_Emissao >= DATEADD(mm, -6, GETDATE())
        GROUP BY MONTH(cb.Dat_Emissao)
        ORDER BY Mes
        """
        dados = db.execute_query(query, (codigo,))
        return jsonify(dados)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)