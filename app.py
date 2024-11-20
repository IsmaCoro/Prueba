from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from pymongo import MongoClient
from bson.objectid import ObjectId
from werkzeug.utils import secure_filename
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Reemplaza "<usuario>" y "<contraseña>" con tus credenciales reales
client = MongoClient("mongodb+srv://jonathancorona6790:KMn801EQIe5L8q4p@ismaelprueba.s4opn.mongodb.net/microgram")
db = client['microgram']


# Flask-Login Setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# File upload setup
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'avi'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


class User(UserMixin):
    def __init__(self, user_id):
        self.id = user_id


@login_manager.user_loader
def load_user(user_id):
    user_data = db.usuarios.find_one({"_id": ObjectId(user_id)})
    if user_data:
        return User(user_id=user_data["_id"])
    return None


# Helper function to check allowed files
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# === Rutas principales ===
@app.route('/')
def home():
    return redirect(url_for('login'))


# === Gestión de usuarios ===
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nombre = request.form['nombre']
        email = request.form['email']
        password = request.form['password']  # Password almacenada sin cifrar (solo para simplicidad)
        db.usuarios.insert_one({
            "nombre": nombre,
            "email": email,
            "password": password,
            "fecha_registro": datetime.now().strftime('%Y-%m-%d'),
            "publicaciones": [],
            "amigos": [],
            "solicitudes": []
        })
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = db.usuarios.find_one({"email": email, "password": password})
        if user:
            login_user(User(user_id=str(user["_id"])))
            return redirect(url_for('profile'))
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/profile')
@login_required
def profile():
    user_data = db.usuarios.find_one({"_id": ObjectId(current_user.id)})
    publicaciones = db.publicaciones.find({"usuario_id": current_user.id})
    return render_template('profile.html', user=user_data, publicaciones=publicaciones)


# === Gestión de publicaciones ===
@app.route('/create_post', methods=['POST'])
@login_required
def create_post():
    content = request.form['content']
    file = request.files.get('file')
    file_url = None

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        file_url = file_path.replace("\\", "/")

    db.publicaciones.insert_one({
        "usuario_id": current_user.id,
        "contenido": content,
        "fecha_publicacion": datetime.now().strftime('%Y-%m-%d'),
        "multimedia": file_url,
        "likes": [],
        "comentarios": []
    })
    return redirect(url_for('profile'))


@app.route('/delete_post/<post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    db.publicaciones.delete_one({"_id": ObjectId(post_id), "usuario_id": current_user.id})
    return redirect(url_for('profile'))


@app.route('/feed')
def feed():
    publicaciones = db.publicaciones.find().sort("fecha_publicacion", -1)
    return render_template('feed.html', publicaciones=publicaciones)


@app.route('/ver_publicaciones_amigos')
@login_required
def ver_publicaciones_amigos():
    user = db.usuarios.find_one({"_id": ObjectId(current_user.id)})
    amigos_ids = user.get("amigos", [])
    publicaciones = list(db.publicaciones.find({"usuario_id": {"$in": amigos_ids}}))

    for post in publicaciones:
        usuario = db.usuarios.find_one({"_id": ObjectId(post["usuario_id"])})
        post["usuario_nombre"] = usuario["nombre"]
        for comentario in post["comentarios"]:
            autor_comentario = db.usuarios.find_one({"_id": ObjectId(comentario["usuario_id"])})
            comentario["usuario_nombre"] = autor_comentario["nombre"]

    return render_template('ver_publicaciones_amigos.html', publicaciones=publicaciones)


# === Likes y comentarios ===
@app.route('/like_post/<post_id>', methods=['POST'])
@login_required
def like_post(post_id):
    post = db.publicaciones.find_one({"_id": ObjectId(post_id)})
    if current_user.id in post.get("likes", []):
        db.publicaciones.update_one({"_id": ObjectId(post_id)}, {"$pull": {"likes": current_user.id}})
    else:
        db.publicaciones.update_one({"_id": ObjectId(post_id)}, {"$pull": {"dislikes": current_user.id}})
        db.publicaciones.update_one({"_id": ObjectId(post_id)}, {"$addToSet": {"likes": current_user.id}})
    post = db.publicaciones.find_one({"_id": ObjectId(post_id)})
    return jsonify({"likes": len(post["likes"]), "dislikes": len(post["dislikes"])})


@app.route('/dislike_post/<post_id>', methods=['POST'])
@login_required
def dislike_post(post_id):
    post = db.publicaciones.find_one({"_id": ObjectId(post_id)})
    if current_user.id in post.get("dislikes", []):
        db.publicaciones.update_one({"_id": ObjectId(post_id)}, {"$pull": {"dislikes": current_user.id}})
    else:
        db.publicaciones.update_one({"_id": ObjectId(post_id)}, {"$pull": {"likes": current_user.id}})
        db.publicaciones.update_one({"_id": ObjectId(post_id)}, {"$addToSet": {"dislikes": current_user.id}})
    post = db.publicaciones.find_one({"_id": ObjectId(post_id)})
    return jsonify({"likes": len(post["likes"]), "dislikes": len(post["dislikes"])})


@app.route('/comment_post/<post_id>', methods=['POST'])
@login_required
def comment_post(post_id):
    try:
        comment_text = request.form['comment']
        if not comment_text.strip():
            return jsonify({"error": "Comentario vacío"}), 400

        user = db.usuarios.find_one({"_id": ObjectId(current_user.id)})
        comment = {
            "usuario_id": str(current_user.id),
            "usuario_nombre": user["nombre"],
            "texto": comment_text,
            "fecha_comentario": datetime.now().strftime('%Y-%m-%d')
        }

        db.publicaciones.update_one({"_id": ObjectId(post_id)}, {"$push": {"comentarios": comment}})
        return jsonify({"comment": comment})
    except Exception as e:
        print(f"Error al agregar comentario: {e}")
        return jsonify({"error": "Hubo un error al agregar el comentario"}), 500


# === Gestión de amigos ===
@app.route('/ver_amigos')
@login_required
def ver_amigos():
    user = db.usuarios.find_one({"_id": ObjectId(current_user.id)})
    amigos = db.usuarios.find({"_id": {"$in": user.get("amigos", [])}})
    return render_template('ver_amigos.html', amigos=amigos)


@app.route('/agregar_amigos')
@login_required
def agregar_amigos():
    user = db.usuarios.find_one({"_id": ObjectId(current_user.id)})
    amigos_ids = user.get("amigos", [])
    usuarios = db.usuarios.find({"_id": {"$nin": amigos_ids + [ObjectId(current_user.id)]}})
    return render_template('agregar_amigos.html', usuarios=usuarios)


@app.route('/enviar_solicitud/<amigo_id>', methods=['POST'])
@login_required
def enviar_solicitud(amigo_id):
    db.usuarios.update_one({"_id": ObjectId(amigo_id)}, {"$addToSet": {"solicitudes": ObjectId(current_user.id)}})
    return redirect(url_for('agregar_amigos'))


@app.route('/aceptar_solicitud/<solicitante_id>', methods=['POST'])
@login_required
def aceptar_solicitud(solicitante_id):
    db.usuarios.update_one({"_id": ObjectId(current_user.id)}, {"$addToSet": {"amigos": ObjectId(solicitante_id)}})
    db.usuarios.update_one({"_id": ObjectId(solicitante_id)}, {"$addToSet": {"amigos": ObjectId(current_user.id)}})
    db.usuarios.update_one({"_id": ObjectId(current_user.id)}, {"$pull": {"solicitudes": ObjectId(solicitante_id)}})
    return redirect(url_for('ver_solicitudes'))


@app.route('/rechazar_solicitud/<solicitante_id>', methods=['POST'])
@login_required
def rechazar_solicitud(solicitante_id):
    db.usuarios.update_one({"_id": ObjectId(current_user.id)}, {"$pull": {"solicitudes": ObjectId(solicitante_id)}})
    return redirect(url_for('ver_solicitudes'))


@app.route('/ver_solicitudes')
@login_required
def ver_solicitudes():
    user = db.usuarios.find_one({"_id": ObjectId(current_user.id)})
    solicitudes_ids = user.get("solicitudes", [])
    solicitudes = db.usuarios.find({"_id": {"$in": solicitudes_ids}})
    return render_template('ver_solicitudes.html', solicitudes=solicitudes)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

