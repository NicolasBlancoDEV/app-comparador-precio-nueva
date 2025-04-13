from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'
DATABASE = '/opt/render/project/src/database.db'

# Configurar Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Modelo de usuario para Flask-Login
class User(UserMixin):
    def __init__(self, id, username, email):
        self.id = id
        self.username = username
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT id, username, email FROM users WHERE id = ?', (user_id,))
            user = c.fetchone()
            if user:
                return User(user[0], user[1], user[2])
            return None
    except sqlite3.Error as e:
        print(f"Error al cargar usuario: {e}")
        return None

# Filtro para formatear precios
@app.template_filter('format_price')
def format_price(value):
    return "${:,.2f}".format(value).replace(',', 'X').replace('.', ',').replace('X', '.')

# Conectar a la base de datos SQLite
def get_db_connection():
    try:
        conn = sqlite3.connect(DATABASE)
        return conn
    except sqlite3.Error as e:
        print(f"Error al conectar a la base de datos: {e}")
        raise e

# Crear las tablas
def init_db():
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            # Tabla de productos
            c.execute('''CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                brand TEXT NOT NULL,
                price REAL NOT NULL,
                place TEXT NOT NULL,
                upload_date TEXT NOT NULL
            )''')
            # Tabla de usuarios
            c.execute('''CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE
            )''')
            # Tabla de mensajes del chat (modificada para usar user_id)
            c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )''')
            conn.commit()
        print("Base de datos inicializada correctamente")
    except sqlite3.Error as e:
        print(f"Error al crear la base de datos: {e}")

# Servir el manifest.json
@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('static', 'manifest.json')

# Registro de usuarios
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']

        if not (username and password and email):
            flash('Por favor, completa todos los campos.')
            return redirect(url_for('register'))

        try:
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute('SELECT id FROM users WHERE username = ? OR email = ?', (username, email))
                existing_user = c.fetchone()
                if existing_user:
                    flash('El nombre de usuario o email ya está registrado.')
                    return redirect(url_for('register'))

                hashed_password = generate_password_hash(password)
                c.execute('INSERT INTO users (username, password, email) VALUES (?, ?, ?)',
                          (username, hashed_password, email))
                conn.commit()
            flash('Registro exitoso. Por favor, inicia sesión.')
            return redirect(url_for('login'))
        except sqlite3.Error as e:
            flash(f'Error al registrarte: {e}')
            print(f"Error al registrar usuario: {e}")
            return redirect(url_for('register'))

    return render_template('register.html')

# Inicio de sesión
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute('SELECT id, username, password, email FROM users WHERE username = ?', (username,))
                user = c.fetchone()
                if user and check_password_hash(user[2], password):
                    user_obj = User(user[0], user[1], user[3])
                    login_user(user_obj)
                    flash('Inicio de sesión exitoso.')
                    return redirect(url_for('index'))
                else:
                    flash('Nombre de usuario o contraseña incorrectos.')
                    return redirect(url_for('login'))
        except sqlite3.Error as e:
            flash(f'Error al iniciar sesión: {e}')
            print(f"Error al iniciar sesión: {e}")
            return redirect(url_for('login'))

    return render_template('login.html')

# Cierre de sesión
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Has cerrado sesión.')
    return redirect(url_for('index'))

# Página principal (productos ordenados por fecha)
@app.route('/')
def index():
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT id, name, brand, price, place, upload_date FROM products ORDER BY upload_date DESC')
            products = c.fetchall()
    except sqlite3.Error as e:
        flash(f'Error al cargar productos: {e}')
        print(f"Error al cargar productos: {e}")
        products = []
    return render_template('index.html', products=products)

# Subir producto
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        name = request.form['name']
        brand = request.form['brand']
        price = request.form['price']
        place = request.form['place']

        if not (name and brand and price and place):
            flash('Por favor, completa todos los campos.')
            return redirect(url_for('upload'))

        try:
            price = float(price)
            if price < 0:
                raise ValueError("El precio no puede ser negativo")
        except ValueError:
            flash('Por favor, ingresa un precio válido (número positivo).')
            return redirect(url_for('upload'))

        try:
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute('INSERT INTO products (name, brand, price, place, upload_date) VALUES (?, ?, ?, ?, ?)',
                          (name, brand, price, place, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit()
            flash('Producto subido exitosamente!')
            print("Producto guardado en la base de datos")
            return redirect(url_for('upload'))
        except sqlite3.Error as e:
            flash(f'Error al guardar el producto: {e}')
            print(f"Error al guardar el producto: {e}")
            return redirect(url_for('upload'))

    return render_template('upload.html')

# Filtrar productos
@app.route('/filter', methods=['GET', 'POST'])
def filter_products():
    products = []
    search_query = ''
    if request.method == 'POST':
        search_query = request.form.get('search', '').strip()
        try:
            with get_db_connection() as conn:
                c = conn.cursor()
                query = '''SELECT id, name, brand, price, place, upload_date 
                          FROM products 
                          WHERE name LIKE ? OR brand LIKE ? OR place LIKE ? 
                          ORDER BY upload_date DESC'''
                c.execute(query, (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))
                products = c.fetchall()
        except sqlite3.Error as e:
            flash(f'Error al buscar productos: {e}')
            print(f"Error al buscar productos: {e}")
    else:
        try:
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute('SELECT id, name, brand, price, place, upload_date FROM products ORDER BY upload_date DESC')
                products = c.fetchall()
        except sqlite3.Error as e:
            flash(f'Error al cargar productos: {e}')
            print(f"Error al cargar productos: {e}")
    return render_template('filter.html', products=products, search_query=search_query)

# Chat universal (restringido a usuarios autenticados)
@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    if request.method == 'POST':
        message = request.form['message']

        if not message:
            flash('Por favor, escribe un mensaje.')
            return redirect(url_for('chat'))

        try:
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute('INSERT INTO chat_messages (user_id, message, timestamp) VALUES (?, ?, ?)',
                          (current_user.id, message, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit()
            flash('Mensaje enviado!')
            return redirect(url_for('chat'))
        except sqlite3.Error as e:
            flash(f'Error al enviar el mensaje: {e}')
            print(f"Error al enviar el mensaje: {e}")
            return redirect(url_for('chat'))

    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('''SELECT u.username, cm.message, cm.timestamp 
                         FROM chat_messages cm 
                         JOIN users u ON cm.user_id = u.id 
                         ORDER BY cm.timestamp DESC LIMIT 50''')
            messages = c.fetchall()
    except sqlite3.Error as e:
        flash(f'Error al cargar los mensajes: {e}')
        print(f"Error al cargar los mensajes: {e}")
        messages = []
    return render_template('chat.html', messages=messages)

# Inicializar la app
with app.app_context():
    init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)