from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# بنجيب رابط الاتصال من متغيرات البيئة عشان الأمان
# لما نرفع على Render هنحط الرابط هناك في الإعدادات
DATABASE_URL = os.getenv("DATABASE_URL")

# إعدادات الاتصال (لو الرابط مش موجود بيستخدم واحد وهمي عشان الكود ميعملش ايرور واحنا بنجرب)
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./test.db"  # داتا بيز مؤقتة للتجربة

# تعديل بسيط عشان التوافق مع بوستجريس
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# دالة عشان نفتح الاتصال ونقفله أوتوماتيك مع كل طلب
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
