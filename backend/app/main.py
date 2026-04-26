"""FastAPI web application entry point."""

from pathlib import Path
from decimal import Decimal
import logging
import os
import time

from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

from .models import Base, ReconRun, PlatformTransaction, BankSettlement, GapResult
from .schemas import ReconSummary, GapResultOut, GapBreakdown
from .ingestion import ingest_csvs, IngestionError
from .matching import run_matching
from .classifier import classify_gaps
from .aggregator import compute_aggregates
from .narrator import generate_narrative

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("recon")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./recon.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("Database ready — tables created/verified")
    yield


app = FastAPI(title="Reconciliation API", lifespan=lifespan)

# In production set ALLOWED_ORIGIN=https://your-app.vercel.app
# In dev, the regex covers any localhost port automatically.
_allowed_origins = [o for o in os.getenv("ALLOWED_ORIGIN", "").split(",") if o]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=r"http://localhost:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/upload")
def upload_csvs(
    platform: UploadFile = File(...),
    bank: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    t0 = time.perf_counter()
    try:
        run_id = ingest_csvs(platform.file, bank.file, db)
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("[upload]     run_id=%d  elapsed_ms=%.1f", run_id, elapsed)
        return {"run_id": run_id}
    except IngestionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/reconcile/{run_id}")
def reconcile_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(ReconRun).filter(ReconRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status == "completed":
        raise HTTPException(status_code=400, detail="Run already reconciled")

    t_total = time.perf_counter()

    t0 = time.perf_counter()
    matching_result = run_matching(run_id, db)
    logger.info(
        "[reconcile]  run_id=%d  stage=matching     elapsed_ms=%6.1f  "
        "matched=%d  unmatched_platform=%d  unmatched_bank=%d  rounding=%d",
        run_id, (time.perf_counter() - t0) * 1000,
        len(matching_result.matched),
        len(matching_result.unmatched_platform),
        len(matching_result.unmatched_bank),
        len(matching_result.rounding_candidates),
    )

    t0 = time.perf_counter()
    gap_results = classify_gaps(matching_result, db)
    logger.info(
        "[reconcile]  run_id=%d  stage=classify     elapsed_ms=%6.1f  gaps_found=%d",
        run_id, (time.perf_counter() - t0) * 1000, len(gap_results),
    )

    t0 = time.perf_counter()
    summary = compute_aggregates(run_id, matching_result, db)
    logger.info(
        "[reconcile]  run_id=%d  stage=aggregate    elapsed_ms=%6.1f  "
        "platform=%s  bank=%s  gap=%s  rounding_drift=%s",
        run_id, (time.perf_counter() - t0) * 1000,
        summary.platform_total, summary.bank_total,
        summary.total_gap, summary.rounding_drift_total,
    )

    t0 = time.perf_counter()
    narrative = generate_narrative(summary, gap_results)
    logger.info(
        "[reconcile]  run_id=%d  stage=narrate      elapsed_ms=%6.1f",
        run_id, (time.perf_counter() - t0) * 1000,
    )

    logger.info(
        "[reconcile]  run_id=%d  DONE               elapsed_ms=%6.1f",
        run_id, (time.perf_counter() - t_total) * 1000,
    )

    run.status = "completed"
    db.commit()

    total_platform_txns = db.query(PlatformTransaction).filter_by(run_id=run_id).count()
    total_bank_settlements = db.query(BankSettlement).filter_by(run_id=run_id).count()
    
    gap_breakdown_list = [
        {"gap_type": k, "count": v[0], "total_amount": v[1]}
        for k, v in summary.gap_breakdown.items()
    ]
    
    recon_summary = ReconSummary(
        run_id=run_id,
        created_at=run.created_at,
        status=run.status,
        total_platform_txns=total_platform_txns,
        total_bank_settlements=total_bank_settlements,
        platform_total=summary.platform_total,
        bank_total=summary.bank_total,
        total_gaps=len(gap_results),
        total_gap_amount=summary.total_gap,
        rounding_drift_total=summary.rounding_drift_total,
        gap_breakdown=gap_breakdown_list,
        narrative=narrative,
    )

    return {
        "result_id": run_id,
        "summary": recon_summary.model_dump(),
    }

@app.get("/results/{run_id}")
def get_results(run_id: int, db: Session = Depends(get_db)):
    run = db.query(ReconRun).filter(ReconRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
        
    total_platform_txns = db.query(PlatformTransaction).filter_by(run_id=run_id).count()
    total_bank_settlements = db.query(BankSettlement).filter_by(run_id=run_id).count()
    
    matching_result = run_matching(run_id, db)
    summary = compute_aggregates(run_id, matching_result, db)
    gap_results = db.query(GapResult).filter_by(run_id=run_id).all()
    narrative = generate_narrative(summary, gap_results)
    
    gap_breakdown_list = [
        {"gap_type": k, "count": v[0], "total_amount": v[1]}
        for k, v in summary.gap_breakdown.items()
    ]
    
    recon_summary = ReconSummary(
        run_id=run_id,
        created_at=run.created_at,
        status=run.status,
        total_platform_txns=total_platform_txns,
        total_bank_settlements=total_bank_settlements,
        platform_total=summary.platform_total,
        bank_total=summary.bank_total,
        total_gaps=len(gap_results),
        total_gap_amount=summary.total_gap,
        rounding_drift_total=summary.rounding_drift_total,
        gap_breakdown=gap_breakdown_list,
        narrative=narrative,
    )

    gaps_grouped = {}
    for g in gap_results:
        try:
            val = GapResultOut.model_validate(g).model_dump()
        except AttributeError:
            val = GapResultOut.from_orm(g).dict()
        gaps_grouped.setdefault(g.gap_type, []).append(val)

    return {
        "summary": recon_summary.model_dump(),
        "gaps": gaps_grouped,
    }

@app.get("/sample-data")
def get_sample_data():
    sample_dir = Path(__file__).resolve().parent.parent.parent / "sample_data"
    plat_path = sample_dir / "platform_transactions.csv"
    bank_path = sample_dir / "bank_settlements.csv"
    
    if not plat_path.exists() or not bank_path.exists():
        raise HTTPException(status_code=404, detail="Sample data not found")
        
    with open(plat_path, "r", encoding="utf-8") as f:
        plat_content = f.read()
    with open(bank_path, "r", encoding="utf-8") as f:
        bank_content = f.read()
        
    return JSONResponse(content={
        "platform_csv": plat_content,
        "bank_csv": bank_content
    })
