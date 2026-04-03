import uuid
import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional, Any

from sqlalchemy import func
from sqlmodel import Session, select
from fastapi import HTTPException, status

from app.models import (
    Wallet, 
    WalletTransaction, 
    WalletOwnerType, 
    WalletTransactionType,
    User,
    Organization,
    AuditLog
)

logger = logging.getLogger(__name__)

class WalletService:
    @staticmethod
    def get_or_create_wallet(
        session: Session, 
        owner_id: uuid.UUID, 
        owner_type: WalletOwnerType
    ) -> Wallet:
        """
        Get an existing wallet or create a new one for an owner.
        """
        statement = select(Wallet).where(
            Wallet.owner_id == owner_id,
            Wallet.owner_type == owner_type
        )
        wallet = session.exec(statement).first()
        
        if not wallet:
            # Create wallet
            wallet = Wallet(
                owner_id=owner_id,
                owner_type=owner_type,
                currency="CREDITS"
            )
            session.add(wallet)
            session.flush() # Flush to get ID
            
            # Seed ledger from legacy credits if present
            # Critical for users who had credits before the Wallet system migration
            from app.models import User, Organization
            legacy_balance = Decimal("0.0000")
            
            if owner_type == WalletOwnerType.USER:
                owner = session.get(User, owner_id)
                if owner and getattr(owner, "credits", 0):
                    legacy_balance = Decimal(str(owner.credits))
            elif owner_type == WalletOwnerType.ORGANIZATION:
                owner = session.get(Organization, owner_id)
                if owner and getattr(owner, "credits_balance", 0):
                    legacy_balance = Decimal(str(owner.credits_balance))
            
            if legacy_balance > 0:
                logger.info(f"Seeding new wallet {wallet.id} with legacy balance: {legacy_balance}")
                init_tx = WalletTransaction(
                    wallet_id=wallet.id,
                    transaction_type=WalletTransactionType.ADJUSTMENT,
                    amount=legacy_balance,
                    credit=legacy_balance,
                    description="Balance migration from legacy system",
                    source="migration",
                    created_at=datetime.now(timezone.utc)
                )
                session.add(init_tx)
                session.flush()

            # Log wallet creation
            WalletService._log_audit(
                session=session,
                action="WALLET_CREATED",
                target_id=str(wallet.id),
                target_type="Wallet",
                meta_data={
                    "owner_id": str(owner_id), 
                    "owner_type": str(owner_type),
                    "seeded_balance": float(legacy_balance)
                }
            )
            
        return wallet

    @staticmethod
    def get_balance(session: Session, wallet_id: uuid.UUID) -> Decimal:
        """
        Calculate balance from the ledger: SUM(credit) - SUM(debit)
        The source of truth for all balances.
        """
        statement = select(
            func.sum(WalletTransaction.credit) - func.sum(WalletTransaction.debit)
        ).where(WalletTransaction.wallet_id == wallet_id)
        
        balance = session.exec(statement).one()
        return Decimal(str(balance)) if balance is not None else Decimal("0.0000")

    @staticmethod
    def add_transaction(
        *,
        session: Session,
        wallet_id: uuid.UUID,
        transaction_type: WalletTransactionType,
        amount: Decimal, # Net amount (credit - debit)
        description: str,
        credit: Decimal = Decimal("0.0000"),
        debit: Decimal = Decimal("0.0000"),
        transfer_in: Decimal = Decimal("0.0000"),
        transfer_out: Decimal = Decimal("0.0000"),
        source: Optional[str] = None,
        reference_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        created_by: Optional[uuid.UUID] = None,
        commit: bool = False
    ) -> WalletTransaction:
        """
        Adds a single entry to the ledger. 
        Updates the cached balance on the owner entity.
        """
        # Lock wallet for the duration of transaction to prevent race conditions on balance checks
        statement = select(Wallet).where(Wallet.id == wallet_id).with_for_update()
        wallet = session.exec(statement).first()
        
        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found")

        # Check for idempotency if key provided
        if idempotency_key:
            existing_stmt = select(WalletTransaction).where(WalletTransaction.idempotency_key == idempotency_key)
            existing = session.exec(existing_stmt).first()
            if existing:
                return existing

        # Create ledger entry
        transaction = WalletTransaction(
            wallet_id=wallet_id,
            transaction_type=transaction_type,
            credit=credit,
            debit=debit,
            transfer_in=transfer_in,
            transfer_out=transfer_out,
            amount=amount,
            description=description,
            source=source,
            reference_id=reference_id,
            idempotency_key=idempotency_key,
            created_by=created_by,
            created_at=datetime.now(timezone.utc)
        )
        
        # 2. Add the transaction
        session.add(transaction)
        session.flush()

        # 3. Sync cached balance on owner model (balance is derived from ledger sums, no need to store balance_after)

        # 4. Log audit for non-usage transactions (usage is too frequent)
        if transaction_type != WalletTransactionType.USAGE:
            WalletService._log_audit(
                session=session,
                action=f"TX_{transaction_type.value}",
                target_id=str(transaction.id),
                target_type="WalletTransaction",
                actor_id=created_by,
                meta_data={
                    "wallet_id": str(wallet_id),
                    "amount": float(amount),
                    "description": description
                }
            )
        
        # 5. Sync cached balance on owner model
        WalletService._sync_cached_balance(session, wallet)
        
        # 6. Commit if requested
        if commit:
            session.commit()
            session.refresh(transaction)
            
        return transaction

    @staticmethod
    def top_up_org(
        session: Session,
        org_id: uuid.UUID,
        amount: Decimal,
        admin_id: uuid.UUID,
        reference_id: str,
        idempotency_key: Optional[str] = None,
        commit: bool = False
    ) -> WalletTransaction:
        """
        Processes a top-up for an organization wallet.
        """
        wallet = WalletService.get_or_create_wallet(session, org_id, WalletOwnerType.ORGANIZATION)
        
        transaction = WalletService.add_transaction(
            session=session,
            wallet_id=wallet.id,
            transaction_type=WalletTransactionType.TOP_UP,
            amount=amount,
            credit=amount,
            description=f"Organization top-up via {reference_id}",
            reference_id=reference_id,
            idempotency_key=idempotency_key,
            created_by=admin_id,
            source="payment_provider",
            commit=False # We handle commit locally below
        )
        
        WalletService._log_audit(
            session=session,
            action="ORG_TOP_UP",
            target_id=str(wallet.id),
            target_type="Wallet",
            actor_id=admin_id,
            meta_data={"amount": str(amount), "org_id": str(org_id)}
        )

        if commit:
            session.commit()
            session.refresh(transaction)
        
        return transaction

    @staticmethod
    def share_credits(
        session: Session,
        org_id: uuid.UUID,
        member_id: uuid.UUID,
        amount: Decimal,
        admin_id: uuid.UUID,
        description: Optional[str] = None,
        commit: bool = False
    ) -> tuple[WalletTransaction, WalletTransaction]:
        """
        Atomic transfer from Organization wallet to Member wallet.
        """
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")

        org_wallet = WalletService.get_or_create_wallet(session, org_id, WalletOwnerType.ORGANIZATION)
        member_wallet = WalletService.get_or_create_wallet(session, member_id, WalletOwnerType.USER)
        
        # Lock both wallets to prevent deadlocks (always lock in same order, e.g. by ID)
        wallets_to_lock = sorted([org_wallet.id, member_wallet.id])
        for wid in wallets_to_lock:
            stmt = select(Wallet).where(Wallet.id == wid).with_for_update()
            session.exec(stmt).first()

        # Validate sufficient balance
        org_balance = WalletService.get_balance(session, org_wallet.id)
        if org_balance < amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Insufficient organization balance. Available: {org_balance}"
            )

        # 1. Debit Org
        debit_desc = description or f"Credit sharing: Distributed {amount} to member {member_id}"
        org_tx = WalletService.add_transaction(
            session=session,
            wallet_id=org_wallet.id,
            transaction_type=WalletTransactionType.CREDIT_SHARE,
            amount=-amount,
            debit=amount,
            transfer_out=amount,
            description=debit_desc,
            created_by=admin_id,
            source="credit_sharing"
        )
        
        # 2. Credit Member
        credit_desc = f"Received {amount} credits from organization"
        member_tx = WalletService.add_transaction(
            session=session,
            wallet_id=member_wallet.id,
            transaction_type=WalletTransactionType.CREDIT_SHARE,
            amount=amount,
            credit=amount,
            transfer_in=amount,
            description=credit_desc,
            created_by=admin_id,
            source="credit_sharing"
        )
        
        WalletService._log_audit(
            session=session,
            action="CREDIT_SHARED",
            target_id=str(member_id),
            target_type="User",
            actor_id=admin_id,
            meta_data={
                "amount": str(amount), 
                "org_id": str(org_id), 
                "recipient_id": str(member_id)
            }
        )
        
        if commit:
            session.commit()
            session.refresh(org_tx)
            session.refresh(member_tx)

        return org_tx, member_tx

    @staticmethod
    def transfer_p2p(
        session: Session,
        sender_id: uuid.UUID,
        recipient_id: uuid.UUID,
        amount: Decimal,
        description: str,
        commit: bool = False
    ) -> tuple[WalletTransaction, WalletTransaction]:
        """
        Atomic transfer between two user wallets.
        """
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")
            
        sender_wallet = WalletService.get_or_create_wallet(session, sender_id, WalletOwnerType.USER)
        recipient_wallet = WalletService.get_or_create_wallet(session, recipient_id, WalletOwnerType.USER)
        
        # Lock both wallets to prevent deadlocks (always lock in same order, e.g. by ID)
        wallets_to_lock = sorted([sender_wallet.id, recipient_wallet.id], key=lambda x: str(x))
        for wid in wallets_to_lock:
            stmt = select(Wallet).where(Wallet.id == wid).with_for_update()
            session.exec(stmt).first()
            
        sender_balance = WalletService.get_balance(session, sender_wallet.id)
        if sender_balance < amount:
            raise HTTPException(status_code=400, detail="Insufficient credits")
            
        sender_tx = WalletService.add_transaction(
            session=session,
            wallet_id=sender_wallet.id,
            transaction_type=WalletTransactionType.ADJUSTMENT,
            amount=-amount,
            debit=amount,
            transfer_out=amount,
            description=description,
            source="p2p_transfer",
            created_by=sender_id
        )
        
        recipient_tx = WalletService.add_transaction(
            session=session,
            wallet_id=recipient_wallet.id,
            transaction_type=WalletTransactionType.ADJUSTMENT,
            amount=amount,
            credit=amount,
            transfer_in=amount,
            description=description,
            source="p2p_transfer",
            created_by=sender_id
        )
        
        WalletService._log_audit(
            session=session,
            action="P2P_TRANSFER",
            target_id=str(recipient_id),
            target_type="User",
            actor_id=sender_id,
            meta_data={"amount": str(amount), "sender_id": str(sender_id)}
        )
        
        if commit:
            session.commit()
            session.refresh(sender_tx)
            session.refresh(recipient_tx)

        return sender_tx, recipient_tx

    @staticmethod
    def deduct_usage(
        session: Session,
        owner_id: uuid.UUID,
        owner_type: WalletOwnerType,
        amount: Decimal,
        description: str,
        reference_id: Optional[str] = None,
        commit: bool = False
    ) -> WalletTransaction:
        """
        Deduction for usage (AI requests, etc.)
        """
        wallet = WalletService.get_or_create_wallet(session, owner_id, owner_type)
        
        # Lock wallet
        statement = select(Wallet).where(Wallet.id == wallet.id).with_for_update()
        session.exec(statement).first()
        
        balance = WalletService.get_balance(session, wallet.id)
        if balance < amount:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Insufficient balance. Available: {balance}, Required: {amount}"
            )
            
        transaction = WalletService.add_transaction(
            session=session,
            wallet_id=wallet.id,
            transaction_type=WalletTransactionType.USAGE,
            amount=-amount,
            debit=amount,
            description=description,
            reference_id=reference_id,
            source="usage",
            commit=commit
        )
        
        return transaction

    @staticmethod
    def _sync_cached_balance(session: Session, wallet: Wallet):
        """Synchronize the ledger balance with the cached credits_balance on owner model"""
        from app.models import User, Organization
        
        balance = WalletService.get_balance(session, wallet.id)
        
        if wallet.owner_type == WalletOwnerType.USER:
            user = session.get(User, wallet.owner_id)
            if user:
                # User model uses 'credits', others use 'credits_balance'
                current_val = getattr(user, "credits", 0)
                logger.info(f"Syncing USER wallet {wallet.id}: {current_val} -> {balance}")
                user.credits = balance
                session.add(user)

        elif wallet.owner_type == WalletOwnerType.ORGANIZATION:
            org = session.get(Organization, wallet.owner_id)
            if org:
                logger.info(f"Syncing ORG wallet {wallet.id} (Org: {org.id}): {org.credits_balance} -> {balance}")
                org.credits_balance = balance
                session.add(org)
                
        session.flush()

    @staticmethod
    def _log_audit(
        session: Session,
        action: str,
        target_id: str,
        target_type: str,
        actor_id: Optional[uuid.UUID] = None,
        meta_data: Optional[dict] = None
    ):
        """Creates an audit log entry."""
        log = AuditLog(
            action=action,
            target_id=target_id,
            target_type=target_type,
            actor_id=actor_id,
            meta_data=meta_data or {},
            timestamp=datetime.now(timezone.utc),
            severity="medium" if action in ["ORG_TOP_UP", "CREDIT_SHARED"] else "low"
        )
        session.add(log)
        session.flush()
