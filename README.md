# Banking Transaction Processor

A multithreaded banking simulation built in Python that demonstrates core operating systems concepts: mutex synchronization, the producer-consumer pattern, SCAN disk scheduling, role-based access control, and deadlock prevention via Dijkstra's Banker's Algorithm.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Threading](https://img.shields.io/badge/Concurrency-threading-informational)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-Complete-brightgreen)

---

## Overview

This project simulates a concurrent banking environment where multiple threads compete for shared account resources. Each transaction goes through a full lifecycle: it is queued by a producer, validated by an RBAC security layer, evaluated by a deadlock-prevention guard, executed atomically on the account objects, and finally written to a structured log file using SCAN-ordered I/O scheduling.

The system exposes two execution modes: an **automated demo** that runs three waves of predefined transactions to showcase every component, and an **interactive mode** for manual transaction input — useful for demonstrations and debugging.

---

## Key Concepts Implemented

| Concept | Implementation |
|---|---|
| Mutual exclusion | Per-account `threading.Lock`; each `Account` instance owns its own mutex |
| Bounded concurrency | `threading.Semaphore` limits simultaneous transaction execution |
| Producer-consumer pattern | `queue.Queue` decouples transaction submission from worker execution |
| SCAN disk scheduling | Log entries sorted by fictional block number before being written to disk |
| Role-based access control | Three-role RBAC matrix intercepts every operation before execution |
| Deadlock prevention | Dijkstra's Banker's Algorithm evaluates safety before multi-account locks |
| Ordered lock acquisition | Transfers always acquire account locks in lexicographic order, eliminating circular wait |

---

## Architecture

The system is organized in four modules integrated through a central orchestrator:

```
main.py  (orchestrator)
│
├── core/
│   ├── account.py              Per-account mutex, atomic deposit/withdraw/transfer
│   ├── transaction.py          Transaction dataclass, TransactionBuilder, status lifecycle
│   └── transaction_engine.py   Producer-consumer engine, worker threads, semaphore
│
├── scheduling/
│   └── scan_scheduler.py       SCAN algorithm over fictional block numbers
│
├── security/
│   ├── roles.py                Role and Operation enums
│   └── rbac_policy.py          Access control matrix, permission verification
│
└── concurrency/
    └── bankers_guard.py        Banker's Algorithm: safety check + rollback
```

### Transaction Lifecycle

Every transaction moves through a defined set of states before completion:

```
PENDING
   │
   ├── RBAC denies ──────────────────────────────► DENIED
   │
   ▼
AUTHORIZED
   │
   ▼
PROCESSING
   │
   ├── Banker's Algorithm denies ────────────────► DENIED
   ├── Insufficient funds / account not found ───► FAILED
   │
   ▼
COMPLETED
```

### Concurrency Model

```
Producers (main.py)
        │
        │  submit_transaction(txn)
        ▼
  ┌─────────────┐
  │ queue.Queue │  ← thread-safe buffer
  └──────┬──────┘
         │
    ┌────┴────┐
    │ Workers │  ← N daemon threads
    └────┬────┘
         │
         ├─ 1. RBAC check
         ├─ 2. semaphore.acquire()
         ├─ 3. Banker's check (transfers only)
         ├─ 4. Execute on Account objects
         ├─ 5. semaphore.release()
         └─ 6. Push to result queue
                  │
                  ▼
          ScanScheduler ──► logs/transactions.log
```

---

## SCAN Scheduling

Log entries are not written in arrival order. Each transaction carries a fictional `block_number` (0–100). After processing, the scheduler applies the SCAN algorithm to determine the optimal write order, minimizing total head movement — the same way a real disk controller handles I/O queues.

```
# Example: head at 50, direction up, requests [10, 30, 70, 90, 20, 60]

SCAN order: [60, 70, 90, 30, 20, 10]
             ↑── sweeps up ──↑ ↑─ sweeps down ─↑
```

---

## RBAC Permission Matrix

```
Operation       ADMIN    CAJERO    AUDITOR
─────────────────────────────────────────
DEPOSIT           ✔        ✔         ✘
WITHDRAWAL        ✔        ✔         ✘
TRANSFER          ✔        ✘         ✘
QUERY             ✔        ✔         ✔
```

Unauthorized operations are intercepted before execution and recorded as `DENIED` in the transaction log.

---

## Deadlock Prevention

Transfers require locking two accounts simultaneously, which creates deadlock risk when two threads transfer between the same accounts in opposite directions. The system handles this at two levels:

**Ordered lock acquisition** — account locks are always acquired in lexicographic order by `account_id`, eliminating circular wait without extra overhead.

**Banker's Algorithm** — before any transfer proceeds, `GuardiaBanquero` simulates the resource allocation and verifies the resulting state is safe. If not, the operation is deferred and marked `DENIED`.

```python
# Safe ordering in _execute_transfer()
first, second = sorted([source, target], key=lambda a: a.account_id)
with first._lock:
    with second._lock:
        source.transfer_internal(target, amount)
```

---

## Getting Started

**Requirements:** Python 3.10+

```bash
# Clone the repository
git clone https://github.com/your-username/banco-transacciones-so.git
cd banco-transacciones-so

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

---

## Usage

On startup, the system presents three modes:

```
  1. Automated demo      — three transaction waves covering all scenarios
  2. Interactive mode    — manual transaction input from the console
  3. Combined            — demo followed by interactive session
```

**Automated demo output (excerpt):**

```
  ✓ [T000001] Deposit $1,000.00 → ACC001       CAJERO       COMPLETED
  ✓ [T000005] Transfer $300.00  ACC001→ACC002  ADMIN        COMPLETED
  ✗ [T000004] Withdrawal $5,000 from ACC004    CAJERO       FAILED     (insufficient funds)
  ✗ [T000009] Deposit $100.00 → ACC002         AUDITOR      DENIED     (RBAC: no write permission)
  ✗ [T000010] Transfer $500.00 ACC003→ACC005   CAJERO       DENIED     (RBAC: no transfer permission)
```

**Generated log file (`logs/transactions.log`) — written in SCAN order:**

```
[T000001] block=005 | DEPOSIT     | account=ACC001 | amount=$  1000.00 | role=CAJERO       | status=COMPLETED
[T000002] block=009 | DEPOSIT     | account=ACC003 | amount=$   500.00 | role=ADMIN        | status=COMPLETED
[T000007] block=020 | QUERY       | account=ACC003 | amount=$     0.00 | role=AUDITOR      | status=COMPLETED
[T000005] block=087 | TRANSFER    | account=ACC001 | amount=$   300.00 | role=ADMIN        | status=COMPLETED
[T000004] block=090 | WITHDRAWAL  | account=ACC004 | amount=$  5000.00 | role=CAJERO       | status=FAILED
```

---

## Project Structure

```
banco-transacciones-so/
│
├── main.py
├── requirements.txt
├── README.md
│
├── core/
│   ├── __init__.py
│   ├── account.py
│   ├── transaction.py
│   └── transaction_engine.py
│
├── scheduling/
│   ├── __init__.py
│   └── scan_scheduler.py
│
├── security/
│   ├── __init__.py
│   ├── roles.py
│   └── rbac_policy.py
│
├── concurrency/
│   ├── __init__.py
│   └── bankers_guard.py
│
├── logs/
│   ├── .gitkeep
│   └── transactions.log        ← generated at runtime
│
└── tests/
    ├── test_account.py
    ├── test_scan.py
    └── test_rbac.py
```

---

## Running Tests

```bash
pytest tests/
pytest tests/ -v                # verbose output
```

---

## Design Decisions

**Per-instance locks over a global lock.** Each `Account` holds its own `threading.Lock` rather than sharing one system-wide mutex. This allows operations on different accounts to run in parallel, with serialization only occurring when two threads target the same account.

**`transfer_internal` holds no lock.** The method that applies the debit/credit delta deliberately does not acquire `self._lock`. The engine acquires both account locks externally before calling it. This avoids re-acquisition on a non-reentrant `Lock`, which would deadlock the calling thread against itself.

**`queue.Queue` over a manual buffer.** Python's `Queue` bundles a list, a mutex, and semaphore-based blocking into one thread-safe structure. Using it for both the transaction queue and the result queue removes the need to manually manage those primitives for the buffer itself.

**Block numbers are assigned at submission time.** The `TransactionEngine` assigns a random `block_number` when a transaction is enqueued, not when it is created. This decouples the SCAN scheduling concern from the domain model and ensures the scheduler always has a stable set of numbers to sort.

---

## References

- Dijkstra, E. W. (1965). Solution of a problem in concurrent programming control. *Communications of the ACM, 8*(9), 569.
- Dijkstra, E. W. (1968). Cooperating sequential processes. In F. Genuys (Ed.), *Programming Languages* (pp. 43–112). Academic Press.
- Ferraiolo, D. F., Sandhu, R., Gavrila, S., Kuhn, D. R., & Chandramouli, R. (2001). Proposed NIST standard for role-based access control. *ACM TISSEC, 4*(3), 224–274.
- Silberschatz, A., Galvin, P. B., & Gagne, G. (2018). *Operating System Concepts* (10th ed.). Wiley.
- Tanenbaum, A. S., & Bos, H. (2015). *Modern Operating Systems* (4th ed.). Pearson.

---

## License

MIT License. See `LICENSE` for details.