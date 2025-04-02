# GUIperf3

Una interfaz gráfica de usuario (GUI) amigable para la herramienta de pruebas de rendimiento de red [iperf3](https://iperf.fr/), construida con Python, Flask y pywebview. Facilita la ejecución de pruebas iperf3 sin necesidad de usar la línea de comandos.

## Características

*   **Interfaz Gráfica:** Configura y ejecuta pruebas iperf3 a través de una GUI intuitiva.
*   **Modos Cliente y Servidor:** Puede iniciar pruebas como cliente o escuchar como servidor (soporte básico para modo servidor).
*   **Opciones Configurables:** Soporta muchas opciones comunes de iperf3:
    *   Protocolos TCP / UDP / SCTP
    *   Dirección y Puerto del Servidor
    *   Duración de la prueba o Cantidad de Datos
    *   Intervalo de Reporte
    *   Dirección de Transmisión (Subida / Bajada)
    *   Ancho de Banda Objetivo (UDP)
    *   Tamaño de Ventana TCP, MSS, NoDelay, Algoritmo de Congestión
    *   Vincular a Interfaz, TTL (UDP), Modo Verboso, Archivo de Log, etc.
*   **Verificación de Conexión:** Botón para probar rápidamente la conectividad con el servidor iperf3 antes de ejecutar una prueba completa.
*   **Visualización de Resultados:**
    *   Muestra un resumen final (Ancho de Banda Promedio, Transferencia Total, Duración).
    *   Muestra el ancho de banda por intervalo en un gráfico de líneas (usando Chart.js).
    *   Proporciona una vista de log con resultados de intervalos y mensajes de estado.
*   **Aplicación Autónoma:** Empaquetada en un único ejecutable (`.exe`) para Windows usando PyInstaller para facilitar la distribución.
*   **iperf3 Incluido:** Incluye los archivos necesarios `iperf3.exe` y `cygwin1.dll` (para la versión de Windows) dentro del paquete.

## Primeros Pasos (Para Usuarios)

Esta aplicación está diseñada para ejecutarse como un ejecutable autónomo en Windows.

1.  **Descargar:** Obtén el archivo `GUIperf3.exe` más reciente desde la [Página de Releases](<!-- Inserta el enlace a tus releases de GitHub aquí -->).
2.  **Ejecutar:** Haz doble clic en el archivo `GUIperf3.exe` descargado. No requiere instalación.
    *   *(Nota: El primer inicio podría ser ligeramente más lento mientras la aplicación se desempaqueta).*
    *   *(Nota: Tu sistema o antivirus podría mostrar una advertencia ya que el ejecutable no está firmado digitalmente. Esto es común en aplicaciones construidas con PyInstaller).*

## Uso

1.  **Iniciar:** Ejecuta `GUIperf3.exe`.
2.  **Configurar Modo:** Selecciona "Cliente" o "Servidor".
3.  **Opciones de Cliente:**
    *   Introduce la **Dirección Servidor** (IP o hostname) de la máquina que ejecuta `iperf3 -s`.
    *   Introduce el **Puerto Servidor** (normalmente 5201).
    *   Selecciona el **Protocolo** (TCP/UDP).
    *   Selecciona la **Dirección** (Subida/Bajada).
    *   (Opcional) Haz clic en **Verificar Conexión** para probar la alcanzabilidad.
4.  **Opciones Generales:** Ajusta la **Duración**, **Intervalo Reporte**, o especifica la **Cantidad Datos**. Establece el **Tamaño Buffer** si es necesario.
5.  **Opciones Específicas del Protocolo:** Configura las opciones TCP o UDP según se requiera.
6.  **Otras Opciones:** Habilita Verbose, especifica un Archivo de Log, etc.
7.  **Iniciar Prueba:** Haz clic en **Iniciar Prueba**.
8.  **Ver Resultados:** Observa el **Estado**, **Resumen Final**, el **Gráfico**, y el panel de **Log / Salida Cruda** para ver los resultados. El gráfico y el resumen se poblarán una vez que la prueba finalice.
9.  **Detener Prueba:** Haz clic en **Detener Prueba** para interrumpir una prueba en curso (modo cliente).

## Configuración de Desarrollo (Para Desarrolladores)

Si quieres ejecutar la aplicación desde el código fuente o contribuir:

1.  **Prerrequisitos:**
    *   [Python](https://www.python.org/) (Versión 3.9+ recomendada)
    *   [Git](https://git-scm.com/) (opcional, para clonar)
    *   Ejecutable `iperf3`: Descarga `iperf3.exe` y `cygwin1.dll` (para Windows) desde el sitio web oficial de iperf3 u otras fuentes confiables y colócalos en un directorio `bin/` dentro de la carpeta raíz del proyecto. El código espera encontrarlos allí.

2.  **Clonar el Repositorio:**
    ```bash
    git clone https://github.com/lordtiva/GUIperf3.git
    cd GUIperf3
    ```

3.  **Crear y Activar Entorno Virtual:**
    ```bash
    # Windows
    python -m venv .venv
    .\.venv\Scripts\activate

    # macOS / Linux
    python3 -m venv .venv
    source .venv/bin/activate
    ```

4.  **Instalar Dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Ejecutar la Aplicación:**
    ```bash
    python main.py
    ```

## Construir el Ejecutable (Empaquetado)

Para crear el archivo `.exe` autónomo para distribución:

1.  **Asegurar Configuración de Desarrollo:** Asegúrate de haber seguido los pasos de configuración de desarrollo, incluyendo la instalación de `requirements.txt`.
2.  **Verificar Binarios:** Confirma que `bin/iperf3.exe` y `bin/cygwin1.dll` existen en la estructura de tu proyecto.
3.  **Ejecutar PyInstaller:** Ejecuta el siguiente comando desde el directorio raíz del proyecto (asegúrate de que tu entorno virtual esté activado):

    ```bash
    # Para Windows (modo --onefile)
    pyinstaller --name="GUIperf3" --onefile --windowed --noconfirm --clean --add-data="templates;templates" --add-data="static;static" --add-binary="bin/iperf3.exe;bin" --add-binary="bin/cygwin1.dll;bin" main.py
    ```

4.  **Encontrar Ejecutable:** La aplicación empaquetada (`GUIperf3.exe`) se encontrará en la carpeta `dist/`.

## Tecnologías Utilizadas

*   **Python:** Lenguaje principal de la aplicación.
*   **Flask:** Framework web para el servidor backend.
*   **Flask-Sock:** Soporte WebSocket para comunicación en tiempo real con la GUI.
*   **pywebview:** Crea una ventana de escritorio nativa para alojar la GUI basada en web.
*   **HTML / CSS / JavaScript:** Interfaz de usuario frontend.
*   **Chart.js:** Librería JavaScript para crear el gráfico de resultados.
*   **iperf3:** La herramienta subyacente de pruebas de red (incluida).
*   **PyInstaller:** Usado para empaquetar la aplicación en un ejecutable autónomo.

## Licencia

<!-- Reemplaza esto con tu licencia preferida. Ejemplo: -->
Este proyecto está bajo la Licencia MIT - consulta el archivo [LICENSE](LICENSE) para más detalles.

## Agradecimientos

*   A los desarrolladores de [iperf3](https://iperf.fr/iperf-download.php).
*   A los creadores de [pywebview](https://pywebview.flowrl.com/), [Flask](https://flask.palletsprojects.com/), [Flask-Sock](https://flask-sock.readthedocs.io/), [Chart.js](https://www.chartjs.org/) y [PyInstaller](https://pyinstaller.org/).