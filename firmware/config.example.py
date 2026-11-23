# Copia este archivo como config.py en la ESP32 y llena tus datos.
# config.py está en .gitignore: no lo subas al repositorio.

WIFI_SSID = "TU_WIFI_O_HOTSPOT"
WIFI_PASSWORD = "TU_PASSWORD"

# IP LAN de la computadora donde corre FastAPI (NO uses localhost).
# En el coche, usa el hotspot del celular y la IP que tenga tu laptop en esa red,
# o un backend desplegado con HTTPS.
API_URL = "http://192.168.1.50:8000"
DEVICE_CODE = "ESP32-REAL-01"

SEND_INTERVAL_S = 5      # cada cuánto se mide y se envía
MAX_BUFFER = 120         # lotes máximos guardados en RAM sin conexión (~10 min a 5 s)
HTTP_TIMEOUT_S = 5
GPS_MAX_AGE_S = 5        # descarta coordenadas más viejas que esto

# Pines (los del reporte ThingsLab)
PIN_DS18B20 = 4
PIN_TRIG = 5
PIN_ECHO = 18
PIN_I2C_SDA = 22
PIN_I2C_SCL = 21
PIN_MQ_DO = 25           # activo en nivel bajo
PIN_GPS_RX = 16          # TX del NEO-6M -> GPIO16 (UART2, 9600)
MPU_ADDR = 0x68
