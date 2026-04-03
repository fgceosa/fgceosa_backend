
from enum import Enum

class WalletOwnerType(str, Enum):
    organization = "ORGANIZATION"
    user = "USER"

    def __str__(self) -> str:
        return self.value

print(f"str(WalletOwnerType.organization): '{str(WalletOwnerType.organization)}'")
