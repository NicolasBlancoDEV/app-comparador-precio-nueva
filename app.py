from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, make_response, session, send_file
import sqlite3
import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import secrets
import pytz

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'

# Definir la ruta de la base de datos dinámicamente
if os.getenv('RENDER'):
    DATABASE = '/opt/render/project/src/database.db'
else:
    DATABASE = os.path.join(os.path.dirname(__file__), 'database.db')

# Definir el usuario administrador desde una variable de entorno
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'tu_usuario')  # Por defecto, "tu_usuario" si no está definida

# Configurar Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Configurar la zona horaria de Argentina (UTC-3)
argentina_tz = pytz.timezone('America/Argentina/Buenos_Aires')

# Resto del código sigue igual...

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
        # Asegurarse de que el directorio exista (por si DATABASE incluye subdirectorios)
        db_dir = os.path.dirname(DATABASE)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
        conn = sqlite3.connect(DATABASE)
        return conn
    except sqlite3.Error as e:
        print(f"Error al conectar a la base de datos: {e}")
        raise e

# Obtener la fecha actual en la zona horaria de Argentina
def get_current_time():
    return datetime.now(argentina_tz).strftime('%Y-%m-%d %H:%M:%S')

# Convertir timestamp a la zona horaria de Argentina
def to_argentina_time(timestamp):
    try:
        dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
        dt = argentina_tz.localize(dt)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        return timestamp

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
            # Tabla de mensajes del chat
            c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )''')
            # Tabla para tokens de recuperación de contraseña
            c.execute('''CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT NOT NULL,
                expiry TEXT NOT NULL,
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
    saved_username = request.cookies.get('username', '')
    saved_password_hash = request.cookies.get('password_hash', '')

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        remember = request.form.get('remember') == 'on'

        try:
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute('SELECT id, username, password, email FROM users WHERE username = ?', (username,))
                user = c.fetchone()
                if user and check_password_hash(user[2], password):
                    user_obj = User(user[0], user[1], user[3])
                    login_user(user_obj)

                    response = make_response(redirect(url_for('index')))
                    if remember:
                        response.set_cookie('username', username, max_age=30*24*60*60)
                        response.set_cookie('password_hash', user[2], max_age=30*24*60*60)
                    else:
                        response.set_cookie('username', '', expires=0)
                        response.set_cookie('password_hash', '', expires=0)

                    flash('Inicio de sesión exitoso.')
                    return response
                else:
                    flash('Nombre de usuario o contraseña incorrectos.')
                    return redirect(url_for('login'))
        except sqlite3.Error as e:
            flash(f'Error al iniciar sesión: {e}')
            print(f"Error al iniciar sesión: {e}")
            return redirect(url_for('login'))

    return render_template('login.html', saved_username=saved_username, saved_password_hash=saved_password_hash)

# Cierre de sesión
@app.route('/logout')
@login_required
def logout():
    logout_user()
    # Limpiar el carrito al cerrar sesión
    session.pop('cart', None)
    response = make_response(redirect(url_for('index')))
    response.set_cookie('username', '', expires=0)
    response.set_cookie('password_hash', '', expires=0)
    flash('Has cerrado sesión.')
    return response

# Página principal (productos ordenados por fecha)
@app.route('/')
def index():
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT id, name, brand, price, place, upload_date FROM products ORDER BY upload_date DESC')
            products = c.fetchall()
            products = [(p[0], p[1], p[2], p[3], p[4], to_argentina_time(p[5])) for p in products]
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
                          (name, brand, price, place, get_current_time()))
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
                products = [(p[0], p[1], p[2], p[3], p[4], to_argentina_time(p[5])) for p in products]
        except sqlite3.Error as e:
            flash(f'Error al buscar productos: {e}')
            print(f"Error al buscar productos: {e}")
    else:
        try:
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute('SELECT id, name, brand, price, place, upload_date FROM products ORDER BY upload_date DESC')
                products = c.fetchall()
                products = [(p[0], p[1], p[2], p[3], p[4], to_argentina_time(p[5])) for p in products]
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
                          (current_user.id, message, get_current_time()))
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
            messages = [(m[0], m[1], to_argentina_time(m[2])) for m in messages]
    except sqlite3.Error as e:
        flash(f'Error al cargar los mensajes: {e}')
        print(f"Error al cargar los mensajes: {e}")
        messages = []
    return render_template('chat.html', messages=messages)

# Solicitar recuperación de contraseña
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']

        try:
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute('SELECT id, username FROM users WHERE email = ?', (email,))
                user = c.fetchone()
                if user:
                    token = secrets.token_urlsafe(32)
                    expiry = (datetime.now(argentina_tz) + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
                    c.execute('INSERT INTO password_reset_tokens (user_id, token, expiry) VALUES (?, ?, ?)',
                              (user[0], token, expiry))
                    conn.commit()

                    reset_link = url_for('reset_password', token=token, _external=True)
                    flash(f'Enlace de recuperación (simulado): {reset_link}')
                else:
                    flash('No se encontró un usuario con ese email.')
                return redirect(url_for('forgot_password'))
        except sqlite3.Error as e:
            flash(f'Error al procesar la solicitud: {e}')
            print(f"Error al procesar la solicitud: {e}")
            return redirect(url_for('forgot_password'))

    return render_template('forgot_password.html')

# Restablecer contraseña
@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT user_id, expiry FROM password_reset_tokens WHERE token = ?', (token,))
            token_data = c.fetchone()
            if not token_data:
                flash('El enlace de recuperación es inválido.')
                return redirect(url_for('login'))

            expiry = datetime.strptime(token_data[1], '%Y-%m-%d %H:%M:%S')
            expiry = argentina_tz.localize(expiry)
            if datetime.now(argentina_tz) > expiry:
                flash('El enlace de recuperación ha expirado.')
                c.execute('DELETE FROM password_reset_tokens WHERE token = ?', (token,))
                conn.commit()
                return redirect(url_for('login'))

            if request.method == 'POST':
                new_password = request.form['password']
                if not new_password:
                    flash('Por favor, ingresa una nueva contraseña.')
                    return redirect(url_for('reset_password', token=token))

                hashed_password = generate_password_hash(new_password)
                c.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_password, token_data[0]))
                c.execute('DELETE FROM password_reset_tokens WHERE token = ?', (token,))
                conn.commit()
                flash('Contraseña restablecida exitosamente. Por favor, inicia sesión.')
                return redirect(url_for('login'))

            return render_template('reset_password.html', token=token)
    except (sqlite3.Error, ValueError) as e:
        flash(f'Error al procesar el restablecimiento: {e}')
        print(f"Error al procesar el restablecimiento: {e}")
        return redirect(url_for('login'))

# Agregar producto al carrito
@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT id, name, brand, price, place FROM products WHERE id = ?', (product_id,))
            product = c.fetchone()
            if not product:
                flash('Producto no encontrado.')
                return redirect(request.referrer or url_for('index'))

            # Inicializar el carrito en la sesión si no existe
            if 'cart' not in session:
                session['cart'] = []

            # Agregar el producto al carrito
            session['cart'].append({
                'id': product[0],
                'name': product[1],
                'brand': product[2],
                'price': product[3],
                'place': product[4]
            })
            session.modified = True  # Marcar la sesión como modificada

            flash(f'{product[1]} ({product[2]}) añadido al carrito.')
            return redirect(request.referrer or url_for('index'))
    except sqlite3.Error as e:
        flash(f'Error al agregar al carrito: {e}')
        print(f"Error al agregar al carrito: {e}")
        return redirect(request.referrer or url_for('index'))

# Ver el carrito
@app.route('/cart')
def cart():
    cart_items = session.get('cart', [])
    total_price = sum(item['price'] for item in cart_items) if cart_items else 0
    return render_template('cart.html', cart_items=cart_items, total_price=total_price)

# Vaciar el carrito
@app.route('/clear_cart', methods=['POST'])
def clear_cart():
    session.pop('cart', None)
    flash('Carrito vaciado.')
    return redirect(url_for('cart'))

# Descargar la base de datos
@app.route('/download_db')
@login_required
def download_db():
    # Restringir el acceso solo al usuario administrador
    if current_user.username != ADMIN_USERNAME:
        flash('No tienes permiso para descargar la base de datos.')
        return redirect(url_for('index'))

    try:
        if not os.path.exists(DATABASE):
            flash('La base de datos no existe.')
            return redirect(url_for('index'))

        return send_file(DATABASE, as_attachment=True, download_name='database.db')
    except Exception as e:
        flash(f'Error al descargar la base de datos: {e}')
        print(f"Error al descargar la base de datos: {e}")
        return redirect(url_for('index'))

# Subir una nueva base de datos
@app.route('/upload_db', methods=['GET', 'POST'])
@login_required
def upload_db():
    # Restringir el acceso solo al usuario administrador
    if current_user.username != ADMIN_USERNAME:
        flash('No tienes permiso para subir una base de datos.')
        return redirect(url_for('index'))

    if request.method == 'POST':
        if 'db_file' not in request.files:
            flash('No se seleccionó ningún archivo.')
            return redirect(url_for('upload_db'))

        db_file = request.files['db_file']
        if db_file.filename == '':
            flash('No se seleccionó ningún archivo.')
            return redirect(url_for('upload_db'))

        if not db_file.filename.endswith('.db'):
            flash('El archivo debe ser un archivo .db')
            return redirect(url_for('upload_db'))

        try:
            conn = sqlite3.connect(DATABASE)
            conn.close()

            db_file.save(DATABASE)
            flash('Base de datos subida exitosamente.')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Error al subir la base de datos: {e}')
            print(f"Error al subir la base de datos: {e}")
            return redirect(url_for('upload_db'))

    return render_template('upload_db.html')
# Inicializar la app
with app.app_context():
    init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)