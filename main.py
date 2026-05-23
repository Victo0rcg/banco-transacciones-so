"""
main.py — Coordinador principal del sistema de transacciones bancarias.

Este módulo integra los componentes funcionales del proyecto:
  - core/           : Motor de cuentas y transacciones (Módulo 1)
  - scheduling/     : Planificador SCAN de logs       (Módulo 2)
  - security/       : Control de acceso RBAC          (Módulo 3)
  - concurrency/    : Algoritmo del Banquero          (Módulo 4)

Modos de ejecución:
  1. Demostración automática  — lanza una batería de transacciones predefinidas
                                organizadas en oleadas para hacer visible la
                                concurrencia y el comportamiento del sistema.
  2. Modo interactivo manual  — permite crear transacciones una a una desde
                                la consola, ideal para depuración y presentación.
  3. Ambos                    — ejecuta la demo primero y luego abre el modo
                                interactivo.
"""

import logging
import threading
import random
import time
import os

from core.account import Account
from core.transaction import Transaction, TransactionType, TransactionStatus, TransactionBuilder
from core.transaction_engine import TransactionEngine
from scheduling.scan_scheduler import scan_scheduling
from security.roles import Rol, Operacion
from security.rbac_policy import PoliticaRBAC
from concurrency.bankers_guard import GuardiaBanquero


# ---------------------------------------------------------------------------
# Configuración de logging
# ---------------------------------------------------------------------------

_LOG_SYSTEM       = "banco-transacciones-so/logs/system.log"
_LOG_TRANSACTIONS = "banco-transacciones-so/logs/transactions.log"
os.makedirs(os.path.dirname(_LOG_SYSTEM), exist_ok=True)

logging.basicConfig(
    filename=_LOG_SYSTEM,
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(message)s",
    datefmt="%H:%M:%S",
)

# Constantes de presentación
SEP  = "=" * 62
SEP2 = "-" * 62
ROLES_VALIDOS   = ["ADMINISTRADOR", "CAJERO", "AUDITOR"]
CUENTAS_VALIDAS = ["ACC001", "ACC002", "ACC003", "ACC004", "ACC005"]


# ===========================================================================
# SECCIÓN 1 — INTEGRACIÓN DE COMPONENTES CON EL MOTOR
# ===========================================================================

# Mapa TransactionType → Operacion RBAC
_TIPO_A_OPERACION = {
    TransactionType.DEPOSIT:    Operacion.DEPOSITO,
    TransactionType.WITHDRAWAL: Operacion.RETIRO,
    TransactionType.TRANSFER:   Operacion.TRANSFERENCIA,
    TransactionType.QUERY:      Operacion.CONSULTA,
}


def construir_hook_rbac(politica: PoliticaRBAC):
    """
    Construye el hook de autorización RBAC para el motor.

    Convierte user_role (str) al enum Rol y TransactionType al enum Operacion
    antes de consultar la política. Captura PermissionError y lo traduce a
    False para que el motor marque la transacción como DENIED.
    """
    def hook(transaction: Transaction) -> bool:
        try:
            rol = Rol(transaction.user_role)
        except ValueError:
            logging.error(f"[RBAC] Rol desconocido: '{transaction.user_role}'")
            return False

        operacion = _TIPO_A_OPERACION.get(transaction.transaction_type)
        if operacion is None:
            logging.error(f"[RBAC] Tipo sin mapeo RBAC: {transaction.transaction_type}")
            return False

        try:
            return politica.verificar_permiso(rol, operacion)
        except PermissionError:
            return False

    return hook


def construir_guard_banquero(cuentas: dict):
    """
    Construye el guard del Algoritmo del Banquero para el motor.

    Adaptación al modelo bancario:
      - Cada cuenta activa es un proceso en el algoritmo.
      - El único recurso es el lock de cuenta (vector de 1 elemento).
      - recursos_disponibles = [n_cuentas]
      - necesidad_maxima[i]  = [1]   (cada cuenta puede necesitar 1 lock)
      - recursos_asignados   = [[0]] * n  (ninguno asignado al inicio)

    El Algoritmo del Banquero actúa como capa de planificación previa:
    deniega transferencias que llevarían al sistema a un estado inseguro
    antes de que se adquiera ningún lock.
    El ordenamiento jerárquico de locks en _execute_transfer actúa como
    capa de sincronización en tiempo de ejecución, eliminando la espera
    circular. Ambas estrategias son complementarias e intencionales.
    """
    n            = len(cuentas)
    cuenta_ids   = list(cuentas.keys())
    indice_cuenta = {cid: i for i, cid in enumerate(cuenta_ids)}

    recursos_disponibles = [n]
    necesidad_maxima     = [[1]] * n
    recursos_asignados   = [[0]] * n

    guard      = GuardiaBanquero(recursos_disponibles, necesidad_maxima, recursos_asignados)
    lock_guard = threading.Lock()

    def bankers_hook(transaction: Transaction) -> bool:
        if transaction.transaction_type != TransactionType.TRANSFER:
            return True

        idx = indice_cuenta.get(transaction.source_account_id)
        if idx is None:
            return True

        with lock_guard:
            try:
                resultado = guard.solicitar_recursos(idx, [1])
                if resultado:
                    # Liberar el recurso simulado: la sincronización real
                    # la gestiona el motor mediante lock ordering.
                    guard.recursos_disponibles[0]    += 1
                    guard.recursos_asignados[idx][0] -= 1
                    guard.matriz_necesidad[idx][0]   += 1
                return resultado
            except ValueError as e:
                logging.warning(f"[BANQUERO] Error al evaluar solicitud: {e}")
                return False

    return bankers_hook


def registrar_resultados_con_scan(resultados: list,
                                   archivo_log: str = _LOG_TRANSACTIONS):
    """
    Ordena los resultados por número de bloque con SCAN y los escribe en el log.

    Simula el subsistema de escritura en disco: cada transacción tiene un
    block_number ficticio asignado por el motor, y SCAN determina el orden
    óptimo de escritura minimizando el movimiento del cabezal.
    """
    os.makedirs(os.path.dirname(archivo_log), exist_ok=True)

    if not resultados:
        logging.info("[SCAN] No hay resultados que registrar.")
        return

    # Agrupar por bloque para manejar colisiones
    bloque_lista: dict[int, list] = {}
    for r in resultados:
        bloque_lista.setdefault(r.block_number, []).append(r)

    solicitudes = [r.block_number for r in resultados]
    orden_scan  = scan_scheduling(solicitudes, head_position=0, direction='up')

    logging.info(f"[SCAN] Orden de escritura de bloques: {orden_scan}")

    with open(archivo_log, "w", encoding="utf-8") as f:
        for bloque in orden_scan:
            for txn in bloque_lista.get(bloque, []):
                linea = (
                    f"[{txn.transaction_id}] "
                    f"bloque={txn.block_number:03d} | "
                    f"{txn.transaction_type.value:<12} | "
                    f"cuenta={txn.source_account_id} | "
                    f"monto=${txn.amount:>10.2f} | "
                    f"rol={txn.user_role:<15} | "
                    f"estado={txn.status.value}\n"
                )
                f.write(linea)
                logging.info(
                    f"[SCAN] Escribiendo bloque {bloque:03d} → "
                    f"{txn.transaction_id} ({txn.status.value})"
                )


# ===========================================================================
# SECCIÓN 2 — UTILIDADES DE PRESENTACIÓN EN CONSOLA
# ===========================================================================

def _icono(status: TransactionStatus) -> str:
    return "✓" if status == TransactionStatus.COMPLETED else "✗"


def imprimir_encabezado():
    print("\n" + SEP)
    print("  PROCESADOR DE TRANSACCIONES BANCARIAS")
    print("  Sistemas Operativos — UTP 2026-1")
    print(SEP)


def imprimir_estado_cuentas(cuentas: dict):
    """Imprime el saldo actual de todas las cuentas."""
    print("\n" + SEP)
    print("  ESTADO ACTUAL DE CUENTAS")
    print(SEP)
    for cuenta in cuentas.values():
        print(f"  {cuenta}")
    print(SEP)


def imprimir_resultado_transaccion(tx: Transaction):
    """Imprime el resultado de una sola transacción de forma inmediata."""
    icono = _icono(tx.status)
    print(f"\n  {icono} [{tx.transaction_id}] {tx.get_operation_summary()}")
    print(f"     Rol    : {tx.user_role}")
    print(f"     Estado : {tx.status.value}", end="")
    razon = tx.metadata.get("failure_reason") or tx.metadata.get("denial_reason")
    if razon:
        print(f"  ({razon})", end="")
    if tx.status == TransactionStatus.COMPLETED and tx.transaction_type == TransactionType.QUERY:
        print(f"\n     Saldo  : ${tx.metadata.get('balance', 0):.2f}", end="")
    print()


def imprimir_resumen_resultados(resultados: list):
    """Imprime tabla resumen de un conjunto de transacciones procesadas."""
    completadas = sum(1 for r in resultados if r.status == TransactionStatus.COMPLETED)
    fallidas    = sum(1 for r in resultados if r.status == TransactionStatus.FAILED)
    denegadas   = sum(1 for r in resultados if r.status == TransactionStatus.DENIED)

    print("\n" + SEP)
    print("  RESUMEN DE TRANSACCIONES")
    print(SEP)
    print(f"  Total procesadas : {len(resultados)}")
    print(f"  Completadas      : {completadas}")
    print(f"  Fallidas         : {fallidas}  (ej: fondos insuficientes)")
    print(f"  Denegadas        : {denegadas}  (RBAC o Banquero)")
    print(SEP)
    print("\n  Detalle:")
    for r in resultados:
        print(
            f"  {_icono(r.status)} [{r.transaction_id}] "
            f"{r.get_operation_summary():<45} "
            f"| rol={r.user_role:<15} | {r.status.value}"
        )
    print()


# ===========================================================================
# SECCIÓN 3 — MODO DEMOSTRACIÓN AUTOMÁTICA
# ===========================================================================

def _someter_oleada(motor: TransactionEngine,
                    transacciones: list,
                    etiqueta: str) -> list:
    """
    Somete una lista de transacciones al motor, espera su finalización
    y devuelve los resultados. Imprime encabezado de oleada.
    """
    print(f"\n{SEP2}")
    print(f"  {etiqueta}")
    print(f"  Sometiendo {len(transacciones)} transacciones al motor...")
    print(SEP2)

    for txn in transacciones:
        motor.submit_transaction(txn)

    motor.wait_completion()
    resultados = motor.get_all_results()

    for r in resultados:
        imprimir_resultado_transaccion(r)

    return resultados


def ejecutar_demo(motor: TransactionEngine, cuentas: dict) -> list:
    """
    Ejecuta la batería de demostración en tres oleadas:
      - Oleada 1: operaciones válidas de todos los tipos
      - Oleada 2: violaciones intencionales de RBAC
      - Oleada 3: carga aleatoria concurrente

    Retorna la lista completa de resultados para el log SCAN.
    """
    print("\n" + SEP)
    print("  MODO DEMOSTRACIÓN AUTOMÁTICA")
    print(SEP)

    ids = list(cuentas.keys())
    todos_resultados = []

    # ------------------------------------------------------------------
    # Oleada 1 — Operaciones válidas (depósitos, retiros, transferencias,
    #            consultas). Cubre todos los tipos y roles permitidos.
    # ------------------------------------------------------------------
    oleada1 = [
        TransactionBuilder("cajero01",  "CAJERO")
            .with_deposit("ACC001", 1_000.0).build(),
        TransactionBuilder("admin01",   "ADMINISTRADOR")
            .with_deposit("ACC003", 500.0).build(),
        TransactionBuilder("cajero01",  "CAJERO")
            .with_withdrawal("ACC002", 200.0).build(),
        TransactionBuilder("cajero02",  "CAJERO")
            .with_withdrawal("ACC004", 5_000.0).build(),   # fallará: fondos insuficientes
        TransactionBuilder("admin01",   "ADMINISTRADOR")
            .with_transfer("ACC001", "ACC002", 300.0).build(),
        TransactionBuilder("admin01",   "ADMINISTRADOR")
            .with_transfer("ACC005", "ACC004", 2_000.0).build(),
        TransactionBuilder("auditor01", "AUDITOR")
            .with_query("ACC003").build(),
        TransactionBuilder("cajero01",  "CAJERO")
            .with_query("ACC001").build(),
    ]
    todos_resultados += _someter_oleada(motor, oleada1,
                                        "OLEADA 1 — Operaciones válidas (todos los tipos)")

    imprimir_estado_cuentas(cuentas)

    # ------------------------------------------------------------------
    # Oleada 2 — Violaciones de RBAC intencionales.
    #            Demuestra que el subsistema de seguridad deniega
    #            correctamente operaciones fuera del dominio del rol.
    # ------------------------------------------------------------------
    oleada2 = [
        TransactionBuilder("auditor01", "AUDITOR")
            .with_deposit("ACC002", 100.0).build(),        # AUDITOR no puede depositar
        TransactionBuilder("cajero02",  "CAJERO")
            .with_transfer("ACC003", "ACC005", 500.0).build(),  # CAJERO no puede transferir
        TransactionBuilder("auditor01", "AUDITOR")
            .with_withdrawal("ACC001", 50.0).build(),      # AUDITOR no puede retirar
    ]
    todos_resultados += _someter_oleada(motor, oleada2,
                                        "OLEADA 2 — Violaciones RBAC (deben ser DENIED)")

    # ------------------------------------------------------------------
    # Oleada 3 — Carga aleatoria concurrente.
    #            Múltiples hilos compiten por las mismas cuentas,
    #            haciendo visibles los mutex y el semáforo.
    # ------------------------------------------------------------------
    random.seed(42)
    roles_posibles = ["CAJERO", "ADMINISTRADOR", "AUDITOR"]
    tipos_posibles = ["deposito", "retiro", "consulta"]
    oleada3 = []
    for i in range(10):
        src  = random.choice(ids)
        rol  = random.choice(roles_posibles)
        tipo = random.choice(tipos_posibles)
        if tipo == "deposito":
            txn = TransactionBuilder(f"user{i}", rol) \
                      .with_deposit(src, round(random.uniform(50, 500), 2)).build()
        elif tipo == "retiro":
            txn = TransactionBuilder(f"user{i}", rol) \
                      .with_withdrawal(src, round(random.uniform(10, 300), 2)).build()
        else:
            txn = TransactionBuilder(f"user{i}", rol).with_query(src).build()
        oleada3.append(txn)

    todos_resultados += _someter_oleada(motor, oleada3,
                                        "OLEADA 3 — Carga aleatoria concurrente (10 transacciones)")

    imprimir_resumen_resultados(todos_resultados)
    return todos_resultados


# ===========================================================================
# SECCIÓN 4 — MODO INTERACTIVO MANUAL
# ===========================================================================

def _pedir_cuenta(prompt: str, cuentas: dict) -> str | None:
    """Solicita un ID de cuenta válido. Retorna None si el usuario cancela."""
    print(f"\n  Cuentas disponibles: {', '.join(cuentas.keys())}")
    valor = input(f"  {prompt}: ").strip().upper()
    if valor not in cuentas:
        print(f"  ✗ Cuenta '{valor}' no existe.")
        return None
    return valor


def _pedir_rol() -> str | None:
    """Solicita un rol válido. Retorna None si es inválido."""
    print(f"  Roles válidos: {', '.join(ROLES_VALIDOS)}")
    valor = input("  Rol del usuario: ").strip().upper()
    if valor not in ROLES_VALIDOS:
        print(f"  ✗ Rol '{valor}' no reconocido.")
        return None
    return valor


def _pedir_monto() -> float | None:
    """Solicita un monto numérico positivo. Retorna None si es inválido."""
    try:
        monto = float(input("  Monto ($): ").strip())
        if monto <= 0:
            print("  ✗ El monto debe ser mayor que cero.")
            return None
        return monto
    except ValueError:
        print("  ✗ Valor numérico inválido.")
        return None


def _ejecutar_y_mostrar(motor: TransactionEngine, txn: Transaction):
    """Somete una transacción, espera su resultado e imprime el detalle."""
    motor.submit_transaction(txn)
    motor.wait_completion()
    resultados = motor.get_all_results()
    for r in resultados:
        imprimir_resultado_transaccion(r)
    return resultados


def _menu_deposito(motor: TransactionEngine, cuentas: dict) -> list:
    print(f"\n{SEP2}\n  DEPÓSITO\n{SEP2}")
    cuenta = _pedir_cuenta("ID cuenta destino", cuentas)
    if not cuenta: return []
    rol = _pedir_rol()
    if not rol: return []
    monto = _pedir_monto()
    if monto is None: return []

    txn = TransactionBuilder(f"usr-{rol[:3].lower()}", rol).with_deposit(cuenta, monto).build()
    return _ejecutar_y_mostrar(motor, txn)


def _menu_retiro(motor: TransactionEngine, cuentas: dict) -> list:
    print(f"\n{SEP2}\n  RETIRO\n{SEP2}")
    cuenta = _pedir_cuenta("ID cuenta origen", cuentas)
    if not cuenta: return []
    rol = _pedir_rol()
    if not rol: return []
    monto = _pedir_monto()
    if monto is None: return []

    txn = TransactionBuilder(f"usr-{rol[:3].lower()}", rol).with_withdrawal(cuenta, monto).build()
    return _ejecutar_y_mostrar(motor, txn)


def _menu_transferencia(motor: TransactionEngine, cuentas: dict) -> list:
    print(f"\n{SEP2}\n  TRANSFERENCIA\n{SEP2}")
    origen = _pedir_cuenta("ID cuenta origen", cuentas)
    if not origen: return []
    destino = _pedir_cuenta("ID cuenta destino", cuentas)
    if not destino: return []
    if origen == destino:
        print("  ✗ Las cuentas origen y destino no pueden ser iguales.")
        return []
    rol = _pedir_rol()
    if not rol: return []
    monto = _pedir_monto()
    if monto is None: return []

    txn = TransactionBuilder(f"usr-{rol[:3].lower()}", rol) \
              .with_transfer(origen, destino, monto).build()
    return _ejecutar_y_mostrar(motor, txn)


def _menu_consulta(motor: TransactionEngine, cuentas: dict) -> list:
    print(f"\n{SEP2}\n  CONSULTA DE SALDO\n{SEP2}")
    cuenta = _pedir_cuenta("ID cuenta a consultar", cuentas)
    if not cuenta: return []
    rol = _pedir_rol()
    if not rol: return []

    txn = TransactionBuilder(f"usr-{rol[:3].lower()}", rol).with_query(cuenta).build()
    return _ejecutar_y_mostrar(motor, txn)


def ejecutar_modo_interactivo(motor: TransactionEngine, cuentas: dict) -> list:
    """
    Bucle de menú interactivo. Permite al usuario crear y ejecutar
    transacciones manualmente, ver el estado de las cuentas y guardar
    el log SCAN en cualquier momento.

    Retorna la lista acumulada de resultados de esta sesión.
    """
    print("\n" + SEP)
    print("  MODO INTERACTIVO MANUAL")
    print("  (Los resultados de cada operación aparecen inmediatamente)")
    print(SEP)

    historial_sesion = []

    while True:
        print(f"\n{SEP2}")
        print("  MENÚ INTERACTIVO")
        print(SEP2)
        print("  1. Depósito")
        print("  2. Retiro")
        print("  3. Transferencia")
        print("  4. Consulta de saldo")
        print(SEP2)
        print("  5. Ver estado de todas las cuentas")
        print("  6. Ver resumen de esta sesión")
        print(SEP2)
        print("  7. Volver al menú principal")
        print(SEP2)

        opcion = input("  Seleccione opción (1-8): ").strip()

        if opcion == "1":
            historial_sesion += _menu_deposito(motor, cuentas)
        elif opcion == "2":
            historial_sesion += _menu_retiro(motor, cuentas)
        elif opcion == "3":
            historial_sesion += _menu_transferencia(motor, cuentas)
        elif opcion == "4":
            historial_sesion += _menu_consulta(motor, cuentas)
        elif opcion == "5":
            imprimir_estado_cuentas(cuentas)
        elif opcion == "6":
            if historial_sesion:
                imprimir_resumen_resultados(historial_sesion)
            else:
                print("\n  No se han procesado transacciones en esta sesión.")
        elif opcion == "7":
            break
        else:
            print("\n  ✗ Opción inválida. Ingrese un número entre 1 y 7.")

    return historial_sesion


# ===========================================================================
# SECCIÓN 5 — INICIALIZACIÓN DEL SISTEMA
# ===========================================================================

def crear_cuentas() -> dict:
    """Crea el conjunto inicial de cuentas bancarias."""
    cuentas_data = [
        ("ACC001", "Alice Gómez",   5_000.0),
        ("ACC002", "Bob Martínez",  3_000.0),
        ("ACC003", "Carol Herrera", 8_000.0),
        ("ACC004", "David Ríos",    1_500.0),
        ("ACC005", "Elena Vargas", 10_000.0),
    ]
    return {cid: Account(cid, nombre, saldo) for cid, nombre, saldo in cuentas_data}


def inicializar_sistema() -> tuple:
    """
    Crea las cuentas, configura los hooks y arranca el motor.
    Retorna (motor, cuentas).
    """
    cuentas = crear_cuentas()
    logging.info(f"[MAIN] {len(cuentas)} cuentas inicializadas.")

    politica_rbac = PoliticaRBAC()
    hook_rbac     = construir_hook_rbac(politica_rbac)
    logging.info("[MAIN] Política RBAC cargada.")

    hook_banquero = construir_guard_banquero(cuentas)
    logging.info("[MAIN] Guardia Banquero inicializado.")

    motor = TransactionEngine(cuentas, max_concurrent=3, num_workers=3)
    motor.set_authorization_hook(hook_rbac)
    motor.set_bankers_guard(hook_banquero)
    motor.start()
    logging.info("[MAIN] Motor de transacciones iniciado.")

    return motor, cuentas


# ===========================================================================
# SECCIÓN 6 — PUNTO DE ENTRADA Y MENÚ PRINCIPAL
# ===========================================================================

def main():
    imprimir_encabezado()

    motor, cuentas = inicializar_sistema()
    todos_resultados = []

    print("\n  Sistema inicializado correctamente.")
    imprimir_estado_cuentas(cuentas)

    while True:
        print(f"\n{SEP}")
        print("  MENÚ PRINCIPAL")
        print(SEP)
        print("  1. Ejecutar demostración automática")
        print("  2. Modo interactivo manual")
        print("  3. Ambos (demo automática + interactivo)")
        print(SEP2)
        print("  4. Ver estado actual de cuentas")
        print("  5. Ver resumen de transacciones procesadas")
        print(SEP2)
        print("  6. Salir")
        print(SEP)

        opcion = input("  Seleccione opción (1-6): ").strip()

        if opcion == "1":
            resultados = ejecutar_demo(motor, cuentas)
            todos_resultados += resultados
            logging.info(f"[MAIN] Demo completada. {len(resultados)} transacciones procesadas.")

        elif opcion == "2":
            resultados = ejecutar_modo_interactivo(motor, cuentas)
            todos_resultados += resultados
            logging.info(f"[MAIN] Sesión interactiva finalizada. {len(resultados)} transacciones.")

        elif opcion == "3":
            print("\n  Ejecutando demostración automática primero...")
            resultados_demo = ejecutar_demo(motor, cuentas)
            todos_resultados += resultados_demo
            logging.info(f"[MAIN] Demo completada. {len(resultados_demo)} transacciones.")

            input("\n  Presione ENTER para continuar al modo interactivo...")
            resultados_int = ejecutar_modo_interactivo(motor, cuentas)
            todos_resultados += resultados_int
            logging.info(f"[MAIN] Sesión interactiva finalizada. {len(resultados_int)} transacciones.")

        elif opcion == "4":
            imprimir_estado_cuentas(cuentas)

        elif opcion == "5":
            if todos_resultados:
                imprimir_resumen_resultados(todos_resultados)
            else:
                print("\n  No hay transacciones procesadas aún.")

        elif opcion == "6":
            print("\n  Deteniendo el motor de transacciones...")
            motor.stop()
            if todos_resultados:
                registrar_resultados_con_scan(todos_resultados)
                print(f"  ✓ Log final escrito en: {_LOG_TRANSACTIONS}")
            logging.info("[MAIN] Sistema detenido correctamente.")
            print("  Sistema detenido. Hasta luego.\n")
            break

        else:
            print("\n  ✗ Opción inválida. Ingrese un número entre 1 y 6.")


if __name__ == "__main__":
    main()