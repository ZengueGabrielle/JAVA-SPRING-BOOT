import sqlite3
import os
from flask import Flask, request, jsonify, send_from_directory
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
DB_NAME = "prime.db"
UPLOAD_FOLDER = 'uploads/avatars'

# S'assurer que le dossier d'upload existe
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    # Table Utilisateurs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT UNIQUE,
            password TEXT,
            first_name TEXT,
            last_name TEXT,
            profile_picture TEXT,
            subscription_status TEXT,
            created_at TEXT
        )
    ''')
    # Table Contenus
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            content_type TEXT,
            release_year INTEGER,
            age_rating TEXT,
            thumbnail_url TEXT,
            requires_extra_payment BOOLEAN
        )
    ''')
    
    # Insérer les données par défaut si la table contents est vide
    cursor.execute("SELECT COUNT(*) FROM contents")
    if cursor.fetchone()[0] == 0:
        default_contents = [
            ("The Boys", "Un groupe de justiciers s'attaque à des super-héros corrompus.", "SERIES", 2019, "18+", "https://cdn.prime.local/thumbs/theboys.jpg", False),
            ("Invincible", "Mark Grayson est un adolescent normal, sauf que son père est le super-héros le plus puissant.", "SERIES", 2021, "16+", "https://cdn.prime.local/thumbs/invincible.jpg", False)
        ]
        cursor.executemany('''
            INSERT INTO contents (title, description, content_type, release_year, age_rating, thumbnail_url, requires_extra_payment)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', default_contents)
    
    conn.commit()
    conn.close()

# Initialiser la base de données au démarrage
init_db()

def dict_from_row(row):
    return dict(zip(row.keys(), row))

# Route pour servir les images uploadées (pour tester que l'upload marche bien)
@app.route('/uploads/avatars/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- ROUTES AUTHENTIFICATION ---
@app.route('/api/v1/auth/register', methods=['POST'])
def register():
    # Avec multipart/form-data, on utilise request.form au lieu de request.get_json()
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    first_name = request.form.get('firstName', '')
    last_name = request.form.get('lastName', '')

    if not email or not password or not username:
        return jsonify({
            "status": 400,
            "error": "Bad Request",
            "message": "Paramètres manquants (username, email, password)"
        }), 400

    # Gestion de l'upload du fichier profilePicture
    profile_picture_url = ""
    if 'profilePicture' in request.files:
        file = request.files['profilePicture']
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            # Sauvegarder le fichier physiquement
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{username}_{filename}")
            file.save(file_path)
            # Générer l'URL locale pour y accéder
            profile_picture_url = f"http://localhost:8080/uploads/avatars/{username}_{filename}"
        
    conn = get_db()
    cursor = conn.cursor()
    try:
        created_at = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO users (username, email, password, first_name, last_name, profile_picture, subscription_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            username,
            email,
            password, # Note: en production, il faut hacher le mot de passe !
            first_name,
            last_name,
            profile_picture_url,
            'ACTIVE',
            created_at
        ))
        conn.commit()
        user_id = cursor.lastrowid
        
        # Récupérer l'utilisateur créé
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user_row = cursor.fetchone()
        user_data = dict_from_row(user_row)
        
        # Formater pour correspondre au YAML
        formatted_user = {
            "id": user_data['id'],
            "username": user_data['username'],
            "email": user_data['email'],
            "firstName": user_data['first_name'],
            "lastName": user_data['last_name'],
            "profilePicture": user_data['profile_picture'],
            "subscriptionStatus": user_data['subscription_status'],
            "createdAt": user_data['created_at']
        }
        
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"message": "Email ou Username déjà utilisé"}), 400
        
    conn.close()
    return jsonify({
        "token": f"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.FakeTokenFor_{user_id}",
        "user": formatted_user
    }), 201

@app.route('/api/v1/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    identifier = data.get('identifier')
    password = data.get('password')
    
    if not identifier or not password:
        return jsonify({"message": "Identifiant et mot de passe requis"}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE (email = ? OR username = ?) AND password = ?", (identifier, identifier, password))
    user_row = cursor.fetchone()
    conn.close()
    
    if not user_row:
        return jsonify({"message": "Identifiants invalides"}), 401
        
    user_data = dict_from_row(user_row)
    formatted_user = {
        "id": user_data['id'],
        "username": user_data['username'],
        "email": user_data['email'],
        "firstName": user_data['first_name'],
        "lastName": user_data['last_name'],
        "profilePicture": user_data['profile_picture'],
        "subscriptionStatus": user_data['subscription_status'],
        "createdAt": user_data['created_at']
    }

    return jsonify({
        "token": f"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.FakeTokenLogin_{user_data['id']}",
        "user": formatted_user
    }), 200

# --- ROUTES UTILISATEURS / PROFILS ---
@app.route('/api/v1/users/me', methods=['GET'])
def get_me():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users ORDER BY id DESC LIMIT 1")
    user_row = cursor.fetchone()
    conn.close()
    
    if not user_row:
        return jsonify({"message": "Aucun utilisateur trouvé"}), 404
        
    user_data = dict_from_row(user_row)
    return jsonify({
        "id": user_data['id'],
        "username": user_data['username'],
        "email": user_data['email'],
        "firstName": user_data['first_name'],
        "lastName": user_data['last_name'],
        "profilePicture": user_data['profile_picture'],
        "subscriptionStatus": user_data['subscription_status'],
        "createdAt": user_data['created_at']
    }), 200

# --- ROUTES CATALOGUE ---
@app.route('/api/v1/contents', methods=['GET'])
def get_contents():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contents")
    rows = cursor.fetchall()
    conn.close()
    
    contents = []
    for row in rows:
        data = dict_from_row(row)
        contents.append({
            "id": data['id'],
            "title": data['title'],
            "description": data['description'],
            "contentType": data['content_type'],
            "releaseYear": data['release_year'],
            "ageRating": data['age_rating'],
            "thumbnailUrl": data['thumbnail_url'],
            "requiresExtraPayment": bool(data['requires_extra_payment'])
        })
        
    return jsonify({
        "data": contents,
        "meta": {
            "currentPage": 0,
            "pageSize": 20,
            "totalElements": len(contents),
            "totalPages": 1,
            "hasNext": False
        }
    }), 200

@app.route('/api/v1/contents/<int:content_id>', methods=['GET'])
def get_content_details(content_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contents WHERE id = ?", (content_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        data = dict_from_row(row)
        return jsonify({
            "id": data['id'],
            "title": data['title'],
            "description": data['description'],
            "contentType": data['content_type'],
            "releaseYear": data['release_year'],
            "ageRating": data['age_rating'],
            "thumbnailUrl": data['thumbnail_url'],
            "requiresExtraPayment": bool(data['requires_extra_payment'])
        }), 200
    
    return jsonify({"message": "Contenu introuvable"}), 404

if __name__ == '__main__':
    from werkzeug.serving import run_simple
    print("🚀 Serveur Mock Amazon Prime (SQLite) en cours d'exécution sur http://localhost:8080")
    print("Dossier d'upload initialisé:", app.config['UPLOAD_FOLDER'])
    app.run(host='0.0.0.0', port=8080, debug=True)
