"""
Módulo 1: Gestión Central de Cuentas
Implementa cuentas bancarias seguras para hilos con sincronización mediante mutex.
"""

import threading
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Account:
    """
    Representa una cuenta bancaria con operaciones seguras para hilos.
    
    Cada cuenta mantiene su propio bloqueo para asegurar la atomicidad de operaciones
    como depósito, retiro y consultas de saldo en hilos concurrentes.
    
    Atributos:
        account_id (str): Identificador único de la cuenta
        holder_name (str): Nombre del titular de la cuenta
        balance (float): Saldo actual de la cuenta
        _lock (threading.Lock): Mutex para sincronizar el acceso al saldo
        _transaction_history (list): Registro de todas las transacciones
    """
    
    account_id: str
    holder_name: str
    initial_balance: float = 0.0
    
    def __post_init__(self):
        """Inicializa la cuenta con primitivas de seguridad para hilos."""
        self.balance = self.initial_balance
        self._lock = threading.Lock()
        self._transaction_history = []
        self._created_at = datetime.now()
    
    def deposit(self, amount: float, description: str = "Deposit") -> bool:
        """
        Deposita fondos en la cuenta (seguro para hilos).
        
        Adquiere el mutex antes de modificar el saldo, asegurando atomicidad.
        Múltiples hilos pueden invocar este método concurrentemente sin condiciones de carrera.
        
        Argumentos:
            amount (float): Cantidad a depositar (debe ser positiva)
            description (str): Descripción opcional del depósito
            
        Retorna:
            bool: Verdadero si es exitoso, Falso si la cantidad es inválida
            
        Levanta:
            ValueError: Si la cantidad es negativa o cero
        """
        if amount <= 0:
            raise ValueError(f"La cantidad de depósito debe ser positiva, se recibió {amount}")
        
        with self._lock:
            previous_balance = self.balance
            self.balance += amount
            self._transaction_history.append({
                'type': 'DEPOSIT',
                'amount': amount,
                'previous_balance': previous_balance,
                'new_balance': self.balance,
                'description': description,
                'timestamp': datetime.now().isoformat(),
                'thread_id': threading.current_thread().ident
            })
            return True
    
    def withdraw(self, amount: float, description: str = "Withdrawal") -> bool:
        """
        Retira fondos de la cuenta (seguro para hilos).
        
        Adquiere el mutex antes de modificar el saldo. Previene sobregiros
        verificando el saldo antes de retirar.
        
        Argumentos:
            amount (float): Cantidad a retirar (debe ser positiva)
            description (str): Descripción opcional del retiro
            
        Retorna:
            bool: Verdadero si es exitoso, Falso si fondos insuficientes o cantidad inválida
            
        Levanta:
            ValueError: Si la cantidad es negativa o cero
        """
        if amount <= 0:
            raise ValueError(f"La cantidad de retiro debe ser positiva, se recibió {amount}")
        
        with self._lock:
            if self.balance < amount:
                return False
            
            previous_balance = self.balance
            self.balance -= amount
            self._transaction_history.append({
                'type': 'WITHDRAWAL',
                'amount': amount,
                'previous_balance': previous_balance,
                'new_balance': self.balance,
                'description': description,
                'timestamp': datetime.now().isoformat(),
                'thread_id': threading.current_thread().ident
            })
            return True
    
    def get_balance(self) -> float:
        """
        Obtiene el saldo actual de la cuenta (seguro para hilos).
        
        Adquiere el mutex para asegurar una instantánea consistente del saldo.
        
        Retorna:
            float: Saldo actual
        """
        with self._lock:
            return self.balance
    
        
    def transfer_internal(self, amount: float, source_id: str, 
                         description: str = "Transfer") -> bool:
        """
        Método interno para ejecutar el cambio de saldo durante la transferencia.
        
        Debe ser invocado mientras el bloqueo de la cuenta ya está retenido por el invocador.
        Utilizado por TransactionEngine después de adquirir todos los bloqueos necesarios.
        
        Argumentos:
            amount (float): Cantidad a debitar o acreditar
            source_id (str): Identificador de la cuenta origen (para transferencia saliente)
            description (str): Descripción de la transferencia
            
        Retorna:
            bool: Verdadero si es exitoso
        """
        self.balance += amount  # amount es negativo para saliente, positivo para entrante
        self._transaction_history.append({
            'type': 'TRANSFER',
            'amount': abs(amount),
            'direction': 'OUTGOING' if amount < 0 else 'INCOMING',
            'counterpart': source_id,
            'new_balance': self.balance,
            'description': description,
            'timestamp': datetime.now().isoformat(),
            'thread_id': threading.current_thread().ident
        })
        return True
    
    def get_transaction_history(self) -> list:
        """
        Recupera el historial completo de transacciones (seguro para hilos).
        
        Retorna:
            list: Copia del historial de transacciones para evitar mutaciones externas
        """
        with self._lock:
            return self._transaction_history.copy()
    
    def acquire_lock(self):
        """Adquiere el bloqueo de la cuenta para sincronización externa."""
        self._lock.acquire()

    def release_lock(self):
        """Libera el bloqueo de la cuenta para sincronización externa."""
        self._lock.release()

    def __repr__(self) -> str:
        """Representación en cadena de la cuenta."""
        return (f"Account(id={self.account_id}, holder={self.holder_name}, "
                f"balance=${self.balance:.2f})")
    
    def __str__(self) -> str:
        """Representación legible en cadena."""
        return f"[{self.account_id}] {self.holder_name}: ${self.balance:.2f}"
