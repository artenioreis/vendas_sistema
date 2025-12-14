from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from database import DatabaseManager
from config import Config
import os
import json
from datetime import datetime, timedelta

app = Flask(__name__)
app.config.from_object(Config)
app.config['SECRET_KEY'] = 'sua_chave_secreta_aqui'  # Altere para uma chave segura

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Simulação de usuários (em produção, use banco de dados)
users = {
    'admin': {'password': 'admin123', 'role': 'admin'},
    'vendedor1': {'password': 'vendedor123', 'role': 'vendedor', 'codigo': 1},
    'vendedor2': {'password': 'vendedor123', 'role': 'vendedor', 'codigo': 2}
}

class User(UserMixin):
    def __init__(self, id, role=None, codigo=None):
        self.id = id
        self.role = role
        self.codigo = codigo

@login_manager.user_loader
def load_user(user_id):
    user_data = users.get(user_id)
    if user_data:
        return User(user_id, user_data['role'], user_data.get('codigo'))
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
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user_data = users.get(username)
        if user_data and user_data['password'] == password:
            user = User(username, user_data['role'], user_data.get('codigo'))
            login_user(user)
            return redirect(url_for('index'))
        
        flash('Usuário ou senha incorretos!', 'error')
    
    return render_template('login.html')

@app.route('/configurar-banco', methods=['GET', 'POST'])
@login_required
def configurar_banco():
    if request.method == 'POST':
        # Salvar configurações no .env
        config_data = {
            'DB_SERVER': request.form['server'],
            'DB_NAME': request.form['database'],
            'DB_USER': request.form['username'],
            'DB_PASSWORD': request.form['password']
        }
        
        # Testar conexão
        try:
            db = DatabaseManager(config_data)
            conn = db.get_connection()
            if conn:
                flash('Conexão bem sucedida! Configurações salvas.', 'success')
                
                # Salvar em arquivo .env
                with open('.env', 'w') as f:
                    for key, value in config_data.items():
                        f.write(f"{key}={value}\n")
                
                # Carregar variáveis de ambiente
                for key, value in config_data.items():
                    os.environ[key] = value
                
                return redirect(url_for('index'))
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
    
    try:
        db = DatabaseManager()
        query = """
        Select v.Codigo, v.Nome_Guerra, v.Cod_EstabeOpe, v.Vlr_Objetivo, Vlr_Realizado = IsNull(n.Vlr_Realizado,0), 
               v.Cod_Supervisor, Vlr_Comissao = IsNull(n.Vlr_Comissao,0),
             v.Email, CPF_CNPJ = v.Cgc, 
             Situacao = Case When v.Bloqueado = 0 Then 
                     'INATIVO'
                    Else 
                      'ATIVO'
                  End
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
            
            # Dados para gráfico
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
            flash('Dados do vendedor não encontrados.', 'error')
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
    
    try:
        db = DatabaseManager()
        query = """
        Select v.Codigo, v.Nome_Guerra, v.Cod_EstabeOpe, v.Vlr_Objetivo, Vlr_Realizado = IsNull(n.Vlr_Realizado,0), 
               v.Cod_Supervisor, Vlr_Comissao = IsNull(n.Vlr_Comissao,0),
             v.Email, CPF_CNPJ = v.Cgc, 
             Situacao = Case When v.Bloqueado = 0 Then 
                     'INATIVO'
                    Else 
                      'ATIVO'
                  End
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
        Order by v.Nome_Guerra
        """
        
        vendedores = db.execute_query(query)
        
        # Preparar dados para gráficos
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
                             chart_data=chart_data)
            
    except Exception as e:
        flash(f'Erro ao buscar dados: {str(e)}', 'error')
        return render_template('admin.html')

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