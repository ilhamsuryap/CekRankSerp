from app import db # Mengimpor instance db dari app.py
from datetime import datetime
import pytz

from flask_login import UserMixin # Untuk integrasi dengan Flask-Login

# Model User untuk autentikasi dan manajemen user
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="user")  # "admin" or "user"
    is_approved = db.Column(db.Boolean, default=False) # Untuk persetujuan admin
    phone_number = db.Column(db.String(20), nullable=True) # Nomor telepon untuk WhatsApp
    amount_to_pay = db.Column(db.Float, nullable=True) # Jumlah yang harus dibayar saat pendaftaran
    unique_code = db.Column(db.Integer, nullable=True) # Kode unik untuk pembayaran
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relasi dengan RankResult
    rank_results = db.relationship("RankResult", backref="user", lazy=True, cascade="all, delete-orphan")
    # Relasi dengan Payment
    payments = db.relationship("Payment", backref="user", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.email}>"

# Model RankResult untuk menyimpan hasil cek ranking
class RankResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    keyword = db.Column(db.String(255), nullable=False)
    domain = db.Column(db.String(255), nullable=False)
    result = db.Column(db.Text, nullable=False)  # Menyimpan hasil lengkap sebagai JSON string
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(pytz.timezone('Asia/Jakarta')))


    def __repr__(self):
        return f"<RankResult {self.keyword} for {self.domain}>"

# Model Payment untuk mencatat transaksi pembayaran
class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    transaction_id = db.Column(db.String(255), unique=True, nullable=True) # ID transaksi dari gateway pembayaran
    is_completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<Payment {self.id} - User: {self.user_id} - Amount: {self.amount}>"

