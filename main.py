from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
import models, schemas, database
from database import engine, get_db
import google.generativeai as genai
import os
from datetime import datetime

# 1. إعداد الجداول في الداتا بيز
models.Base.metadata.create_all(bind=engine)

# 2. إعداد مفتاح جوجل (Gemini)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    print("Warning: GOOGLE_API_KEY is missing! AI features will not work.")
else:
    genai.configure(api_key=GOOGLE_API_KEY)

# إعدادات الموديل (سريع ومجاني)
generation_config = {
  "temperature": 0.7,
  "top_p": 1,
  "top_k": 1,
  "max_output_tokens": 2048,
}

app = FastAPI(title="Hunter Pro CRM - AI Backend")

# --- Helper Functions ---
def check_balance_and_deduct(user_id: int, cost: int, db: Session):
    """دالة لخصم الرصيد والتأكد من وجوده"""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    
    if user.wallet_balance < cost:
        raise HTTPException(status_code=402, detail=f"عفواً، رصيدك ({user.wallet_balance}) لا يكفي لإتمام العملية. التكلفة: {cost}")
    
    user.wallet_balance -= cost
    return user

# --- 1. بوابات المستخدمين (Users) ---
@app.post("/users/", response_model=schemas.UserResponse)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="البريد الإلكتروني مسجل بالفعل")
    
    # تشفير وهمي (للتجربة)
    fake_hashed_password = user.password + "secret"
    new_user = models.User(
        email=user.email, 
        full_name=user.full_name, 
        hashed_password=fake_hashed_password,
        wallet_balance=50 # هدية 50 نقطة
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.get("/users/{user_id}", response_model=schemas.UserResponse)
def get_user_profile(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# --- 2. المحاور الذكي (AI Chat & Coding) ---
@app.post("/chat/{user_id}", response_model=schemas.ChatResponse)
def chat_with_gemini(user_id: int, request: schemas.ChatRequest, db: Session = Depends(get_db)):
    cost = 2 # تكلفة الشات العادي
    
    # خصم الرصيد
    user = check_balance_and_deduct(user_id, cost, db)
    
    try:
        # استدعاء Gemini
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # تجهيز "برومبت" عشان يفهم إنه مساعد مبرمج ومسوق
        system_instruction = "أنت مساعد ذكي لنظام Hunter Pro CRM. تتحدث العربية وتجيد كتابة الأكواد البرمجية والتسويق."
        full_prompt = f"{system_instruction}\nسؤال المستخدم: {request.message}"
        
        response = model.generate_content(full_prompt, generation_config=generation_config)
        ai_reply = response.text

        # تسجيل المعاملة
        transaction = models.WalletTransaction(
            user_id=user.id, action_type="AI Chat", amount=-cost, description="Chat Message"
        )
        db.add(transaction)
        
        # حفظ الشات
        chat_msg = models.ChatMessage(user_id=user.id, role="user", content=request.message)
        ai_msg = models.ChatMessage(user_id=user.id, role="assistant", content=ai_reply)
        db.add(chat_msg)
        db.add(ai_msg)
        
        db.commit()
        
        return {"response": ai_reply, "tokens_used": cost}
        
    except Exception as e:
        db.rollback() # إلغاء الخصم لو حصل خطأ
        raise HTTPException(status_code=500, detail=str(e))

# --- 3. صانع الحملات (Campaigns Generator) ---
@app.post("/campaigns/generate/{user_id}", response_model=schemas.CampaignResponse)
def generate_campaign_content(user_id: int, campaign_req: schemas.CampaignCreate, db: Session = Depends(get_db)):
    cost = 10 # تكلفة الحملة غالية شوية
    user = check_balance_and_deduct(user_id, cost, db)
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
        تصرف كخبير تسويق إلكتروني. اكتب نص إعلاني جذاب لمنصة فيسبوك وواتساب.
        اسم الحملة: {campaign_req.name}
        التفاصيل: {campaign_req.message_body}
        اكتب النص باللهجة المصرية وبشكل مقنع مع استخدام الإيموجي.
        """
        
        response = model.generate_content(prompt)
        ai_content = response.text
        
        # حفظ الحملة في الداتا بيز
        new_campaign = models.Campaign(
            user_id=user.id,
            name=campaign_req.name,
            message_body=ai_content, # المحتوى اللي الـ AI كتبه
            status="draft"
        )
        
        # تسجيل المعاملة
        transaction = models.WalletTransaction(
            user_id=user.id, action_type="Campaign Gen", amount=-cost, description=f"Campaign: {campaign_req.name}"
        )
        
        db.add(new_campaign)
        db.add(transaction)
        db.commit()
        db.refresh(new_campaign)
        
        return new_campaign
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- 4. العملاء والفيدباك (CRM Core) ---
@app.post("/leads/{user_id}", response_model=schemas.LeadResponse)
def add_lead(user_id: int, lead: schemas.LeadCreate, db: Session = Depends(get_db)):
    new_lead = models.Lead(**lead.dict(), user_id=user_id)
    db.add(new_lead)
    db.commit()
    db.refresh(new_lead)
    return new_lead

@app.post("/leads/{lead_id}/feedback")
def add_customer_feedback(lead_id: int, feedback: schemas.FeedbackCreate, db: Session = Depends(get_db)):
    # ممكن هنا نستخدم AI يحلل هل الفيدباك إيجابي ولا سلبي
    new_feedback = models.CustomerFeedback(**feedback.dict(), lead_id=lead_id)
    db.add(new_feedback)
    db.commit()
    return {"message": "تم حفظ التقييم بنجاح"}

# --- 5. مشاركة البيانات (Data Share) ---
@app.post("/share/{user_id}", response_model=schemas.DataShareResponse)
def create_share_link(user_id: int, share: schemas.DataShareCreate, db: Session = Depends(get_db)):
    new_share = models.DataShare(**share.dict(), user_id=user_id)
    db.add(new_share)
    db.commit()
    db.refresh(new_share)
    
    link = f"https://hunter-pro.app/view/{new_share.share_uuid}"
    return {"share_uuid": new_share.share_uuid, "link_url": link}

# رسالة الصفحة الرئيسية
@app.get("/")
def read_root():
    return {
        "system": "Hunter Pro CRM 🚀",
        "status": "Online",
        "ai_engine": "Google Gemini 1.5 Flash",
        "database": "Connected to Supabase"
    }
