import sqlite3
import os
import hashlib
import secrets
from flask import Flask, request, jsonify, send_from_directory
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

app = Flask(__name__)
DB_NAME = "prime.db"
UPLOAD_FOLDER = 'uploads/avatars'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ============================================================
# UTILITAIRES BASE DE DONNÉES
# ============================================================

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def dict_from_row(row):
    return dict(zip(row.keys(), row)) if row else None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def hash_password(password):
    """Hache le mot de passe avec SHA-256 + sel aléatoire (simplification pédagogique)."""
    salt = "prime_salt_2026"
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()

def generate_fake_jwt(user_id, prefix="access"):
    """Génère un faux token JWT pour la démo."""
    token_data = secrets.token_hex(16)
    return f"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.{prefix}_{user_id}_{token_data}"

def get_user_from_token(req):
    """
    Extrait l'utilisateur depuis le token Bearer.
    Dans cette démo, le token contient l'ID utilisateur : 'access_<id>_<hex>'.
    En production, on vérifierait la signature JWT.
    """
    auth = req.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    token = auth.replace('Bearer ', '')
    parts = token.split('.')
    if len(parts) < 2:
        return None
    try:
        payload = parts[1]  # ex: access_42_abcdef...
        user_id = int(payload.split('_')[1])
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return dict_from_row(row)
    except Exception:
        return None

def format_user(user_data):
    return {
        "id": user_data['id'],
        "username": user_data['username'],
        "email": user_data['email'],
        "firstName": user_data['first_name'],
        "lastName": user_data['last_name'],
        "profilePicture": user_data['profile_picture'],
        "subscriptionStatus": user_data['subscription_status'],
        "createdAt": user_data['created_at']
    }

def format_content(data):
    return {
        "id": data['id'],
        "title": data['title'],
        "description": data['description'],
        "contentType": data['content_type'],
        "releaseYear": data['release_year'],
        "ageRating": data['age_rating'],
        "thumbnailUrl": data['thumbnail_url'],
        "requiresExtraPayment": bool(data['requires_extra_payment']),
        "durationMinutes": data.get('duration_minutes'),
        "director": data.get('director'),
        "totalSeasons": data.get('total_seasons'),
        "creator": data.get('creator'),
        "categories": []
    }

# ============================================================
# INITIALISATION BASE DE DONNÉES
# ============================================================

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # --- USERS ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT UNIQUE,
            password TEXT,
            first_name TEXT,
            last_name TEXT,
            profile_picture TEXT DEFAULT '',
            subscription_status TEXT DEFAULT 'ACTIVE',
            created_at TEXT
        )
    ''')

    # --- PROFILS ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            avatar_url TEXT DEFAULT '',
            age_limite TEXT DEFAULT '18+',
            is_guest INTEGER DEFAULT 0,
            guest_expires_at TEXT,
            pin_code TEXT,
            has_pin INTEGER DEFAULT 0,
            time_limit_start TEXT,
            time_limit_end TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # --- CONTENUS ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            content_type TEXT,
            release_year INTEGER,
            age_rating TEXT DEFAULT '18+',
            thumbnail_url TEXT DEFAULT '',
            requires_extra_payment INTEGER DEFAULT 0,
            duration_minutes INTEGER,
            director TEXT,
            total_seasons INTEGER,
            creator TEXT
        )
    ''')

    # --- CATÉGORIES ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS content_categories (
            content_id INTEGER,
            category_id INTEGER,
            PRIMARY KEY (content_id, category_id)
        )
    ''')

    # --- ÉPISODES ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id INTEGER,
            season_number INTEGER,
            episode_number INTEGER,
            title TEXT,
            duration_minutes INTEGER DEFAULT 45,
            is_filler INTEGER DEFAULT 0,
            has_post_credits_scene INTEGER DEFAULT 0,
            FOREIGN KEY (series_id) REFERENCES contents(id)
        )
    ''')

    # --- WATCHLIST ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER,
            content_id INTEGER,
            added_at TEXT,
            UNIQUE(profile_id, content_id),
            FOREIGN KEY (profile_id) REFERENCES profiles(id),
            FOREIGN KEY (content_id) REFERENCES contents(id)
        )
    ''')

    # --- HISTORIQUE ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS viewing_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER,
            content_id INTEGER,
            episode_id INTEGER,
            progress_seconds INTEGER DEFAULT 0,
            last_watched_at TEXT,
            UNIQUE(profile_id, content_id, episode_id),
            FOREIGN KEY (profile_id) REFERENCES profiles(id)
        )
    ''')

    # --- AVIS ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id INTEGER,
            user_id INTEGER,
            rating INTEGER,
            comment TEXT DEFAULT '',
            created_at TEXT,
            UNIQUE(content_id, user_id),
            FOREIGN KEY (content_id) REFERENCES contents(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # --- NOTIFICATIONS ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            title TEXT,
            message TEXT,
            is_read INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # --- TÉLÉCHARGEMENTS ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER,
            content_id INTEGER,
            episode_id INTEGER,
            status TEXT DEFAULT 'PENDING',
            expires_at TEXT,
            created_at TEXT,
            FOREIGN KEY (profile_id) REFERENCES profiles(id)
        )
    ''')

    # --- WATCH PARTIES ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watch_parties (
            id TEXT PRIMARY KEY,
            content_id INTEGER,
            host_id INTEGER,
            status TEXT DEFAULT 'WAITING',
            position_seconds INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY (content_id) REFERENCES contents(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watch_party_participants (
            party_id TEXT,
            user_id INTEGER,
            PRIMARY KEY (party_id, user_id)
        )
    ''')

    # --- PRÉFÉRENCES PROFIL ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS profile_preferences (
            profile_id INTEGER PRIMARY KEY,
            dual_subtitles_enabled INTEGER DEFAULT 0,
            audio_focus_level INTEGER DEFAULT 50,
            sdr_to_hdr_enabled INTEGER DEFAULT 0,
            FOREIGN KEY (profile_id) REFERENCES profiles(id)
        )
    ''')

    # --- DÉFIS ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            reward_badge_url TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_challenges (
            user_id INTEGER,
            challenge_id INTEGER,
            is_completed INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, challenge_id)
        )
    ''')

    # --- DONNÉES PAR DÉFAUT ---
    cursor.execute("SELECT COUNT(*) FROM contents")
    if cursor.fetchone()[0] == 0:
        default_contents = [
            ("The Boys", "Un groupe de justiciers s'attaque à des super-héros corrompus.", "SERIES", 2019, "18+", "https://cdn.prime.local/thumbs/theboys.jpg", 0, None, None, 4, "Eric Kripke"),
            ("Invincible", "Mark Grayson est un adolescent normal, sauf que son père est le super-héros le plus puissant.", "SERIES", 2021, "16+", "https://cdn.prime.local/thumbs/invincible.jpg", 0, None, None, 3, "Robert Kirkman"),
            ("The Terminal List", "Un Navy SEAL enquête sur les évènements qui ont coûté la vie à ses hommes.", "SERIES", 2022, "18+", "https://cdn.prime.local/thumbs/terminallist.jpg", 0, None, None, 1, "David DiGilio"),
            ("Everything Everywhere All at Once", "Une femme découvre qu'elle doit parcourir des univers parallèles.", "MOVIE", 2022, "12+", "https://cdn.prime.local/thumbs/eeaao.jpg", 0, 139, "Daniel Kwan & Daniel Scheinert", None, None),
            ("Reacher", "Un ancien policier militaire enquête sur des crimes dans une petite ville.", "SERIES", 2022, "16+", "https://cdn.prime.local/thumbs/reacher.jpg", 0, None, None, 3, "Nick Santora"),
        ]
        cursor.executemany('''
            INSERT INTO contents (title, description, content_type, release_year, age_rating, thumbnail_url, requires_extra_payment, duration_minutes, director, total_seasons, creator)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', default_contents)

        # Episodes pour The Boys (id=1)
        episodes_data = [
            (1, 1, 1, "Le nom du jeu", 60, 0, 1),
            (1, 1, 2, "Ce qui est invisible", 55, 0, 0),
            (1, 1, 3, "Popclaw", 52, 0, 0),
            (1, 2, 1, "La grande fuite", 58, 0, 1),
        ]
        cursor.executemany('''
            INSERT INTO episodes (series_id, season_number, episode_number, title, duration_minutes, is_filler, has_post_credits_scene)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', episodes_data)

    cursor.execute("SELECT COUNT(*) FROM categories")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("INSERT INTO categories (name) VALUES (?)", [
            ("Action & Aventure",), ("Science-Fiction",), ("Comédie",),
            ("Thriller",), ("Drame",), ("Animation",), ("Documentaire",)
        ])

    cursor.execute("SELECT COUNT(*) FROM challenges")
    if cursor.fetchone()[0] == 0:
        cursor.executemany('''INSERT INTO challenges (title, description, reward_badge_url) VALUES (?, ?, ?)''', [
            ("Binge-Watcher de l'Extrême", "Regardez une saison complète en moins de 24h.", "https://cdn.prime.local/badges/binge.png"),
            ("Critique en herbe", "Laissez 5 avis sur des contenus différents.", "https://cdn.prime.local/badges/critic.png"),
            ("Social Streamer", "Rejoignez 3 Watch Parties.", "https://cdn.prime.local/badges/social.png"),
        ])

    conn.commit()
    conn.close()

init_db()

# ============================================================
# FICHIERS STATIQUES
# ============================================================

@app.route('/uploads/avatars/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ============================================================
# AUTH
# ============================================================

@app.route('/api/v1/auth/register', methods=['POST'])
def register():
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    first_name = request.form.get('firstName', '')
    last_name = request.form.get('lastName', '')

    if not email or not password or not username:
        return jsonify({"status": 400, "error": "Bad Request", "message": "Paramètres manquants (username, email, password)"}), 400

    profile_picture_url = ''
    if 'profilePicture' in request.files:
        file = request.files['profilePicture']
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{username}_{filename}")
            file.save(file_path)
            profile_picture_url = f"http://localhost:8080/uploads/avatars/{username}_{filename}"

    conn = get_db()
    cursor = conn.cursor()
    try:
        created_at = datetime.now().isoformat()
        hashed_pwd = hash_password(password)
        cursor.execute('''
            INSERT INTO users (username, email, password, first_name, last_name, profile_picture, subscription_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (username, email, hashed_pwd, first_name, last_name, profile_picture_url, 'ACTIVE', created_at))
        conn.commit()
        user_id = cursor.lastrowid

        # Créer un profil principal automatiquement
        cursor.execute('''
            INSERT INTO profiles (user_id, name, age_limite, is_guest)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, '18+', 0))
        conn.commit()

        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user_row = cursor.fetchone()
        user_data = dict_from_row(user_row)

        # Notification de bienvenue
        cursor.execute('''INSERT INTO notifications (user_id, type, title, message, created_at)
            VALUES (?, ?, ?, ?, ?)''',
            (user_id, "WELCOME", "Bienvenue sur Prime Next-Gen !",
             "Découvrez nos contenus exclusifs et fonctionnalités Next-Gen.", created_at))
        conn.commit()

    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"status": 400, "error": "Conflict", "message": "Email ou Username déjà utilisé"}), 400

    conn.close()
    token = generate_fake_jwt(user_id)
    return jsonify({"token": token, "refreshToken": generate_fake_jwt(user_id, "refresh"), "user": format_user(user_data)}), 201


@app.route('/api/v1/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({"status": 400, "error": "Bad Request", "message": "Corps JSON requis"}), 400
    identifier = data.get('identifier')
    password = data.get('password')
    if not identifier or not password:
        return jsonify({"status": 400, "error": "Bad Request", "message": "Identifiant et mot de passe requis"}), 400

    hashed_pwd = hash_password(password)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE (email = ? OR username = ?) AND password = ?", (identifier, identifier, hashed_pwd))
    user_row = cursor.fetchone()
    conn.close()

    if not user_row:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Identifiants invalides"}), 401

    user_data = dict_from_row(user_row)
    token = generate_fake_jwt(user_data['id'])
    return jsonify({"token": token, "refreshToken": generate_fake_jwt(user_data['id'], "refresh"), "user": format_user(user_data)}), 200


@app.route('/api/v1/auth/logout', methods=['POST'])
def logout():
    """Déconnexion (invalidation côté client dans cette démo)."""
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    return jsonify({"message": "Déconnexion réussie"}), 200


@app.route('/api/v1/auth/refresh', methods=['POST'])
def refresh_token():
    """Rafraîchissement du token d'accès."""
    data = request.get_json() or {}
    refresh_token_val = data.get('refreshToken', '')
    if not refresh_token_val or 'refresh_' not in refresh_token_val:
        return jsonify({"status": 400, "error": "Bad Request", "message": "refreshToken invalide ou manquant"}), 400
    try:
        parts = refresh_token_val.split('.')
        user_id = int(parts[1].split('_')[1])
    except Exception:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "refreshToken invalide"}), 401
    new_token = generate_fake_jwt(user_id)
    return jsonify({"token": new_token}), 200

# ============================================================
# UTILISATEURS
# ============================================================

@app.route('/api/v1/users/me', methods=['GET'])
def get_me():
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    return jsonify(format_user(user)), 200


@app.route('/api/v1/users/me', methods=['PUT'])
def update_me():
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401

    first_name = request.form.get('firstName', user['first_name'])
    last_name = request.form.get('lastName', user['last_name'])
    profile_picture_url = user['profile_picture']

    if 'profilePicture' in request.files:
        file = request.files['profilePicture']
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{user['username']}_{filename}")
            file.save(file_path)
            profile_picture_url = f"http://localhost:8080/uploads/avatars/{user['username']}_{filename}"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''UPDATE users SET first_name=?, last_name=?, profile_picture=? WHERE id=?''',
                   (first_name, last_name, profile_picture_url, user['id']))
    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user['id'],))
    updated = dict_from_row(cursor.fetchone())
    conn.close()
    return jsonify(format_user(updated)), 200


@app.route('/api/v1/users/me/subscription', methods=['GET'])
def get_subscription():
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    end_date = (datetime.now() + timedelta(days=30)).isoformat()
    return jsonify({
        "status": user['subscription_status'],
        "planName": "Prime Next-Gen Premium",
        "currentPeriodEnd": end_date,
        "autoRenew": True,
        "price": 8.99,
        "currency": "EUR"
    }), 200


@app.route('/api/v1/users/me/subscription/cancel', methods=['POST'])
def cancel_subscription():
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET subscription_status='CANCELLED' WHERE id=?", (user['id'],))
    conn.commit()
    conn.close()
    return jsonify({"message": "Abonnement annulé. Votre accès reste actif jusqu'à la fin de la période en cours."}), 200

# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route('/api/v1/users/me/notifications', methods=['GET'])
def get_notifications():
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC", (user['id'],))
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{
        "id": r['id'], "type": r['type'], "title": r['title'],
        "message": r['message'], "isRead": bool(r['is_read']), "createdAt": r['created_at']
    } for r in rows]), 200


@app.route('/api/v1/users/me/notifications/<int:notif_id>/read', methods=['PUT'])
def mark_notification_read(notif_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?", (notif_id, user['id']))
    conn.commit()
    conn.close()
    return jsonify({"message": "Notification marquée comme lue"}), 200

# ============================================================
# PROFILS
# ============================================================

@app.route('/api/v1/profiles', methods=['GET'])
def get_profiles():
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM profiles WHERE user_id=?", (user['id'],))
    rows = cursor.fetchall()
    conn.close()
    return jsonify([format_profile(dict_from_row(r)) for r in rows]), 200


@app.route('/api/v1/profiles', methods=['POST'])
def create_profile():
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401

    # Limite de 6 profils par compte
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM profiles WHERE user_id=?", (user['id'],))
    if cursor.fetchone()[0] >= 6:
        conn.close()
        return jsonify({"status": 400, "error": "Bad Request", "message": "Nombre maximum de profils atteint (6)"}), 400

    data = request.get_json() or {}
    name = data.get('name')
    age_limite = data.get('ageLimite', '18+')
    is_guest = data.get('isGuest', False)
    pin_code = data.get('pinCode')
    avatar_url = data.get('avatarUrl', '')
    time_start = data.get('timeLimitStart')
    time_end = data.get('timeLimitEnd')

    if not name:
        conn.close()
        return jsonify({"status": 400, "error": "Bad Request", "message": "Le champ 'name' est requis"}), 400

    guest_expires_at = None
    if is_guest:
        guest_expires_at = (datetime.now() + timedelta(hours=24)).isoformat()

    cursor.execute('''
        INSERT INTO profiles (user_id, name, avatar_url, age_limite, is_guest, guest_expires_at, pin_code, has_pin, time_limit_start, time_limit_end)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user['id'], name, avatar_url, age_limite, int(is_guest), guest_expires_at,
          pin_code, int(bool(pin_code)), time_start, time_end))
    conn.commit()
    profile_id = cursor.lastrowid

    # Préférences par défaut
    cursor.execute("INSERT OR IGNORE INTO profile_preferences (profile_id) VALUES (?)", (profile_id,))
    conn.commit()

    cursor.execute("SELECT * FROM profiles WHERE id=?", (profile_id,))
    row = dict_from_row(cursor.fetchone())
    conn.close()
    return jsonify(format_profile(row)), 201


@app.route('/api/v1/profiles/<int:profile_id>', methods=['PUT'])
def update_profile(profile_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM profiles WHERE id=? AND user_id=?", (profile_id, user['id']))
    profile = dict_from_row(cursor.fetchone())
    if not profile:
        conn.close()
        return jsonify({"status": 404, "error": "Not Found", "message": "Profil introuvable"}), 404

    data = request.get_json() or {}
    name = data.get('name', profile['name'])
    age_limite = data.get('ageLimite', profile['age_limite'])
    avatar_url = data.get('avatarUrl', profile['avatar_url'])
    pin_code = data.get('pinCode', profile['pin_code'])
    time_start = data.get('timeLimitStart', profile['time_limit_start'])
    time_end = data.get('timeLimitEnd', profile['time_limit_end'])

    cursor.execute('''UPDATE profiles SET name=?, age_limite=?, avatar_url=?, pin_code=?, has_pin=?, time_limit_start=?, time_limit_end=?
        WHERE id=?''', (name, age_limite, avatar_url, pin_code, int(bool(pin_code)), time_start, time_end, profile_id))
    conn.commit()
    cursor.execute("SELECT * FROM profiles WHERE id=?", (profile_id,))
    row = dict_from_row(cursor.fetchone())
    conn.close()
    return jsonify(format_profile(row)), 200


@app.route('/api/v1/profiles/<int:profile_id>', methods=['DELETE'])
def delete_profile(profile_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM profiles WHERE id=? AND user_id=?", (profile_id, user['id']))
    if not cursor.fetchone():
        conn.close()
        return jsonify({"status": 404, "error": "Not Found", "message": "Profil introuvable"}), 404
    cursor.execute("DELETE FROM profiles WHERE id=?", (profile_id,))
    conn.commit()
    conn.close()
    return '', 204


@app.route('/api/v1/profiles/<int:profile_id>/verify-pin', methods=['POST'])
def verify_pin(profile_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    data = request.get_json() or {}
    pin_code = data.get('pinCode')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM profiles WHERE id=? AND user_id=?", (profile_id, user['id']))
    profile = dict_from_row(cursor.fetchone())
    conn.close()
    if not profile:
        return jsonify({"status": 404, "error": "Not Found", "message": "Profil introuvable"}), 404
    if profile['pin_code'] != pin_code:
        return jsonify({"status": 403, "error": "Forbidden", "message": "Code PIN incorrect"}), 403
    return jsonify({"message": "PIN vérifié. Accès accordé.", "accessGrantedUntil": (datetime.now() + timedelta(minutes=30)).isoformat()}), 200


@app.route('/api/v1/profiles/<int:profile_id>/preferences', methods=['GET'])
def get_preferences(profile_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM profile_preferences WHERE profile_id=?", (profile_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({"dualSubtitlesEnabled": False, "audioFocusLevel": 50, "sdrToHdrEnabled": False}), 200
    data = dict_from_row(row)
    return jsonify({
        "dualSubtitlesEnabled": bool(data['dual_subtitles_enabled']),
        "audioFocusLevel": data['audio_focus_level'],
        "sdrToHdrEnabled": bool(data['sdr_to_hdr_enabled'])
    }), 200


@app.route('/api/v1/profiles/<int:profile_id>/preferences', methods=['PUT'])
def update_preferences(profile_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    data = request.get_json() or {}
    dual = int(data.get('dualSubtitlesEnabled', False))
    audio = data.get('audioFocusLevel', 50)
    sdr = int(data.get('sdrToHdrEnabled', False))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''INSERT OR REPLACE INTO profile_preferences (profile_id, dual_subtitles_enabled, audio_focus_level, sdr_to_hdr_enabled)
        VALUES (?, ?, ?, ?)''', (profile_id, dual, audio, sdr))
    conn.commit()
    conn.close()
    return jsonify({"dualSubtitlesEnabled": bool(dual), "audioFocusLevel": audio, "sdrToHdrEnabled": bool(sdr)}), 200


def format_profile(p):
    return {
        "id": p['id'], "userId": p['user_id'], "name": p['name'],
        "avatarUrl": p.get('avatar_url', ''), "ageLimite": p['age_limite'],
        "isGuest": bool(p['is_guest']), "guestExpiresAt": p.get('guest_expires_at'),
        "hasPin": bool(p['has_pin']),
        "timeLimitStart": p.get('time_limit_start'),
        "timeLimitEnd": p.get('time_limit_end')
    }

# ============================================================
# CATALOGUE
# ============================================================

@app.route('/api/v1/categories', methods=['GET'])
def get_categories():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM categories")
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{"id": r['id'], "name": r['name']} for r in rows]), 200


@app.route('/api/v1/contents', methods=['GET'])
def get_contents():
    q = request.args.get('q', '')
    page = int(request.args.get('page', 0))
    size = int(request.args.get('size', 20))
    category_id = request.args.get('categoryId')
    min_age = request.args.get('minAge')
    zero_cost = request.args.get('zeroCostOnly', 'false').lower() == 'true'
    content_type = request.args.get('contentType')

    conn = get_db()
    cursor = conn.cursor()
    query = "SELECT * FROM contents WHERE 1=1"
    params = []

    if q:
        query += " AND (title LIKE ? OR description LIKE ? OR director LIKE ? OR creator LIKE ?)"
        params.extend([f'%{q}%', f'%{q}%', f'%{q}%', f'%{q}%'])
    if zero_cost:
        query += " AND requires_extra_payment = 0"
    if content_type in ('MOVIE', 'SERIES'):
        query += " AND content_type = ?"
        params.append(content_type)

    cursor.execute(query, params)
    all_rows = cursor.fetchall()
    conn.close()

    contents = [format_content(dict_from_row(r)) for r in all_rows]
    total = len(contents)
    start = page * size
    paginated = contents[start:start + size]

    return jsonify({
        "data": paginated,
        "meta": {
            "currentPage": page, "pageSize": size,
            "totalElements": total, "totalPages": max(1, -(-total // size)),
            "hasNext": (start + size) < total
        }
    }), 200


@app.route('/api/v1/contents/<int:content_id>', methods=['GET'])
def get_content_details(content_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contents WHERE id = ?", (content_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({"status": 404, "error": "Not Found", "message": "Contenu introuvable"}), 404
    return jsonify(format_content(dict_from_row(row))), 200


@app.route('/api/v1/contents/<int:content_id>/episodes', methods=['GET'])
def get_episodes(content_id):
    season = request.args.get('seasonNumber')
    conn = get_db()
    cursor = conn.cursor()
    query = "SELECT * FROM episodes WHERE series_id=?"
    params = [content_id]
    if season:
        query += " AND season_number=?"
        params.append(int(season))
    query += " ORDER BY season_number, episode_number"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    if not rows and season is None:
        return jsonify({"status": 404, "error": "Not Found", "message": "Série introuvable ou aucun épisode"}), 404
    return jsonify([{
        "id": r['id'], "seriesId": r['series_id'],
        "seasonNumber": r['season_number'], "episodeNumber": r['episode_number'],
        "title": r['title'], "durationMinutes": r['duration_minutes'],
        "isFiller": bool(r['is_filler']), "hasPostCreditsScene": bool(r['has_post_credits_scene'])
    } for r in rows]), 200


@app.route('/api/v1/contents/<int:content_id>/stream', methods=['GET'])
def get_stream(content_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contents WHERE id=?", (content_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({"status": 404, "error": "Not Found", "message": "Contenu introuvable"}), 404
    data = dict_from_row(row)
    if data['requires_extra_payment']:
        return jsonify({"status": 403, "error": "Forbidden", "message": "Ce contenu requiert un paiement supplémentaire"}), 403
    return jsonify({
        "streamUrl": f"https://video-edge.prime.local/hls/{content_id}/master.m3u8",
        "dashUrl": f"https://video-edge.prime.local/dash/{content_id}/manifest.mpd",
        "availableSubtitles": ["fr-FR", "en-US", "es-ES"],
        "audioTracks": ["fr-FR (Dialogues Boostés)", "en-US (Original)", "fr-FR (Standard)"],
        "drmToken": f"drm_{secrets.token_hex(8)}",
        "expiresAt": (datetime.now() + timedelta(hours=4)).isoformat()
    }), 200

# ============================================================
# WATCHLIST
# ============================================================

@app.route('/api/v1/profiles/<int:profile_id>/watchlist', methods=['GET'])
def get_watchlist(profile_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''SELECT w.content_id, w.added_at, c.title, c.thumbnail_url, c.content_type
        FROM watchlist w JOIN contents c ON w.content_id=c.id WHERE w.profile_id=?
        ORDER BY w.added_at DESC''', (profile_id,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{
        "contentId": r['content_id'], "addedAt": r['added_at'],
        "title": r['title'], "thumbnailUrl": r['thumbnail_url'], "contentType": r['content_type']
    } for r in rows]), 200


@app.route('/api/v1/profiles/<int:profile_id>/watchlist', methods=['POST'])
def add_to_watchlist(profile_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    data = request.get_json() or {}
    content_id = data.get('contentId')
    if not content_id:
        return jsonify({"status": 400, "error": "Bad Request", "message": "contentId requis"}), 400
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO watchlist (profile_id, content_id, added_at) VALUES (?, ?, ?)",
                       (profile_id, content_id, datetime.now().isoformat()))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"status": 409, "error": "Conflict", "message": "Contenu déjà dans la watchlist"}), 409
    conn.close()
    return jsonify({"message": "Contenu ajouté à la watchlist"}), 201


@app.route('/api/v1/profiles/<int:profile_id>/watchlist/<int:content_id>', methods=['DELETE'])
def remove_from_watchlist(profile_id, content_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM watchlist WHERE profile_id=? AND content_id=?", (profile_id, content_id))
    conn.commit()
    conn.close()
    return '', 204

# ============================================================
# HISTORIQUE DE VISIONNAGE
# ============================================================

@app.route('/api/v1/profiles/<int:profile_id>/history', methods=['GET'])
def get_history(profile_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM viewing_history WHERE profile_id=? ORDER BY last_watched_at DESC", (profile_id,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{
        "contentId": r['content_id'], "episodeId": r['episode_id'],
        "progressSeconds": r['progress_seconds'], "lastWatchedAt": r['last_watched_at']
    } for r in rows]), 200


@app.route('/api/v1/profiles/<int:profile_id>/history', methods=['PUT'])
def update_history(profile_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    data = request.get_json() or {}
    content_id = data.get('contentId')
    episode_id = data.get('episodeId')
    progress = data.get('progressSeconds', 0)
    if not content_id:
        return jsonify({"status": 400, "error": "Bad Request", "message": "contentId requis"}), 400
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''INSERT OR REPLACE INTO viewing_history (profile_id, content_id, episode_id, progress_seconds, last_watched_at)
        VALUES (?, ?, ?, ?, ?)''', (profile_id, content_id, episode_id, progress, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return jsonify({"message": "Progression sauvegardée", "progressSeconds": progress}), 200


@app.route('/api/v1/profiles/<int:profile_id>/history/<int:content_id>', methods=['DELETE'])
def delete_history_item(profile_id, content_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM viewing_history WHERE profile_id=? AND content_id=?", (profile_id, content_id))
    conn.commit()
    conn.close()
    return '', 204

# ============================================================
# AVIS / REVIEWS
# ============================================================

@app.route('/api/v1/contents/<int:content_id>/reviews', methods=['GET'])
def get_reviews(content_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reviews WHERE content_id=? ORDER BY created_at DESC", (content_id,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{
        "id": r['id'], "contentId": r['content_id'], "userId": r['user_id'],
        "rating": r['rating'], "comment": r['comment'], "createdAt": r['created_at']
    } for r in rows]), 200


@app.route('/api/v1/contents/<int:content_id>/reviews', methods=['POST'])
def add_review(content_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    data = request.get_json() or {}
    rating = data.get('rating')
    if not rating or not (1 <= int(rating) <= 5):
        return jsonify({"status": 400, "error": "Bad Request", "message": "rating entre 1 et 5 requis"}), 400
    comment = data.get('comment', '')
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''INSERT INTO reviews (content_id, user_id, rating, comment, created_at)
            VALUES (?, ?, ?, ?, ?)''', (content_id, user['id'], rating, comment, datetime.now().isoformat()))
        conn.commit()
        review_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"status": 409, "error": "Conflict", "message": "Vous avez déjà laissé un avis sur ce contenu"}), 409
    conn.close()
    return jsonify({"id": review_id, "contentId": content_id, "userId": user['id'], "rating": rating, "comment": comment}), 201


@app.route('/api/v1/contents/<int:content_id>/reviews/<int:review_id>', methods=['PUT'])
def update_review(content_id, review_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    data = request.get_json() or {}
    rating = data.get('rating')
    comment = data.get('comment', '')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE reviews SET rating=?, comment=? WHERE id=? AND user_id=?",
                   (rating, comment, review_id, user['id']))
    conn.commit()
    conn.close()
    return jsonify({"id": review_id, "contentId": content_id, "rating": rating, "comment": comment}), 200


@app.route('/api/v1/contents/<int:content_id>/reviews/<int:review_id>', methods=['DELETE'])
def delete_review(content_id, review_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reviews WHERE id=? AND user_id=?", (review_id, user['id']))
    conn.commit()
    conn.close()
    return '', 204

# ============================================================
# TÉLÉCHARGEMENTS (OFFLINE)
# ============================================================

@app.route('/api/v1/profiles/<int:profile_id>/downloads', methods=['GET'])
def get_downloads(profile_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM downloads WHERE profile_id=? ORDER BY created_at DESC", (profile_id,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{
        "id": r['id'], "contentId": r['content_id'], "episodeId": r['episode_id'],
        "status": r['status'], "expiresAt": r['expires_at'], "createdAt": r['created_at']
    } for r in rows]), 200


@app.route('/api/v1/profiles/<int:profile_id>/downloads', methods=['POST'])
def add_download(profile_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    data = request.get_json() or {}
    content_id = data.get('contentId')
    episode_id = data.get('episodeId')
    if not content_id:
        return jsonify({"status": 400, "error": "Bad Request", "message": "contentId requis"}), 400
    expires_at = (datetime.now() + timedelta(days=30)).isoformat()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO downloads (profile_id, content_id, episode_id, status, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?)''', (profile_id, content_id, episode_id, 'DOWNLOADING', expires_at, datetime.now().isoformat()))
    conn.commit()
    dl_id = cursor.lastrowid
    conn.close()
    return jsonify({"id": dl_id, "contentId": content_id, "status": "DOWNLOADING", "expiresAt": expires_at}), 201


@app.route('/api/v1/profiles/<int:profile_id>/downloads/<int:download_id>', methods=['DELETE'])
def delete_download(profile_id, download_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM downloads WHERE id=? AND profile_id=?", (download_id, profile_id))
    conn.commit()
    conn.close()
    return '', 204

# ============================================================
# RECOMMANDATIONS
# ============================================================

@app.route('/api/v1/profiles/<int:profile_id>/recommendations', methods=['GET'])
def get_recommendations(profile_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    conn = get_db()
    cursor = conn.cursor()
    # Recommandations simples : contenus pas encore vus
    cursor.execute('''SELECT c.* FROM contents c WHERE c.id NOT IN
        (SELECT content_id FROM viewing_history WHERE profile_id=?) LIMIT 5''', (profile_id,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify({
        "reason": "Basé sur votre historique de visionnage",
        "recommendations": [format_content(dict_from_row(r)) for r in rows]
    }), 200

# ============================================================
# NEXT-GEN FEATURES
# ============================================================

@app.route('/api/v1/contents/<int:content_id>/smart-catchup', methods=['GET'])
def smart_catchup(content_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contents WHERE id=?", (content_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({"status": 404, "error": "Not Found", "message": "Contenu introuvable"}), 404
    content = dict_from_row(row)
    return jsonify({
        "contentId": content_id,
        "summaryText": f"Précédemment dans '{content['title']}' : Les personnages principaux ont traversé des épreuves décisives. Les enjeux montent et un retournement de situation inattendu se profile. Prêt pour la suite ?",
        "videoUrl": f"https://video-edge.prime.local/catchup/{content_id}_user{user['id']}.mp4",
        "generatedAt": datetime.now().isoformat()
    }), 200


@app.route('/api/v1/contents/<int:content_id>/soundtrack/current', methods=['GET'])
def soundtrack_sync(content_id):
    timestamp = request.args.get('timestampSeconds')
    if not timestamp:
        return jsonify({"status": 400, "error": "Bad Request", "message": "timestampSeconds requis"}), 400
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contents WHERE id=?", (content_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({"status": 404, "error": "Not Found", "message": "Contenu introuvable"}), 404
    return jsonify({
        "trackName": "Shape of My Heart",
        "artist": "Sting",
        "albumArt": "https://cdn.prime.local/music/shape_of_my_heart.jpg",
        "spotifyUrl": "https://open.spotify.com/track/1yAZNdY0vblLMFZ8s2hGNh",
        "deezerUrl": "https://www.deezer.com/track/672309",
        "timestampSeconds": int(timestamp)
    }), 200


@app.route('/api/v1/users/me/challenges', methods=['GET'])
def get_challenges():
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''SELECT c.*, COALESCE(uc.is_completed, 0) as is_completed
        FROM challenges c LEFT JOIN user_challenges uc
        ON c.id=uc.challenge_id AND uc.user_id=?''', (user['id'],))
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{
        "id": r['id'], "title": r['title'], "description": r['description'],
        "rewardBadgeUrl": r['reward_badge_url'], "isCompleted": bool(r['is_completed'])
    } for r in rows]), 200

# ============================================================
# WATCH PARTIES
# ============================================================

@app.route('/api/v1/watch-parties', methods=['POST'])
def create_watch_party():
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    data = request.get_json() or {}
    content_id = data.get('contentId')
    if not content_id:
        return jsonify({"status": 400, "error": "Bad Request", "message": "contentId requis"}), 400
    party_id = f"wp-{secrets.token_hex(6)}"
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO watch_parties (id, content_id, host_id, status, created_at)
        VALUES (?, ?, ?, ?, ?)''', (party_id, content_id, user['id'], 'WAITING', datetime.now().isoformat()))
    cursor.execute("INSERT INTO watch_party_participants (party_id, user_id) VALUES (?, ?)", (party_id, user['id']))
    conn.commit()
    conn.close()
    return jsonify({
        "id": party_id, "contentId": content_id, "hostId": user['id'],
        "participantIds": [user['id']], "status": "WAITING", "createdAt": datetime.now().isoformat()
    }), 201


@app.route('/api/v1/watch-parties/<party_id>', methods=['GET'])
def get_watch_party(party_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM watch_parties WHERE id=?", (party_id,))
    party = dict_from_row(cursor.fetchone())
    if not party:
        conn.close()
        return jsonify({"status": 404, "error": "Not Found", "message": "Watch Party introuvable"}), 404
    cursor.execute("SELECT user_id FROM watch_party_participants WHERE party_id=?", (party_id,))
    participants = [r['user_id'] for r in cursor.fetchall()]
    conn.close()
    return jsonify({
        "id": party['id'], "contentId": party['content_id'], "hostId": party['host_id'],
        "participantIds": participants, "status": party['status'],
        "positionSeconds": party['position_seconds'], "createdAt": party['created_at']
    }), 200


@app.route('/api/v1/watch-parties/<party_id>/join', methods=['POST'])
def join_watch_party(party_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM watch_parties WHERE id=?", (party_id,))
    party = dict_from_row(cursor.fetchone())
    if not party:
        conn.close()
        return jsonify({"status": 404, "error": "Not Found", "message": "Watch Party introuvable"}), 404
    try:
        cursor.execute("INSERT INTO watch_party_participants (party_id, user_id) VALUES (?, ?)", (party_id, user['id']))
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # Déjà participant
    cursor.execute("SELECT user_id FROM watch_party_participants WHERE party_id=?", (party_id,))
    participants = [r['user_id'] for r in cursor.fetchall()]
    conn.close()
    return jsonify({
        "id": party['id'], "contentId": party['content_id'], "hostId": party['host_id'],
        "participantIds": participants, "status": party['status'], "createdAt": party['created_at']
    }), 200


@app.route('/api/v1/watch-parties/<party_id>/leave', methods=['POST'])
def leave_watch_party(party_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM watch_party_participants WHERE party_id=? AND user_id=?", (party_id, user['id']))
    conn.commit()
    conn.close()
    return jsonify({"message": "Vous avez quitté la Watch Party"}), 200


@app.route('/api/v1/watch-parties/<party_id>/state', methods=['PUT'])
def update_watch_party_state(party_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"status": 401, "error": "Unauthorized", "message": "Token requis"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM watch_parties WHERE id=? AND host_id=?", (party_id, user['id']))
    if not cursor.fetchone():
        conn.close()
        return jsonify({"status": 403, "error": "Forbidden", "message": "Seul l'hôte peut synchroniser la Watch Party"}), 403
    data = request.get_json() or {}
    status = data.get('status', 'PLAYING')
    position = data.get('positionSeconds', 0)
    cursor.execute("UPDATE watch_parties SET status=?, position_seconds=? WHERE id=?", (status, position, party_id))
    conn.commit()
    conn.close()
    return jsonify({"message": "État synchronisé pour tous les participants", "status": status, "positionSeconds": position}), 200

# ============================================================
# DÉMARRAGE
# ============================================================

if __name__ == '__main__':
    print("Serveur Mock Amazon Prime Next-Gen (SQLite) sur http://localhost:8080")
    print("Dossier d'upload:", app.config['UPLOAD_FOLDER'])
    app.run(host='0.0.0.0', port=8080, debug=True)
