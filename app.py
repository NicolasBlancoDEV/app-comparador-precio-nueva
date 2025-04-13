from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'
DATABASE = '/opt/render/project/src/database.db'

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

# Crear la tabla de productos y chat
def init_db():
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                brand TEXT NOT NULL,
                price REAL NOT NULL,
                place TEXT NOT NULL,
                upload_date TEXT NOT NULL
            )''')
            # Tabla para mensajes del chat
            c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )''')
            conn.commit()
        print("Base de datos inicializada correctamente")
    except sqlite3.Error as e:
        print(f"Error al crear la base de datos: {e}")

# Servir el manifest.json
@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('static', 'manifest.json')

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

        # Validar y convertir el precio
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

# Chat universal
@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if request.method == 'POST':
        username = request.form['username']
        message = request.form['message']

        if not (username and message):
            flash('Por favor, completa todos los campos.')
            return redirect(url_for('chat'))

        try:
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute('INSERT INTO chat_messages (username, message, timestamp) VALUES (?, ?, ?)',
                          (username, message, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
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
            c.execute('SELECT username, message, timestamp FROM chat_messages ORDER BY timestamp DESC LIMIT 50')
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