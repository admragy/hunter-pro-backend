from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import models, schemas, database
from database import engine, get_db
import google.generativeai as genai
from openai import OpenAI
from duckduckgo_search import DDGS
import requests
import os
import json

# --- 1. إعداد النظام ---
models.Base.metadata.create_all(bind=engine) # إنشاء الجداول عند التشغيل

# جلب المفاتيح من Fly.io Secrets
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

openai_client = None
if OPENAI_API_KEY:
    try: openai_client = OpenAI(api_key=OPENAI_API_KEY)
    except: pass

if GOOGLE_API_KEY:
    try: genai.configure(api_key=GOOGLE_API_KEY)
    except: pass

app = FastAPI(title="Hunter Pro Backend - Ultimate Edition")

# --- 2. دوال مساعدة ---
def check_balance(user_id: int, cost: int, db: Session):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود. برجاء تسجيل الدخول أولاً في الواجهة الرئيسية.")
    if user.wallet_balance < cost:
        raise HTTPException(status_code=402, detail=f"رصيدك ({user.wallet_balance}) لا يكفي. العملية تتطلب {cost} توكن")
    return user

def ask_ai_hybrid(prompt: str):
    """المحرك الهجين: يجرب OpenAI أولاً ثم Gemini"""
    # 1. محاولة OpenAI
    if openai_client:
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content
        except: pass
    
    # 2. محاولة Gemini
    if GOOGLE_API_KEY:
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            return response.text
        except: pass
            
    raise Exception("لا يوجد مفاتيح ذكاء اصطناعي فعالة! (تحقق من OPENAI_API_KEY أو GOOGLE_API_KEY)")

def search_duckduckgo(query: str):
    """البحث المجاني الاحتياطي"""
    results = []
    try:
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(f"{query} phone number contact", max_results=10))
            for r in raw_results:
                results.append({
                    "title": r.get('title'),
                    "link": r.get('href'),
                    "snippet": r.get('body')
                })
        return results
    except: return []

# --- 3. البوابات (Endpoints) ---

# الصفحة الرئيسية (تعرض التطبيق)
@app.get("/", response_class=HTMLResponse)
def read_root():
    """هذه البوابة تقدم ملف index.html للمستخدم."""
    try:
        with open("index.html", "r", encoding="utf-8") as f: return f.read()
    except: return "<h1>Hunter Pro System Online 🚀 (Error: index.html not found)</h1>"

# تسجيل الدخول/الإنشاء
@app.post("/users/", response_model=schemas.UserResponse)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """ينشئ مستخدماً جديداً أو يعيد البيانات إذا كان موجوداً بالفعل."""
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user: return db_user
    
    # كود بناء المستخدم في الداتا بيز
    new_user = models.User(email=user.email, full_name=user.full_name, hashed_password="pw", wallet_balance=50)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

# جلب بيانات المستخدم
@app.get("/users/{user_id}", response_model=schemas.UserResponse)
def get_user_data(user_id: int, db: Session = Depends(get_db)):
    """جلب بيانات المستخدم بناءً على ID."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود.")
    return user

# بوابة الشات
@app.post("/chat/{user_id}", response_model=schemas.ChatResponse)
def chat_endpoint(user_id: int, request: schemas.ChatRequest, db: Session = Depends(get_db)):
    cost = 2
    user = check_balance(user_id, cost, db)
    
    try:
        prompt = f"أنت مساعد Hunter Pro. أجب باللهجة المصرية. السؤال: {request.message}"
        reply = ask_ai_hybrid(prompt)
        
        # كود خصم الرصيد
        user.wallet_balance -= cost
        db.add(models.WalletTransaction(user_id=user.id, action_type="Chat", amount=-cost, description="AI Chat"))
        db.commit()
        
        return {"response": reply, "tokens_used": cost}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"خطأ في الذكاء الاصطناعي: {str(e)}")

# بوابة الصيد (Hunt)
@app.post("/hunt/{user_id}", response_model=schemas.HuntResponse)
def hunt_endpoint(user_id: int, request: schemas.HuntRequest, db: Session = Depends(get_db)):
    cost = 20
    user = check_balance(user_id, cost, db)
    
    final_leads = []
    
    # 1. البحث (Serper أو DuckDuckGo)
    raw_results = []
    if SERPER_API_KEY:
        try:
            url = "https://google.serper.dev/search"
            payload = json.dumps({"q": request.query, "gl": "eg", "hl": "ar"})
            headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
            resp = requests.post(url, headers=headers, data=payload).json()
            if "places" in resp: # نتائج الخرائط
                for place in resp["places"]:
                    raw_results.append({
                        "title": place.get("title"),
                        "phone": place.get("phoneNumber"),
                        "address": place.get("address"),
                        "snippet": place.get("snippet")
                    })
            if "organic" in resp: raw_results.extend(resp["organic"])
        except: pass
    
    if not raw_results:
        raw_results = search_duckduckgo(request.query)

    if not raw_results:
        raise HTTPException(status_code=404, detail="لم يتم العثور على نتائج.")

    # 2. التحليل بالـ AI
    try:
        data_str = json.dumps(raw_results[:8], ensure_ascii=False)
        prompt = f"استخرج بيانات العملاء (شركات/أشخاص) من هذه النتائج. الناتج JSON List فقط: [{{ 'title': '', 'phone': '', 'address': '' }}] البيانات: {data_str}"
        
        ai_resp = ask_ai_hybrid(prompt)
        clean_json = ai_resp.replace("```json", "").replace("```", "").strip()
        final_leads = json.loads(clean_json)
        
        # 3. الحفظ في الداتا بيز (Database Code)
        for item in final_leads:
            # التحقق من عدم التكرار
            exists = db.query(models.Lead).filter(models.Lead.name == item.get('title'), models.Lead.user_id == user.id).first()
            if not exists and item.get('title'):
                db.add(models.Lead(user_id=user.id, name=item['title'], phone=item.get('phone'), status="New"))

        # 4. الخصم وتحديث المحفظة
        user.wallet_balance -= cost
        db.add(models.WalletTransaction(user_id=user.id, action_type="Hunt", amount=-cost, description=request.query))
        db.commit()
        
        return {"results": final_leads, "new_balance": user.wallet_balance}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"خطأ في تحليل البيانات: {str(e)}")
