import os
import sqlite3
import re
from flask import Flask, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-for-dev')
DB_PATH = 'database/shop.db'

# Дерекқорға қосылу функциясы
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Нәтижені dict ретінде алу үшін
    return conn

# Дерекқорды іске қосу (Кестелерді құру және тауарларды енгізу)
def init_db():
    if not os.path.exists('database'):
        os.makedirs('database')
    conn = get_db_connection()
    with open('database/schema.sql', 'r') as f:
        conn.executescript(f.read())
    
    # Егер тауарлар бос болса, seed деректерін енгіземіз
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        with open('database/seed.sql', 'r') as f:
            conn.executescript(f.read())
    conn.commit()
    conn.close()

# --- 1. АУТЕНТИФИКАЦИЯ (Тіркелу және Кіру) ---

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    # Валидация (Міндетті өрістерді тексеру)
    if not username or not email or not password:
        return jsonify({"error": "Барлық өрістерді толтырыңыз!"}), 400
    
    # Email форматын валидациялау (Regex)
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return jsonify({"error": "Email форматы қате!"}), 400

    # Құпия сөзді хэштеу (Қауіпсіздік талабы)
    password_hash = generate_password_hash(password)

    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (username, email, password_hash) # Параметрленген сұрау (SQL инъекциядан қорғаныс)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Бұл username немесе email бос емес!"}), 400
    finally:
        conn.close()

    return jsonify({"message": "Пайдаланушы сәтті тіркелді!"}), 201

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()

    # Хэшті тексеру
    if user and check_password_hash(user['password_hash'], password):
        session['user_id'] = user['id'] # Сессияға сақтау
        return jsonify({"message": f"Қош келдіңіз, {user['username']}!", "user_id": user['id']}), 200
    
    return jsonify({"error": "Логин немесе құпия сөз қате!"}), 401


# --- 2. CRUD ОПЕРАЦИЯЛАРЫ ЖӘНЕ ІЗДЕУ (Тауарлармен жұмыс) ---

# Тексеру (GET) + Іздеу және Сүзгілеу (Сериялы түрде іздеу)
@app.route('/api/products', methods=['GET'])
def get_products():
    search_query = request.args.get('search', '')
    category_query = request.args.get('category', '')

    conn = get_db_connection()
    
    # Динамикалық SQL сұраныс іздеу мен сүзгі үшін
    sql = "SELECT * FROM products WHERE title LIKE ? AND category LIKE ?"
    params = (f'%{search_query}%', f'%{category_query}%')
    
    products = conn.execute(sql, params).fetchall()
    conn.close()

    return jsonify([dict(row) for row in products]), 200

# Бір тауарды ID бойынша алу (GET)
@app.route('/api/products/<int:id>', methods=['GET'])
def get_product(id):
    conn = get_db_connection()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (id,)).fetchone()
    conn.close()
    
    if product is None:
        return jsonify({"error": "Тауар табылмады!"}), 404
    return jsonify(dict(product)), 200

# Жаңа тауар қосу (POST)
@app.route('/api/products', methods=['POST'])
def create_product():
    data = request.json
    title = data.get('title')
    category = data.get('category')
    price = data.get('price')
    stock = data.get('stock')

    if not title or not category or price is None or stock is None:
        return jsonify({"error": "Деректер толық емес!"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (title, category, price, stock) VALUES (?, ?, ?, ?)",
        (title, category, price, stock)
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()

    return jsonify({"message": "Тауар қосылды!", "product_id": new_id}), 201

# Тауарды жаңарту (PUT)
@app.route('/api/products/<int:id>', methods=['PUT'])
def update_product(id):
    data = request.json
    conn = get_db_connection()
    
    # Тауардың бар-жоғын тексеру (404 қатесін өңдеу)
    product = conn.execute("SELECT * FROM products WHERE id = ?", (id,)).fetchone()
    if not product:
        conn.close()
        return jsonify({"error": "Жаңартылатын тауар табылмады!"}), 404

    conn.execute(
        "UPDATE products SET title=?, category=?, price=?, stock=? WHERE id=?",
        (data.get('title'), data.get('category'), data.get('price'), data.get('stock'), id)
    )
    conn.commit()
    conn.close()
    return jsonify({"message": "Тауар сәтті жаңартылды!"}), 200

# Тауарды өшіру (DELETE)
@app.route('/api/products/<int:id>', methods=['DELETE'])
def delete_product(id):
    conn = get_db_connection()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (id,)).fetchone()
    
    if not product:
        conn.close()
        return jsonify({"error": "Өшірілетін тауар табылмады!"}), 404

    conn.execute("DELETE FROM products WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Тауар өшірілді!"}), 200


# --- 3. ТАПСЫРЫС БЕРУ (Байланысқан үшінші кестемен жұмыс) ---
@app.route('/api/orders', methods=['POST'])
def create_order():
    # Талап: Пайдаланушы жүйеге кірген болуы керек (сессия тексеру)
    if 'user_id' not in session:
        return jsonify({"error": "Алдымен жүйеге кіріңіз (Авторизация)!"}), 401

    data = request.json
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)

    conn = get_db_connection()
    # Тауардың қоймада бар-жоғын тексеру
    product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product or product['stock'] < quantity:
        conn.close()
        return jsonify({"error": "Тауар жеткіліксіз немесе табылмады!"}), 400

    # Тапсырыс құру және қойма санын азайту
    conn.execute(
        "INSERT INTO orders (user_id, product_id, quantity) VALUES (?, ?, ?)",
        (session['user_id'], product_id, quantity)
    )
    conn.execute(
        "UPDATE products SET stock = stock - ? WHERE id = ?", 
        (quantity, product_id)
    )
    conn.commit()
    conn.close()

    return jsonify({"message": "Тапсырыс сәтті қабылданды!"}), 201


if __name__ == '__main__':
    init_db()  # Қосымша қосылғанда дерекқор автоматты түрде құрылады
    app.run(debug=True, port=5000)