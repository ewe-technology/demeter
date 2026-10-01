"""First day of minute data per pool, so an EMA warm-up never asks for days before the pool has data."""
from datetime import date

# lower-cased pool address -> first UTC day with minute data
POOL_DATA_START = {
    "0x4585fe77225b41b697c938b018e2ac67ac5a20c0": date(2021, 5, 13),  # ethereum wbtc/weth 0.05% (2021-05-12 missing)
    "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640": date(2021, 5, 5),   # ethereum usdc/weth 0.05%
    "0x7aea2e8a3843516afa07293a10ac8e49906dabd1": date(2024, 9, 13),  # base weth/cbbtc 0.05%
    "0xd0b53d9277642d899df5c87a3966a349a798f224": date(2023, 9, 6),   # base weth/usdc 0.05%
}


def data_floor(*addresses: str) -> date:
    """Earliest day every given pool has data: the latest of their start days."""
    missing = [a for a in addresses if a.lower() not in POOL_DATA_START]
    if missing:
        raise KeyError(f"no data start day for pool(s) {missing}, add them to pool_data.POOL_DATA_START")
    return max(POOL_DATA_START[a.lower()] for a in addresses)
