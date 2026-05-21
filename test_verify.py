import asyncio
from sqlmodel import Session, create_engine
from app.services.payment_service import payment_service

engine = create_engine("postgresql://jamesoyanna@/qorebit_db?host=/tmp")

async def main():
    try:
        with Session(engine) as session:
            result = await payment_service.verify_transaction(
                session=session, 
                transaction_id="FGCEOSA-PSTK-0892a8fe-403f-4f1e-99ce-72a396cebde7-20260521125254"
            )
            print("RESULT:", result)
    except Exception as e:
        print("EXCEPTION:", e)

asyncio.run(main())
