"""Interface das estratégias de ordenação (ver docs/CONTRACT.md, seção 5)."""
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from mps.models import Order


class Strategy(ABC):
    """Fila de prioridade de UMA classe de doca.

    O simulador cria uma instância por classe. `now` é o relógio da
    simulação em minutos. `ops` conta comparações/trocas (custo do algoritmo).
    """

    name = "base"

    def __init__(self, **params):
        self.params = params
        self.ops = 0

    @abstractmethod
    def key(self, order: Order, now: float) -> Tuple:
        """Chave de ordenação (menor = mais prioritário), comparável entre filas
        da mesma estratégia. Estratégias de 'maior primeiro' devem negar."""

    @abstractmethod
    def push(self, order: Order, now: float) -> None: ...

    @abstractmethod
    def pop(self, now: float) -> Optional[Order]:
        """Remove e devolve o pedido mais prioritário (None se vazia)."""

    @abstractmethod
    def peek(self, now: float, k: int = 1) -> List[Order]:
        """Os k próximos pedidos, sem remover (não deve copiar o heap inteiro)."""

    @abstractmethod
    def update(self, order_id: str, now: float,
               new_score: Optional[float] = None,
               new_deadline_min: Optional[float] = None) -> bool:
        """Atualiza score/prazo de um pedido na fila. False se não está na fila."""

    @abstractmethod
    def cancel(self, order_id: str) -> bool:
        """Remove um pedido da fila. False se não está na fila."""

    @abstractmethod
    def __len__(self) -> int: ...

    @abstractmethod
    def __contains__(self, order_id: str) -> bool: ...
