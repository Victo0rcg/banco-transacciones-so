# 🏦 Procesador de Transacciones Bancarias

**Asignatura:** Sistemas Operativos  
**Institución:** Universidad Tecnológica de Pereira  
**Docente:** Juan Andrés García Moreno  
**Período:** 2026-1  
**Equipo:** 5

---

## Tabla de contenidos

1. [Descripción General](#1-descripción-general)
2. [Objetivos](#2-objetivos)
3. [Marco Conceptual](#3-marco-conceptual)
4. [Arquitectura del Sistema](#4-arquitectura-del-sistema)
5. [Estructura del Proyecto](#5-estructura-del-proyecto)
6. [Módulos y Arquitectura de Clases](#6-módulos-y-arquitectura-de-clases)
   - 6.1 [Core — Motor de Cuentas y Transacciones](#61-core--motor-de-cuentas-y-transacciones)
   - 6.2 [Scheduling — Planificador SCAN](#62-scheduling--planificador-scan)
   - 6.3 [Security — Control de Acceso RBAC](#63-security--control-de-acceso-rbac)
   - 6.4 [Concurrency — Algoritmo del Banquero](#64-concurrency--algoritmo-del-banquero)
   - 6.5 [main.py — Orquestador](#65-mainpy--orquestador)
7. [Flujo de Ejecución Detallado](#7-flujo-de-ejecución-detallado)
8. [Mecanismos de Sincronización](#8-mecanismos-de-sincronización)
9. [Prevención de Interbloqueos](#9-prevención-de-interbloqueos)
10. [Modelo de Permisos y Dominios](#10-modelo-de-permisos-y-dominios)
11. [Planificación SCAN Aplicada al Logging](#11-planificación-scan-aplicada-al-logging)
12. [Manejo de Interrupciones y Señales](#12-manejo-de-interrupciones-y-señales)
13. [Especificaciones Técnicas](#13-especificaciones-técnicas)
14. [Ejecución y Modos de Uso](#14-ejecución-y-modos-de-uso)
15. [Salida Esperada del Sistema](#15-salida-esperada-del-sistema)
16. [Referencias](#16-referencias)

---

## 1. Descripción General

Este proyecto implementa un **simulador de procesador de transacciones bancarias** que demuestra de forma práctica cuatro conceptos fundamentales de los sistemas operativos: sincronización con exclusión mutua, planificación de disco, control de acceso basado en roles y prevención de interbloqueos.

El sistema permite que múltiples hilos de ejecución compitan simultáneamente por el acceso a cuentas bancarias compartidas, garantizando la consistencia de los saldos mediante primitivas de sincronización estándar (`threading.Lock`, `threading.Semaphore`) y un patrón productor-consumidor implementado sobre `queue.Queue`.

Cada transacción atraviesa un ciclo de vida completo: es creada por un productor, encolada, validada por el subsistema RBAC, evaluada por el Algoritmo del Banquero (en el caso de transferencias), ejecutada atómicamente sobre las cuentas y, finalmente, registrada en disco mediante el planificador SCAN.

El sistema ofrece dos modos de uso: una **demostración automática** organizada en oleadas que hace visible el comportamiento concurrente, y un **modo interactivo** que permite crear transacciones manualmente desde la consola para depuración y presentación.

---

## 2. Objetivos

### Objetivo General

Desarrollar un simulador de procesador de transacciones bancarias en Python que integre mecanismos de sincronización concurrente, planificación de operaciones de disco y control de acceso basado en roles, evidenciando la aplicación práctica de los principios fundamentales de los sistemas operativos.

### Objetivos Específicos

- Implementar un modelo de concurrencia con `threading.Thread` y exclusión mutua con `threading.Lock` que garantice la consistencia del saldo de cada cuenta frente a accesos simultáneos de múltiples hilos.
- Demostrar el patrón productor-consumidor mediante una cola thread-safe (`queue.Queue`) que desacopla la generación de transacciones de su ejecución.
- Simular el algoritmo SCAN de planificación de disco aplicado al subsistema de logging, modelando cada entrada de log como una solicitud con número de bloque ficticio.
- Diseñar e integrar una política RBAC que restrinja las operaciones permitidas según el rol asignado al usuario solicitante.
- Implementar el **Algoritmo del Banquero** de Dijkstra para la prevención de interbloqueos en transferencias que requieren adquirir los locks de dos cuentas simultáneamente.

---

## 3. Marco Conceptual

### 3.1 Condición de Carrera y Sección Crítica

Una **condición de carrera** (*race condition*) ocurre cuando dos o más hilos acceden concurrentemente a un recurso compartido y el resultado final depende del orden no determinístico de planificación del sistema operativo (Silberschatz et al., 2018). En el contexto bancario, si dos hilos leen el mismo saldo antes de que cualquiera de los dos lo actualice, ambos calcularán el nuevo saldo sobre el valor anterior, produciendo un resultado incorrecto.

La **sección crítica** es el fragmento de código que accede al recurso compartido y que debe ejecutarse de forma atómica. El mecanismo de exclusión mutua garantiza que en todo momento solo un hilo esté dentro de la sección crítica para un recurso dado.

### 3.2 Mutex y Semáforo

El **mutex** (`threading.Lock` en Python) es un mecanismo binario de exclusión mutua. Su operación `acquire()` bloquea al hilo si el lock ya está tomado; `release()` lo libera y despierta a un hilo en espera. El uso con la sentencia `with` garantiza la liberación incluso ante excepciones.

El **semáforo** (`threading.Semaphore`) generaliza el mutex permitiendo que hasta *N* hilos accedan simultáneamente a un recurso. En este sistema, un semáforo con valor *max_concurrent* limita el número de transacciones que el motor puede ejecutar en paralelo en un instante dado.

### 3.3 Patrón Productor-Consumidor

El patrón productor-consumidor desacopla la generación de trabajo (productores) de su ejecución (consumidores) mediante un buffer compartido thread-safe. En este sistema:

- Los **productores** son los hilos de aplicación que llaman a `submit_transaction()`.
- El **buffer** es la `queue.Queue` interna del motor, que implementa exclusión mutua internamente.
- Los **consumidores** son los hilos worker (`TrabajadorTransacción-N`) que extraen transacciones y las ejecutan.

### 3.4 Algoritmo SCAN (elevador)

El algoritmo SCAN, también conocido como **algoritmo del elevador**, planifica el acceso al disco moviendo el cabezal en una dirección y atendiendo todas las solicitudes en su camino antes de invertir la dirección (Silberschatz et al., 2018). Reduce el tiempo de búsqueda promedio respecto a FCFS al minimizar el movimiento total del cabezal.

En este proyecto, SCAN se aplica al subsistema de logging: cada transacción tiene un `block_number` ficticio (entero entre 0 y 100), y el planificador ordena las entradas de log según la secuencia SCAN antes de escribirlas en disco.

### 3.5 Control de Acceso Basado en Roles (RBAC)

RBAC (*Role-Based Access Control*) es un modelo de control de acceso estandarizado por el NIST (Ferraiolo et al., 2001) que asigna permisos a roles funcionales en lugar de a usuarios individuales. Un usuario hereda los permisos del rol que tiene asignado. Esto simplifica la administración de políticas de seguridad en sistemas con muchos usuarios.

En este sistema hay tres roles (`ADMINISTRADOR`, `CAJERO`, `AUDITOR`) y cuatro operaciones (`DEPOSITO`, `RETIRO`, `TRANSFERENCIA`, `CONSULTA`), organizados en una matriz de control de acceso.

### 3.6 Algoritmo del Banquero

El Algoritmo del Banquero, propuesto por Dijkstra (1965), evita el interbloqueo evaluando si la concesión de una solicitud de recursos dejaría al sistema en un **estado seguro**: un estado desde el cual existe al menos una secuencia de procesos que puede completar su ejecución sin generar espera circular (Tanenbaum y Bos, 2015).

El algoritmo mantiene cuatro estructuras:
- **Disponible** (*Available*): recursos actualmente libres.
- **Máximo** (*Max*): máxima demanda de recursos de cada proceso.
- **Asignado** (*Allocated*): recursos actualmente asignados a cada proceso.
- **Necesidad** (*Need*) = Máximo − Asignado: recursos adicionales que puede solicitar cada proceso.

Ante una solicitud, el algoritmo simula la asignación, verifica si el nuevo estado es seguro y, si no lo es, ejecuta un *rollback*.

---

## 4. Arquitectura del Sistema

El sistema se organiza en cuatro capas funcionales que se integran a través del orquestador `main.py`:

```
┌─────────────────────────────────────────────────────────────┐
│                         main.py                             │
│              Orquestador e integrador de módulos            │
└────────────┬──────────────┬──────────────┬──────────────────┘
             │              │              │
    ┌────────▼──────┐  ┌────▼──────┐  ┌───▼────────────────┐
    │  core/        │  │security/  │  │  concurrency/      │
    │  ─────────    │  │─────────  │  │  ────────────────  │
    │  Account      │  │  Rol      │  │  GuardiaBanquero   │
    │  Transaction  │  │  Operacion│  │                    │
    │  Transaction  │  │  Politica │  └────────────────────┘
    │  Builder      │  │  RBAC     │
    │  Transaction  │  └───────────┘
    │  Engine       │
    └───────┬───────┘
            │ resultados con block_number
    ┌───────▼───────────────────┐
    │  scheduling/              │
    │  ─────────────────────    │
    │  scan_scheduling()        │
    │  → ordena logs por SCAN   │
    │  → escribe transactions   │
    │    .log                   │
    └───────────────────────────┘
```

### Flujo de Datos entre Capas

```
Productor (hilo de app)
        │
        │  submit_transaction(txn)
        ▼
┌───────────────────────┐
│   _transaction_queue  │  ← queue.Queue (thread-safe)
└───────────┬───────────┘
            │  get(timeout=1.0)
            ▼
┌───────────────────────┐
│   Worker Thread       │
│   ─────────────────   │
│   1. RBAC hook?       │──── denegado ──→ _result_queue
│   2. mark_authorized  │
│   3. semaphore.acquire│
│   4. mark_processing  │
│   5. _process_txn()   │
│      ├─ DEPOSIT       │──→ account.deposit()
│      ├─ WITHDRAWAL    │──→ account.withdraw()
│      ├─ TRANSFER      │──→ bankers_guard?
│      │                │    → _execute_transfer()
│      └─ QUERY         │──→ account.get_balance()
│   6. mark_completed / │
│      mark_failed      │
│   7. semaphore.release│
└───────────┬───────────┘
            │  put(result)
            ▼
┌───────────────────────┐
│   _result_queue       │
└───────────┬───────────┘
            │  get_all_results()
            ▼
┌───────────────────────┐
│  scan_scheduling()    │──→ logs/transactions.log
└───────────────────────┘
```

---

## 5. Estructura del Proyecto

```
banco-transacciones-so/
│
├── main.py                        # Punto de entrada y orquestador
├── requirements.txt               # Dependencias externas (pytest)
├── README.md                      # Este documento
│
├── core/                          # Módulo 1: Motor de cuentas y transacciones
│   ├── __init__.py
│   ├── account.py                 # Clase Account con mutex por instancia
│   ├── transaction.py             # Clases Transaction, TransactionBuilder,
│   │                              #   TransactionType, TransactionStatus
│   └── transaction_engine.py      # Motor productor-consumidor con semáforo
│
├── scheduling/                    # Módulo 2: Planificador SCAN
│   ├── __init__.py
│   └── scan_scheduler.py          # Función scan_scheduling()
│
├── security/                      # Módulo 3: Control de acceso RBAC
│   ├── __init__.py
│   ├── roles.py                   # Enums Rol y Operacion
│   └── rbac_policy.py             # Clase PoliticaRBAC
│
├── concurrency/                   # Módulo 4: Algoritmo del Banquero
│   ├── __init__.py
│   └── bankers_guard.py           # Clase GuardiaBanquero
│
└── logs/                          # Generados en tiempo de ejecución
    ├── transactions.log           # Registro ordenado por SCAN
    └── system.log                 # Traza detallada por hilos
```

---

## 6. Módulos y Arquitectura de Clases

### 6.1 `Core/` — Motor de Cuentas y Transacciones

#### Clase `Account` (`core/account.py`)

Representa una cuenta bancaria con operaciones atómicas garantizadas por un `threading.Lock` propio de cada instancia. Los saldos se mantienen exclusivamente en memoria — no hay persistencia en disco — lo que elimina las condiciones de carrera asociadas a operaciones de E/S dentro de la sección crítica.

**Atributos:**

| Atributo | Tipo | Descripción |
|---|---|---|
| `account_id` | `str` | Identificador único de la cuenta |
| `holder_name` | `str` | Nombre del titular |
| `initial_balance` | `float` | Saldo inicial (parámetro del dataclass) |
| `balance` | `float` | Saldo actual (inicializado en `__post_init__`) |
| `_lock` | `threading.Lock` | Mutex exclusivo de esta cuenta |
| `_transaction_history` | `list[dict]` | Historial inmutable de operaciones |
| `_created_at` | `datetime` | Marca de tiempo de creación |

**Métodos públicos:**

| Método | Firma | Descripción | Thread-safe |
|---|---|---|---|
| `deposit` | `(amount: float, description: str) -> bool` | Incrementa el saldo. Lanza `ValueError` si `amount <= 0`. Adquiere `_lock` antes de modificar. | ✔ |
| `withdraw` | `(amount: float, description: str) -> bool` | Decrementa el saldo. Retorna `False` si fondos insuficientes. Adquiere `_lock`. | ✔ |
| `get_balance` | `() -> float` | Retorna el saldo actual. Adquiere `_lock` para snapshot consistente. | ✔ |
| `transfer_internal` | `(amount: float, source_id: str, description: str) -> bool` | Aplica un delta al saldo (negativo = débito, positivo = crédito). **Debe llamarse con `_lock` ya adquirido por el llamador.** | ✘ (interna) |
| `get_transaction_history` | `() -> list` | Retorna copia del historial. Adquiere `_lock`. | ✔ |
| `acquire_lock` | `() -> None` | Expone `_lock.acquire()` para sincronización externa (usada por el motor en transferencias). | — |
| `release_lock` | `() -> None` | Expone `_lock.release()` para sincronización externa. | — |

**Invariante de diseño:** `transfer_internal` no adquiere `_lock` porque el motor (`_execute_transfer`) ya lo adquiere externamente para ambas cuentas antes de llamarlo. Esto evita que un `Lock` no reentrante cause un interbloqueo por re-adquisición.

---

#### Enumeraciones `TransactionType` y `TransactionStatus` (`core/transaction.py`)

```
TransactionType
├── DEPOSIT      → "DEPOSIT"
├── WITHDRAWAL   → "WITHDRAWAL"
├── TRANSFER     → "TRANSFER"
└── QUERY        → "QUERY"

TransactionStatus
├── PENDING      → estado inicial al construir
├── AUTHORIZED   → aprobado por RBAC
├── PROCESSING   → adquirido el semáforo, en ejecución
├── COMPLETED    → operación exitosa
├── FAILED       → error de negocio (fondos insuficientes, cuenta no encontrada)
└── DENIED       → rechazado por RBAC o por el Algoritmo del Banquero
```

#### Clase `Transaction` (`core/transaction.py`)

Modelo de datos que encapsula toda la información de una transacción a lo largo de su ciclo de vida.

**Campos del dataclass** (en orden de declaración):

| Campo | Tipo | Default | Descripción |
|---|---|---|---|
| `source_account_id` | `str` | — | Cuenta origen de la operación |
| `amount` | `float` | — | Monto de la operación |
| `user_id` | `str` | — | Identificador del usuario solicitante |
| `user_role` | `str` | — | Rol del usuario (`"ADMINISTRADOR"`, `"CAJERO"`, `"AUDITOR"`) |
| `transaction_type` | `TransactionType` | — | Tipo de operación |
| `transaction_id` | `Optional[str]` | `None` | Asignado por el motor al someter; `None` antes de `submit_transaction()` |
| `destination_account_id` | `Optional[str]` | `None` | Cuenta destino (solo para `TRANSFER`) |
| `timestamp` | `Optional[datetime]` | `None` | Auto-asignado en `__post_init__` si no se provee |
| `block_number` | `int` | `0` | Número de bloque ficticio para planificación SCAN; asignado por el motor |
| `status` | `TransactionStatus` | `PENDING` | Estado actual del ciclo de vida |
| `description` | `str` | `""` | Descripción legible de la operación |
| `metadata` | `dict` | `{}` | Metadatos adicionales (timestamps de cada transición, saldo en consultas, etc.) |

**Ciclo de vida del estado:**

```
PENDING
   │
   ├─ RBAC deniega ──────────────────────────────→ DENIED
   │
   ▼
AUTHORIZED
   │
   ▼
PROCESSING
   │
   ├─ Banquero deniega ──────────────────────────→ DENIED
   ├─ Fondos insuficientes / cuenta no existe ──→ FAILED
   │
   ▼
COMPLETED
```

**Métodos de transición de estado:**

| Método | Precondición | Efecto |
|---|---|---|
| `mark_authorized()` | `status == PENDING` | `status → AUTHORIZED`; registra `authorized_at` en metadata |
| `mark_processing()` | `status in {AUTHORIZED, PENDING}` | `status → PROCESSING`; registra `processing_started_at` |
| `mark_completed()` | Ninguna | `status → COMPLETED`; registra `completed_at` |
| `mark_failed(reason)` | Ninguna | `status → FAILED`; registra `failed_at` y `failure_reason` |
| `mark_denied(reason)` | Ninguna | `status → DENIED`; registra `denied_at` y `denial_reason` |

**Métodos de consulta:**

| Método | Retorno | Descripción |
|---|---|---|
| `get_operation_summary()` | `str` | Descripción legible de la operación |
| `to_dict()` | `dict` | Serialización completa a diccionario |

---

#### Clase `TransactionBuilder` (`core/transaction.py`)

Implementa el patrón *Builder* para construir objetos `Transaction` con una interfaz fluida, garantizando que todos los campos obligatorios estén presentes antes de crear el objeto.

**Constructor:**

```python
TransactionBuilder(user_id: str, user_role: str)
```

No acepta `transaction_id`: el motor es el único responsable de asignar identificadores.

**Métodos de configuración (retornan `self` para encadenamiento):**

| Método | Descripción |
|---|---|
| `with_deposit(account_id, amount)` | Configura como depósito |
| `with_withdrawal(account_id, amount)` | Configura como retiro |
| `with_transfer(source_id, dest_id, amount)` | Configura como transferencia |
| `with_query(account_id)` | Configura como consulta de saldo |
| `build()` | Valida y construye el objeto `Transaction`; lanza `ValueError` si faltan campos obligatorios |

**Ejemplo de uso:**

```python
txn = (TransactionBuilder("cajero01", "CAJERO")
       .with_deposit("ACC001", 500.0)
       .build())
```

---

#### Clase `TransactionEngine` (`core/transaction_engine.py`)

Núcleo del sistema. Implementa el patrón productor-consumidor con `N` hilos worker y control de concurrencia mediante semáforo.

**Atributos internos:**

| Atributo | Tipo | Descripción |
|---|---|---|
| `_transaction_queue` | `queue.Queue` | Cola de entrada; buffer entre productores y consumidores |
| `_result_queue` | `queue.Queue` | Cola de salida con transacciones completadas |
| `_accounts` | `dict[str, Account]` | Mapa de cuentas registradas en el sistema |
| `_max_concurrent` | `int` | Límite de transacciones en ejecución simultánea |
| `_semaphore` | `threading.Semaphore` | Controla el límite de concurrencia |
| `_num_workers` | `int` | Número de hilos consumidores |
| `_workers` | `list[Thread]` | Referencias a los hilos activos |
| `_running` | `bool` | Bandera de estado del motor |
| `_lock` | `threading.Lock` | Protege `_running` y `_transaction_counter` |
| `_transaction_counter` | `int` | Contador autoincremental para asignar IDs |
| `_authorization_hook` | `Callable` | Callback RBAC inyectado desde `main.py` |
| `_bankers_guard` | `Callable` | Callback Banquero inyectado desde `main.py` |

**Métodos públicos:**

| Método | Descripción |
|---|---|
| `start()` | Lanza los `N` hilos worker en modo daemon |
| `stop(timeout)` | Envía señales de cierre (centinela `None`) y espera que los workers terminen con `join()` |
| `submit_transaction(txn)` | Asigna ID, asigna `block_number` aleatorio y encola la transacción; retorna el ID asignado |
| `set_authorization_hook(hook)` | Inyecta el callback RBAC |
| `set_bankers_guard(guard)` | Inyecta el callback del Banquero |
| `get_all_results()` | Drena todos los resultados disponibles de `_result_queue` |
| `wait_completion()` | Bloquea hasta que `_transaction_queue.join()` retorne (todos los `task_done()` emitidos) |

**Método `_execute_transfer` — Locking ordenado:**

Para transferencias, el motor necesita adquirir los locks de dos cuentas simultáneamente. Si dos hilos adquieren los locks en orden inverso se produce un **deadlock circular**. La solución implementada es adquirir siempre los locks en **orden lexicográfico por `account_id`**:

```python
if source_id < dest_id:
    first_account, second_account = source_account, dest_account
else:
    first_account, second_account = dest_account, source_account

first_account.acquire_lock()
try:
    second_account.acquire_lock()
    try:
        # sección crítica: verificar saldo y ejecutar débito/crédito
    finally:
        second_account.release_lock()
finally:
    first_account.release_lock()
```

Con este ordenamiento, dos hilos que intenten transferir entre las mismas cuentas en sentidos opuestos siempre competirán por el mismo primer lock, eliminando la espera circular.

---

### 6.2 `Scheduling/` — Planificador SCAN

#### Función `scan_scheduling` (`scheduling/scan_scheduler.py`)

Implementa el algoritmo SCAN puro. No mantiene estado entre llamadas.

**Firma:**

```python
def scan_scheduling(requests: list[int], head_position: int, direction: str) -> list[int]
```

**Parámetros:**

| Parámetro | Tipo | Descripción |
|---|---|---|
| `requests` | `list[int]` | Lista de números de bloque solicitados (puede tener duplicados) |
| `head_position` | `int` | Posición actual del cabezal |
| `direction` | `str` | Dirección inicial: `'up'` (hacia bloques mayores) o `'down'` (hacia menores) |

**Retorno:** Lista de bloques en el orden en que deben ser atendidos.

**Lógica interna:**

```
Si direction == 'up':
    orden = [solicitudes >= head_position, ordenadas asc]
           + [solicitudes < head_position, ordenadas desc]

Si direction == 'down':
    orden = [solicitudes <= head_position, ordenadas desc]
           + [solicitudes > head_position, ordenadas asc]
```

**Ejemplo con `head_position=50`, `direction='up'`, `requests=[10, 30, 70, 90, 20, 60]`:**

```
Orden SCAN: [60, 70, 90, 30, 20, 10]
            ↑ sube desde 50    ↑ baja desde 90
```

---

### 6.3 `Security/` — Control de Acceso RBAC

#### Enumeraciones `Rol` y `Operacion` (`security/roles.py`)

```python
class Rol(Enum):
    ADMINISTRADOR = "ADMINISTRADOR"   # acceso completo
    CAJERO        = "CAJERO"          # depósitos, retiros y consultas
    AUDITOR       = "AUDITOR"         # solo consultas

class Operacion(Enum):
    DEPOSITO      = "DEPOSITO"
    RETIRO        = "RETIRO"
    TRANSFERENCIA = "TRANSFERENCIA"
    CONSULTA      = "CONSULTA"
```

#### Clase `PoliticaRBAC` (`security/rbac_policy.py`)

Implementa la matriz de control de acceso. Es el único lugar del sistema donde se define qué rol puede ejecutar qué operación.

**Matriz de acceso:**

| Operación | ADMINISTRADOR | CAJERO | AUDITOR |
|---|:---:|:---:|:---:|
| `DEPOSITO` | ✔ | ✔ | ✘ |
| `RETIRO` | ✔ | ✔ | ✘ |
| `TRANSFERENCIA` | ✔ | ✘ | ✘ |
| `CONSULTA` | ✔ | ✔ | ✔ |

**Método `verificar_permiso(rol, operacion) -> bool`:**

- Si la operación está en el conjunto de permisos del rol: registra en log y retorna `True`.
- Si no: registra el evento como error de seguridad y lanza `PermissionError` con el mensaje de violación de dominio.

**Integración con el motor:** `main.py` construye un *hook* que actúa como puente entre el motor (que almacena `user_role` como `str`) y `PoliticaRBAC` (que trabaja con el enum `Rol`). El hook convierte el string al enum antes de llamar a `verificar_permiso`, captura el `PermissionError` y lo convierte en `False` para el motor.

---

### 6.4 `Concurrency/` — Algoritmo del Banquero

#### Clase `GuardiaBanquero` (`concurrency/bankers_guard.py`)

Implementa el Algoritmo del Banquero de Dijkstra en su versión completa con detección de estado seguro y rollback.

**Constructor:**

```python
GuardiaBanquero(
    recursos_disponibles: list[int],    # vector Available
    necesidad_maxima: list[list[int]],  # matriz Max
    recursos_asignados: list[list[int]] # matriz Allocated
)
```

Al inicializar calcula automáticamente la **matriz Need** = Max − Allocated.

**Atributos:**

| Atributo | Descripción |
|---|---|
| `recursos_disponibles` | Vector `Available`: recursos libres actualmente |
| `necesidad_maxima` | Matriz `Max`: demanda máxima declarada por proceso |
| `recursos_asignados` | Matriz `Allocated`: asignación actual |
| `matriz_necesidad` | Matriz `Need` = Max − Allocated |
| `cantidad_procesos` | Número de procesos (filas de las matrices) |
| `cantidad_recursos` | Número de tipos de recursos (columnas) |

**Método `es_estado_seguro() -> bool`:**

Implementa el algoritmo de detección de estado seguro:

```
Work   = Available.copy()
Finish = [False] * n_procesos

mientras len(secuencia_segura) < n_procesos:
    para cada proceso i no terminado:
        si Need[i] <= Work:
            Work   += Allocated[i]
            Finish[i] = True
            secuencia_segura.append(i)
    si ningún proceso avanzó en esta ronda:
        retornar False  ← estado inseguro

retornar True  ← estado seguro
```

**Método `solicitar_recursos(id_proceso, solicitud) -> bool`:**

1. Verifica que la solicitud no supere `Need[id_proceso]` (lanza `ValueError` si la supera).
2. Verifica que haya recursos disponibles suficientes (retorna `False` si no).
3. **Simula** la asignación: descuenta de `Available`, suma a `Allocated[id]`, descuenta de `Need[id]`.
4. Llama a `es_estado_seguro()`.
5. Si el estado no es seguro: **rollback** completo y retorna `False`.
6. Si es seguro: retorna `True` con la asignación confirmada.

**Adaptación al contexto bancario (`main.py`):**

En el sistema bancario, el único recurso disputado en una transferencia es el lock de una cuenta. La adaptación modela:
- Cada cuenta → un proceso.
- Tipo de recurso único → lock de cuenta (vector de 1 elemento).
- `Available = [n_cuentas]`, `Max[i] = [1]`, `Allocated[i] = [0]` inicialmente.

Un `threading.Lock` externo (`lock_guard`) protege el estado interno del `GuardiaBanquero` ya que múltiples workers pueden invocarlo concurrentemente.

---

### 6.5 `main.py` — Orquestador

`main.py` se organiza en seis secciones con responsabilidades claramente separadas:

**Sección 1 — Integración de componentes:**
- `construir_hook_rbac`: convierte `user_role: str` al enum `Rol`, mapea `TransactionType` a `Operacion` y delega en `PoliticaRBAC.verificar_permiso()`. Captura `PermissionError` y lo traduce a `False` para el motor.
- `construir_guard_banquero`: instancia `GuardiaBanquero` con el estado inicial del conjunto de cuentas. Solo actúa sobre transacciones de tipo `TRANSFER`. Protege el estado del banquero con un lock propio para concurrencia segura entre workers.
- `registrar_resultados_con_scan`: recolecta los `block_number` de los resultados, invoca `scan_scheduling()` para obtener el orden óptimo y escribe las entradas en `logs/transactions.log`.

**Sección 2 — Utilidades de presentación en consola:**
Funciones de impresión reutilizables: `imprimir_estado_cuentas`, `imprimir_resumen_resultados`, `imprimir_resultado_transaccion`. Esta última imprime el resultado de una transacción individual de forma inmediata, incluyendo la razón de fallo o denegación desde `metadata`.

**Sección 3 — Modo demostración automática (`ejecutar_demo`):**
Lanza tres oleadas de transacciones predefinidas esperando la finalización de cada una antes de iniciar la siguiente, lo que hace visible la concurrencia y el comportamiento de cada subsistema de forma ordenada.

**Sección 4 — Modo interactivo manual (`ejecutar_modo_interactivo`):**
Bucle de menú que permite crear y ejecutar transacciones una a una, ver el estado de las cuentas y revisar el historial de la sesión activa.

**Sección 5 — Inicialización (`inicializar_sistema`):**
Crea las cuentas, configura los hooks y arranca el motor. Devuelve `(motor, cuentas)`.

**Sección 6 — Punto de entrada (`main`):**
Menú principal que coordina los modos de uso y garantiza que el log SCAN se escriba al salir.

---

## 7. Flujo de Ejecución Detallado

```
INICIO
│
├─ 1. Inicializar cuentas bancarias (dict account_id → Account)
│
├─ 2. Inicializar PoliticaRBAC y construir hook_rbac
│
├─ 3. Inicializar GuardiaBanquero con estado de cuentas
│      y construir hook_banquero
│
├─ 4. Crear TransactionEngine(cuentas, max_concurrent, num_workers)
│      └─ Inyectar hook_rbac y hook_banquero
│
├─ 5. motor.start()
│      └─ Lanzar N hilos TrabajadorTransacción (daemon=True)
│
├─ 6. Para cada transacción sometida:
│      └─ motor.submit_transaction(txn)
│             ├─ Asignar transaction_id = "T{contador:06d}"  [bajo _lock]
│             ├─ Asignar block_number = random(0, 100)
│             └─ _transaction_queue.put(txn)
│
├─ 7. motor.wait_completion()
│      └─ Bloquea hasta que la cola quede vacía
│
├─ 8. Para cada Worker (ejecutándose en paralelo):
│      └─ BUCLE:
│             ├─ txn = _transaction_queue.get(timeout=1.0)
│             │    └─ queue.Empty → continue  (timer interrupt simulado)
│             │    └─ None       → break      (señal de cierre)
│             │
│             ├─ RBAC hook(txn)?
│             │    └─ No → mark_denied → _result_queue.put → task_done → continue
│             │
│             ├─ mark_authorized()
│             ├─ semaphore.acquire()
│             ├─ mark_processing()
│             │
│             ├─ _process_transaction(txn):
│             │    ├─ DEPOSIT    → account.deposit()
│             │    ├─ WITHDRAWAL → account.withdraw()
│             │    ├─ TRANSFER   → bankers_guard(txn)?
│             │    │                 └─ No → mark_denied
│             │    │              → _execute_transfer()
│             │    │                 ├─ Ordenar locks por account_id
│             │    │                 ├─ acquire first_lock
│             │    │                 ├─ acquire second_lock
│             │    │                 ├─ verificar saldo (balance directo)
│             │    │                 ├─ transfer_internal(-amount, dest_id)
│             │    │                 ├─ transfer_internal(+amount, src_id)
│             │    │                 ├─ release second_lock
│             │    │                 └─ release first_lock
│             │    └─ QUERY      → get_balance() → metadata['balance']
│             │
│             ├─ mark_completed() / mark_failed()
│             ├─ _result_queue.put(txn)
│             ├─ semaphore.release()
│             └─ task_done()
│
├─ 9. motor.stop()
│      ├─ Enviar None × N_workers a _transaction_queue
│      └─ worker.join(timeout) para cada worker
│
├─ 10. resultados = motor.get_all_results()
│
├─ 11. scan_scheduling(block_numbers, head=0, direction='up')
│       └─ Escribir resultados ordenados en logs/transactions.log
│
└─ 12. Mostrar resumen en consola y estado final de cuentas

FIN
```

---

## 8. Mecanismos de Sincronización

El sistema usa tres primitivas de sincronización distintas, cada una para un propósito específico:

### `threading.Lock` — Exclusión mutua por cuenta

Cada instancia de `Account` posee su propio `threading.Lock`. Esto significa que dos hilos pueden operar simultáneamente sobre cuentas distintas sin bloquearse entre sí, maximizando el paralelismo. Solo compiten cuando intentan operar sobre la misma cuenta.

```
Hilo-1: deposit(ACC001) → acquire(lock_ACC001) → modifica saldo → release
Hilo-2: deposit(ACC002) → acquire(lock_ACC002) → modifica saldo → release
  ↑ Ambos avanzan en paralelo sin interferencia

Hilo-1: deposit(ACC001) → acquire(lock_ACC001) → ...
Hilo-3: withdraw(ACC001) → acquire(lock_ACC001) → BLOQUEADO hasta que Hilo-1 libere
  ↑ Serialización correcta sobre la misma cuenta
```

### `threading.Semaphore` — Límite de concurrencia global

El semáforo `_semaphore(max_concurrent)` limita cuántas transacciones pueden estar en fase de ejecución simultáneamente, independientemente del número de workers. Esto protege el sistema de sobrecarga cuando hay muchos workers y pocas cuentas.

### `threading.Lock` del motor — Protección del contador de IDs

El `_lock` interno del motor protege el `_transaction_counter` y el flag `_running`. Dado que múltiples productores pueden llamar a `submit_transaction()` concurrentemente, sin este lock dos transacciones podrían recibir el mismo ID.

---

## 9. Prevención de Interbloqueos

El sistema emplea dos estrategias complementarias e intencionales de prevención de interbloqueos que operan en capas distintas:

### Estrategia 1: Algoritmo del Banquero (capa de planificación previa)

Antes de que el motor entre en `_execute_transfer`, el `hook_banquero` consulta a `GuardiaBanquero` si la asignación de un lock adicional dejaría al sistema en estado seguro. Si no, la transacción se deniega sin haber adquirido ningún lock, evitando la situación de riesgo desde el inicio.

### Estrategia 2: Locking ordenado en transferencias (capa de sincronización en ejecución)

La condición necesaria de **espera circular** se rompe adquiriendo los locks de las dos cuentas involucradas siempre en el mismo orden (lexicográfico por `account_id`). Si `ACC001 < ACC002`, cualquier hilo que quiera operar sobre este par siempre adquirirá primero `lock_ACC001`, eliminando la posibilidad de espera circular en tiempo de ejecución.

Ambas estrategias son complementarias: el Banquero actúa como puerta de entrada antes de cualquier adquisición de lock; el locking ordenado actúa como garantía durante la adquisición misma. Esta defensa en profundidad es coherente con la práctica en sistemas reales, donde múltiples capas de prevención coexisten para cubrir distintos puntos del ciclo de vida de un recurso.

---

## 10. Modelo de Permisos y Dominios

El modelo RBAC implementado sigue el estándar NIST RBAC Nivel 1 (*Flat RBAC*): roles planos sin jerarquía ni herencia. Cada usuario tiene exactamente un rol asignado en el campo `user_role` de la transacción.

### Dominios de protección

Cada rol define un **dominio de protección**: el conjunto de operaciones que tiene permitido ejecutar.

```
Dominio ADMINISTRADOR = {DEPOSITO, RETIRO, TRANSFERENCIA, CONSULTA}
Dominio CAJERO        = {DEPOSITO, RETIRO, CONSULTA}
Dominio AUDITOR       = {CONSULTA}
```

### Flujo de verificación

```
submit_transaction(txn)
        │
        ▼
_worker_loop llama hook_rbac(txn)
        │
        ▼
construir_hook_rbac:
    rol       = Rol(txn.user_role)
    operacion = _TIPO_A_OPERACION[txn.transaction_type]
        │
        ▼
PoliticaRBAC.verificar_permiso(rol, operacion)
    ├─ operacion en permisos[rol] → True → mark_authorized() → semaphore
    └─ operacion no en permisos  → PermissionError
                                        │
                                        ▼
                            mark_denied("Authorization denied")
                            _result_queue.put(txn)
```

### Tratamiento de Violaciones

Cuando se detecta una violación de dominio, `PoliticaRBAC` registra el evento como `logging.ERROR` (auditoría) y lanza `PermissionError`. El hook captura esta excepción y retorna `False` al worker, quien marca la transacción como `DENIED` sin ejecutar ninguna operación sobre las cuentas. La transacción denegada se envía igualmente al `_result_queue` para que quede registrada en el log SCAN.

---

## 11. Planificación SCAN Aplicada al Logging

### Modelado del problema

Cada transacción recibe en `submit_transaction()` un `block_number` aleatorio entre 0 y 100, que simula el número de cilindro en el que se debe escribir la entrada de log. El cabezal del disco comienza en la posición 0.

### Proceso de escritura

```
resultados    = motor.get_all_results()
block_numbers = [r.block_number for r in resultados]
orden_scan    = scan_scheduling(block_numbers, head_position=0, direction='up')

para bloque en orden_scan:
    escribir en logs/transactions.log
    todas las transacciones con ese block_number
```

### Beneficio Demostrado

Con 6 transacciones en bloques `[70, 10, 90, 30, 60, 20]` y cabezal en 0 dirección `up`:

| Algoritmo | Secuencia atendida | Movimiento total del cabezal |
|---|---|---|
| FCFS | 70 → 10 → 90 → 30 → 60 → 20 | 340 unidades |
| SCAN | 10 → 20 → 30 → 60 → 70 → 90 | 90 unidades |

### Formato de Cada Entrada en el Log

```
[T000001] bloque=042 | DEPOSIT      | cuenta=ACC001 | monto=$   1000.00 | rol=CAJERO          | estado=COMPLETED
[T000003] bloque=017 | WITHDRAWAL   | cuenta=ACC002 | monto=$    200.00 | rol=CAJERO          | estado=COMPLETED
[T000009] bloque=083 | DEPOSIT      | cuenta=ACC002 | monto=$    100.00 | rol=AUDITOR         | estado=DENIED
```

---

## 12. Manejo de Interrupciones y Señales

El sistema implementa tres formas de manejo de interrupciones:

### 12.1 Interrupción por Timeout (timer interrupt simulado)

En `_worker_loop`, la llamada `_transaction_queue.get(timeout=1.0)` lanza `queue.Empty` si no hay transacciones disponibles en 1 segundo. El worker captura esta excepción y continúa el bucle. Esto simula un **timer interrupt** que periódicamente cede el control para comprobar el estado del sistema.

```python
except queue.Empty:
    continue   # volver al inicio del bucle y re-verificar condición de parada
```

### 12.2 Señal de Cierre (sentinel interrupt)

Cuando se llama a `motor.stop()`, el motor envía un valor centinela (`None`) a la cola por cada worker activo. Al recibir `None`, el worker reconoce la señal, llama a `task_done()` y rompe su bucle. Esto es análogo a una **interrupción de software** que ordena la terminación ordenada de un proceso.

```python
if transaction is None:
    self._transaction_queue.task_done()
    break
```

### 12.3 Interrupciones de Dominio (excepciones controladas)

Las violaciones de RBAC (`PermissionError`) y los rechazos del Banquero interrumpen el flujo normal de ejecución de una transacción sin afectar al sistema en su conjunto. Cada tipo de interrupción de dominio produce una transición de estado específica (`DENIED` o `FAILED`) y registra la causa en `metadata`.

---

## 13. Especificaciones Técnicas

### Lenguaje y Versión

Python 3.10 o superior.

### Librerías utilizadas

| Librería | Tipo | Uso en el proyecto |
|---|---|---|
| `threading` | Estándar | `Thread`, `Lock`, `Semaphore` |
| `queue` | Estándar | `Queue` thread-safe para el patrón productor-consumidor |
| `logging` | Estándar | Registro estructurado de eventos en `system.log` |
| `dataclasses` | Estándar | Definición de `Account` y `Transaction` con `@dataclass` |
| `enum` | Estándar | `TransactionType`, `TransactionStatus`, `Rol`, `Operacion` |
| `random` | Estándar | Asignación de `block_number` en `submit_transaction` |
| `datetime` | Estándar | Timestamps en historial de cuentas y metadata de transacciones |
| `typing` | Estándar | Anotaciones de tipo (`Optional`, `Callable`, `Dict`) |

---

## 14. Ejecución y Modos de Uso

### Ejecución

```bash
python main.py
```

### Menú principal

Al iniciar, el sistema presenta tres modos de uso:

```
==============================================================
  MENÚ PRINCIPAL
==============================================================
  1. Ejecutar demostración automática
  2. Modo interactivo manual
  3. Ambos (demo automática + interactivo)
--------------------------------------------------------------
  4. Ver estado actual de cuentas
  5. Ver resumen de transacciones procesadas
--------------------------------------------------------------
  6. Salir
==============================================================
```

### Modo demostración automática (opción 1)

Ejecuta una batería predefinida de transacciones organizada en tres oleadas. Cada oleada espera la finalización completa antes de iniciar la siguiente, y muestra los resultados entre oleadas:

- **Oleada 1:** operaciones válidas de todos los tipos (depósitos, retiros, transferencias, consultas). Incluye un retiro con fondos insuficientes para demostrar el estado `FAILED`.
- **Oleada 2:** violaciones intencionales de RBAC (AUDITOR intentando depósito y retiro, CAJERO intentando transferencia). Todas deben producir estado `DENIED`.
- **Oleada 3:** diez transacciones aleatorias concurrentes que hacen visible la competencia por los mutex de las cuentas.

### Modo interactivo manual (opción 2)

Permite crear transacciones una a una desde la consola. El resultado de cada operación se imprime de forma inmediata tras su procesamiento:

```
--------------------------------------------------------------
  MENÚ INTERACTIVO
--------------------------------------------------------------
  1. Depósito
  2. Retiro
  3. Transferencia
  4. Consulta de saldo
--------------------------------------------------------------
  5. Ver estado de todas las cuentas
  6. Ver resumen de esta sesión
  7. Volver al menú principal
--------------------------------------------------------------
```

### Modo combinado (opción 3)

Ejecuta la demostración automática completa y luego abre el modo interactivo, permitiendo hacer operaciones manuales sobre los saldos resultantes de la demo. Ideal para presentaciones.

### Flujo de Trabajo con Git

| Prefijo de commit | Uso |
|---|---|
| `feat:` | Nueva funcionalidad |
| `fix:` | Corrección de bug |
| `test:` | Agregar o modificar pruebas |
| `docs:` | Documentación |
| `refactor:` | Mejora sin cambio de comportamiento |

---

## 15. Salida Esperada del Sistema

### Demostración automática

```
==============================================================
  PROCESADOR DE TRANSACCIONES BANCARIAS
  Sistemas Operativos — UTP 2026-1
==============================================================

  Sistema inicializado correctamente.

==============================================================
  ESTADO ACTUAL DE CUENTAS
==============================================================
  [ACC001] Alice Gómez: $5000.00
  [ACC002] Bob Martínez: $3000.00
  [ACC003] Carol Herrera: $8000.00
  [ACC004] David Ríos: $1500.00
  [ACC005] Elena Vargas: $10000.00
==============================================================

--------------------------------------------------------------
  OLEADA 1 — Operaciones válidas (todos los tipos)
  Sometiendo 8 transacciones al motor...
--------------------------------------------------------------

  ✓ [T000001] Depósito $1000.00 en ACC001
     Rol    : CAJERO
     Estado : COMPLETED

  ✗ [T000004] Retiro $5000.00 de ACC004
     Rol    : CAJERO
     Estado : FAILED  (Withdrawal operation failed)

  ✓ [T000005] Transferencia $300.00 de ACC001 a ACC002
     Rol    : ADMINISTRADOR
     Estado : COMPLETED
  ...

==============================================================
  RESUMEN DE TRANSACCIONES
==============================================================
  Total procesadas : 21
  Completadas      : 16
  Fallidas         :  2  (ej: fondos insuficientes)
  Denegadas        :  3  (RBAC o Banquero)
==============================================================
```

### Modo interactivo

```
--------------------------------------------------------------
  DEPÓSITO
--------------------------------------------------------------

  Cuentas disponibles: ACC001, ACC002, ACC003, ACC004, ACC005
  ID cuenta destino: ACC002
  Roles válidos: ADMINISTRADOR, CAJERO, AUDITOR
  Rol del usuario: CAJERO
  Monto ($): 500

  ✓ [T000022] Depósito $500.00 en ACC002
     Rol    : CAJERO
     Estado : COMPLETED
```

---

## 16. Referencias

- Dijkstra, E. W. (1965). Solution of a problem in concurrent programming control. *Communications of the ACM, 8*(9), 569. https://doi.org/10.1145/365559.365617

- Dijkstra, E. W. (1968). Cooperating sequential processes. En F. Genuys (Ed.), *Programming Languages* (pp. 43–112). Academic Press.

- Ferraiolo, D. F., Sandhu, R., Gavrila, S., Kuhn, D. R., y Chandramouli, R. (2001). Proposed NIST standard for role-based access control. *ACM Transactions on Information and System Security, 4*(3), 224–274. https://doi.org/10.1145/501978.501980

- Silberschatz, A., Galvin, P. B., y Gagne, G. (2018). *Operating system concepts* (10.ª ed.). John Wiley & Sons.

- Tanenbaum, A. S., y Bos, H. (2015). *Modern operating systems* (4.ª ed.). Pearson Education.

---

<div align="center">
  <sub>Proyecto académico · Sistemas Operativos · Universidad Tecnológica de Pereira · 2026-1</sub>
</div>
