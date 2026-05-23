"""
Módulo 1: Motor de Transacciones
Implementa un patrón productor-consumidor para el procesamiento concurrente de transacciones
con gestión de colas seguras para hilos y control de concurrencia basado en semáforos.
"""

import logging
import threading
import queue
import random
from typing import Dict, Optional, Callable, TYPE_CHECKING
from dataclasses import dataclass
from .transaction import (Transaction, TransactionType)

if TYPE_CHECKING:
    from .account import Account


class TransactionEngine:
    """
    Motor productor-consumidor para el procesamiento de transacciones concurrentes.
    
    Gestiona una cola de transacciones segura para hilos con control de concurrencia
    basado en semáforos. Coordina entre productores de transacciones (hilos de aplicación) y
    consumidores (hilos trabajadores que ejecutan transacciones contra cuentas).
    
    Atributos:
        _transaction_queue (queue.Queue): Búfer seguro para hilos de transacciones pendientes
        _result_queue (queue.Queue): Búfer seguro para hilos de transacciones completadas
        _accounts (dict): Diccionario que mapea IDs de cuentas a objetos Account
        _max_concurrent (int): Máximo de transacciones concurrentes vía semáforo
        _semaphore (threading.Semaphore): Limita la ejecución de transacciones concurrentes
        _workers (list): Lista de hilos trabajadores
        _running (bool): Bandera para controlar la operación del motor
        _lock (threading.Lock): Protege el estado del motor
        _transaction_counter (int): Contador auto-incremental para IDs de transacciones
        _authorization_hook (Callable): Callback opcional de autorización RBAC
        _bankers_guard (Callable): Callback opcional de prevención de interbloqueo
    """
    
    def __init__(self, accounts: Dict[str, 'Account'], 
                 max_concurrent: int = 5,
                 num_workers: int = 3):
        """
        Inicializa el motor de transacciones.
        
        Args:
            accounts (dict): Diccionario de objetos Account por account_id
            max_concurrent (int): Máximo de transacciones concurrentes (por defecto: 5)
            num_workers (int): Número de hilos trabajadores (por defecto: 3)
        """
        self._transaction_queue = queue.Queue()
        self._result_queue = queue.Queue()
        self._accounts = accounts
        self._max_concurrent = max_concurrent
        self._semaphore = threading.Semaphore(max_concurrent)
        self._num_workers = num_workers
        self._workers = []
        self._running = False
        self._lock = threading.Lock()
        self._transaction_counter = 0
        self._authorization_hook: Optional[Callable] = None
        self._bankers_guard: Optional[Callable] = None
    
    def set_authorization_hook(self, hook: Callable) -> None:
        """
        Establece el callback de autorización RBAC.
        
        Args:
            hook (callable): Función que valida la autorización de transacción
                            Firma: hook(transaction: Transaction) -> bool
        """
        self._authorization_hook = hook
    
    def set_bankers_guard(self, guard: Callable) -> None:
        """
        Establece el callback de prevención de interbloqueo (Algoritmo del Banquero).
        
        Args:
            guard (callable): Función que valida el estado libre de interbloqueo
                             Firma: guard(transaction: Transaction) -> bool
        """
        self._bankers_guard = guard
    
    def start(self) -> None:
        """Inicia el motor de transacciones con hilos trabajadores."""
        with self._lock:
            if self._running:
                raise RuntimeError("Engine is already running")
            self._running = True
        
        # Inicia hilos trabajadores
        for i in range(len(self._workers), self._num_workers):  # Por defecto 3 trabajadores
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"TrabajadorTransacción-{i+1}",
                daemon=True
            )
            worker.start()
            self._workers.append(worker)
    
    def stop(self, timeout: float = 5.0) -> None:
        """
        Detiene el motor de transacciones de manera elegante.
        
        Args:
            timeout (float): Segundos para esperar a que los trabajadores terminen
        """
        with self._lock:
            self._running = False
        
        # Señala a los trabajadores enviando valores centinela
        for _ in self._workers:
            self._transaction_queue.put(None)
        
        # Espera a que los trabajadores terminen
        for worker in self._workers:
            worker.join(timeout=timeout)
        
        self._workers.clear()
    
    def submit_transaction(self, transaction: Transaction) -> str:
        """
        Envía una transacción al motor.
        
        Args:
            transaction (Transaction): La transacción a procesar
            
        Returns:
            str: El ID de transacción asignado
            
        Raises:
            RuntimeError: Si el motor no está ejecutándose
        """
        if not self._running:
            raise RuntimeError("Engine is not running")
        
        with self._lock:
            self._transaction_counter += 1
            transaction.transaction_id = f"T{self._transaction_counter:06d}"
        
        # Asigna número de bloque ficticio para planificación SCAN
        transaction.block_number = random.randint(0, 100)
        
        self._transaction_queue.put(transaction)
        return transaction.transaction_id
    
    def _worker_loop(self) -> None:
        """Bucle principal del hilo trabajador (consumidor)."""
        while True:
            try:
                # Espera una transacción con tiempo de espera para permitir apagado elegante
                transaction = self._transaction_queue.get(timeout=1.0)
                
                # Valor centinela indica apagado
                if transaction is None:
                    self._transaction_queue.task_done()
                    break
                
                # Marca como autorizada
                if self._authorization_hook:
                    if not self._authorization_hook(transaction):
                        transaction.mark_denied("Authorization denied")
                        self._result_queue.put(transaction)          # enviar a resultados
                        self._transaction_queue.task_done()
                        continue                                      # ir a la siguiente tarea

                transaction.mark_authorized()
                
                # Adquiere ranura de semáforo antes del procesamiento
                self._semaphore.acquire()
                try:
                    # Marca como procesando
                    transaction.mark_processing()
                    result = self._process_transaction(transaction)
                    self._result_queue.put(result)
                finally:
                    self._semaphore.release()
                
                self._transaction_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                logging.exception(f"Error del trabajador: {e}")
    
    def _process_transaction(self, transaction: Transaction) -> Transaction:
        """
        Ejecuta una transacción contra la(s) cuenta(s).
        
        Aplica verificaciones de autorización y prevención de interbloqueo antes de la ejecución.
        
        Args:
            transaction (Transaction): La transacción a ejecutar
            
        Returns:
            Transaction: Transacción actualizada con estado y resultado
        """
        try:            
            # Valida que las cuentas existan
            if transaction.source_account_id not in self._accounts:
                transaction.mark_failed("Source account not found")
                return transaction
            
            source_account = self._accounts[transaction.source_account_id]
            
            # Procesa la transacción por tipo
            if transaction.transaction_type == TransactionType.DEPOSIT:
                if source_account.deposit(transaction.amount, 
                                         f"Depósito por {transaction.user_id}"):
                    transaction.mark_completed()
                else:
                    transaction.mark_failed("Deposit operation failed")
            
            elif transaction.transaction_type == TransactionType.WITHDRAWAL:
                if source_account.withdraw(transaction.amount,
                                          f"Retiro por {transaction.user_id}"):
                    transaction.mark_completed()
                else:
                    transaction.mark_failed("Withdrawal operation failed")
            
            elif transaction.transaction_type == TransactionType.TRANSFER:
                if not transaction.destination_account_id:
                    transaction.mark_failed("Destination account not specified")
                    return transaction
                
                if transaction.destination_account_id not in self._accounts:
                    transaction.mark_failed("Destination account not found")
                    return transaction
                
                dest_account = self._accounts[transaction.destination_account_id]
                
                # Aplica el Algoritmo del Banquero si el guard está establecido
                if self._bankers_guard:
                    if not self._bankers_guard(transaction):
                        transaction.mark_denied("Banker's Algorithm check failed")
                        return transaction
                
                # Ejecuta transferencia con bloqueo ordenado para prevenir interbloqueo
                if self._execute_transfer(source_account, dest_account, 
                                        transaction.amount,
                                        transaction.source_account_id,
                                        transaction.destination_account_id):
                    transaction.mark_completed()
                else:
                    transaction.mark_failed("Transfer operation failed")
            
            elif transaction.transaction_type == TransactionType.QUERY:
                # Las operaciones de consulta no modifican el estado, siempre tienen éxito
                transaction.metadata['balance'] = source_account.get_balance()
                transaction.mark_completed()
            
            else:
                transaction.mark_failed("Unknown transaction type")
            
            return transaction
            
        except ValueError as e:
            transaction.mark_failed(f"Validation error: {str(e)}")
            return transaction
        except Exception as e:
            logging.exception(f"Error en transacción {transaction.transaction_id}: {e}")
            transaction.mark_failed(f"Excepción: {str(e)}")
            return transaction
    
    def _execute_transfer(self, source_account: 'Account', 
                         dest_account: 'Account',
                         amount: float,
                         source_id: str,
                         dest_id: str) -> bool:
        """
        Ejecuta una transferencia entre dos cuentas con bloqueo ordenado.
        
        Gestiona la orquestación de sincronización para operaciones de transferencia.
        Adquiere bloqueos en orden de ID de cuenta para prevenir interbloqueo de espera circular.
        Realiza: verificar saldo -> debitar fuente -> acreditar destino
        
        Args:
            source_account (Account): Objeto de cuenta fuente
            dest_account (Account): Objeto de cuenta destino
            amount (float): Cantidad a transferir
            source_id (str): ID de cuenta fuente
            dest_id (str): ID de cuenta destino
            
        Returns:
            bool: True si la transferencia tuvo éxito, False en caso contrario
        """
        if source_id < dest_id:
            first_account, second_account = source_account, dest_account
        else:
            first_account, second_account = dest_account, source_account
        
        first_account.acquire_lock()
        try:
            second_account.acquire_lock()
            try:
                # Accede al saldo directamente — los bloqueos ya están retenidos, NO llames a get_balance()
                if source_account.balance < amount:
                    return False
                
                # Usa la firma correcta de transfer_internal: (amount, source_id, description)
                source_account.transfer_internal(-amount, dest_id, f"Transferencia a {dest_id}")
                dest_account.transfer_internal(amount, source_id, f"Transferencia desde {source_id}")
                
                return True
            finally:
                second_account.release_lock()
        finally:
            first_account.release_lock()
    
    def get_all_results(self) -> list:
        """
        Recupera todas las transacciones completadas de la cola de resultados.
        
        Returns:
            list: Todas las transacciones completadas disponibles
        """
        results = []
        while True:
            try:
                result = self._result_queue.get_nowait()
                results.append(result)
            except queue.Empty:
                break
        return results
    
    def wait_completion(self):
        """
        Espera a que todas las transacciones pendientes se completen.
                   
        Returns:
            bool: True si todas se completaron, False si tiempo de espera
        """
        self._transaction_queue.join()
        return True