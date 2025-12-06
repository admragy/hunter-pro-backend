from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
import models, schemas, database
from database import engine, get_db
import google.generativeai as genai
import os

# إعداد قاعدة البيانات
models.Base.metadata.create_all(bind=engine)

# إعداد ذكاء جوجل (Gemini)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

app = FastAPI(title="Hunter Pro AI Backend")

# --- بوابات المستخدمين (Users) ---
@app.post("/users/", response_model=schemas.UserResponse)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    fake_hashed_password = user.password + "notreallyhashed"
    new_user = models.User(
        email=user.email, 
        full_name=user.full_name, 
        hashed_password=fake_hashed_password,
        wallet_balance=50 # هدية التسجيل
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

# --- بوابة الشات الذكي (Gemini Powered) ---
@app.post("/chat/{user_id}", response_model=schemas.ChatResponse)
def chat_with_ai(user_id: int, request: schemas.ChatRequest, db: Session = Depends(get_db)):
    # 1. التحقق من المستخدم والرصيد
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    cost = 1
    if user.wallet_balance < cost:
        raise HTTPException(status_code=402, detail="رصيدك لا يسمح! يرجى الشحن.")

    # 2. استدعاء Gemini
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        # لو فيه صورة (مستقبلاً) ممكن نبعتها هنا، حالياً نص فقط
        response = model.generate_content(request.message)
        ai_reply = response.text
    except Exception as e:
        ai_reply = f"عفواً، حدث خطأ في الاتصال بالذكاء الاصطناعي: {str(e)}"

    # 3. خصم الرصيد وحفظ العملية
    user.wallet_balance -= cost
    
    transaction = models.WalletTransaction(
        user_id=user.id, action_type="Chat Message", amount=-cost, description="Gemini AI Chat"
    )
    chat_msg = models.ChatMessage(user_id=user.id, role="user", content=request.message)
    ai_msg = models.ChatMessage(user_id=user.id, role="assistant", content=ai_reply)

    db.add(transaction)
    db.add(chat_msg)
    db.add(ai_msg)
    db.commit()
    
    return {"response": ai_reply, "tokens_used": cost}

# رسالة ترحيب
@app.get("/")
def read_root():
    return {"message": "Hunter Pro AI (Gemini Edition) is Online! 🚀"}
