import os
import json
import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from sklearn.preprocessing import StandardScaler
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from xgboost import XGBClassifier

from processor import (
    MODELS_DIR, WINDOW_SIZE, MAX_LEN, 
    AttentionSessionCNN, CharVocabInference, get_meta_features
)

class StylometricFeatureExtractor:
    def fit(self, X, y=None):
        return self
    def transform(self, X, y=None):
        return np.array([get_meta_features(text) for text in X])

# Generic negative samples to provide a baseline for binary classification 
# against the user's personalized active typing style.
NEGATIVE_SAMPLES = [
    "สวัสดีครับ ยินดีที่ได้รู้จัก", "ตอนนี้ทำอะไรอยู่เหรอ", "ไปกินข้าวด้วยกันไหม?",
    "วันนี้อากาศดีจังเลยนะ", "ฉันคิดว่าแบบนั้นก็ดีนะ", "ไม่มีปัญหาจัดการให้ได้",
    "เดี๋ยวจะรีบส่งงานให้นะครับ", "ช่วยตรวจสอบไฟล์นี้ที", "ขอบคุณมากครับที่แนะนำ",
    "แล้วแต่เลย เอาที่สบายใจ", "ไม่เป็นไรครับ ยินดีครับ", "รับทราบ จะดำเนินการเดี๋ยวนี้",
    "น่าสนใจมาก ขอดูรายละเอียดหน่อย", "ทำไมถึงคิดแบบนั้นล่ะ", "ก็ว่าอยู่ว่าทำไมแปลกๆ",
    "5555 ตลกมากเลย", "จริงดิ ไม่น่าเชื่อ", "อ๋อ เข้าใจแล้วครับ",
    "รบกวนหน่อยนะครับ", "ขอโทษทีที่ตอบช้า", "เดี๋ยวทักไปใหม่นะ",
    "พรุ่งนี้ว่างหรือเปล่า", "ไม่แน่ใจแฮะ ขอเช็คดูก่อน", "เยี่ยมไปเลย!",
    "โอเค ตกลงตามนี้", "ได้เลย ไม่มีปัญหา", "งั้นเดี๋ยวเจอกันนะ"
]

class SessionDataset(Dataset):
    def __init__(self, texts, labels, vocab):
        self.texts = texts
        self.labels = labels
        self.vocab = vocab
        
        self.sessions = []
        for i in range(len(self.texts) - WINDOW_SIZE + 1):
            session_msgs = self.texts[i:i+WINDOW_SIZE]
            self.sessions.append({
                "messages": session_msgs,
                "label": self.labels[i] # Just map label roughly
            })

    def __len__(self):
        return len(self.sessions)

    def __getitem__(self, idx):
        session = self.sessions[idx]
        inputs = []
        for msg in session["messages"]:
            encoded = self.vocab.encode(msg, MAX_LEN)
            inputs.append(torch.tensor(encoded, dtype=torch.long))
            
        y = torch.tensor(session["label"], dtype=torch.float)
        combined_text = " ".join([str(m) for m in session["messages"]])
        return inputs, y, combined_text

def collate_fn(batch):
    inputs_list, labels, texts = zip(*batch)
    batched_inputs = []
    for i in range(WINDOW_SIZE):
        m_i = torch.stack([sample[i] for sample in inputs_list])
        batched_inputs.append(m_i)
    labels = torch.stack(labels)
    return batched_inputs, labels, texts

class PersonalTrainer:
    def __init__(self, user_id, device="cpu"):
        self.user_id = user_id
        self.device = torch.device(device)
        self.users_dir = os.path.join(MODELS_DIR, "users")
        os.makedirs(self.users_dir, exist_ok=True)
        
        # Load global vocab
        vocab_path = os.path.join(MODELS_DIR, "barrier_strict_vocab.json")
        self.vocab = CharVocabInference(vocab_path)
        
    def _get_user_model_path(self, model_type):
        return os.path.join(self.users_dir, f"{self.user_id}_{model_type}")

    def _prepare_data(self, messages, include_negatives=True):
        texts = list(messages)
        labels = [1] * len(texts) # Positive samples
        
        if include_negatives:
            # Generate enough negative baseline samples relative to the user messages (Ratio 1:2)
            num_neg_needed = len(messages) * 2
            
            # ตรวจสอบขีดจำกัดเพื่อให้มี data เพียงพอและไม่เกิดปัญหาตอนแบ่ง batch เล็กๆ
            num_neg_needed = max(num_neg_needed, 60) 
            
            neg_texts = (NEGATIVE_SAMPLES * (num_neg_needed // len(NEGATIVE_SAMPLES) + 1))[:num_neg_needed]
            texts.extend(neg_texts)
            labels.extend([0] * len(neg_texts)) # Negative samples
            
        return SessionDataset(texts, labels, self.vocab)

    def train(self, messages):
        """ Trains a completely fresh baseline model for exactly 1 user using 30-50 messages. """
        print(f"--- [Trainer] Starting Baseline Training for User: {self.user_id} ---")
        dataset = self._prepare_data(messages)
        dataloader = DataLoader(dataset, batch_size=16, shuffle=True, collate_fn=collate_fn)
        dataloader_eval = DataLoader(dataset, batch_size=16, shuffle=False, collate_fn=collate_fn)
        
        # 1. Train CNN Body
        model = AttentionSessionCNN(len(self.vocab)).to(self.device)
        optimizer = optim.Adam(model.parameters(), lr=0.001)
        criterion = nn.BCELoss()
        
        model.train()
        epochs = 10 # Fast training loop for dynamic generation
        for epoch in range(epochs):
            for inputs, y, _ in dataloader:
                inputs = [x.to(self.device) for x in inputs]
                y = y.to(self.device)
                optimizer.zero_grad()
                outputs = model(inputs)
                loss = criterion(outputs.squeeze(), y)
                loss.backward()
                optimizer.step()
                
        # 2. Extract Deep & Meta Features
        model.eval()
        meta_extractor = StylometricFeatureExtractor()
        deep_feats, labels_arr, raw_texts = [], [], []
        
        with torch.no_grad():
            for inputs, y, texts in dataloader_eval:
                inputs = [x.to(self.device) for x in inputs]
                feats = model(inputs, return_features=True)
                deep_feats.extend(feats.cpu().numpy())
                labels_arr.extend(y.numpy())
                raw_texts.extend(texts)
                
        # Scikit-learn Feature Scaling
        X_meta = meta_extractor.transform(raw_texts)
        scaler = StandardScaler()
        X_meta = scaler.fit_transform(X_meta)
        
        # 3. TF-IDF Stacking
        tfidf = TfidfVectorizer(analyzer='char', ngram_range=(2, 4), max_features=3000)
        X_tfidf = tfidf.fit_transform(raw_texts)
        
        stacking_lr = LogisticRegression(max_iter=1000, random_state=42)
        stacking_lr.fit(X_tfidf, labels_arr)
        lr_probs = stacking_lr.predict_proba(X_tfidf)[:, 1].reshape(-1, 1)
        
        # 4. Final Fusion XGBoost
        X_final = np.hstack((np.array(deep_feats), X_meta, lr_probs))
        final_xgb = XGBClassifier(
            verbosity=0, objective='binary:logistic', eval_metric='logloss',
            n_estimators=100, max_depth=4, learning_rate=0.1
        )
        final_xgb.fit(X_final, labels_arr)
        
        # 5. Save all User specific Models
        os.makedirs(self.users_dir, exist_ok=True)
        torch.save(model.state_dict(), self._get_user_model_path("cnn.pth"))
        joblib.dump(scaler, self._get_user_model_path("scaler.pkl"))
        joblib.dump(tfidf, self._get_user_model_path("tfidf.pkl"))
        joblib.dump(stacking_lr, self._get_user_model_path("lr.pkl"))
        joblib.dump(final_xgb, self._get_user_model_path("xgb.pkl"))
        print(f"--- [Trainer] User {self.user_id} Training Complete & Saved! ---")
        return True

    def retrain(self, historical_messages, new_messages):
        """ Fine-tunes model based on historical mixed with correctly flagged suspicious messages """
        print(f"--- [Trainer] Retraining Model for User: {self.user_id} to prevent Catastrophic Forgetting ---")
        # Combine historical and new messages to prevent catastrophic forgetting
        combined_messages = list(historical_messages) + list(new_messages)
        
        # We simply re-run the full, fast training pipeline with the expanded dataset
        # For small datasets (< 100 messages), retraining from scratch is faster, more stable, 
        # and mathematically safer against drifting than incremental gradient updates.
        return self.train(combined_messages)
