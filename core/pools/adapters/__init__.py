"""Per-provider adapters that map platform-native Account objects to PoolItem.

Each adapter MUST be a pure mapping function:

* No HTTP, no DB writes, no Pusher calls — those belong upstream of the adapter.
* Output is a fully-validated :class:`core.pools.schema.PoolItem`; the adapter
  is responsible for computing :attr:`PoolItem.credential_hash` via
  :func:`core.pools.canonical.canonical_hash`.
* New providers follow the constitution's Provider Registry Discipline
  (Principle IV): adding a file here MUST be paired with the downstream
  ``internal/model/account.go`` constant and the factory registry entry.
"""

__all__: list[str] = ["to_pool_item_grok"]

from .grok_adapter import to_pool_item as to_pool_item_grok
