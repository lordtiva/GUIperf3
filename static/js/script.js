// static/js/script.js
document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('iperf-form');
    const startBtn = document.getElementById('start-btn');
    const stopBtn = document.getElementById('stop-btn');
    const verifyBtn = document.getElementById('verify-btn');
    const verifyStatus = document.getElementById('verify-status');
    const outputLog = document.getElementById('output');
    const statusMessage = document.getElementById('status-message');

    // Elementos del resumen
    const summaryBandwidth = document.getElementById('summary-bandwidth');
    const summaryTransfer = document.getElementById('summary-transfer');
    const summaryDuration = document.getElementById('summary-duration');
    const summaryJitterRow = document.getElementById('summary-jitter-row');
    const summaryJitter = document.getElementById('summary-jitter');
    const summaryLossRow = document.getElementById('summary-loss-row');
    const summaryLoss = document.getElementById('summary-loss');

    // Campos de formulario específicos
    const modeRadios = document.querySelectorAll('input[name="mode"]');
    const clientOptions = document.getElementById('client-options');
    const serverOptions = document.getElementById('server-options');
    const protocolSelect = document.getElementById('protocol');
    const udpOptions = document.getElementById('udp-options');
    const tcpOptions = document.getElementById('tcp-options');
    
    // Configuración WebSocket
    let ws = null;
    const wsUrl = `ws://${window.location.host}/iperf`; // Asume que Flask corre en el mismo host/puerto

    // Configuración Chart.js
    const ctx = document.getElementById('bandwidthChart').getContext('2d');
    let bandwidthChart = null;
    let chartData = {
        labels: [],
        datasets: [{
            label: 'Ancho de Banda (Mbps)',
            data: [],
            borderColor: 'rgb(75, 192, 192)',
            backgroundColor: 'rgba(75, 192, 192, 0.2)',
            tension: 0.1,
            fill: true,
            yAxisID: 'yBandwidth', // Asignar al eje Y de Ancho de Banda
        },
        {
            label: 'Jitter (ms)',
            data: [],
            borderColor: 'rgb(255, 159, 64)',
            backgroundColor: 'rgba(255, 159, 64, 0.2)',
            tension: 0.1,
            fill: false, // No rellenar jitter
            hidden: true, // Oculto por defecto
            yAxisID: 'yJitter', // Asignar al eje Y de Jitter
        }]
    };
    const chartConfig = {
        type: 'line',
        data: chartData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    title: { display: true, text: 'Intervalo (seg)' }
                },
                yBandwidth: { // Eje Y para Ancho de Banda
                    beginAtZero: true,
                    position: 'left',
                    title: { display: true, text: 'Ancho de Banda (Mbps)' }
                },
                 yJitter: { // Eje Y para Jitter
                    beginAtZero: true,
                    position: 'right', // Mostrar a la derecha
                    title: { display: true, text: 'Jitter (ms)' },
                    grid: { // No mostrar la rejilla de este eje para no saturar
                         drawOnChartArea: false, 
                    },
                    display: false // Oculto hasta que haya datos UDP
                }
            },
            animation: {
                duration: 200 // Animación suave
            },
             plugins: {
                 legend: {
                     position: 'top',
                 },
                 tooltip: {
                     mode: 'index',
                     intersect: false,
                 },
             }
        }
    };

    function initializeChart() {
        if (bandwidthChart) {
            bandwidthChart.destroy(); // Destruir gráfico anterior si existe
        }
        // Resetear datos
        chartData.labels = [];
        chartData.datasets[0].data = []; // Bandwidth data
        chartData.datasets[1].data = []; // Jitter data
        chartData.datasets[1].hidden = true; // Ocultar jitter por defecto
        chartConfig.options.scales.yJitter.display = false; // Ocultar eje Y jitter
        
        bandwidthChart = new Chart(ctx, chartConfig);
        console.log("Chart initialized.");
    }

    function updateChart(label, bandwidth, jitter = null) {
        if (!bandwidthChart) return;

        chartData.labels.push(label);
        chartData.datasets[0].data.push(bandwidth); // Añadir dato de ancho de banda

         // Si tenemos dato de jitter, añadirlo y mostrar el dataset/eje
         if (jitter !== null && !isNaN(jitter)) {
            chartData.datasets[1].data.push(jitter);
            if (chartData.datasets[1].hidden) { // Mostrar solo la primera vez que llega jitter
                 chartData.datasets[1].hidden = false;
                 chartConfig.options.scales.yJitter.display = true; 
            }
         } else {
            // Si no hay jitter (TCP o no reportado), añadir null para mantener la sincronía
             chartData.datasets[1].data.push(null);
         }

        bandwidthChart.update();
    }
    
    function logOutput(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
         const line = document.createElement('div');
         line.textContent = `[${timestamp}] ${message}`;
         if(type === 'error') line.style.color = 'red';
         if(type === 'status') line.style.color = 'blue';
         outputLog.appendChild(line);
        // Auto-scroll
        outputLog.scrollTop = outputLog.scrollHeight;
    }

    function setStatus(message, type = 'info') {
        statusMessage.textContent = message;
        logOutput(`Status: ${message}`, type);
         // Quitar clases de estado anteriores
        statusMessage.classList.remove('status-success', 'status-error', 'status-warning'); 
        if(type === 'error') statusMessage.classList.add('status-error');
        if(type === 'success') statusMessage.classList.add('status-success');
        if(type === 'warning') statusMessage.classList.add('status-warning');
    }

    function clearResults() {
        outputLog.innerHTML = ''; // Limpiar log
        summaryBandwidth.textContent = '---';
        summaryTransfer.textContent = '---';
        summaryDuration.textContent = '---';
        summaryJitter.textContent = '---';
        summaryLoss.textContent = '---';
        summaryJitterRow.style.display = 'none';
        summaryLossRow.style.display = 'none';
        verifyStatus.textContent = '';
        verifyStatus.className = '';
        initializeChart(); // Reiniciar gráfico
    }
    
    function setTestingState(isTesting) {
        startBtn.disabled = isTesting;
        stopBtn.disabled = !isTesting;
        // Deshabilitar formulario durante la prueba
        form.querySelectorAll('input, select, button[type="submit"], #verify-btn').forEach(el => {
             if (el.id !== 'stop-btn') { // No deshabilitar el botón de detener
                 el.disabled = isTesting;
             }
        });
        // Re-habilitar específicamente el botón de detener si estamos probando
        stopBtn.disabled = !isTesting; 
    }

    function connectWebSocket() {
        if (ws && ws.readyState === WebSocket.OPEN) {
            console.log("WebSocket ya está abierto.");
            return;
        }

        clearResults();
        setStatus("Conectando al backend...");
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            setStatus("Conectado al backend. Listo para iniciar prueba.");
             console.log("WebSocket connection opened");
        };

        ws.onmessage = (event) => {
            console.log("WebSocket message received:", event.data);
            try {
                const data = JSON.parse(event.data);

                switch (data.type) {
                    case 'status':
                        setStatus(data.message, 'status');
                        break;
                    case 'interval':
                         const intervalLabel = data.interval || `${chartData.labels.length * (parseFloat(document.getElementById('reportInterval').value) || 1)}s`; // Usa el intervalo o calcula
                         const bw = parseFloat(data.bandwidth_mbps);
                         const jt = data.jitter_ms !== undefined ? parseFloat(data.jitter_ms) : null;
                         
                         logOutput(`Intervalo ${intervalLabel}: BW=${bw.toFixed(2)} Mbps` + (jt !== null ? `, Jitter=${jt.toFixed(3)} ms, Loss=${parseFloat(data.lost_percent || 0).toFixed(2)}%` : ''));
                         updateChart(intervalLabel, bw, jt);
                         
                         // Mostrar campos UDP en resumen si es relevante
                         if (jt !== null) {
                             summaryJitterRow.style.display = 'block';
                             summaryLossRow.style.display = 'block';
                         }
                        break;
                    case 'summary':
                        setStatus("Prueba completada.", 'success');
                        setTestingState(false);
                         summaryBandwidth.textContent = parseFloat(data.avg_bandwidth_mbps || 0).toFixed(2);
                         summaryTransfer.textContent = parseFloat(data.total_transfer_mb || 0).toFixed(2);
                         summaryDuration.textContent = parseFloat(data.duration_s || 0).toFixed(1);
                         if (data.avg_jitter_ms !== undefined) {
                             summaryJitter.textContent = parseFloat(data.avg_jitter_ms).toFixed(3);
                             summaryLoss.textContent = parseFloat(data.total_lost_percent || 0).toFixed(2);
                             summaryJitterRow.style.display = 'block';
                             summaryLossRow.style.display = 'block';
                         } else {
                              summaryJitterRow.style.display = 'none';
                              summaryLossRow.style.display = 'none';
                         }
                         logOutput(`RESUMEN FINAL: BW Avg=${summaryBandwidth.textContent} Mbps, Transfer=${summaryTransfer.textContent} MB, Duración=${summaryDuration.textContent}s` + 
                                   (data.avg_jitter_ms !== undefined ? `, Jitter Avg=${summaryJitter.textContent} ms, Loss Total=${summaryLoss.textContent}%` : ''));
                        break;
                    case 'error':
                        setStatus(`Error: ${data.message}`, 'error');
                         logOutput(`ERROR: ${data.message}${data.details ? '\nDetalles: ' + data.details : ''}`, 'error');
                        setTestingState(false); // Re-habilitar controles en error
                        break;
                    default:
                         logOutput(`Mensaje desconocido: ${event.data}`);
                }
            } catch (error) {
                console.error("Error parsing WebSocket message:", error);
                logOutput(`Error procesando mensaje del backend: ${error}`, 'error');
            }
        };

        ws.onerror = (error) => {
            console.error("WebSocket error:", error);
            setStatus("Error de conexión WebSocket. Asegúrate de que el backend esté corriendo.", 'error');
            setTestingState(false); // Re-habilitar controles
        };

        ws.onclose = (event) => {
            console.log("WebSocket connection closed:", event.code, event.reason);
             if (!event.wasClean) {
                  setStatus("Conexión WebSocket cerrada inesperadamente.", 'warning');
             } else {
                  setStatus("Desconectado del backend.");
             }
             setTestingState(false); // Re-habilitar controles
            ws = null; // Resetear variable ws
        };
    }

    // --- Manejadores de Eventos ---

    form.addEventListener('submit', (event) => {
        event.preventDefault(); // Evitar envío de formulario HTML normal

        if (!ws || ws.readyState !== WebSocket.OPEN) {
             setStatus("No conectado al backend. Intentando conectar...", 'warning');
             connectWebSocket(); // Intentar conectar si no lo está
             // Esperar un poco a que se establezca la conexión
             setTimeout(() => {
                 if (ws && ws.readyState === WebSocket.OPEN) {
                     sendStartCommand();
                 } else {
                     setStatus("Fallo al conectar con el backend.", 'error');
                 }
             }, 1000); // Espera 1 segundo
             return;
        }
        
        sendStartCommand();
    });

    function sendStartCommand() {
         clearResults();
        const formData = new FormData(form);
        const config = {};
        // Recolectar datos del formulario
        for (const [key, value] of formData.entries()) {
             // Convertir checkboxes a booleanos
             if (value === 'on') {
                 config[key] = true;
             } else if (value) { // Solo añadir si tiene valor
                 // Intentar convertir números donde sea apropiado (validación más robusta sería ideal)
                 const numValue = parseFloat(value);
                 config[key] = isNaN(numValue) || key.includes('Address') || key.includes('Interface') || key.includes('File') || key.includes('congestion') || key.includes('Amount') || key.includes('Size') || key.includes('bandwidth') ? value : numValue; // No convertir ciertos campos a número
             }
        }

        // Ajustes específicos basados en el modo
         const selectedMode = document.querySelector('input[name="mode"]:checked').value;
         config.mode = selectedMode; // Asegurarse de que el modo está
         
         if(selectedMode === 'server') {
             config.serverPort = parseInt(document.getElementById('serverPortServer').value) || 5201;
             config.bindInterface = document.getElementById('bindInterfaceServer').value || null;
             // Eliminar opciones de cliente que no aplican
             delete config.serverAddress;
             delete config.protocol;
             delete config.direction;
             delete config.bandwidth; // etc.
         } else { // Modo cliente
             config.serverPort = parseInt(document.getElementById('serverPort').value) || 5201;
             config.bindInterface = document.getElementById('bindInterfaceClient').value || null;
             // Eliminar opciones de servidor
             delete config.oneOff;
         }
         // Eliminar campos vacíos opcionales para no enviar flags innecesarias
          Object.keys(config).forEach(key => {
              if (config[key] === null || config[key] === '') {
                  delete config[key];
              }
          });


        console.log("Sending config:", config);
        setStatus("Iniciando prueba...");
        setTestingState(true);
        
        // Enviar mensaje de inicio con la configuración
        ws.send(JSON.stringify({ action: 'start', config: config }));
    }


    stopBtn.addEventListener('click', () => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            setStatus("Enviando solicitud para detener...");
             console.log("Sending stop request");
             ws.send(JSON.stringify({ action: 'stop' }));
             // El backend enviará un status 'detenido' y 'summary' (si aplica)
             // setTestingState se llamará cuando llegue la respuesta del backend
        } else {
            setStatus("No conectado para detener.", 'warning');
            setTestingState(false); // Re-habilitar si no hay conexión
        }
    });

    verifyBtn.addEventListener('click', async () => {
         const serverAddress = document.getElementById('serverAddress').value;
         const serverPort = document.getElementById('serverPort').value;
         
         if (!serverAddress) {
             verifyStatus.textContent = 'Introduce una dirección de servidor.';
             verifyStatus.className = 'status-error';
             return;
         }
         
         verifyStatus.textContent = 'Verificando...';
         verifyStatus.className = '';
         verifyBtn.disabled = true;

         try {
             const response = await fetch('/verify_connection', {
                 method: 'POST',
                 headers: {
                     'Content-Type': 'application/json',
                 },
                 body: JSON.stringify({ serverAddress, serverPort }),
             });
             
             const result = await response.json();
             
             if (result.status === 'success') {
                 verifyStatus.textContent = `Éxito: ${result.message}`;
                 verifyStatus.className = 'status-success';
             } else {
                  verifyStatus.textContent = `Error: ${result.message}`;
                  verifyStatus.className = 'status-error';
                  if(result.output) {
                      logOutput(`DETALLES VERIFICACIÓN:\n${result.output}`, 'error');
                  }
             }

         } catch (error) {
              console.error("Error en verificación:", error);
              verifyStatus.textContent = 'Error al verificar (¿Backend caído?)';
              verifyStatus.className = 'status-error';
         } finally {
             verifyBtn.disabled = false;
         }
    });

     // Mostrar/ocultar opciones según el modo y protocolo
     function toggleOptions() {
         const selectedMode = document.querySelector('input[name="mode"]:checked').value;
         const selectedProtocol = protocolSelect.value;

         clientOptions.style.display = selectedMode === 'client' ? 'block' : 'none';
         serverOptions.style.display = selectedMode === 'server' ? 'block' : 'none';

         if (selectedMode === 'client') {
             tcpOptions.style.display = selectedProtocol === 'tcp' ? 'block' : 'none';
             udpOptions.style.display = selectedProtocol === 'udp' ? 'block' : 'none';
             // Ocultar/mostrar botón de verificar conexión
             verifyBtn.style.display = 'inline-block'; 
             verifyStatus.style.display = 'inline';
         } else { // Modo servidor
             tcpOptions.style.display = 'none';
             udpOptions.style.display = 'none';
             verifyBtn.style.display = 'none';
             verifyStatus.style.display = 'none';
         }
     }

     modeRadios.forEach(radio => radio.addEventListener('change', toggleOptions));
     protocolSelect.addEventListener('change', toggleOptions);

    // Estado inicial
    initializeChart();
    setTestingState(false); // Botones y form habilitados inicialmente
    toggleOptions(); // Ajustar visibilidad inicial de opciones
    connectWebSocket(); // Intentar conectar al cargar la página

});