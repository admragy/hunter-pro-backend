from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import models, schemas, database
from database import engine, get_db

# 1. إنشاء جداول الداتا بيز (لو مش موجودة)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Hunter Pro AI Backend")

# --- بوابات المستخدمين (Users) ---
@app.post("/users/", response_model=schemas.UserResponse)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # نتأكد إن الإيميل مش متسجل قبل كده
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # نكريت اليوزر الجديد ونديله 50 توكين هدية
    fake_hashed_password = user.password + "notreallyhashed"
    new_user = models.User(
        email=user.email, 
        full_name=user.full_name, 
        hashed_password=fake_hashed_password,
        wallet_balance=50 # الهدية
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

# --- بوابة الشات الذكي (The AI Chat) ---
@app.post("/chat/{user_id}", response_model=schemas.ChatResponse)
def chat_with_ai(user_id: int, request: schemas.ChatRequest, db: Session = Depends(get_db)):
    # 1. نجيب اليوزر ونشيك على الرصيد
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    cost = 1 # تكلفة الرسالة العادية
    if request.image_url:
        cost = 10 # تكلفة تحليل الصور أغلى
        
    if user.wallet_balance < cost:
        raise HTTPException(status_code=402, detail="رصيدك لا يسمح! يرجى الشحن.")

    # 2. (هنا هنحط كود OpenAI الحقيقي لاحقاً)
    # دلوقتي هنرد برد تجريبي عشان نتأكد إن السيستم شغال
    ai_reply = f"أهلاً يا {user.full_name}! أنا استلمت رسالتك: '{request.message}'. (هذا رد تجريبي، رصيدك شغال تمام!)"
    
    # 3. نخصم الرصيد ونسجل المعاملة
    user.wallet_balance -= cost
    
    # نسجل العملية في الهيستوري
    transaction = models.WalletTransaction(
        user_id=user.id,
        action_type="Chat Message",
        amount=-cost,
        description="AI Chat Request"
    )
    
    # نسجل الرسالة في الشات
    chat_msg = models.ChatMessage(user_id=user.id, role="user", content=request.message)
    ai_msg = models.ChatMessage(user_id=user.id, role="assistant", content=ai_reply)

    db.add(transaction)
    db.add(chat_msg)
    db.add(ai_msg)
    db.commit()
    
    return {"response": ai_reply, "tokens_used": cost}

# --- بوابة العملاء والفيدباك (Leads & Feedback) ---
@app.post("/leads/{user_id}", response_model=schemas.LeadResponse)
def create_lead(user_id: int, lead: schemas.LeadCreate, db: Session = Depends(get_db)):
    new_lead = models.Lead(**lead.dict(), user_id=user_id)
    db.add(new_lead)
    db.commit()
    db.refresh(new_lead)
    return new_lead

@app.post("/leads/{lead_id}/feedback")
def add_feedback(lead_id: int, feedback: schemas.FeedbackCreate, db: Session = Depends(get_db)):
    # إضافة رأي عن العميل
    new_feedback = models.CustomerFeedback(**feedback.dict(), lead_id=lead_id)
    db.add(new_feedback)
    db.commit()
    return {"message": "Feedback added successfully"}

# --- بوابة مشاركة البيانات (Data Share) ---
@app.post("/share/{user_id}", response_model=schemas.DataShareResponse)
def create_share_link(user_id: int, share: schemas.DataShareCreate, db: Session = Depends(get_db)):
    # إنشاء رابط مشاركة جديد
    new_share = models.DataShare(**share.dict(), user_id=user_id)
    db.add(new_share)
    db.commit()
    db.refresh(new_share)
    
    # نرجع الرابط النهائي
    link = f"https://hunter-pro.app/view/{new_share.share_uuid}"
    return {"share_uuid": new_share.share_uuid, "link_url": link}

# رسالة ترحيب عشان نتأكد إن السيرفر شغال
@app.get("/")
def read_root():
    return {"message": "Hunter Pro AI System is Online! 🚀"}
