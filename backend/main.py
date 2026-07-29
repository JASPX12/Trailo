import os
import yt_dlp
from fastapi import FastAPI, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db

app = FastAPI(title="OTT MVP Backend", version="0.1.0")

# 1. Configuración de CORS para permitir peticiones del frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Sistema de archivos para Video On Demand local
os.makedirs("media", exist_ok=True)
app.mount("/media", StaticFiles(directory="media"), name="media")


# 3. Endpoint: Consultar el catálogo local
@app.get("/api/catalogo")
def obtener_catalogo_completo(db: Session = Depends(get_db)):
    # Limitamos a 50 para el prototipo inicial
    consulta = text("SELECT * FROM catalogo_trailers LIMIT 50;")
    resultados = db.execute(consulta).fetchall()
    
    datos = []
    for fila in resultados:
        datos.append({
            "pelicula": getattr(fila, "pelicula", "Sin título"),
            "trailer_key": getattr(fila, "trailer_link", ""),
            "categorias": getattr(fila, "categorias", ""),
            "paises_permitidos": getattr(fila, "paises_permitidos", ""),
            "idiomas": getattr(fila, "idiomas_disponibles", "")
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