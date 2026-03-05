from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict
from pydantic import BaseModel
import logging
import numpy as np

from processor import extract_features, run_inference
from trainer import PersonalTrainer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Stylometry Inference API", version="1.0.0")

@app.on_event("startup")
async def on_startup():
    logger.info(f"📍 Numpy Version loaded by AI Service: {np.__version__}")
    try:
        import torch
        logger.info(f"📍 PyTorch Version loaded: {torch.__version__}")
    except ImportError:
        logger.warning("PyTorch could not be loaded!")

# Allow requests from the main backend (usually 8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Can be restricted to ["http://localhost:8000"] in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PredictRequest(BaseModel):
    user_id: str
    messages: List[str]

class PredictResponse(BaseModel):
    trust_score: float
    features: Dict[str, float]
    identity_status: str

class TrainRequest(BaseModel):
    user_id: str
    messages: List[str]

class RetrainRequest(BaseModel):
    user_id: str
    historical_messages: List[str]
    new_messages: List[str]

@app.get("/health")
async def health_check():
    return {"status": "AI Service is running"}

@app.post("/api/predict", response_model=PredictResponse)
async def predict_stylometry(request: PredictRequest):
    """
    Inference Endpoint: Receive 5 messages, extract features, predict trust score.
    """
    if len(request.messages) != 5:
        logger.warning(f"Received {len(request.messages)} messages, expected 5.")
        raise HTTPException(status_code=400, detail="Expected exactly 5 messages for the rolling window.")
    
    try:
        # 1. Feature Extraction
        features = extract_features(request.user_id, request.messages)
        
        # 2. Inference (ทำนายผล)
        trust_score = run_inference(request.user_id, request.messages)
        
        # 3. ตรวจสอบสถานะและสร้าง Response
        status = "Verified" if trust_score >= 0.5 else "Suspicious"
        
        return PredictResponse(
            trust_score=trust_score,
            features=features,
            identity_status=status
        )
    except FileNotFoundError as e:
        logger.warning(f"Uncalibrated User Attempted Predict: {str(e)}")
        # Raise 400 or 404 to let Backend know user needs Calibration Phase
        raise HTTPException(status_code=400, detail="Model not calibrated")
    except Exception as e:
        import traceback
        err_detail = f"{str(e)} | Trace: {traceback.format_exc()}"
        logger.error(f"Prediction error: {err_detail}")
        raise HTTPException(status_code=500, detail=err_detail)

@app.post("/api/train_personal")
async def train_personal_model(request: TrainRequest):
    """
    Initial Training Endpoint: Creates a personalized baseline from 5-50 messages
    """
    if len(request.messages) < 5: 
        raise HTTPException(status_code=400, detail="Not enough messages to build a baseline.")
    
    try:
        trainer = PersonalTrainer(request.user_id)
        success = trainer.train(request.messages)
        return {"status": "success", "message": f"Personalized model compiled securely for {request.user_id}."}
    except Exception as e:
        import traceback
        print(f"🔥 Train Error: {str(e)}")
        logger.error(f"Training error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/retrain_personal")
async def retrain_personal_model(request: RetrainRequest):
    """
    Adaptive Learning: Feedback Loop for fixing false positives 
    """
    try:
        trainer = PersonalTrainer(request.user_id)
        success = trainer.retrain(request.historical_messages, request.new_messages)
        return {"status": "success", "message": f"Personalized model fine-tuned for {request.user_id}."}
    except Exception as e:
        import traceback
        logger.error(f"Retraining error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # รันบน Port 8001 ตามที่ขอ
    uvicorn.run(app, host="0.0.0.0", port=8001)
