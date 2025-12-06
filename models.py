from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import uuid

# 1. جدول المستخدمين (الأساس)
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    
    # المحفظة والاشتراكات
    wallet_balance = Column(Integer, default=50) # رصيد ابتدائي 50 توكين
    is_admin = Column(Boolean, default=False)
    preferred_language = Column(String, default="ar") # "ar" or "en"

    # العلاقات مع الجداول التانية
    leads = relationship("Lead", back_populates="owner")
    campaigns = relationship("Campaign", back_populates="owner")
    transactions = relationship("WalletTransaction", back_populates="user")
    chats = relationship("ChatMessage", back_populates="user")
    shared_links = relationship("DataShare", back_populates="creator")

# 2. جدول العملاء (Leads)
class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    name = Column(String)
    phone = Column(String)
    status = Column(String, default="new") # new, contacted, closed
    
    # علاقة الفيدباك
    feedbacks = relationship("CustomerFeedback", back_populates="lead")
    owner = relationship("User", back_populates="leads")

# 3. ميزة الفيدباك (Customer Feedback)
class CustomerFeedback(Base):
    __tablename__ = "customer_feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    
    rating = Column(Integer) # تقييم 1-5
    comment = Column(Text)   # ملاحظات العميل
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    lead = relationship("Lead", back_populates="feedbacks")

# 4. ميزة مشاركة البيانات (Data Share)
class DataShare(Base):
    __tablename__ = "data_shares"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    share_uuid = Column(String, default=lambda: str(uuid.uuid4()), unique=True) # رابط سري فريد
    resource_type = Column(String) # "lead_list" or "campaign_report"
    resource_id = Column(Integer)
    is_active = Column(Boolean, default=True)
    
    creator = relationship("User", back_populates="shared_links")

# 5. جدول الحملات (Campaigns & WhatsApp)
class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    name = Column(String)
    message_body = Column(Text) # نص الرسالة
    image_url = Column(String, nullable=True) # صورة الـ AI
    status = Column(String, default="draft")
    
    owner = relationship("User", back_populates="campaigns")

# 6. سجل المحفظة (Transactions)
class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    amount = Column(Integer) # كم توكين اتخصم أو اتضاف
    description = Column(String) # وصف العملية
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="transactions")

# 7. سجل الشات (Chat History)
class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    role = Column(String) # "user" or "assistant"
    content = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="chats")
