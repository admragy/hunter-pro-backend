from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

# --- 1. схemas للمستخدم (User) ---
class UserBase(BaseModel):
    email: str
    full_name: str

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    wallet_balance: int
    is_admin: bool
    preferred_language: str

    class Config:
        from_attributes = True

# --- 2. schemas للمحفظة (Wallet) ---
class TransactionResponse(BaseModel):
    id: int
    amount: int
    description: str
    created_at: datetime

    class Config:
        from_attributes = True

# --- 3. schemas للشات (Chat) ---
class ChatRequest(BaseModel):
    message: str
    image_url: Optional[str] = None # لو باعت صورة يحللها

class ChatResponse(BaseModel):
    response: str
    media_url: Optional[str] = None
    tokens_used: int

# --- 4. schemas للعملاء (Leads & Feedback) ---
class FeedbackCreate(BaseModel):
    rating: int # 1 to 5
    comment: str

class LeadCreate(BaseModel):
    name: str
    phone: str
    status: str = "new"

class LeadResponse(LeadCreate):
    id: int
    feedbacks: List[FeedbackCreate] = [] # يرجع معاه الفيدباك بتاعه

    class Config:
        from_attributes = True

# --- 5. schemas لمشاركة البيانات (Data Share) ---
class DataShareCreate(BaseModel):
    resource_type: str # "lead_list", "campaign"
    resource_id: int
    password_protected: Optional[str] = None

class DataShareResponse(BaseModel):
    share_uuid: str
    link_url: str # الرابط النهائي للمشاركة

# --- 6. schemas للحملات (Campaigns) ---
class CampaignCreate(BaseModel):
    name: str
    message_body: str
    target_filter: Optional[str] = None

class CampaignResponse(CampaignCreate):
    id: int
    status: str
    image_url: Optional[str] = None

    class Config:
        from_attributes = True
