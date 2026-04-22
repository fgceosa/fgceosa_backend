import re

with open("app/models.py.bak", "r") as f:
    lines = f.readlines()

new_models = []
keep = True
for line in lines:
    if line.startswith("class TransactionStatus(str, Enum):") or line.startswith("class WalletOwnerType(str, Enum):") or line.startswith("# Transaction Status"):
        keep = False
    
    if keep:
        new_models.append(line)

new_models_str = "".join(new_models)

additions = """
# FGCEOSA MODELS

class Payment(SQLModel, table=True):
    __tablename__ = "payment"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True)
    status: str = Field(default="pending", max_length=20) # completed, pending, failed
    transaction_reference: str = Field(max_length=255, unique=True, index=True)
    amount: Decimal = Field(default=Decimal("0.00"), max_digits=10, decimal_places=2)
    description: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    
    user: "User" = Relationship(back_populates="payments")

class Announcement(SQLModel, table=True):
    __tablename__ = "announcement"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(max_length=255)
    content: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    created_by_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")

class Event(SQLModel, table=True):
    __tablename__ = "event"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(max_length=255)
    description: str
    date: datetime
    location: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")

"""

new_models_str += additions

# We need to add fields to UserBase and User
# User needs: graduation_year, profession, membership_id
# Relationships: payments
userbase_re = re.compile(r'(class UserBase\(SQLModel\):.*?)(\s+model_config = ConfigDict)', re.DOTALL)
def userbase_sub(match):
    return match.group(1) + "    graduation_year: str | None = Field(default=None, max_length=4)\n    profession: str | None = Field(default=None, max_length=255)\n    membership_id: str | None = Field(default=None, max_length=50, unique=True, index=True)\n" + match.group(2)

new_models_str = userbase_re.sub(userbase_sub, new_models_str)

user_re = re.compile(r'(class User\(UserBase, table=True\):.*?)(class UserPublic)', re.DOTALL)
def user_sub(match):
    code = match.group(1)
    code = code.replace('    user_roles: list["UserRole"] = Relationship(back_populates="user", cascade_delete=True)',
                       '    user_roles: list["UserRole"] = Relationship(back_populates="user", cascade_delete=True)\n    payments: list["Payment"] = Relationship(back_populates="user", cascade_delete=True)')
    return code + match.group(2)

new_models_str = user_re.sub(user_sub, new_models_str)

with open("app/models.py", "w") as f:
    f.write(new_models_str)
