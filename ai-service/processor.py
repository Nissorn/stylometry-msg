import os
import json
import joblib
import re
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import List, Dict

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
USERS_MODELS_DIR = os.path.join(MODELS_DIR, "users")
WINDOW_SIZE = 5
MAX_LEN = 256

# -----------------------------------------------------------------------------
# Deep Learning Architecture
# -----------------------------------------------------------------------------
class SharedCharCNN(nn.Module):
    def __init__(self, vocab_size, embed_dim=64, num_filters=128):
        super(SharedCharCNN, self).__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.conv1 = nn.Conv1d(embed_dim, num_filters, kernel_size=3, padding=1)
        self.pool1 = nn.MaxPool1d(kernel_size=2)
        self.conv2 = nn.Conv1d(num_filters, num_filters, kernel_size=5, padding=2)
        self.global_pool = nn.AdaptiveMaxPool1d(1)
        self.dropout = nn.Dropout(0.3)
        self.relu = nn.ReLU()
        
    def forward(self, x):
        x = self.embedding(x).permute(0, 2, 1)
        x = self.pool1(self.relu(self.conv1(x)))
        x = self.global_pool(self.relu(self.conv2(x))).squeeze(2)
        return self.dropout(x)

class AttentionLayer(nn.Module):
    def __init__(self, feature_dim=128, hidden_dim=64):
        super(AttentionLayer, self).__init__()
        self.attn = nn.Sequential(
            nn.Linear(feature_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, 1)
        )
    def forward(self, features): # (B, N, 128)
        scores = self.attn(features) # (B, N, 1)
        weights = F.softmax(scores, dim=1) # Softmax over N
        context = torch.sum(features * weights, dim=1) # (B, 128)
        return context

class AttentionSessionCNN(nn.Module):
    def __init__(self, vocab_size):
        super(AttentionSessionCNN, self).__init__()
        self.base_model = SharedCharCNN(vocab_size)
        self.attention = AttentionLayer(feature_dim=128)
        self.classifier = nn.Linear(128, 1)
        
    def forward(self, inputs, return_features=False):
        features_list = []
        for x in inputs:
            features_list.append(self.base_model(x))
            
        features = torch.stack(features_list, dim=1) # (B, N, 128)
        context = self.attention(features) # (B, 128)
        
        if return_features:
            return context
            
        logits = self.classifier(context)
        return torch.sigmoid(logits)

# -----------------------------------------------------------------------------
# Vocabulary and Metadata Extraction
# -----------------------------------------------------------------------------
class CharVocabInference:
    def __init__(self, vocab_path):
        with open(vocab_path, "r") as f:
            self.char2idx = json.load(f)
            
    def encode(self, text, max_len=256):
        if not isinstance(text, str): text = ""
        indices = [self.char2idx.get(c, 1) for c in text[:max_len]]
        if len(indices) < max_len: indices += [0] * (max_len - len(indices))
        return list(indices)
    
    def __len__(self): 
        return len(self.char2idx)

def get_meta_features(text):
    text = str(text)
    length = len(text)
    laugh_count = len(re.findall(r'5+|[hH]aha|ฮ่า+|อิอิ', text))
    elongation_count = len(re.findall(r'(.)\1{2,}|ๆ', text))
    punct_count = len(re.findall(r'[?!.]{2,}|~+', text))
    space_count = text.count(' ')
    return [length, laugh_count, elongation_count, punct_count, space_count]

# -----------------------------------------------------------------------------
# AI State and Feature Extraction
# -----------------------------------------------------------------------------
class EngineState:
    detectors = {}

class SylometryDetector:
    def __init__(self, user_id: str, models_dir=MODELS_DIR):
        self.user_id = user_id
        self.models_dir = models_dir
        self.users_dir = USERS_MODELS_DIR
        self.device = torch.device("cpu")
        
        # Load global vocab (this remains fixed for the character encoding base)
        vocab_path = os.path.join(models_dir, "barrier_strict_vocab.json")
        self.vocab = CharVocabInference(vocab_path)
        
        # Model paths for this specific user
        cnn_path = os.path.join(self.users_dir, f"{user_id}_cnn.pth")
        scaler_path = os.path.join(self.users_dir, f"{user_id}_scaler.pkl")
        tfidf_path = os.path.join(self.users_dir, f"{user_id}_tfidf.pkl")
        lr_path = os.path.join(self.users_dir, f"{user_id}_lr.pkl")
        xgb_path = os.path.join(self.users_dir, f"{user_id}_xgb.pkl")
        
        # IMPORTANT: Reject if personal model doesn't exist
        for path in [cnn_path, scaler_path, tfidf_path, lr_path, xgb_path]:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Model not calibrated for user '{user_id}'. Missing: {path}")

        print(f"Loading Personalized Models on {self.device} for user {user_id}")
        
        self.cnn_model = AttentionSessionCNN(vocab_size=len(self.vocab))
        self.cnn_model.load_state_dict(torch.load(cnn_path, map_location=self.device))
        self.cnn_model.to(self.device).eval()
        
        self.scaler = joblib.load(scaler_path)
        self.tfidf = joblib.load(tfidf_path)
        self.lr_model = joblib.load(lr_path)
        self.xgb_model = joblib.load(xgb_path)
        print(f"User {user_id} Models successfully loaded in memory.")

    def run_inference(self, messages: List[str]) -> float:
        cnn_inputs = []
        for msg in messages:
            encoded = self.vocab.encode(msg, MAX_LEN)
            tensor = torch.tensor([encoded], dtype=torch.long).to(self.device)
            cnn_inputs.append(tensor)
            
        with torch.no_grad():
            deep_features = self.cnn_model(cnn_inputs, return_features=True).numpy()
            
        combined_text = " ".join([str(m) for m in messages])
        
        raw_meta = [get_meta_features(combined_text)]
        meta_features = self.scaler.transform(raw_meta)
        
        tfidf_features = self.tfidf.transform([combined_text])
        lr_prob = self.lr_model.predict_proba(tfidf_features)[:, 1].reshape(1, 1)
        
        X_final = np.hstack((deep_features, meta_features, lr_prob))
        prob = self.xgb_model.predict_proba(X_final)[0, 1]
        
        return float(prob)

    def extract_features_meta(self, messages: List[str]) -> Dict[str, float]:
        """ Extracts basic meta features for frontend UI Display """
        combined_text = " ".join([str(m) for m in messages])
        f_list = get_meta_features(combined_text)
        return {
            "length": float(f_list[0]),
            "laugh_intensity": float(f_list[1]),
            "letter_elongation": float(f_list[2]),
            "punctuation_usage": float(f_list[3]),
            "spacing_ratio": float(f_list[4]) / max(f_list[0], 1)
        }

def get_engine(user_id: str) -> SylometryDetector:
    if user_id not in EngineState.detectors:
        # Raises FileNotFoundError if the user hasn't trained a model
        EngineState.detectors[user_id] = SylometryDetector(user_id)
    return EngineState.detectors[user_id]

def extract_features(user_id: str, messages: List[str]) -> Dict[str, float]:
    engine = get_engine(user_id)
    return engine.extract_features_meta(messages)

def run_inference(user_id: str, messages: List[str]) -> float:
    engine = get_engine(user_id)
    return engine.run_inference(messages)
