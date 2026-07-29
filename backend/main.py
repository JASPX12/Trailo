import os
import yt_dlp
from fastapi import FastAPI, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
# backend/main.py (Importaciones adicionales que necesitas añadir al principio)
from fastapi import HTTPException, status
from pydantic import BaseModel, EmailStr, Field
import bcrypt

app = FastAPI(title="OTT MVP Backend", version="0.1.0")

# --- NUEVO: Configuración de CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción debes cambiar "*" por el dominio de tu frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 1. Configuración de Cifrado ---
def get_password_hash(password: str) -> str:
    # bcrypt requiere que la contraseña esté en bytes, así que la codificamos
    pwd_bytes = password.encode('utf-8')
    # Generamos una "sal" (un valor aleatorio para hacer el hash más seguro)
    salt = bcrypt.gensalt()
    # Creamos el hash
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    # Lo decodificamos a string normal para poder guardarlo en Supabase
    return hashed_password.decode('utf-8')

def verificar_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )

# --- 2. Esquema Pydantic (Validación del "Formulario" de entrada) ---
class UsuarioRegistro(BaseModel):
    nombre: str
    email: EmailStr  # Valida que tenga formato de correo electrónico
    password: str
    nacionalidad: str

class UsuarioLogin(BaseModel):
    email: EmailStr
    password: str

class UsuarioActualizarPassword(BaseModel):
    email: EmailStr
    nueva_password: str = Field(...,min_length=4, max_length=72)

@app.post("/api/registro", status_code=status.HTTP_201_CREATED)
def registrar_usuario(usuario: UsuarioRegistro, db: Session = Depends(get_db)):
    # 1. Verificar si el correo ya existe en la base de datos
    consulta_existe = text("SELECT id FROM users WHERE email = :email")
    usuario_existente = db.execute(consulta_existe, {"email": usuario.email}).fetchone()

    if usuario_existente:
        # Si existe, lanzamos un error 400 (Bad Request) que tu frontend leerá
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo electrónico ya está registrado."
        )

    # 2. Cifrar la contraseña usando la función que ya tenías
    hashed_password = get_password_hash(usuario.password)

    # 3. Insertar el nuevo usuario mapeando los datos del Pydantic a las columnas de tu tabla
    consulta_insertar = text("""
        INSERT INTO users (email, password_hash, country_code, name)
        VALUES (:email, :password_hash, :country_code, :name)
    """)

    try:
        db.execute(consulta_insertar, {
            "email": usuario.email,
            "password_hash": hashed_password,
            "country_code": usuario.nacionalidad,  # Mapeamos nacionalidad a country_code
            "name": usuario.nombre
        })
        db.commit()  # ¡Muy importante para guardar los cambios en Supabase!

        return {"mensaje": "Usuario registrado exitosamente"}

    except Exception as e:
        db.rollback()  # Si algo falla, deshacemos la transacción
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno al crear el usuario: {str(e)}"
        )


@app.post("/api/login")
def iniciar_sesion(credenciales: UsuarioLogin, db: Session = Depends(get_db)):
    # 1. Buscar al usuario por correo
    consulta_usuario = text("SELECT id, password_hash FROM users WHERE email = :email")
    usuario = db.execute(consulta_usuario, {"email": credenciales.email}).fetchone()

    # Si no existe el correo o la contraseña no coincide, enviamos error 401
    if not usuario or not verificar_password(credenciales.password, usuario.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos."
        )

    # 2. Registrar la sesión en la tabla user_sessions
    consulta_sesion = text("""
        INSERT INTO user_sessions (user_id, is_active) 
        VALUES (:user_id, true) 
        RETURNING id
    """)

    try:
        resultado = db.execute(consulta_sesion, {"user_id": usuario.id})
        session_id = resultado.scalar()  # Obtenemos el ID de la sesión recién creada
        db.commit()

        return {
            "mensaje": "Inicio de sesión exitoso",
            "user_id": usuario.id,
            "session_id": session_id
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear la sesión: {str(e)}"
        )


@app.put("/api/actualizar-password")
def actualizar_password(datos: UsuarioActualizarPassword, db: Session = Depends(get_db)):
    # 1. Verificar si el usuario existe
    consulta_usuario = text("SELECT id FROM users WHERE email = :email")
    usuario = db.execute(consulta_usuario, {"email": datos.email}).fetchone()

    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe ninguna cuenta con este correo."
        )

    # 2. Cifrar la NUEVA contraseña
    hashed_password = get_password_hash(datos.nueva_password)

    # 3. Actualizar la base de datos
    consulta_update = text("""
        UPDATE users 
        SET password_hash = :nuevo_hash 
        WHERE email = :email
    """)

    try:
        db.execute(consulta_update, {
            "nuevo_hash": hashed_password,
            "email": datos.email
        })
        db.commit()  # Guardamos los cambios

        return {"mensaje": "Contraseña actualizada exitosamente"}

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar la contraseña: {str(e)}"
        )

# 2. Sistema de archivos para Video On Demand local
os.makedirs("media", exist_ok=True)
app.mount("/media", StaticFiles(directory="media"), name="media")


# 3. Endpoint: Consultar el catálogo local
@app.get("/api/catalogo")
def obtener_catalogo(
        region_usuario: str = None,
        busqueda: str = None,
        idioma: str = None,
        db: Session = Depends(get_db)
):
    # 1. Definimos la consulta base
    consulta_str = "SELECT * FROM catalogo_trailers WHERE 1=1"

    # 2. Diccionario para guardar los valores de forma segura
    parametros = {}

    # 3. Construimos la consulta y asignamos los parámetros dinámicamente
    if busqueda:
        consulta_str += " AND pelicula ILIKE :busqueda"
        parametros["busqueda"] = f"%{busqueda}%"

    if region_usuario:
        consulta_str += " AND paises_permitidos ILIKE :region_usuario"
        parametros["region_usuario"] = f"%{region_usuario}%"

    if idioma:
        consulta_str += " AND idiomas_disponibles ILIKE :idioma"
        parametros["idioma"] = f"%{idioma}%"

    consulta_str += " LIMIT 50;"

    # 4. Ejecutamos usando text() y pasamos el diccionario de parámetros
    resultados = db.execute(text(consulta_str), parametros).mappings().fetchall()

    # 5. Formateamos la respuesta (usando .get() sobre el mapping por seguridad)
    datos = []
    for fila in resultados:
        datos.append({
            "pelicula": fila.get("pelicula", "Sin título"),
            "trailer_key": fila.get("trailer_link", ""),
            "categorias": fila.get("categorias", ""),
            "paises_permitidos": fila.get("paises_permitidos", ""),
            "idiomas": fila.get("idiomas_disponibles", "")
        })

    return {"datos": datos}


# 4. Motor de Descarga Asíncrona (Background Task)
def tarea_descarga(trailer_key: str):
    opciones = {
        # 'best' busca el mejor archivo único que ya tenga audio y video juntos
        'format': 'best[ext=mp4]', 
        'outtmpl': f'media/{trailer_key}.mp4',
        'quiet': True,
        'noplaylist': True
    }
    
    try:
        with yt_dlp.YoutubeDL(opciones) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={trailer_key}"])
        print(f"Descarga completada en MP4: {trailer_key}")
    except Exception as e:
        print(f"Error descargando {trailer_key}: {e}")


# 5. Endpoint: Gestionar la petición de video
@app.post("/api/descargar/{trailer_key}")
def descargar_video_local(trailer_key: str, background_tasks: BackgroundTasks):
    ruta_archivo = f"media/{trailer_key}.mp4"
    
    # Si ya lo descargó otro usuario, lo servimos de caché instantáneamente
    if os.path.exists(ruta_archivo):
        return {"status": "ready", "video_url": f"http://127.0.0.1:8000/{ruta_archivo}"}
    
    # Si no existe, iniciamos la tarea asíncrona sin bloquear la respuesta
    background_tasks.add_task(tarea_descarga, trailer_key)
    
    return {
        "status": "downloading", 
        "mensaje": "Descarga liviana en segundo plano iniciada."
    }

@app.get("/api/carruseles/{user_id}")
def obtener_carruseles_usuario(user_id: int, db: Session = Depends(get_db)):
    # 1. Obtener el país del usuario para el carrusel nacional
    consulta_usuario = text("SELECT country_code FROM users WHERE id = :user_id")
    usuario = db.execute(consulta_usuario, {"user_id": user_id}).fetchone()
    
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    country_code = usuario.country_code
    
    carruseles = {
        "seguir_viendo": [],
        "nacionales": [],
        "guardados": [],
        "recomendados": []
    }

    # 2. Carrusel: Seguir Viendo (watch_progress)
    consulta_progreso = text("""
        SELECT c.* 
        FROM watch_progress wp 
        JOIN catalogo_trailers c ON wp.id_trailer = c.movie_id 
        WHERE wp.user_id = :user_id 
        ORDER BY wp.updated_at DESC LIMIT 10
    """)
    carruseles["seguir_viendo"] = [dict(row) for row in db.execute(consulta_progreso, {"user_id": user_id}).mappings()]

    # 3. Carrusel: Nacionales (Filtro por país del usuario)
    if country_code:
        consulta_nacionales = text("""
            SELECT * FROM catalogo_trailers 
            WHERE paises_permitidos ILIKE :pais 
            LIMIT 15
        """)
        carruseles["nacionales"] = [dict(row) for row in db.execute(consulta_nacionales, {"pais": f"%{country_code}%"}).mappings()]

    # 4. Carrusel: Guardados (user_watchlist)
    consulta_guardados = text("""
        SELECT c.* 
        FROM user_watchlists uw 
        JOIN catalogo_trailers c ON uw.movie_id = c.movie_id 
        WHERE uw.user_id = :user_id 
        ORDER BY uw.added_at DESC LIMIT 15
    """)
    carruseles["guardados"] = [dict(row) for row in db.execute(consulta_guardados, {"user_id": user_id}).mappings()]

    # 5. Carrusel: Recomendados (Basado en el top score de user_category_scores)
    # Seleccionamos la categoría con mayor puntaje para este usuario
    consulta_top_categoria = text("""
        SELECT category_id FROM user_category_scores 
        WHERE user_id = :user_id 
        ORDER BY score DESC LIMIT 1
    """)
    top_categoria = db.execute(consulta_top_categoria, {"user_id": user_id}).scalar()

    if top_categoria:
        # Aquí asumimos que category_id se mapea al texto en 'categorias'. 
        # En tu modelo real, esto cruzaría con una tabla de categorías.
        consulta_recomendados = text("""
            SELECT * FROM catalogo_trailers 
            WHERE categorias ILIKE :categoria 
            LIMIT 15
        """)
        # Nota: Ajusta el parámetro según cómo guardes el nombre de la categoría
        carruseles["recomendados"] = [dict(row) for row in db.execute(consulta_recomendados, {"categoria": f"%{top_categoria}%"}).mappings()]
    else:
        # Si no tiene puntajes, mostramos los más recientes por defecto
        consulta_defecto = text("SELECT * FROM catalogo_trailers ORDER BY anio DESC LIMIT 15")
        carruseles["recomendados"] = [dict(row) for row in db.execute(consulta_defecto).mappings()]

    return carruseles