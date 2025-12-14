from iqoptionapi.stable_api import IQ_Option
import time
import threading

# Configuración del bot
EMAIL = ''
PASSWORD = ''
modo_operacion = 1  # 1 = demo, 2 = real
tiempo_vela = 1  # Periodo de velas (en minutos)

# Parámetros de la estrategia
NUM_VELAS_ANALISIS = 15
PORCENTAJE_TENDENCIA = 60

# Secuencia de martingala (7 niveles)
secuencia_martingala = [1.2, 2.6, 5.6, 12.1, 27.2, 57.5, 129]

# Variable para activos personalizados (vacío = todos los disponibles)
activos_personalizados = []  # Todos los activos disponibles
# activos_personalizados = ["TIAUSD-OTC", "PENGUUSD-OTC", "USDCAD-OTC"]  # Personalizados

# Variables globales
activo_seleccionado = None
ultimo_minuto_operado = None
indice_martingala_global = 0

# Funciones auxiliares
def login():
    try:
        print("\n🔒 Conectando a IQ Option...")
        iq = IQ_Option(EMAIL, PASSWORD)
        iq.connect()
        
        if iq.check_connect():
            print("\n✅ Conexión exitosa")
            iq.change_balance("PRACTICE" if modo_operacion == 1 else "REAL")
            cuenta = 'demo' if modo_operacion == 1 else 'real'
            print(f"✨ Operando en la cuenta {cuenta.upper()}")
            return iq
        else:
            print("❌ Error de conexión.")
            return None
            
    except Exception as e:
        print(f"❌ Error al conectar: {e}")
        return None

def obtener_todos_activos_disponibles(iq):
    try:
        iq.update_ACTIVES_OPCODE()
        activos_disponibles = iq.get_all_open_time()
        
        # Obtener todos los activos abiertos en binarios
        activos_binarios = [activo for activo, data in activos_disponibles['binary'].items() 
                           if data['open']]
        
        print(f"\n✨ Activos disponibles en IQ Option ({len(activos_binarios)}):")
        for i, activo in enumerate(activos_binarios[:10]):
            print(f"- {activo}")
        if len(activos_binarios) > 10:
            print(f"- ... y {len(activos_binarios) - 10} más")
        
        return activos_binarios
        
    except Exception as e:
        print(f"❌ Error al obtener activos disponibles: {e}")
        return []

def filtrar_activos_personalizados(activos_disponibles):
    if not activos_personalizados:
        print("ℹ️ Usando TODOS los activos disponibles")
        return activos_disponibles
    
    activos_filtrados = [activo for activo in activos_disponibles 
                        if activo in activos_personalizados]
    
    print(f"\n✨ Activos seleccionados de la lista personalizada ({len(activos_filtrados)}):")
    for activo in activos_filtrados:
        print(f"- {activo}")
    
    return activos_filtrados

def obtener_velas(iq, activo, cantidad_velas):
    try:
        # Obtener las velas históricas (excluyendo la vela en curso)
        tiempo_actual = time.time()
        tiempo_final_ultima_vela = tiempo_actual - (tiempo_actual % (tiempo_vela * 60))
        velas = iq.get_candles(activo, tiempo_vela * 60, cantidad_velas, tiempo_final_ultima_vela)
        return velas
        
    except Exception as e:
        print(f"❌ Error al obtener velas de {activo}: {e}")
        return None

def determinar_tendencia_global(velas):
    if not velas or len(velas) < NUM_VELAS_ANALISIS:
        return None
    
    # Tomar las últimas NUM_VELAS_ANALISIS velas
    ultimas_velas = velas[-NUM_VELAS_ANALISIS:]
    
    # Contar velas alcistas y bajistas
    alcistas = sum(1 for vela in ultimas_velas if vela['close'] > vela['open'])
    bajistas = len(ultimas_velas) - alcistas
    
    # Calcular porcentajes
    porc_alcistas = (alcistas / len(ultimas_velas)) * 100
    porc_bajistas = (bajistas / len(ultimas_velas)) * 100
    
    print(f"📊 Análisis de {len(ultimas_velas)} velas: {alcistas} alcistas ({porc_alcistas:.1f}%), "
          f"{bajistas} bajistas ({porc_bajistas:.1f}%)")
    
    # Determinar tendencia según el porcentaje mínimo
    if porc_alcistas >= PORCENTAJE_TENDENCIA:
        return "alcista"
    elif porc_bajistas >= PORCENTAJE_TENDENCIA:
        return "bajista"
    else:
        return "indefinida"

def sincronizar_proximo_minuto():
    tiempo_actual = time.time()
    tiempo_restante = 60 - (tiempo_actual % 60)
    minuto_objetivo = time.strftime("%H:%M", time.localtime(tiempo_actual + tiempo_restante))
    
    # Si queda menos de 2 segundos, esperar al siguiente minuto
    if tiempo_restante < 2:
        tiempo_restante += 60
        minuto_objetivo = time.strftime("%H:%M", time.localtime(tiempo_actual + tiempo_restante))
    
    print(f"⏳ Esperando {tiempo_restante:.2f} segundos para las {minuto_objetivo}...")
    
    # Esperar hasta 0.5 segundos antes del minuto exacto
    if tiempo_restante > 0.5:
        time.sleep(tiempo_restante - 0.5)

    # Espera activa para máxima precisión
    inicio = time.time()
    while time.time() - inicio < 0.5:
        time.sleep(0.05)  # Reducir CPU durante la espera activa
    
    return minuto_objetivo

def ejecutar_operacion(iq, activo, direccion, monto, tiempo_operacion):
    try:
        # OBTENER SALDO INICIAL Y TIEMPO EXACTO
        saldo_inicial = iq.get_balance()
        tiempo_inicio_operacion = time.time()  # Registrar tiempo exacto de inicio
        hora_operacion = time.strftime("%H:%M:%S")
        
        print(f"💰 [{hora_operacion}] Abriendo operación {direccion.upper()} en {activo} con ${monto}...")
        
        # Ejecutar la operación
        if direccion == "alcista":
            id_operacion = iq.buy(monto, activo, "call", tiempo_operacion)
        else:
            id_operacion = iq.buy(monto, activo, "put", tiempo_operacion)
        
        if not id_operacion:
            print("❌ Error al ejecutar la operación")
            return "error"
        
        print(f"📝 ID de operación: {id_operacion}")
        
        # CALCULAR TIEMPO DE ESPERA EXACTO
        tiempo_transcurrido = time.time() - tiempo_inicio_operacion
        tiempo_faltante = max(0, (tiempo_operacion * 60) - tiempo_transcurrido)

        print(f"⏳ Tiempo transcurrido: {tiempo_transcurrido:.2f}s, faltante: {tiempo_faltante:.2f}s")

        # Esperar solo lo indispensable para no perder el siguiente minuto
        if tiempo_faltante > 0:
            time.sleep(tiempo_faltante + 1)
        
        # VERIFICACIÓN CON REINTENTOS
        print("🔍 Verificando resultado...")
        saldo_actual = iq.get_balance()
        intentos = 0
        max_intentos = 5
        
        # Reintentar si el saldo no ha cambiado
        while saldo_actual == saldo_inicial and intentos < max_intentos:
            print(f"⏳ Esperando confirmación ({intentos+1}/{max_intentos})...")
            time.sleep(3)
            saldo_actual = iq.get_balance()
            intentos += 1
        
        # DETERMINAR RESULTADO FINAL
        if saldo_actual > saldo_inicial:
            print(f"✅ OPERACIÓN GANADORA! Saldo: {saldo_inicial} → {saldo_actual} USD")
            return "ganada"
        elif saldo_actual < saldo_inicial:
            print(f"❌ OPERACIÓN PERDEDORA. Saldo: {saldo_inicial} → {saldo_actual} USD")
            return "perdida"
        else:
            print(f"⚖️ RESULTADO INDETERMINADO. Saldo sin cambios: {saldo_actual} USD")
            # ⭐⭐ CAMBIO: Ahora se considera EMPATE en lugar de pérdida ⭐⭐
            return "empatada"
            
    except Exception as e:
        print(f"❌ Error en ejecutar_operacion: {e}")
        return "error"

def analizar_activo_en_tiempo_real(iq, activo):
    global indice_martingala_global
    
    print(f"📈 Analizando {activo} en tiempo real...")
    
    # Obtener velas para análisis
    velas = obtener_velas(iq, activo, NUM_VELAS_ANALISIS + 2)
    if not velas or len(velas) < NUM_VELAS_ANALISIS:
        print("❌ No hay suficientes velas para analizar")
        return False
    
    # Determinar tendencia global
    tendencia = determinar_tendencia_global(velas)
    
    if tendencia in ["alcista", "bajista"]:
        monto_operacion = secuencia_martingala[indice_martingala_global]
        print(f"🎯 Señal {tendencia.upper()} - Martingala nivel {indice_martingala_global + 1}")
        
        resultado = ejecutar_operacion(iq, activo, tendencia, monto_operacion, tiempo_vela)
        
        if resultado == "ganada":
            indice_martingala_global = 0  # Reiniciar martingala
            print("🔄 Reiniciando martingala por operación ganadora")
            return True
        elif resultado == "empatada":
            # ⭐⭐ MANTENER mismo nivel de martingala por empate/indeterminación ⭐⭐
            print("🔄 Repitiendo mismo nivel de martingala por empate/indeterminación")
            return False
        elif resultado == "perdida":
            indice_martingala_global += 1  # Siguiente nivel de martingala
            if indice_martingala_global >= len(secuencia_martingala):
                print("💥 Martingala completa perdida. Reiniciando...")
                indice_martingala_global = 0
            else:
                print(f"📈 Subiendo a nivel {indice_martingala_global + 1} de martingala")
            return False
        else:  # error
            print("⚠️ Manteniendo nivel de martingala por error")
            return False
    else:
        print("⏭️ Tendencia indefinida, saltando operación")
        # No reiniciamos martingala aquí para no perder el progreso
        return False

def analizar_y_operar(iq):
    global activo_seleccionado, ultimo_minuto_operado, indice_martingala_global
    
    # Obtener todos los activos disponibles
    activos_disponibles = obtener_todos_activos_disponibles(iq)
    if not activos_disponibles:
        print("❌ No hay activos disponibles")
        return
    
    # Filtrar activos según configuración
    activos_operables = filtrar_activos_personalizados(activos_disponibles)
    if not activos_operables:
        print("❌ No hay activos operables después del filtrado")
        return
    
    operaciones_consecutivas = 0
    
    print(f"\n🎯 Iniciando estrategia: {NUM_VELAS_ANALISIS} velas, {PORCENTAJE_TENDENCIA}% tendencia")
    print(f"🎯 Martingala: {len(secuencia_martingala)} niveles")
    print(f"💰 Secuencia: {secuencia_martingala}")
    
    while True:
        try:
            ciclo_inicio = time.time()
            
            # Sincronizar con el próximo minuto
            minuto_objetivo = sincronizar_proximo_minuto()
            
            # Evitar operar el mismo minuto múltiples veces
            if minuto_objetivo == ultimo_minuto_operado:
                print(f"⏭️ Saltando minuto {minuto_objetivo} (ya operado)")
                time.sleep(1)
                continue
                
            ultimo_minuto_operado = minuto_objetivo
            operaciones_consecutivas += 1
            
            print(f"\n🔄 Ciclo #{operaciones_consecutivas} - Minuto: {minuto_objetivo}")
            print(f"📊 Nivel actual de martingala: {indice_martingala_global + 1}")
            
            # Rotar entre los activos operables
            if activo_seleccionado is None:
                activo_seleccionado = activos_operables[0]
            else:
                indice_actual = activos_operables.index(activo_seleccionado)
                siguiente_indice = (indice_actual + 1) % len(activos_operables)
                activo_seleccionado = activos_operables[siguiente_indice]
            
            # Analizar y operar en tiempo real
            analizar_activo_en_tiempo_real(iq, activo_seleccionado)
            
            # Medir tiempo del ciclo y ajustar espera
            tiempo_ciclo = time.time() - ciclo_inicio
            print(f"⏱️  Tiempo del ciclo: {tiempo_ciclo:.2f} segundos")
            
            # Pequeña pausa antes del próximo ciclo
            if tiempo_ciclo < 55:
                time.sleep(1)  # Esperar 1 segundo si el ciclo fue rápido
            
        except Exception as e:
            print(f"❌ Error en el ciclo principal: {e}")
            time.sleep(5)

# Ejecutar el bot
if __name__ == "__main__":
    iq = login()
    if iq:
        try:
            analizar_y_operar(iq)
        except KeyboardInterrupt:
            print("\n🛑 Bot detenido por el usuario")
