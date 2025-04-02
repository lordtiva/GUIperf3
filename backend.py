# backend.py
import sys
import os
import subprocess
import json
import threading
import time
import re
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_sock import Sock

app = Flask(__name__)
# Configura CORS de forma más restrictiva si sabes desde dónde se servirá tu GUI
# Si pywebview carga desde file://, puede que no necesites CORS. Para http://localhost, sí.
CORS(app) 
sock = Sock(app)

# --- Lógica para encontrar iperf3 (¡IMPORTANTE PARA PACKAGING!) ---
def get_iperf3_path():
    """Obtiene la ruta al ejecutable iperf3 empaquetado o del sistema."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Ejecutando en un paquete PyInstaller/cx_Freeze
        base_path = sys._MEIPASS
        print(f"INFO: Ejecutando desde paquete, buscando iperf3 en: {base_path}")
    else:
        # Ejecutando como script normal
        base_path = os.path.abspath(os.path.dirname(__file__)) # Directorio del script backend.py
        print(f"INFO: Ejecutando como script, buscando iperf3 cerca de: {base_path}")

    iperf3_name = "iperf3.exe" if sys.platform == "win32" else "iperf3"
    
    # Buscar en la raíz del proyecto, en ./bin, o relativo al script
    possible_paths = [
        os.path.join(base_path, iperf3_name),
        os.path.join(base_path, 'bin', iperf3_name), # Si lo pones en una carpeta bin/
        # Si main.py está un nivel arriba y bin/ también
        os.path.join(os.path.dirname(base_path), 'bin', iperf3_name), 
        os.path.join(os.path.dirname(base_path), iperf3_name), 
    ]

    for path in possible_paths:
        if os.path.exists(path) and os.path.isfile(path):
            print(f"INFO: iperf3 encontrado en: {path}")
            return path

    # Si no se encuentra empaquetado, intenta usar el del PATH (menos ideal)
    print(f"ADVERTENCIA: iperf3 no encontrado en las rutas buscadas ({possible_paths}). Intentando buscar en el PATH del sistema.")
    # Devolver solo el nombre para que Popen lo busque en el PATH
    # Si quieres forzar que *debe* estar empaquetado, lanza un error aquí.
    # raise FileNotFoundError("iperf3 no encontrado en el paquete.") 
    return iperf3_name 

IPERF3_EXECUTABLE = get_iperf3_path()
# Diccionario para rastrear procesos iperf por conexión WebSocket
active_processes = {}

# --- Limpieza de JSON (si aún es necesaria) ---
def clean_json_output(output):
    """Intenta limpiar la salida de iperf3 si no es JSON válido."""
    # Intenta encontrar el inicio del JSON
    json_start_index = output.find('{')
    if json_start_index == -1:
        return output # No parece haber JSON

    # Intenta encontrar el final del JSON (última '}')
    json_end_index = output.rfind('}')
    if json_end_index == -1 or json_end_index < json_start_index:
        return output # No parece haber JSON completo

    cleaned_output = output[json_start_index : json_end_index + 1]
    
    # Eliminación básica de caracteres de control o líneas extra antes/después
    cleaned_output = ''.join(char for char in cleaned_output if char.isprintable() or char in ['\n', '\r', '\t'])
    cleaned_output = cleaned_output.strip()
    
    # Quitar comas finales antes de } o ] (puede ser necesario)
    cleaned_output = re.sub(r',\s*([\}\]])', r'\1', cleaned_output)

    return cleaned_output

# --- Ejecución de iperf3 ---
def run_iperf(config, ws_id, ws):
    """Ejecuta iperf3 y envía resultados por WebSocket."""
    global active_processes
    process = None # Inicializar process

    try:
        iperf_command = [IPERF3_EXECUTABLE] # Usa la ruta encontrada

        # --- Validación y Construcción del Comando ---
        is_server_mode = config.get("mode") == "server"

        if is_server_mode:
            iperf_command.append("-s")
            iperf_command.extend(["-p", str(config.get("serverPort", 5201))])
            if config.get("oneOff"):
                iperf_command.append("-1")
            bind_interface = config.get("bindInterface")
            if bind_interface:
                # Validación simple (mejorar si es necesario)
                if not re.match(r'^[a-zA-Z0-9\.\-\:]+$', bind_interface):
                     raise ValueError("Interfaz/IP de bind inválida.")
                iperf_command.extend(["--bind", bind_interface])
        else: # Modo cliente
            server_address = config.get("serverAddress")
            if not server_address:
                 raise ValueError("La dirección del servidor es requerida en modo cliente.")
            # Validación simple (mejorar si es necesario)
            if not re.match(r'^[a-zA-Z0-9\.\-\:]+$', server_address):
                 raise ValueError("Dirección de servidor inválida.")
                 
            iperf_command.extend(["-c", server_address])
            iperf_command.extend(["-p", str(config.get("serverPort", 5201))])
            
            protocol = config.get("protocol", "tcp")
            if protocol == "udp":
                iperf_command.append("-u")
                iperf_command.extend(["-b", config.get("bandwidth", "1M")]) # Default 1M para UDP
                if config.get("ttl"):
                    iperf_command.extend(["--ttl", str(config["ttl"])])
            elif protocol == "sctp":
                iperf_command.append("--sctp")
            elif protocol != "tcp":
                 raise ValueError(f"Protocolo no soportado: {protocol}")

            direction = config.get("direction", "upload")
            if direction == "download":
                iperf_command.append("-R")
            # Nota: iperf3 -d (bidireccional) es experimental y su salida JSON puede variar.
            # elif direction == "bidirectional":
            #     iperf_command.append("-d")
            elif direction != "upload":
                 raise ValueError(f"Dirección no soportada: {direction}")

            # --- Opciones de duración/tamaño (CORREGIDO) ---
            data_amount = config.get("dataAmount")
            duration = config.get("duration", 10) # Default 10s si no hay dataAmount

            if data_amount:
                # Si se especifica cantidad de datos, usar -n y NO -t
                iperf_command.extend(["-n", data_amount])
                print(f"[{ws_id}] Usando cantidad de datos (-n {data_amount}) en lugar de duración.")
            else:
                # Si no hay cantidad de datos, usar duración -t
                iperf_command.extend(["-t", str(duration)])

            # --- Intervalo ---
            iperf_command.extend(["-i", str(config.get("reportInterval", 1))]) # Default 1s
            
            # --- Otras opciones de cliente ---
            if config.get("bufferSize"):
                iperf_command.extend(["-l", config["bufferSize"]])
            
            bind_interface = config.get("bindInterface") # Puede ser diferente del servidor
            if bind_interface:
                 if not re.match(r'^[a-zA-Z0-9\.\-\:]+$', bind_interface):
                      raise ValueError("Interfaz/IP de bind (cliente) inválida.")
                 iperf_command.extend(["--bind", bind_interface])


            if protocol == "tcp":
                if config.get("noDelay"):
                    iperf_command.append("-N")
                if config.get("windowSize"):
                    iperf_command.extend(["-w", config["windowSize"]])
                if config.get("mss"):
                    iperf_command.extend(["-M", config["mss"]])
                congestion = config.get("congestion")
                if congestion:
                    # Validación simple (solo caracteres seguros)
                    if not re.match(r'^[a-zA-Z0-9_\-]+$', congestion):
                        raise ValueError("Nombre de algoritmo de congestión inválido.")
                    iperf_command.extend(["--congestion", congestion])

        # --- Opciones Comunes ---
        if config.get("verbose"):
            iperf_command.append("-V")
            
        log_file = config.get("logFile")
        if log_file:
             # ¡¡VALIDAR ESTA RUTA CUIDADOSAMENTE!! 
             # Permitir solo nombres de archivo relativos simples por seguridad
             safe_logfile = os.path.basename(log_file) 
             if safe_logfile != log_file or not re.match(r'^[a-zA-Z0-9_\-\.]+$', safe_logfile):
                 raise ValueError("Nombre de archivo de log inválido o contiene rutas.")
             iperf_command.extend(["--logfile", safe_logfile])

        # Añadir -J al final
        iperf_command.append("-J") # Salida en formato JSON

        # --- Ejecución del Proceso ---
        command_str = ' '.join(iperf_command)
        print(f"[{ws_id}] Comando iperf: {command_str}")
        ws.send(json.dumps({"type": "status", "message": f"Ejecutando: {command_str}"}))

        process = subprocess.Popen(iperf_command, 
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   text=True,
                                   encoding='utf-8',
                                   errors='replace')

        active_processes[ws_id] = process
        print(f"[{ws_id}] Proceso iperf iniciado (PID: {process.pid}).")

        # --- Ya NO intentaremos parsear intervalos en tiempo real aquí ---
        # Simplemente esperamos a que el proceso termine y recogemos TODO.
        # El bucle 'for line in iter...' se elimina o simplifica.
        
        # Opción simple: Esperar y comunicar directamente
        print(f"[{ws_id}] Esperando finalización de iperf3...")
        try:
             # Añadir un timeout un poco mayor que la duración esperada (si la hay)
             # o un timeout general razonable si se usa -n.
             timeout_duration = None
             if config.get("duration"):
                 timeout_duration = int(config["duration"]) + 15 # Segundos extra de margen
             elif config.get("dataAmount"):
                 timeout_duration = 300 # Timeout generoso para transferencia por tamaño (5 min)
             else:
                  timeout_duration = 60 # Timeout por defecto si no hay duración ni tamaño

             stdout_data, stderr_data = process.communicate(timeout=timeout_duration)
        except subprocess.TimeoutExpired:
             process.kill() # Matar si excede el timeout
             stdout_data, stderr_data = process.communicate() # Obtener lo que se pueda
             print(f"[{ws_id}] ERROR: iperf3 excedió el timeout de {timeout_duration}s y fue terminado.")
             ws.send(json.dumps({"type": "error", "message": f"La prueba excedió el tiempo límite ({timeout_duration}s)."}))
             # Salir de la función si hubo timeout, ya hemos enviado el error.
             # La limpieza en finally se ejecutará.
             return 
        except Exception as comm_err:
             # Otro error durante communicate
             print(f"[{ws_id}] ERROR durante process.communicate(): {comm_err}")
             # Intentar obtener código de retorno si es posible
             return_code = process.poll() if process else -1 
             ws.send(json.dumps({"type": "error", "message": f"Error interno esperando resultado de iperf3 (código: {return_code})."}))
             return


        full_output = stdout_data.strip() 
        return_code = process.returncode

        print(f"[{ws_id}] iperf terminó con código: {return_code}")
        
        # --- Procesamiento Final (Similar a antes, pero ahora es el principal) ---
        stderr_strip = stderr_data.strip()
        stderr_already_sent = False 
        if stderr_strip:
            print(f"[{ws_id}] iperf stderr:\n{stderr_strip}")
            if return_code != 0 and ("warning:" not in stderr_strip.lower() and "terminated" not in stderr_strip.lower()):
                 ws.send(json.dumps({"type": "error", "message": f"iperf stderr: {stderr_strip}"}))
                 stderr_already_sent = True

        # --- Parseo del JSON completo y envío de datos ---
        iperf_error_message = None 
        data = None 

        if full_output and full_output.strip().startswith('{'):
            try:
                data = json.loads(full_output)
                print(f"[{ws_id}] iperf JSON completo parseado OK.")
                if "error" in data:
                     iperf_error_message = data["error"]
                     print(f"[{ws_id}] Mensaje de error encontrado en JSON de iperf3: {iperf_error_message}")
                     if not stderr_already_sent:
                          ws.send(json.dumps({"type": "error", "message": f"Error de iperf3: {iperf_error_message}"}))
            # ... (Bloque except json.JSONDecodeError con intento de clean_json_output como antes) ...
            except json.JSONDecodeError:
                print(f"[{ws_id}] Falló el parseo JSON completo. Intentando limpiar...")
                cleaned_output = clean_json_output(full_output)
                try:
                    data = json.loads(cleaned_output)
                    print(f"[{ws_id}] iperf JSON limpiado parseado OK.")
                    if "error" in data:
                         iperf_error_message = data["error"]
                         print(f"[{ws_id}] Mensaje de error encontrado en JSON (limpiado) de iperf3: {iperf_error_message}")
                         if not stderr_already_sent:
                              ws.send(json.dumps({"type": "error", "message": f"Error de iperf3: {iperf_error_message}"}))
                except json.JSONDecodeError as e:
                    print(f"[{ws_id}] ERROR: Falló el parseo JSON incluso después de limpiar: {e}")
                    if not stderr_already_sent and not iperf_error_message:
                         ws.send(json.dumps({"type": "error", 
                                             "message": "Error al decodificar la salida JSON final de iperf3.", 
                                             "details": full_output[:500]}))
        
        # --- >>> NUEVO: Enviar Intervalos Acumulados <<< ---
        if data and not iperf_error_message and "intervals" in data:
             print(f"[{ws_id}] Enviando {len(data['intervals'])} intervalos acumulados...")
             for interval_item in data["intervals"]:
                 interval_sum = interval_item.get("sum")
                 if interval_sum and isinstance(interval_sum, dict) and \
                    'start' in interval_sum and 'end' in interval_sum and \
                    'bits_per_second' in interval_sum:
                      
                      # Definir el diccionario interval_data
                      interval_data = {
                         "type": "interval",
                         "timestamp": time.time(), # Usar tiempo actual puede no ser ideal, pero es simple
                         "interval": f"{interval_sum.get('start', '?')}-{interval_sum.get('end', '?')}",
                         "transfer_mb": round(interval_sum.get('bytes', 0) / (1024*1024), 2),
                         "bandwidth_mbps": round(interval_sum.get('bits_per_second', 0) / 1e6, 2),
                         "unit": "Mbps"
                      }
                      if "jitter_ms" in interval_sum:
                           interval_data["jitter_ms"] = round(interval_sum.get('jitter_ms', 0), 3)
                           interval_data["lost_percent"] = round(interval_sum.get('lost_percent', 0), 2)
                      
                      # Enviar el intervalo al WebSocket
                      # print(f"[{ws_id}] Enviando intervalo: {interval_data}") # Debug opcional
                      ws.send(json.dumps(interval_data))
                 else:
                      print(f"[{ws_id}] ADVERTENCIA: Intervalo inválido o incompleto encontrado: {interval_item}")


        # --- Enviar Resumen (si aplica) ---
        if data and not iperf_error_message and "end" in data: 
            # ... (Lógica existente para extraer y enviar 'summary_data') ...
            # (Asegúrate que esta lógica esté aquí y funcione)
            summary_section = data["end"]
            summary = None 
            is_server_mode = config.get("mode") == "server"
            direction = config.get("direction", "upload")
            if is_server_mode: summary = summary_section.get("sum_received") or summary_section.get("sum")
            elif direction == "download": summary = summary_section.get("sum_received")
            else: summary = summary_section.get("sum_sent")
            if not summary: summary = summary_section.get("sum") # Fallback
            
            if summary:
                actual_duration = summary.get("seconds", config.get("duration"))
                data_amount = config.get("dataAmount") # Necesitas obtener dataAmount aquí también
                if data_amount and not actual_duration: actual_duration = summary_section.get("sum_sent",{}).get("seconds")
                summary_data = {
                    "type": "summary", "timestamp": time.time(),
                    "total_transfer_mb": round(summary.get('bytes', 0) / (1024*1024), 2),
                    "avg_bandwidth_mbps": round(summary.get('bits_per_second', 0) / 1e6, 2),
                    "duration_s": round(actual_duration, 2) if actual_duration else '?',
                    "unit": "Mbps"
                }
                if "jitter_ms" in summary:
                    summary_data["avg_jitter_ms"] = round(summary.get('jitter_ms', 0), 3)
                    summary_data["total_lost_percent"] = round(summary.get('lost_percent', 0), 2)

                print(f"[{ws_id}] Enviando resumen: {summary_data}")
                ws.send(json.dumps(summary_data))
            else:
                 warning_msg = f"No se encontró sección de resumen válida ('sum_sent/received/sum') en 'end'."
                 print(f"[{ws_id}] ADVERTENCIA: {warning_msg}")
                 # No enviar advertencia si ya hubo un error más grave
                 if return_code == 0 and not iperf_error_message and not stderr_already_sent:
                      ws.send(json.dumps({"type": "warning", "message": warning_msg}))


        # --- Manejo de otros errores finales ---
        elif return_code == 0 and not iperf_error_message and not data:
             # Terminó bien, sin error iperf, pero no se pudo parsear JSON.
             ws.send(json.dumps({"type": "error", "message": "La prueba terminó sin errores, pero no se pudo interpretar la salida JSON."}))
        elif return_code != 0 and not iperf_error_message and not stderr_already_sent:
             # Falló iperf, sin error iperf en JSON, sin error stderr enviado.
             fallback_error = stderr_strip if stderr_strip else f"Prueba fallida con código iperf3 {return_code}."
             print(f"[{ws_id}] Enviando error fallback por código de salida != 0: {fallback_error}")
             ws.send(json.dumps({"type": "error", "message": fallback_error}))
        elif return_code !=0 and iperf_error_message:
             # iperf falló, pero ya enviamos el error específico del JSON. No hacer nada más.
             print(f"[{ws_id}] iperf falló, error JSON específico ya enviado.")
        elif return_code !=0 and stderr_already_sent:
              # iperf falló, pero ya enviamos el error específico del stderr. No hacer nada más.
              print(f"[{ws_id}] iperf falló, error stderr específico ya enviado.")


    except FileNotFoundError:
         error_msg = f"ERROR: El ejecutable '{IPERF3_EXECUTABLE}' no se encontró. Asegúrate de que iperf3 esté instalado y en el PATH o empaquetado correctamente."
         print(f"[{ws_id}] {error_msg}")
         ws.send(json.dumps({"type": "error", "message": error_msg}))
    except ValueError as ve: # Captura errores de validación de configuración
         error_msg = f"Error de configuración: {ve}"
         print(f"[{ws_id}] ERROR: {error_msg}")
         ws.send(json.dumps({"type": "error", "message": error_msg}))
    except Exception as e:
        error_message = f"Error inesperado ejecutando iperf3: {e.__class__.__name__}: {e}"
        import traceback
        print(f"[{ws_id}] {error_message}\n{traceback.format_exc()}") # Log completo del error
        try:
            # Enviar un mensaje de error genérico al cliente
            ws.send(json.dumps({"type": "error", "message": "Ocurrió un error inesperado en el backend."}))
        except Exception as ws_err:
            print(f"[{ws_id}] Error enviando mensaje de error por WebSocket: {ws_err}")
    finally:
        # --- Limpieza Final ---
        if ws_id in active_processes:
            process_to_clean = active_processes.get(ws_id) 
            if process_to_clean and process_to_clean.poll() is None: 
                 print(f"[{ws_id}] Proceso iperf aún activo al final de run_iperf, intentando terminar...")
                 process_to_clean.terminate() 
                 try:
                     process_to_clean.wait(timeout=1) 
                 except subprocess.TimeoutExpired:
                     print(f"[{ws_id}] Proceso no terminó con SIGTERM, forzando kill (SIGKILL)...")
                     process_to_clean.kill() 
            print(f"[{ws_id}] Limpiando proceso del registro en finally.")
            # Asegurarse de eliminarlo si todavía existe
            if ws_id in active_processes:
                 del active_processes[ws_id] 
        else:
            print(f"[{ws_id}] No se encontró proceso activo para limpiar en finally.")


# --- Endpoint WebSocket ---
@sock.route('/iperf')
def iperf_websocket(ws):
    """Maneja la conexión WebSocket para las pruebas iperf3."""
    # Usar un ID único basado en el objeto ws o un contador sería más robusto que el thread ID
    # Pero para empezar, thread ID puede funcionar si no reutilizas hilos rápidamente.
    ws_id = str(threading.get_ident()) 
    print(f"Cliente WebSocket conectado: {ws_id}")
    
    try:
        while True:
            message = ws.receive()
            if message is None:
                print(f"[{ws_id}] Cliente WebSocket desconectado (mensaje None recibido).")
                break # Salir del bucle si la conexión se cierra limpiamente desde el cliente

            print(f"[{ws_id}] Mensaje recibido: {message[:300]}...") # Limita el log de mensajes largos

            try:
                data = json.loads(message)
                action = data.get("action")

                if action == "start":
                    # Si ya hay una prueba corriendo para este cliente, ¿qué hacer?
                    # Opción 1: Rechazar la nueva prueba
                    if ws_id in active_processes:
                         print(f"[{ws_id}] ADVERTENCIA: Se recibió 'start' mientras ya hay una prueba activa. Ignorando.")
                         ws.send(json.dumps({"type": "warning", "message": "Ya hay una prueba en curso."}))
                         continue # Ignorar este mensaje y esperar el siguiente
                    # Opción 2: Detener la anterior y empezar la nueva (menos común)
                    # ... (código para detener si existe process = active_processes.get(ws_id)) ...

                    config = data.get("config", {})
                    print(f"[{ws_id}] Recibida configuración para iniciar: {config}")
                    
                    # Iniciar iperf en un hilo separado para no bloquear el WebSocket
                    iperf_thread = threading.Thread(target=run_iperf, args=(config, ws_id, ws))
                    iperf_thread.daemon = True # Permite salir aunque el hilo corra
                    iperf_thread.start()
                    
                elif action == "stop":
                     print(f"[{ws_id}] Solicitud de detener recibida.")
                     process_to_stop = active_processes.get(ws_id)
                     if process_to_stop:
                         print(f"[{ws_id}] Intentando detener proceso iperf (PID: {process_to_stop.pid})...")
                         process_to_stop.terminate() # Envía SIGTERM
                         # Nota: No esperamos aquí, la función run_iperf manejará la finalización
                         # y la limpieza de active_processes eventualmente.
                         # Solo enviamos una confirmación de que se intentó detener.
                         ws.send(json.dumps({"type": "status", "message": "Solicitud de detención enviada."}))
                     else:
                         print(f"[{ws_id}] No se encontró proceso activo para detener.")
                         ws.send(json.dumps({"type": "warning", "message": "No había ninguna prueba activa para detener."}))
                else:
                     print(f"[{ws_id}] Acción desconocida recibida: {action}")
                     ws.send(json.dumps({"type": "error", "message": f"Acción no reconocida: {action}"}))


            except json.JSONDecodeError:
                print(f"[{ws_id}] Error: Mensaje recibido no es JSON válido.")
                ws.send(json.dumps({"type": "error", "message": "Mensaje JSON inválido recibido."}))
            except ValueError as ve: # Captura errores de validación de run_iperf si ocurren síncronamente
                 error_msg = f"Error en la solicitud: {ve}"
                 print(f"[{ws_id}] {error_msg}")
                 ws.send(json.dumps({"type": "error", "message": error_msg}))
            except Exception as e: # Captura otros errores al procesar el mensaje
                error_msg = f"Error procesando mensaje WebSocket: {e.__class__.__name__}: {e}"
                import traceback
                print(f"[{ws_id}] {error_msg}\n{traceback.format_exc()}")
                ws.send(json.dumps({"type": "error", "message": "Error interno procesando la solicitud."}))

    except ConnectionAbortedError:
         print(f"[{ws_id}] Conexión WebSocket abortada por el cliente.")
    except Exception as e: # Error general del WebSocket (p.ej., desconexión abrupta)
        # Podría ser websockets.exceptions.ConnectionClosedOK, ConnectionClosedError etc. dependiendo de la librería subyacente
        print(f"[{ws_id}] Error o cierre en la conexión WebSocket: {e.__class__.__name__}: {e}")
    finally:
        print(f"[{ws_id}] Cerrando conexión WebSocket y limpiando recursos...")
        # --- Limpieza al Cerrar WebSocket ---
        # Es crucial detener cualquier proceso iperf asociado a esta conexión si aún existe
        process_to_stop = active_processes.get(ws_id)
        if process_to_stop:
            print(f"[{ws_id}] La conexión WebSocket se cerró. Deteniendo proceso iperf asociado (PID: {process_to_stop.pid})...")
            if process_to_stop.poll() is None: # Verificar si aún corre antes de intentar detener
                 process_to_stop.terminate()
                 # Dar un respiro muy corto para que termine
                 time.sleep(0.2) 
                 if process_to_stop.poll() is None: # Si sigue vivo, forzar
                     print(f"[{ws_id}] Forzando kill del proceso remanente...")
                     process_to_stop.kill()
            # Eliminar del diccionario ahora que la conexión murió
            # (run_iperf podría intentar eliminarlo también, pero es seguro hacerlo aquí)
            if ws_id in active_processes:
                 del active_processes[ws_id] 
                 print(f"[{ws_id}] Proceso eliminado del registro debido a cierre de WS.")
        
        # No es necesario llamar a ws.close() explícitamente aquí, 
        # el contexto `finally` o el manejo de excepciones de Flask-Sock/Werkzeug lo harán.


# --- Endpoint para servir la GUI ---
@app.route('/')
def index():
    """Sirve el archivo HTML principal de la interfaz."""
    # Usar render_template busca en la carpeta 'templates' por defecto
    return render_template('index.html')

# --- Endpoint de Verificación (mejorado) ---
@app.route('/verify_connection', methods=['POST'])
def verify_connection():
    """Verifica rápidamente la conexión a un servidor iperf3."""
    ws_id = f"verify_{str(threading.get_ident())}" # ID temporal para logs
    try:
        data = request.get_json()
        if not data:
             return jsonify({"status": "error", "message": "Falta cuerpo JSON en la solicitud."}), 400
             
        server_address = data.get('serverAddress')
        server_port = data.get('serverPort', 5201)

        if not server_address:
            return jsonify({"status": "error", "message": "Falta la dirección del servidor."}), 400

        # Comando corto para verificar conectividad (-t 1 o -n pequeño)
        # Usar -t 1 es generalmente bueno. -J es crucial.
        iperf_command = [IPERF3_EXECUTABLE, "-c", server_address, "-p", str(server_port), "-t", "1", "-J"]
        print(f"[{ws_id}] Comando de verificación: {' '.join(iperf_command)}")

        # Usar run para simplicidad aquí, con timeout
        process = subprocess.run(iperf_command, 
                                 capture_output=True, 
                                 text=True, 
                                 timeout=7, # Aumentar ligeramente el timeout
                                 encoding='utf-8', 
                                 errors='replace')

        print(f"[{ws_id}] Verify stdout: {process.stdout[:200]}...") # Log limitado
        print(f"[{ws_id}] Verify stderr: {process.stderr[:200]}...") # Log limitado
        print(f"[{ws_id}] Verify return code: {process.returncode}")

        # Analizar resultado
        if process.returncode == 0:
            # iperf terminó sin error, intentar parsear JSON
            try:
                result = json.loads(process.stdout)
                # Criterio más fiable: ¿Existe 'start' y 'end'?
                if "start" in result and "end" in result: 
                    # Podríamos extraer el bit/s del resumen si quisiéramos
                    bw = result.get("end", {}).get("sum_sent", {}).get("bits_per_second", 0)
                    bw_mbps = round(bw / 1e6, 2)
                    msg = f"Conexión exitosa (aprox. {bw_mbps} Mbps en prueba corta)."
                    print(f"[{ws_id}] Verificación OK: {msg}")
                    return jsonify({"status": "success", "message": msg})
                else:
                     # Terminó bien pero JSON no tiene estructura esperada? Raro.
                     warning_msg = "Prueba corta OK, pero respuesta JSON inesperada."
                     print(f"[{ws_id}] ADVERTENCIA Verificación: {warning_msg}")
                     return jsonify({"status": "warning", "message": warning_msg, "output": process.stdout[:500]})

            except json.JSONDecodeError:
                # Si devuelve 0 pero la salida no es JSON, es muy raro.
                 error_msg = "Respuesta inesperada del servidor (no es JSON)."
                 print(f"[{ws_id}] ERROR Verificación: {error_msg}\nSTDOUT:\n{process.stdout}")
                 return jsonify({"status": "error", "message": error_msg, "output": process.stdout[:1000]})
        else:
            # iperf falló (código != 0)
            error_message = f"No se pudo conectar (código iperf3: {process.returncode})."
            details = process.stderr.strip() if process.stderr else "Sin detalles en stderr."
            
            # Intentar dar mensajes más útiles basados en stderr
            details_lower = details.lower()
            if "connection refused" in details_lower:
                 error_message = "Error: Conexión rechazada. ¿Está el servidor iperf3 corriendo en ese puerto?"
            elif "no route to host" in details_lower:
                 error_message = "Error: No se puede alcanzar la dirección del servidor (problema de red/ruta)."
            elif "timed out" in details_lower or "timeout" in details_lower:
                 error_message = "Error: Tiempo de espera agotado al intentar conectar (firewall o servidor no responde)."
            elif "unable to connect" in details_lower:
                 error_message = "Error: No se pudo establecer conexión (causa específica en detalles)."
            elif "parameter error" in details_lower:
                 error_message = "Error: Problema con los parámetros enviados a iperf3 (error interno)."
            
            print(f"[{ws_id}] ERROR Verificación: {error_message}\nSTDERR:\n{details}")
            return jsonify({"status": "error", "message": error_message, "output": details})

    except subprocess.TimeoutExpired:
         error_msg = "Timeout: La verificación de conexión tardó demasiado (>7s)."
         print(f"[{ws_id}] ERROR Verificación: {error_msg}")
         return jsonify({"status": "error", "message": error_msg})
    except FileNotFoundError:
         error_msg = f"Error crítico: Ejecutable iperf3 no encontrado en {IPERF3_EXECUTABLE}."
         print(f"[{ws_id}] ERROR FATAL Verificación: {error_msg}")
         # Devolver 500 Internal Server Error porque es un problema de configuración del backend
         return jsonify({"status": "error", "message": "Error interno del servidor: no se encuentra iperf3."}), 500
    except Exception as e:
        error_msg = f"Error inesperado durante la verificación: {e.__class__.__name__}: {e}"
        import traceback
        print(f"[{ws_id}] ERROR Verificación: {error_msg}\n{traceback.format_exc()}")
        return jsonify({"status": "error", "message": "Error interno inesperado durante la verificación."}), 500


# --- Inicio (Solo si se ejecuta directamente, no desde main.py) ---
# Normalmente, main.py se encargará de llamar a app.run()
if __name__ == '__main__':
    print("ADVERTENCIA: Ejecutando backend.py directamente.")
    print(f"Intentando iniciar servidor en http://127.0.0.1:5000")
    # Es mejor usar el servidor de desarrollo de Flask/Werkzeug para debug directo
    app.run(host='127.0.0.1', port=5000, debug=True, threaded=True)