# main.py
import webview
import threading
import sys
from backend import app, sock # Importar app y sock desde tu backend.py

# Puerto para Flask (puede ser diferente si es necesario)
FLASK_PORT = 5000 
# URL que cargará pywebview
web_url = f"http://localhost:{FLASK_PORT}" 

# Variable global para la ventana de pywebview
window = None

def run_flask():
    """Función para ejecutar Flask en un hilo separado."""
    print(f"Iniciando servidor Flask/WebSocket en {web_url}...")
    try:
        # Usa 'gunicorn' o 'waitress' en producción en lugar de app.run(debug=True)
        # Para desarrollo simple, app.run está bien
        # Asegúrate de que el puerto coincida con web_url
        # host='0.0.0.0' permite conexiones desde otras máquinas en la red (si es necesario)
        # host='127.0.0.1' solo permite conexiones locales (más seguro por defecto)
        app.run(host='127.0.0.1', port=FLASK_PORT, debug=False, threaded=True) # debug=False es mejor con pywebview
        print("Servidor Flask detenido.")
    except Exception as e:
        print(f"Error al iniciar el servidor Flask: {e}")
        # Intentar cerrar la ventana de pywebview si Flask falla al iniciar
        if window:
             print("Cerrando ventana de la aplicación debido a error del servidor.")
             window.destroy()

def main():
    global window
    print("Iniciando aplicación GUIperf3...")
    
    # Iniciar Flask en un hilo demonio
    # Un hilo demonio se cerrará automáticamente cuando el hilo principal (pywebview) termine
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Crear y mostrar la ventana de pywebview
    print(f"Creando ventana webview apuntando a {web_url}")
    try:
         window = webview.create_window(
             'Cliente Gráfico GUIperf3',  # Título de la ventana
             web_url,                   # URL a cargar
             width=1280,                 # Ancho inicial
             height=960,                # Alto inicial
             resizable=True,           # Permitir redimensionar
             confirm_close=False        # Preguntar antes de cerrar
         )
         
         # Iniciar el bucle de eventos de pywebview (esto bloquea hasta que se cierra la ventana)
         # debug=True abre las herramientas de desarrollador del navegador (¡útil!)
         # Usar debug=False para la versión final empaquetada
         webview.start(debug=False) 

    except Exception as e:
        print(f"Error al crear o iniciar la ventana de pywebview: {e}")
    finally:
        # Esto se ejecuta cuando la ventana de pywebview se cierra
        print("Ventana cerrada. La aplicación terminará.")
        # El hilo de Flask (demonio) debería detenerse automáticamente.
        # Si usaste un servidor como gunicorn, podrías necesitar detenerlo explícitamente.

if __name__ == '__main__':
    main()