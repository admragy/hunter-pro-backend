from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import models, schemas, database
from database import engine, get_db
import google.generativeai as genai
from duckduckgo_search import DDGS
import os
import re
import json

# --- 1. الإعدادات الأولية ---
models.Base.metadata.create_all(bind=engine)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

# إعدادات الموديل (سريع ودقيق)
generation_config = {
  "temperature": 0.7,
  "top_p": 1,
  "top_k": 1,
  "max_output_tokens": 2048,
}

app = FastAPI(title="Hunter Pro Backend")

# --- 2. دوال مساعدة (Helper Functions) ---

def check_balance(user_id: int, cost: int, db: Session):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    if user.wallet_balance < cost:
        raise HTTPException(status_code=402, detail=f"رصيدك غير كافي. العملية تتطلب {cost} توكن")
    return user

def deduct_balance(user, cost: int, action: str, db: Session):
    user.wallet_balance -= cost
    transaction = models.WalletTransaction(
        user_id=user.id, action_type=action, amount=-cost, description=action
    )
    db.add(transaction)
    db.commit()
    db.refresh(user)
    return user.wallet_balance

# --- 3. نماذج البيانات الخاصة بالبحث (Hunt Models) ---
class HuntRequest(BaseModel):
    query: str

class LeadResult(BaseModel):
    title: str
    phone: Optional[str] = "غير متوفر"
    address: Optional[str] = "غير محدد"
    source: Optional[str] = ""

class HuntResponse(BaseModel):
    results: List[LeadResult]
    new_balance: int

# --- 4. البوابات (Endpoints) ---

# الصفحة الرئيسية (تشغيل التطبيق)
@app.get("/", response_class=HTMLResponse)
def read_root():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1 style='color:red;text-align:center'>خطأ: ملف index.html غير مرفوع على السيرفر!</h1>"

# بوابة المستخدمين (Auth)
@app.post("/users/", response_model=schemas.UserResponse)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        return db_user # لو موجود رجعه عشان الدخول
    
    new_user = models.User(
        email=user.email, full_name=user.full_name,
        hashed_password=user.password + "hash", wallet_balance=50
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    return user

# بوابة الشات (AI Chat)
@app.post("/chat/{user_id}", response_model=schemas.ChatResponse)
def chat_ai(user_id: int, request: schemas.ChatRequest, db: Session = Depends(get_db)):
    cost = 2
    user = check_balance(user_id, cost, db)
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"أنت مساعد في نظام CRM يسمى Hunter Pro. أجب باختصار واحترافية. سؤال المستخدم: {request.message}"
        response = model.generate_content(prompt)
        reply = response.text
        
        # خصم وحفظ
        deduct_balance(user, cost, "AI Chat", db)
        
        # حفظ الرسالة (اختياري لعدم تضخيم الكود)
        # ... كود الحفظ في models.ChatMessage ...

        return {"response": reply, "tokens_used": cost}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 🔥 بوابة الصياد (Lead Hunter) - الميزة الجديدة 🔥
@app.post("/hunt/{user_id}", response_model=HuntResponse)
def run_hunter(user_id: int, request: HuntRequest, db: Session = Depends(get_db)):
    cost = 20 # تكلفة البحث
    user = check_balance(user_id, cost, db)
    
    results_list = []
    
    try:
        # 1. البحث في DuckDuckGo
        with DDGS() as ddgs:
            # نبحث عن نتائج تحتوي على أرقام هواتف أو عناوين
            search_query = f"{request.query} رقم تليفون عنوان contact info"
            ddg_results = list(ddgs.text(search_query, max_results=8))
        
        # 2. استخدام Gemini لاستخراج البيانات من النتائج (تنظيف الداتا)
        if ddg_results:
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            # نجهز الداتا للذكاء الاصطناعي
            data_str = json.dumps(ddg_results, ensure_ascii=False)
            prompt = f"""
            لديك نتائج بحث خام بتنسيق JSON. استخرج منها قائمة بالشركات/الأشخاص.
            أريد الإخراج بتنسيق JSON List فقط بدون أي نصوص إضافية.
            لكل عنصر استخرج: "title" (الاسم), "phone" (رقم الهاتف إن وجد), "address" (العنوان إن وجد).
            إذا لم تجد رقم هاتف، اكتب "غير متوفر".
            البيانات الخام:
            {data_str}
            """
            
            ai_response = model.generate_content(prompt)
            cleaned_text = ai_response.text.replace("```json", "").replace("```", "").strip()
            
            try:
                results_list = json.loads(cleaned_text)
            except:
                # لو الـ AI معرفش يظبط الـ JSON، نرجع النتائج الخام
                for res in ddg_results:
                    results_list.append({
                        "title": res.get('title'),
                        "phone": "تحتاج زيارة الموقع",
                        "address": res.get('body')
                    })

        # 3. حفظ النتائج في الداتا بيز (Leads Table)
        for item in results_list:
            # تأكد من عدم التكرار (اختياري)
            new_lead = models.Lead(
                user_id=user.id,
                name=item.get("title", "Unknown"),
                phone=item.get("phone", ""),
                # يمكن إضافة العنوان في الـ status مؤقتاً أو تعديل الموديل
                status="New Lead" 
            )
            db.add(new_lead)
        
        # 4. خصم الرصيد
        new_balance = deduct_balance(user, cost, f"Hunter: {request.query}", db)
        
        return {"results": results_list, "new_balance": new_balance}

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail="فشل عملية البحث، حاول مرة أخرى لاحقاً.")

