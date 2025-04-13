from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
import sqlite3
import os
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['SECRET_KEY'] = 'supersecretkey'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# Crear base de datos
def init_db():
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            brand TEXT NOT NULL,
            price REAL NOT NULL,
            place TEXT NOT NULL,
            image_path TEXT NOT NULL,
            upload_date TEXT NOT NULL
        )''')
        conn.commit()

# Verificar extensión de archivo
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Servir el manifest.json
@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('static', 'manifest.json')

# Ruta principal
@app.route('/')
def index():
    return render_template('upload.html')

# Subir producto
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        name = request.form['name']
        brand = request.form['brand']
        price = request.form['price']
        place = request.form['place']
        file = request.files['image']

        if not (name and brand and price and place and file):
            flash('Por favor, completa todos los campos.')
            return redirect(url_for('upload'))

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            with sqlite3.connect('database.db') as conn:
                c = conn.cursor()
                c.execute('INSERT INTO products (name, brand, price, place, image_path, upload_date) VALUES (?, ?, ?, ?, ?, ?)',
                          (name, brand, float(price), place, file_path, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit()
            flash('Producto subido exitosamente!')
            return redirect(url_for('upload'))
        else:
            flash('Archivo no permitido. Usa PNG, JPG o JPEG.')
            return redirect(url_for('upload'))

    return render_template('upload.html')

# Comparar productos
@app.route('/compare', methods=['GET', 'POST'])
def compare():
    products = []
    if request.method == 'POST':
        name = request.form['name']
        brand = request.form['brand']
        with sqlite3.connect('database.db') as conn:
            c = conn.cursor()
            query = 'SELECT name, brand, price, place, image_path, upload_date FROM products WHERE name LIKE ? AND brand LIKE ?'
            c.execute(query, (f'%{name}%', f'%{brand}%'))
            products = c.fetchall()
    return render_template('compare.html', products=products)

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    init_db()
    app.run(debug=True)