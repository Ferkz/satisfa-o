import sqlite3
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import matplotlib.pyplot as plt
import io
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'uma_string_bem_grande_e_difícil')

DATABASE = 'survey.db'

# Credenciais de teste para o RH
RH_CREDENTIALS = {
    "rh1": "senha123",
    "rh2": "secret456"
}


def get_db_connection():
    conn = sqlite3.connect('survey.db')  # Ajuste o caminho do seu banco de dados aqui
    conn.row_factory = sqlite3.Row  # Faz com que as linhas retornadas sejam dicionários
    return conn


@app.template_filter('format_datetime')
def format_datetime(value):
    if not value:
        return ''
    dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return dt.strftime("%d/%m/%Y %H:%M")


@app.route('/', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        cpf = request.form['cpf'].strip()
        data_nascimento = request.form['data_nascimento']

        if not cpf.isdigit():
            error = 'Use somente números no campo CPF.'
            return render_template('./login/login.html', error=error)

        # Abrir a conexão com o banco de dados
        conn = get_db_connection()

        try:
            # Realizar consulta para verificar se o colaborador existe no banco
            user = conn.execute(
                'SELECT * FROM colaboradores WHERE cpf = ? AND data_nascimento = ?',
                (cpf, data_nascimento)
            ).fetchone()  # Isso retornará uma tupla ou None se não encontrar

            if user:  # Verifica se o usuário foi encontrado
                if user['respondeu']:  # Checa se o usuário já respondeu
                    error = 'Você já respondeu à pesquisa.'
                else:
                    conn.close()
                    return redirect(
                        url_for('pesquisa', user_id=user['id']))  # Redireciona para o formulário de pesquisa
            else:
                error = 'Dados inválidos.'

        except Exception as e:
            error = f'Ocorreu um erro: {e}'

        finally:
            conn.close()  # Fecha a conexão com o banco de dados

    return render_template('./login/login.html', error=error)

@app.route('/pesquisa/<int:user_id>', methods=['GET', 'POST'])
def pesquisa(user_id):
    if request.method == 'POST':
        # Captura as respostas dos campos 'resposta1', 'resposta2', ..., 'resposta10'
        respostas = [request.form.get(f'resposta{i}') for i in range(1, 11)]  # A alteração aqui, de resposta9 para resposta10

        # Verifica se todas as respostas foram preenchidas
        if not all(respostas):
            flash('Por favor, responda todas as perguntas.')
            return redirect(url_for('pesquisa', user_id=user_id))  # Redireciona de volta para a pesquisa

        # Abre a conexão com o banco de dados e insere as respostas
        with get_db_connection() as conn:
            conn.execute('''
                INSERT INTO respostas (
                    resposta1, resposta2, resposta3, resposta4, resposta5, resposta6,
                    resposta7, resposta8, resposta9, resposta10
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', respostas)

            # Atualiza a tabela de colaboradores para indicar que ele já respondeu
            conn.execute(
                'UPDATE colaboradores SET respondeu = 1 WHERE id = ?',
                (user_id,)
            )
            conn.commit()

        return redirect(url_for('pesquisa_concluida'))  # Redireciona para a página de "Obrigado"

    return render_template('login/pesquisa.html', user_id=user_id)





@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        with get_db_connection() as conn:
            try:
                user = conn.execute(
                    'SELECT * FROM admins WHERE username = ? AND password = ?',
                    (username, password)
                ).fetchone()

                if user:
                    session['admin_logged_in'] = True
                    return redirect(url_for('admin'))
                else:
                    error = 'Usuário ou senha incorretos.'

            except Exception as e:
                error = f'Ocorreu um erro: {str(e)}'

    return render_template('login/admin_login.html', error=error)


@app.route('/admin')
def admin():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    with get_db_connection() as conn:
        respostas = conn.execute(
            'SELECT * FROM respostas ORDER BY data_resposta DESC'
        ).fetchall()

        medias = []
        for i in range(1, 9):
            coluna = f"resposta{i}"
            result = conn.execute(
                f'SELECT AVG(CAST({coluna} AS FLOAT)) as media FROM respostas'
            ).fetchone()
            medias.append(round(result[0], 2) if result[0] is not None else 0)  # Usando índice numérico

        charts = []
        questions = conn.execute('SELECT * FROM form_questions ORDER BY order_index').fetchall()
        for q in questions:
            opts = conn.execute(
                'SELECT option_label, COUNT(ra.id) AS cnt '
                'FROM form_options o '
                'LEFT JOIN response_answers ra '
                '  ON ra.question_id = o.question_id AND ra.answer = o.option_value '
                'WHERE o.question_id = ? '
                'GROUP BY o.id',
                (q['id'],)
            ).fetchall()

            labels = [o['option_label'] for o in opts]
            values = [o['cnt'] for o in opts]

            fig, ax = plt.subplots()
            ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
            ax.axis('equal')

            img = io.BytesIO()
            FigureCanvas(fig).print_png(img)
            img.seek(0)
            charts.append({
                'id': q['id'],
                'text': q['question_text'],
                'img': img
            })

    return render_template('login/admin.html', charts=charts, respostas=respostas, medias=medias)
@app.route('/admin/chart/<int:chart_id>')
def chart(chart_id):
    chart = next((chart for chart in charts if chart['id'] == chart_id), None)
    if not chart:
        return "Gráfico não encontrado", 404
    return send_file(chart['img'], mimetype='image/png')


if __name__ == '__main__':
    app.run(debug=True, port=10000)
