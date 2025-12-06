# 1. بنختار نسخة بايثون خفيفة وسريعة
FROM python:3.9-slim

# 2. بنعمل فولدر جوه السيرفر نحط فيه ملفاتنا
WORKDIR /app

# 3. بننسخ ملف المكتبات الأول ونسطبها (عشان السرعة)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. بننسخ باقي ملفات المشروع (main.py, models.py, etc)
COPY . .

# 5. بنفتح البورت 8080 (Fly.io بيحب البورت ده)
EXPOSE 8080

# 6. أمر التشغيل (الموتور)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
