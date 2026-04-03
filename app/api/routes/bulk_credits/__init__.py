from fastapi import APIRouter

router = APIRouter(prefix="/bulk-credits", tags=["bulk-credits"])

from . import stats, transactions, programs, distribution

router.include_router(stats.router)
router.include_router(transactions.router)
router.include_router(programs.router)
router.include_router(distribution.router)
