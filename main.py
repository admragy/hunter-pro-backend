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
models.Base.metadata.create_all(bind=engine)

# جلب كل المفاتيح من الخزنة
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY") # مفتاح الـ 2500 بحث

# إعداد عملاء الذكاء الاصطناعي
openai_client = None
if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

app = FastAPI(title="Hunter Pro Backend - Ultimate Edition")

# --- 2. دوال مساعدة ---
def check_balance(user_id: int, cost: int, db: Session):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    if user.wallet_balance < cost:
        raise HTTPException(status_code=402, detail=f"رصيدك ({user.wallet_balance}) لا يكفي.")
    return user

# --- 3. نماذج البيانات ---
class HuntRequest(BaseModel):
    query: str

class HuntResponse(BaseModel):
    results: List[dict]
    new_balance: int
    source: str

# --- 4. العقل المدبر (AI Brain) ---
def ask_ai(prompt: str):
    """يختار تلقائياً بين OpenAI و Gemini"""
    # الأولوية لـ OpenAI (الأذكى)
    if openai_client:
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content
        except:
            pass # لو فشل، جرب اللي بعده
    
    # البديل Gemini (المجاني)
    if GOOGLE_API_KEY:
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            raise Exception(f"AI Error: {str(e)}")
            
    raise Exception("السيرفر لا يحتوي على مفاتيح ذكاء اصطناعي فعالة!")

# --- 5. محركات البحث (Serper + DuckDuckGo) ---
def search_google_serper(query):
    """بحث جوجل الرسمي (بيجيب أرقام وعناوين بدقة)"""
    url = "https://google.serper.dev/search"
    # بنبحث في الأماكن (Places) عشان نجيب أرقام تليفونات
    payload = json.dumps({"q": query, "gl": "eg", "hl": "ar"}) 
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    try:
        response = requests.post(url, headers=headers, data=payload).json()
        results = []
        
        # تجميع نتائج الخرائط (الأهم للشركات)
        if "places" in response:
            for place in response["places"]:
                results.append({
                    "title": place.get("title"),
                    "phone": place.get("phoneNumber"),
                    "address": place.get("address"),
                    "link": f"https://www.google.com/maps/search/?api=1&query={place.get('latitude')},{place.get('longitude')}"
                })
        
        # تجميع النتائج العادية لو مفيش خرائط
        if not results and "organic" in response:
            for org in response["organic"]:
                results.append({
                    "title": org.get("title"),
                    "phone": "غير متوفر", # النتائج العادية مفهاش رقم مباشر غالباً
                    "address": org.get("snippet"),
                    "link": org.get("link")
                })
        return results
    except:
        return []

def search_duckduckgo(query):
    """البحث المجاني الاحتياطي"""
    results = []
    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(f"{query} رقم تليفون", max_results=10))
            for r in raw:
                results.append({
                    "title": r.get('title'),
                    "phone": "غير متوفر", # DDG مبيجبش الرقم في خانة لوحده
                    "address": r.get('body'),
                    "link": r.get('href')
                })
        return results
    except:
        return []

# --- 6. البوابات (Endpoints) ---

@app.get("/", response_class=HTMLResponse)
def read_root():
    try:
        with open("index.html", "r", encoding="utf-8") as f: return f.read()
    except: return "<h1>System Online 🚀</h1>"

@app.post("/users/", response_model=schemas.UserResponse)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user: return db_user
    new_user = models.User(email=user.email, full_name=user.full_name, hashed_password="pw", wallet_balance=50)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    return db.query(models.User).filter(models.User.id == user_id).first()

# بوابة الشات
@app.post("/chat/{user_id}", response_model=schemas.ChatResponse)
def chat_endpoint(user_id: int, request: schemas.ChatRequest, db: Session = Depends(get_db)):
    cost = 2
    user = check_balance(user_id, cost, db)
    try:
        prompt = f"أنت مساعد Hunter Pro. أجب باللهجة المصرية. السؤال: {request.message}"
        reply = ask_ai(prompt)
        
        user.wallet_balance -= cost
        db.add(models.WalletTransaction(user_id=user.id, action_type="Chat", amount=-cost, description="AI Chat"))
        db.commit()
        return {"response": reply, "tokens_used": cost}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# بوابة الصياد (Hybrid Hunter)
@app.post("/hunt/{user_id}", response_model=HuntResponse)
def hunt_endpoint(user_id: int, request: HuntRequest, db: Session = Depends(get_db)):
    cost = 20
    user = check_balance(user_id, cost, db)
    
    final_leads = []
    source_used = "DuckDuckGo"

    # 1. محاولة استخدام Serper (جوجل)
    if SERPER_API_KEY:
        print("Using Serper...")
        final_leads = search_google_serper(request.query)
        if final_leads: source_used = "Google Maps (Serper)"
    
    # 2. لو فشل أو مش موجود، استخدم DuckDuckGo
    if not final_leads:
        print("Using DuckDuckGo...")
        raw_ddg = search_duckduckgo(request.query)
        if raw_ddg:
            # هنا بنحتاج AI عشان ينظف داتا DuckDuckGo لأنها نصية مش منظمة
            try:
                data_str = json.dumps(raw_ddg, ensure_ascii=False)
                prompt = f"""
                استخرج بيانات العملاء من هذا النص.
                الناتج JSON List: [{{ "title": "", "phone": "", "address": "" }}]
                البيانات: {data_str}
                """
                ai_resp = ask_ai(prompt)
                clean_json = ai_resp.replace("```json", "").replace("```", "").strip()
                final_leads = json.loads(clean_json)
                source_used = "DuckDuckGo + AI"
            except:
                final_leads = raw_ddg # لو الـ AI فشل نرجع الداتا زي ما هي

    if not final_leads:
        raise HTTPException(status_code=404, detail="لم يتم العثور على نتائج.")

    # 3. الحفظ والخصم
    for item in final_leads:
        exists = db.query(models.Lead).filter(models.Lead.name == item.get('title'), models.Lead.user_id == user.id).first()
        if not exists and item.get('title'):
            db.add(models.Lead(
                user_id=user.id, 
                name=item.get('title'), 
                phone=item.get('phone', 'غير متوفر'), 
                status="New"
            ))
    
    user.wallet_balance -= cost
    db.commit()
    
    return {"results": final_leads, "new_balance": user.wallet_balance, "source": source_used}
