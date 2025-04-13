from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
import sqlite3
import os
from datetime import datetime
from werkzeug.utils import secure_filename
import cloudinary
import cloudinary.uploader
import cloudinary.api
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Límite de 16 MB para las imágenes
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
DATABASE = '/opt/render/project/src/database.db'

# Configurar Cloudinary
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

# Filtro para formatear precios
@app.template_filter('format_price')
def format_price(value):
    return "${:,.2f}".format(value).replace(',', 'X').replace('.', ',').replace('X', '.')

# Crear base de datos
def init_db():
    try:
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                brand TEXT NOT NULL,
                price REAL NOT NULL,
                place TEXT NOT NULL,
                image_url TEXT NOT NULL,  -- Cambiamos image_path a image_url
                upload_date TEXT NOT NULL
            )''')
            conn.commit()
        print("Base de datos inicializada correctamente")
    except sqlite3.Error as e:
        print(f"Error al crear la base de datos: {e}")

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

        # Validar y convertir el precio
        try:
            price = float(price)
            if price < 0:
                raise ValueError("El precio no puede ser negativo")
        except ValueError:
            flash('Por favor, ingresa un precio válido (número positivo).')
            return redirect(url_for('upload'))

        if file and allowed_file(file.filename):
            try:
                # Subir la imagen a Cloudinary
                upload_result = cloudinary.uploader.upload(file, folder="comparador-precios")
                image_url = upload_result['secure_url']
                print(f"Imagen subida a Cloudinary: {image_url}")
            except Exception as e:
                flash(f'Error al subir la imagen a Cloudinary: {e}')
                print(f"Error al subir la imagen: {e}")
                return redirect(url_for('upload'))

            try:
                with sqlite3.connect(DATABASE) as conn:
                    c = conn.cursor()
                    c.execute('INSERT INTO products (name, brand, price, place, image_url, upload_date) VALUES (?, ?, ?, ?, ?, ?)',
                              (name, brand, price, place, image_url, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                    conn.commit()
                flash('Producto subido exitosamente!')
                print("Producto guardado en la base de datos")
                return redirect(url_for('upload'))
            except sqlite3.Error as e:
                flash(f'Error al guardar el producto: {e}')
                print(f"Error al guardar el producto: {e}")
                return redirect(url_for('upload'))
        else:
            flash('Archivo no permitido. Usa PNG, JPG o JPEG.')
            return redirect(url_for('upload'))

    return render_template('upload.html')

# Ver todos los productos
@app.route('/products', methods=['GET', 'POST'])
def products():
    products = []
    search_query = ''
    if request.method == 'POST':
        search_query = request.form.get('search', '').strip()
        try:
            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                query = '''SELECT id, name, brand, price, place, image_url, upload_date 
                          FROM products 
                          WHERE name LIKE ? OR brand LIKE ? OR place LIKE ?'''
                c.execute(query, (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))
                products = c.fetchall()
        except sqlite3.Error as e:
            flash(f'Error al buscar productos: {e}')
            print(f"Error al buscar productos: {e}")
    else:
        try:
            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                c.execute('SELECT id, name, brand, price, place, image_url, upload_date FROM products')
                products = c.fetchall()
        except sqlite3.Error as e:
            flash(f'Error al cargar productos: {e}')
            print(f"Error al cargar productos: {e}")
    return render_template('products.html', products=products, search_query=search_query)

# Comparar productos
@app.route('/compare', methods=['GET', 'POST'])
def compare():
    products = []
    if request.method == 'POST':
        name = request.form['name']
        brand = request.form['brand']
        try:
            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                query = 'SELECT id, name, brand, price, place, image_url, upload_date FROM products WHERE name LIKE ? AND brand LIKE ?'
                c.execute(query, (f'%{name}%', f'%{brand}%'))
                products = c.fetchall()
        except sqlite3.Error as e:
            flash(f'Error al buscar productos: {e}')
            print(f"Error al buscar productos: {e}")
    return render_template('compare.html', products=products)

# Modificar precio de un producto
@app.route('/edit/<int:product_id>', methods=['GET', 'POST'])
def edit(product_id):
    if request.method == 'POST':
        new_price = request.form['price']
        try:
            new_price = float(new_price)
            if new_price < 0:
                raise ValueError("El precio no puede ser negativo")
        except ValueError:
            flash('Por favor, ingresa un precio válido (número positivo).')
            return redirect(url_for('products'))

        try:
            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                c.execute('UPDATE products SET price = ? WHERE id = ?', (new_price, product_id))
                conn.commit()
            flash('Precio actualizado exitosamente!')
        except sqlite3.Error as e:
            flash(f'Error al actualizar el precio: {e}')
            print(f"Error al actualizar el precio: {e}")
        return redirect(url_for('products'))

    try:
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            c.execute('SELECT id, name, brand, price FROM products WHERE id = ?', (product_id,))
            product = c.fetchone()
        if not product:
            flash('Producto no encontrado.')
            return redirect(url_for('products'))
    except sqlite3.Error as e:
        flash(f'Error al cargar el producto: {e}')
        print(f"Error al cargar el producto: {e}")
        return redirect(url_for('products'))
    return render_template('edit.html', product=product)

# Eliminar un producto
@app.route('/delete/<int:product_id>', methods=['POST'])
def delete(product_id):
    try:
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            c.execute('SELECT image_url FROM products WHERE id = ?', (product_id,))
            product = c.fetchone()
            if product:
                # Eliminar la imagen de Cloudinary
                public_id = product[0].split('/')[-1].split('.')[0]  # Extraer el public_id de la URL
                cloudinary.uploader.destroy(f"comparador-precios/{public_id}")
                print(f"Imagen eliminada de Cloudinary: {public_id}")
                # Eliminar el producto de la base de datos
                c.execute('DELETE FROM products WHERE id = ?', (product_id,))
                conn.commit()
                flash('Producto eliminado exitosamente!')
            else:
                flash('Producto no encontrado.')
    except (sqlite3.Error, Exception) as e:
        flash(f'Error al eliminar el producto: {e}')
        print(f"Error al eliminar el producto: {e}")
    return redirect(url_for('products'))

# Inicializar la app
with app.app_context():
    init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)