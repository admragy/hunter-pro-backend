from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import models, schemas, database
from database import engine, get_db
import google.generativeai as genai
from duckduckgo_search import DDGS
import requests
import os
import json

# --- إعداد النظام ---
models.Base.metadata.create_all(bind=engine)

# مفاتيح القوة
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY") # المفتاح الجديد لتقوية الصيد

if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

app = FastAPI(title="Hunter Pro Backend")

# --- نماذج البيانات ---
class HuntRequest(BaseModel):
    query: str

class HuntResponse(BaseModel):
    results: List[dict]
    new_balance: int
    source: str

# --- دوال مساعدة ---
def check_balance(user_id: int, cost: int, db: Session):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    if user.wallet_balance < cost:
        raise HTTPException(status_code=402, detail=f"رصيدك غير كافي ({user.wallet_balance}). تحتاج {cost}")
    return user

# --- محرك الصيد المزدوج (Dual Engine Hunter) ---
def search_google_serper(query):
    """محرك بحث جوجل القوي (يحتاج مفتاح Serper)"""
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": query, "num": 10, "gl": "eg", "hl": "ar"}) # مصر واللغة العربية
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    
    try:
        response = requests.post(url, headers=headers, data=payload)
        data = response.json()
        results = []
        # تجميع النتائج العضوية والمحلية (الخرائط)
        if "organic" in data:
            for item in data["organic"]:
                results.append(f"الاسم: {item.get('title')} - الوصف: {item.get('snippet')} - الرابط: {item.get('link')}")
        if "places" in data:
            for item in data["places"]:
                results.append(f"النشاط: {item.get('title')} - العنوان: {item.get('address')} - الهاتف: {item.get('phoneNumber', 'غير متوفر')}")
        return results
    except Exception as e:
        print(f"Serper Error: {e}")
        return []

def search_duckduckgo(query):
    """محرك بحث مجاني احتياطي"""
    try:
        results = []
        with DDGS() as ddgs:
            # نبحث عن نتائج فيها تواصل
            keywords = f"{query} رقم تليفون عنوان contact"
            ddg_gen = ddgs.text(keywords, region='wt-wt', safesearch='off', max_results=10)
            for r in ddg_gen:
                results.append(f"العنوان: {r['title']} - المحتوى: {r['body']}")
        return results
    except Exception as e:
        print(f"DDG Error: {e}")
        return []

# --- البوابات (Endpoints) ---

@app.get("/", response_class=HTMLResponse)
def read_root():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "<h1>نظام Hunter Pro يعمل ✅ (يرجى رفع ملف index.html)</h1>"

@app.post("/users/", response_model=schemas.UserResponse)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user: return db_user
    new_user = models.User(email=user.email, full_name=user.full_name, hashed_password="123", wallet_balance=50)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.get("/users/{user_id}")
def get_user_data(user_id: int, db: Session = Depends(get_db)):
    return db.query(models.User).filter(models.User.id == user_id).first()

@app.post("/chat/{user_id}", response_model=schemas.ChatResponse)
def chat_ai(user_id: int, request: schemas.ChatRequest, db: Session = Depends(get_db)):
    user = check_balance(user_id, 2, db)
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        chat = model.start_chat(history=[])
        response = chat.send_message(f"أنت مساعد Hunter Pro CRM. أجب بالعربية. السؤال: {request.message}")
        
        user.wallet_balance -= 2
        db.commit()
        return {"response": response.text, "tokens_used": 2}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 🔥 بوابة الصياد المطورة 🔥
@app.post("/hunt/{user_id}", response_model=HuntResponse)
def run_hunter(user_id: int, request: HuntRequest, db: Session = Depends(get_db)):
    user = check_balance(user_id, 20, db)
    
    # 1. اختيار المحرك (لو فيه مفتاح Serper استخدمه، لو مفيش استخدم DuckDuckGo)
    raw_results = []
    source = "DuckDuckGo (مجاني)"
    
    if SERPER_API_KEY:
        print("Using Serper API...")
        raw_results = search_google_serper(request.query)
        source = "Google Search (دقيق)"
    
    if not raw_results: # لو سيربر فشل أو مش موجود
        print("Using DuckDuckGo...")
        raw_results = search_duckduckgo(request.query)
        source = "DuckDuckGo (احتياطي)"

    if not raw_results:
        raise HTTPException(status_code=404, detail="لم يتم العثور على نتائج. جرب كلمات بحث أخرى.")

    # 2. تحليل النتائج بالذكاء الاصطناعي (Gemini)
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        data_str = "\n".join(raw_results[:10])
        
        prompt = f"""
        استخرج بيانات العملاء من نتائج البحث التالية.
        أريد النتيجة بتنسيق JSON List فقط.
        الحقول المطلوبة: title (الاسم), phone (رقم الهاتف أو 'غير متوفر'), address (العنوان).
        *مهم*: حاول استنتاج المدينة من السياق.
        البيانات الخام:
        {data_str}
        """
        
        ai_response = model.generate_content(prompt)
        clean_json = ai_response.text.replace("```json", "").replace("```", "").strip()
        final_leads = json.loads(clean_json)
        
        # 3. حفظ في الداتا بيز (مع منع التكرار)
        saved_count = 0
        for item in final_leads:
            # لو العميل ده مش موجود قبل كدة بنفس الاسم
            exists = db.query(models.Lead).filter(models.Lead.name == item['title'], models.Lead.user_id == user.id).first()
            if not exists:
                lead = models.Lead(
                    user_id=user.id,
                    name=item.get('title', 'Unknown'),
                    phone=item.get('phone', ''),
                    status="New"
                )
                db.add(lead)
                saved_count += 1
        
        # 4. خصم الرصيد
        user.wallet_balance -= 20
        db.commit()
        
        return {"results": final_leads, "new_balance": user.wallet_balance, "source": source}

    except Exception as e:
        print(f"Error parsing AI: {e}")
        # لو حصل خطأ في التحليل، نرجع خطأ بدل ما نضرب
        raise HTTPException(status_code=500, detail="فشل تحليل البيانات، حاول مرة أخرى.")
