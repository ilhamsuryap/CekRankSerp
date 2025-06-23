# Import modul yang diperlukan
import os
import requests
from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import json
import random

# For PDF generation
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

# For XLSX generation
import openpyxl

# Inisialisasi aplikasi Flask
app = Flask(__name__)

# Konfigurasi database SQLite
# Menggunakan path absolut untuk database
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "db.sqlite3")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "your_super_secret_key_here" # Ganti dengan kunci rahasia yang kuat

# Inisialisasi ekstensi
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = "login" # Menentukan rute untuk login

# Tambahkan filter kustom Jinja2 untuk mem-parse JSON string
# Ini akan memungkinkan penggunaan `{{ data_string | from_json }}` di template
import json
app.jinja_env.filters['from_json'] = lambda s: json.loads(s) if s else {}

# Import model setelah db diinisialisasi untuk menghindari circular import
# Pastikan models.py ada di direktori yang sama atau di PYTHONPATH
from models import User, RankResult, Payment

# Konfigurasi login manager
@login_manager.user_loader
def load_user(user_id):
    """
    Memuat user dari ID untuk Flask-Login.
    """
    return User.query.get(int(user_id))

# API Key untuk SerpApi (sebaiknya disimpan di variabel lingkungan)
SERPAPI_API_KEY = "572db24d1b3554570e4013212f0b26160f44709c398abb0a65dee3428e1ed4e6"

# API Key dan URL untuk Quods.id (Ganti dengan API key dan URL Anda yang sebenarnya)
# QUODS_BASE_URL diubah agar sesuai dengan endpoint API Quods.id
QUODS_API_KEY = "TMeTyUimv75LmlHRlCutowWU2z86QW" # Ganti dengan API key Quods.id Anda
QUODS_BASE_URL = "https://api.quods.id/api" # Base URL untuk Quods.id API (seperti di dokumentasi)
QUODS_DEVICE_KEY = "UMSZSzMyen40UdD" # Anda perlu mendapatkan ini dari API Quods.id Info User: https://api.quods.id/api/user

def send_whatsapp_notification(phone_number, message):
    """
    Mengirim notifikasi WhatsApp menggunakan Quods.id API (metode Direct Send).
    Dokumentasi: B. Message | 3. Send Direct Message
    """
    headers = {
        "Authorization": f"Bearer {QUODS_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "device_key": QUODS_DEVICE_KEY, # Diperlukan oleh API Quods.id untuk Direct Send
        "phone": phone_number,          # Menggunakan 'phone' sesuai dokumentasi Quods.id
        "message": message
    }
    try:
        # Endpoint diubah menjadi /direct-send sesuai dokumentasi
        response = requests.post(f"{QUODS_BASE_URL}/direct-send", headers=headers, json=payload)
        response.raise_for_status() # Akan memunculkan HTTPError untuk status kode error
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error sending WhatsApp notification: {e}")
        return {"error": str(e)}

def get_ranks_serpapi(keyword, domain, hl, gl, google_domain, num):
    """
    Mengambil data ranking dari SerpApi.
    """
    params = {
        "engine": "google",
        "q": keyword,
        "google_domain": google_domain,
        "hl": hl,
        "gl": gl,
        "num": num,
        "api_key": SERPAPI_API_KEY
    }
    try:
        response = requests.get("https://serpapi.com/search", params=params)
        response.raise_for_status() # Akan memunculkan HTTPError untuk status kode error
        data = response.json()

        ranks = []
        total_found_count = 0
        if "organic_results" in data:
            for idx, result in enumerate(data["organic_results"]):
                link = result.get("link", "")
                # Periksa apakah domain target ada dalam link hasil
                if domain in link:
                    total_found_count += 1
                    ranks.append({
                        "position": idx + 1,
                        "link": link,
                        "title": result.get("title", "No Title")
                    })
        return ranks, total_found_count
    except requests.exceptions.RequestException as e:
        flash(f"Error fetching SERP data: {e}", "error")
        return [], 0


# Rute untuk Landing Page
@app.route("/landing")
def landing_page():
    """
    Menampilkan halaman landing utama aplikasi.
    """
    return render_template("landing_page.html", now=datetime.utcnow())

# Rute utama (akan dialihkan ke landing page jika belum login)
@app.route("/", methods=["GET", "POST"])
@login_required # Membutuhkan login untuk mengakses halaman ini
def index():
    """
    Halaman utama untuk memeriksa ranking SERP.
    """
    result_data = None
    if request.method == "POST":
        domain = request.form["domain"]
        keyword = request.form["keyword"]
        hl = request.form["hl"]
        gl = request.form["gl"]
        google_domain = request.form["google_domain"]
        num = request.form["num"]

        ranks, total_found = get_ranks_serpapi(keyword, domain, hl, gl, google_domain, num)
        
        result_data = {
            "domain": domain,
            "keyword": keyword,
            "total_found": total_found,
            "ranks": ranks
        }

        # Simpan hasil ke database jika user login
        if current_user.is_authenticated:
            new_rank_result = RankResult(
                keyword=keyword,
                domain=domain,
                result=json.dumps(result_data), # Simpan sebagai JSON string
                user_id=current_user.id
            )
            db.session.add(new_rank_result)
            db.session.commit()
            flash("Hasil ranking berhasil disimpan!", "success")

    return render_template("index.html", result=result_data, now=datetime.utcnow())

# Rute untuk login
@app.route("/login", methods=["GET", "POST"])
def login():
    """
    Menangani proses login user.
    """
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        remember = True if request.form.get("remember_me") else False

        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password, password):
            flash("Silakan periksa email atau password Anda dan coba lagi.", "error")
            return redirect(url_for("login"))
        
        if not user.is_approved and user.role != 'admin':
            flash("Akun Anda belum disetujui oleh admin. Mohon tunggu.", "warning")
            return redirect(url_for("login"))

        login_user(user, remember=remember)
        return redirect(url_for("dashboard"))

    return render_template("login.html", now=datetime.utcnow())

# Rute untuk pendaftaran
@app.route("/register", methods=["GET", "POST"])
def register():
    """
    Menangani proses pendaftaran user baru.
    """
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        phone_number = request.form["phone_number"] # Untuk notifikasi WhatsApp

        # Validasi sederhana
        if password != confirm_password:
            flash("Konfirmasi password tidak cocok.", "error")
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash("Email sudah terdaftar. Silakan login atau gunakan email lain.", "error")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)
        
        # Buat kode unik pembayaran
        unique_code = random.randint(100, 999) # Kode unik 3 digit
        amount_to_pay = 50000 + unique_code # Contoh: Rp 50.000 + kode unik

        new_user = User(
            email=email, 
            password=hashed_password, 
            phone_number=phone_number,
            amount_to_pay=amount_to_pay,
            unique_code=unique_code # Simpan kode unik
        )
        db.session.add(new_user)
        db.session.commit()

        # Kirim notifikasi WhatsApp ke user
        whatsapp_message = (
            f"Terima kasih telah mendaftar! "
            f"Untuk mengaktifkan akun Anda, mohon lakukan pembayaran sebesar Rp {amount_to_pay:,} "
            f"ke rekening [Nomor Rekening Anda] a/n [Nama Bank Anda]. "
            f"Sertakan kode unik {unique_code} di belakang nominal. "
            f"Setelah pembayaran diverifikasi, admin akan menyetujui akun Anda. "
            f"Jangan lupa simpan email: {email} sebagai username Anda."
        )
        send_whatsapp_notification(phone_number, whatsapp_message)
        
        flash("Akun Anda berhasil dibuat. Mohon lakukan pembayaran dan tunggu persetujuan admin.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", now=datetime.utcnow())

# Rute untuk lupa password (placeholder, implementasi lebih lanjut diperlukan)
@app.route("/forgot_password")
def forgot_password():
    """
    Halaman untuk reset password.
    """
    flash("Fitur reset password belum diimplementasikan sepenuhnya.", "info")
    return render_template("forgot_password.html", now=datetime.utcnow())

# Rute untuk logout
@app.route("/logout")
@login_required
def logout():
    """
    Menangani proses logout user.
    """
    logout_user()
    flash("Anda telah berhasil keluar.", "info")
    return redirect(url_for("login")) # Tidak perlu now di redirect

# Rute Dashboard
@app.route("/dashboard")
@login_required
def dashboard():
    """
    Menampilkan dashboard berdasarkan role user.
    """
    if current_user.role == "admin":
        # Data untuk dashboard admin
        pending_users = User.query.filter_by(is_approved=False).all()
        all_users = User.query.all()
        all_rank_results = RankResult.query.all()
        all_payments = Payment.query.all()
        return render_template(
            "dashboard_admin.html", 
            pending_users=pending_users, 
            all_users=all_users,
            all_rank_results=all_rank_results,
            all_payments=all_payments,
            now=datetime.utcnow() # Tambahkan now
        )
    else:
        # Data untuk dashboard user
        user_rank_results = RankResult.query.filter_by(user_id=current_user.id).order_by(RankResult.created_at.desc()).all()
        return render_template("dashboard_user.html", user_rank_results=user_rank_results, now=datetime.utcnow())

# Rute untuk menyetujui user (hanya untuk admin)
@app.route("/approve_user/<int:user_id>")
@login_required
def approve_user(user_id):
    """
    Menyetujui akun user. Hanya bisa diakses oleh admin.
    """
    if current_user.role != "admin":
        flash("Anda tidak memiliki izin untuk melakukan tindakan ini.", "error")
        return redirect(url_for("dashboard"))

    user_to_approve = User.query.get_or_404(user_id)
    user_to_approve.is_approved = True
    db.session.commit()
    
    # Kirim notifikasi WhatsApp ke user yang disetujui
    if user_to_approve.phone_number:
        whatsapp_message = (
            f"Selamat! Akun Anda ({user_to_approve.email}) telah disetujui. "
            f"Anda sekarang dapat login dan mulai menggunakan fitur cek ranking SERP kami."
        )
        send_whatsapp_notification(user_to_approve.phone_number, whatsapp_message)

    flash(f"User {user_to_approve.email} berhasil disetujui.", "success")
    return redirect(url_for("dashboard"))

# Rute untuk menghapus user (hanya untuk admin)
@app.route("/delete_user/<int:user_id>")
@login_required
def delete_user(user_id):
    """
    Menghapus akun user. Hanya bisa diakses oleh admin.
    """
    if current_user.role != "admin":
        flash("Anda tidak memiliki izin untuk melakukan tindakan ini.", "error")
        return redirect(url_for("dashboard"))

    user_to_delete = User.query.get_or_404(user_id)
    # Hapus juga semua hasil ranking terkait user ini
    RankResult.query.filter_by(user_id=user_to_delete.id).delete()
    Payment.query.filter_by(user_id=user_to_delete.id).delete()
    db.session.delete(user_to_delete)
    db.session.commit()
    flash(f"User {user_to_delete.email} dan semua datanya berhasil dihapus.", "success")
    return redirect(url_for("dashboard"))

# Rute untuk menandai pembayaran selesai (hanya untuk admin)
@app.route("/mark_payment_complete/<int:payment_id>")
@login_required
def mark_payment_complete(payment_id):
    """
    Menandai pembayaran sebagai selesai. Hanya bisa diakses oleh admin.
    """
    if current_user.role != "admin":
        flash("Anda tidak memiliki izin untuk melakukan tindakan ini.", "error")
        return redirect(url_for("dashboard"))

    payment = Payment.query.get_or_404(payment_id)
    payment.is_completed = True
    payment.completed_at = datetime.utcnow()
    db.session.commit()
    flash(f"Pembayaran {payment.id} berhasil ditandai sebagai selesai.", "success")
    return redirect(url_for("dashboard"))

# Rute API untuk konfirmasi pembayaran otomatis (misal dari webhook payment gateway)
@app.route("/api/confirm_payment", methods=["POST"])
def api_confirm_payment():
    """
    Endpoint API untuk mengkonfirmasi pembayaran.
    Ini adalah contoh endpoint yang bisa dipanggil oleh sistem pembayaran (misal webhook).
    """
    data = request.json
    transaction_id = data.get("transaction_id")
    amount_paid = data.get("amount")
    unique_code_from_payment = data.get("unique_code") # Kode unik dari pembayaran
    user_email_or_id = data.get("user_identifier") # Email atau ID user dari sistem pembayaran

    # Cari user berdasarkan email atau ID
    user = User.query.filter_by(email=user_email_or_id).first()
    if not user:
        return jsonify({"message": "User not found"}), 404

    # Verifikasi kode unik dan jumlah pembayaran
    # Ini adalah logika sederhana, Anda mungkin perlu logika yang lebih kuat
    if user.unique_code == unique_code_from_payment and amount_paid >= user.amount_to_pay:
        # Tandai pembayaran sebagai selesai
        payment = Payment(
            user_id=user.id,
            amount=amount_paid,
            transaction_id=transaction_id,
            is_completed=True,
            completed_at=datetime.utcnow()
        )
        db.session.add(payment)
        # Set is_approved menjadi True jika pembayaran dikonfirmasi otomatis
        user.is_approved = True 
        db.session.commit()

        # Kirim notifikasi WhatsApp ke user
        if user.phone_number:
            whatsapp_message = (
                f"Pembayaran Anda sebesar Rp {amount_paid:,} telah berhasil dikonfirmasi! "
                f"Akun Anda ({user.email}) telah diaktifkan."
            )
            send_whatsapp_notification(user.phone_number, whatsapp_message)

        return jsonify({"message": "Payment confirmed and user approved"}), 200
    else:
        return jsonify({"message": "Payment verification failed"}), 400

# Rute untuk menampilkan detail hasil ranking (dari dashboard user/admin)
@app.route("/rank_result/<int:result_id>")
@login_required
def view_rank_result(result_id):
    """
    Menampilkan detail hasil ranking yang disimpan.
    """
    rank_result = RankResult.query.get_or_404(result_id)
    # Pastikan user hanya bisa melihat hasil rankingnya sendiri, kecuali admin
    if current_user.role != "admin" and rank_result.user_id != current_user.id:
        flash("Anda tidak memiliki izin untuk melihat hasil ini.", "error")
        return redirect(url_for("dashboard"))
    
    # Parse string JSON kembali ke objek Python
    result_data = json.loads(rank_result.result)
    return render_template("view_rank_result.html", result=result_data, rank_result_obj=rank_result, now=datetime.utcnow())


## Download Rank Result Route
@app.route('/download_rank_result/<int:result_id>/<string:file_format>')
@login_required
def download_rank_result(result_id, file_format):
    """
    Memungkinkan user untuk mengunduh hasil rank dalam format PDF atau XLSX.
    """
    rank_result_obj = RankResult.query.get_or_404(result_id)

    # Pastikan user hanya bisa mengunduh hasil rankingnya sendiri, kecuali admin
    if current_user.role != "admin" and rank_result_obj.user_id != current_user.id:
        flash("Anda tidak memiliki izin untuk mengunduh hasil ini.", "error")
        return redirect(url_for("dashboard"))

    result_data = json.loads(rank_result_obj.result)

    if file_format == 'pdf':
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []

        # Header informasi umum
        elements.append(Paragraph(f"<b>Detail Hasil Cek Ranking</b>", styles['h1']))
        elements.append(Paragraph(f"Kata Kunci: <b>{result_data.get('keyword', 'N/A')}</b>", styles['Normal']))
        elements.append(Paragraph(f"Domain Target: <b>{result_data.get('domain', 'N/A')}</b>", styles['Normal']))
        elements.append(Paragraph(f"Ditemukan di: <b>{result_data.get('total_found', 0)}</b> posisi", styles['Normal']))
        elements.append(Paragraph(f"Dicek Pada: <b>{rank_result_obj.created_at.strftime('%d %b %Y %H:%M')}</b>", styles['Normal']))
        elements.append(Paragraph(f"Dicek Oleh: <b>{rank_result_obj.user.email if rank_result_obj.user else 'N/A'}</b>", styles['Normal']))
        elements.append(Spacer(1, 12)) # Add some space

        if result_data.get('ranks'):
            elements.append(Paragraph(f"<b>Posisi Ditemukan:</b>", styles['h2']))
            data = [['Posisi', 'Judul', 'URL']]
            for item in result_data['ranks']:
                data.append([str(item.get('position', '')), item.get('title', ''), item.get('link', '')])

            table = Table(data, colWidths=[50, 200, 250]) # Set column widths
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E0E0E0')), # Lighter grey for header
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('FONTSIZE', (0,0), (-1,-1), 9), # Smaller font for table content
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('LEFTPADDING', (0,0), (-1,-1), 6),
                ('RIGHTPADDING', (0,0), (-1,-1), 6),
                ('TOPPADDING', (0,0), (-1,-1), 6),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6),
                ('WORDWRAP', (2,0), (2,-1), True), # Word wrap for URL column
            ]))
            elements.append(table)
        else:
            elements.append(Paragraph("Domain tidak ditemukan dalam hasil pencarian untuk kata kunci ini, atau data rank tidak tersedia.", styles['Normal']))

        doc.build(elements)
        buffer.seek(0)
        filename = f"SERP_Rank_Result_{result_data.get('keyword', 'unknown').replace(' ', '_')}_{datetime.now().strftime('%Y%m%d%H%M')}.pdf"
        return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

    elif file_format == 'xlsx':
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "SERP Rank Results"

        # General information
        sheet['A1'] = "Detail Hasil Cek Ranking"
        sheet['A2'] = "Kata Kunci:"
        sheet['B2'] = result_data.get('keyword', 'N/A')
        sheet['A3'] = "Domain Target:"
        sheet['B3'] = result_data.get('domain', 'N/A')
        sheet['A4'] = "Ditemukan di:"
        sheet['B4'] = f"{result_data.get('total_found', 0)} posisi"
        sheet['A5'] = "Dicek Pada:"
        sheet['B5'] = rank_result_obj.created_at.strftime('%d %b %Y %H:%M')
        sheet['A6'] = "Dicek Oleh:"
        sheet['B6'] = rank_result_obj.user.email if rank_result_obj.user else 'N/A'

        # Add a blank row for separation
        sheet.append([])
        sheet.append([])
        
        if result_data.get('ranks'):
            sheet.append(['Posisi', 'Judul', 'URL'])
            for item in result_data['ranks']:
                sheet.append([item.get('position', ''), item.get('title', ''), item.get('link', '')])
            
            # Auto-size columns for better readability
            for column in sheet.columns:
                max_length = 0
                column_letter = column[0].column_letter # Get the column letter
                for cell in column:
                    try: # Necessary to avoid error on empty cells
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = (max_length + 2) * 1.2 # Add padding
                sheet.column_dimensions[column_letter].width = adjusted_width
        else:
            sheet.append(["Domain tidak ditemukan dalam hasil pencarian untuk kata kunci ini, atau data rank tidak tersedia."])


        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        filename = f"SERP_Rank_Result_{result_data.get('keyword', 'unknown').replace(' ', '_')}_{datetime.now().strftime('%Y%m%d%H%M')}.xlsx"
        return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    else:
        flash("Format file tidak didukung.", "error")
        return redirect(url_for('view_rank_result', result_id=result_id))



# # Import modul yang diperlukan
# import os
# import requests
# from flask import Flask, request, render_template, redirect, url_for, flash, jsonify
# from flask_sqlalchemy import SQLAlchemy
# from flask_migrate import Migrate
# from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
# from werkzeug.security import generate_password_hash, check_password_hash
# from datetime import datetime, timedelta
# import json
# import random

# # Inisialisasi aplikasi Flask
# app = Flask(__name__)

# # Konfigurasi database SQLite
# # Menggunakan path absolut untuk database
# basedir = os.path.abspath(os.path.dirname(__file__))
# app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "db.sqlite3")
# app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# app.config["SECRET_KEY"] = "your_super_secret_key_here" # Ganti dengan kunci rahasia yang kuat

# # Inisialisasi ekstensi
# db = SQLAlchemy(app)
# migrate = Migrate(app, db)
# login_manager = LoginManager(app)
# login_manager.login_view = "login" # Menentukan rute untuk login

# # Tambahkan filter kustom Jinja2 untuk mem-parse JSON string
# # Ini akan memungkinkan penggunaan `{{ data_string | from_json }}` di template
# import json
# app.jinja_env.filters['from_json'] = lambda s: json.loads(s) if s else {}

# # Import model setelah db diinisialisasi untuk menghindari circular import
# from models import User, RankResult, Payment

# # Konfigurasi login manager
# @login_manager.user_loader
# def load_user(user_id):
#     """
#     Memuat user dari ID untuk Flask-Login.
#     """
#     return User.query.get(int(user_id))

# # API Key untuk SerpApi (sebaiknya disimpan di variabel lingkungan)
# SERPAPI_API_KEY = "572db24d1b3554570e4013212f0b26160f44709c398abb0a65dee3428e1ed4e6"

# # API Key dan URL untuk Quods.id (Ganti dengan API key dan URL Anda yang sebenarnya)
# # QUODS_BASE_URL diubah agar sesuai dengan endpoint API Quods.id
# QUODS_API_KEY = "YOUR_QUODS_API_KEY" # Ganti dengan API key Quods.id Anda
# QUODS_BASE_URL = "https://api.quods.id/api" # Base URL untuk Quods.id API (seperti di dokumentasi)
# QUODS_DEVICE_KEY = "YOUR_QUODS_DEVICE_KEY" # Anda perlu mendapatkan ini dari API Quods.id Info User: https://api.quods.id/api/user

# def send_whatsapp_notification(phone_number, message):
#     """
#     Mengirim notifikasi WhatsApp menggunakan Quods.id API (metode Direct Send).
#     Dokumentasi: B. Message | 3. Send Direct Message
#     """
#     headers = {
#         "Authorization": f"Bearer {QUODS_API_KEY}",
#         "Content-Type": "application/json"
#     }
#     payload = {
#         "device_key": QUODS_DEVICE_KEY, # Diperlukan oleh API Quods.id untuk Direct Send
#         "phone": phone_number,          # Menggunakan 'phone' sesuai dokumentasi Quods.id
#         "message": message
#     }
#     try:
#         # Endpoint diubah menjadi /direct-send sesuai dokumentasi
#         response = requests.post(f"{QUODS_BASE_URL}/direct-send", headers=headers, json=payload)
#         response.raise_for_status() # Akan memunculkan HTTPError untuk status kode error
#         return response.json()
#     except requests.exceptions.RequestException as e:
#         print(f"Error sending WhatsApp notification: {e}")
#         return {"error": str(e)}

# def get_ranks_serpapi(keyword, domain, hl, gl, google_domain, num):
#     """
#     Mengambil data ranking dari SerpApi.
#     """
#     params = {
#         "engine": "google",
#         "q": keyword,
#         "google_domain": google_domain,
#         "hl": hl,
#         "gl": gl,
#         "num": num,
#         "api_key": SERPAPI_API_KEY
#     }
#     try:
#         response = requests.get("https://serpapi.com/search", params=params)
#         response.raise_for_status() # Akan memunculkan HTTPError untuk status kode error
#         data = response.json()

#         ranks = []
#         total_found_count = 0
#         if "organic_results" in data:
#             for idx, result in enumerate(data["organic_results"]):
#                 link = result.get("link", "")
#                 # Periksa apakah domain target ada dalam link hasil
#                 if domain in link:
#                     total_found_count += 1
#                     ranks.append({
#                         "position": idx + 1,
#                         "link": link,
#                         "title": result.get("title", "No Title")
#                     })
#         return ranks, total_found_count
#     except requests.exceptions.RequestException as e:
#         flash(f"Error fetching SERP data: {e}", "error")
#         return [], 0


# # Rute untuk Landing Page
# @app.route("/landing")
# def landing_page():
#     """
#     Menampilkan halaman landing utama aplikasi.
#     """
#     return render_template("landing_page.html", now=datetime.utcnow())

# # Rute utama (akan dialihkan ke landing page jika belum login)
# @app.route("/", methods=["GET", "POST"])
# @login_required # Membutuhkan login untuk mengakses halaman ini
# def index():
#     """
#     Halaman utama untuk memeriksa ranking SERP.
#     """
#     result_data = None
#     if request.method == "POST":
#         domain = request.form["domain"]
#         keyword = request.form["keyword"]
#         hl = request.form["hl"]
#         gl = request.form["gl"]
#         google_domain = request.form["google_domain"]
#         num = request.form["num"]

#         ranks, total_found = get_ranks_serpapi(keyword, domain, hl, gl, google_domain, num)
        
#         result_data = {
#             "domain": domain,
#             "keyword": keyword,
#             "total_found": total_found,
#             "ranks": ranks
#         }

#         # Simpan hasil ke database jika user login
#         if current_user.is_authenticated:
#             new_rank_result = RankResult(
#                 keyword=keyword,
#                 domain=domain,
#                 result=json.dumps(result_data), # Simpan sebagai JSON string
#                 user_id=current_user.id
#             )
#             db.session.add(new_rank_result)
#             db.session.commit()
#             flash("Hasil ranking berhasil disimpan!", "success")

#     return render_template("index.html", result=result_data, now=datetime.utcnow())

# # Rute untuk login
# @app.route("/login", methods=["GET", "POST"])
# def login():
#     """
#     Menangani proses login user.
#     """
#     if current_user.is_authenticated:
#         return redirect(url_for("dashboard"))
    
#     if request.method == "POST":
#         email = request.form["email"]
#         password = request.form["password"]
#         remember = True if request.form.get("remember_me") else False

#         user = User.query.filter_by(email=email).first()

#         if not user or not check_password_hash(user.password, password):
#             flash("Silakan periksa email atau password Anda dan coba lagi.", "error")
#             return redirect(url_for("login"))
        
#         if not user.is_approved and user.role != 'admin':
#             flash("Akun Anda belum disetujui oleh admin. Mohon tunggu.", "warning")
#             return redirect(url_for("login"))

#         login_user(user, remember=remember)
#         return redirect(url_for("dashboard"))

#     return render_template("login.html", now=datetime.utcnow())

# # Rute untuk pendaftaran
# @app.route("/register", methods=["GET", "POST"])
# def register():
#     """
#     Menangani proses pendaftaran user baru.
#     """
#     if current_user.is_authenticated:
#         return redirect(url_for("dashboard"))

#     if request.method == "POST":
#         email = request.form["email"]
#         password = request.form["password"]
#         confirm_password = request.form["confirm_password"]
#         phone_number = request.form["phone_number"] # Untuk notifikasi WhatsApp

#         # Validasi sederhana
#         if password != confirm_password:
#             flash("Konfirmasi password tidak cocok.", "error")
#             return redirect(url_for("register"))

#         if User.query.filter_by(email=email).first():
#             flash("Email sudah terdaftar. Silakan login atau gunakan email lain.", "error")
#             return redirect(url_for("register"))

#         hashed_password = generate_password_hash(password)
        
#         # Buat kode unik pembayaran
#         unique_code = random.randint(100, 999) # Kode unik 3 digit
#         amount_to_pay = 50000 + unique_code # Contoh: Rp 50.000 + kode unik

#         new_user = User(
#             email=email, 
#             password=hashed_password, 
#             phone_number=phone_number,
#             amount_to_pay=amount_to_pay,
#             unique_code=unique_code # Simpan kode unik
#         )
#         db.session.add(new_user)
#         db.session.commit()

#         # Kirim notifikasi WhatsApp ke user
#         whatsapp_message = (
#             f"Terima kasih telah mendaftar! "
#             f"Untuk mengaktifkan akun Anda, mohon lakukan pembayaran sebesar Rp {amount_to_pay:,} "
#             f"ke rekening [Nomor Rekening Anda] a/n [Nama Bank Anda]. "
#             f"Sertakan kode unik {unique_code} di belakang nominal. "
#             f"Setelah pembayaran diverifikasi, admin akan menyetujui akun Anda. "
#             f"Jangan lupa simpan email: {email} sebagai username Anda."
#         )
#         send_whatsapp_notification(phone_number, whatsapp_message)
        
#         flash("Akun Anda berhasil dibuat. Mohon lakukan pembayaran dan tunggu persetujuan admin.", "success")
#         return redirect(url_for("login"))

#     return render_template("register.html", now=datetime.utcnow())

# # Rute untuk lupa password (placeholder, implementasi lebih lanjut diperlukan)
# @app.route("/forgot_password")
# def forgot_password():
#     """
#     Halaman untuk reset password.
#     """
#     flash("Fitur reset password belum diimplementasikan sepenuhnya.", "info")
#     return render_template("forgot_password.html", now=datetime.utcnow())

# # Rute untuk logout
# @app.route("/logout")
# @login_required
# def logout():
#     """
#     Menangani proses logout user.
#     """
#     logout_user()
#     flash("Anda telah berhasil keluar.", "info")
#     return redirect(url_for("login")) # Tidak perlu now di redirect

# # Rute Dashboard
# @app.route("/dashboard")
# @login_required
# def dashboard():
#     """
#     Menampilkan dashboard berdasarkan role user.
#     """
#     if current_user.role == "admin":
#         # Data untuk dashboard admin
#         pending_users = User.query.filter_by(is_approved=False).all()
#         all_users = User.query.all()
#         all_rank_results = RankResult.query.all()
#         all_payments = Payment.query.all()
#         return render_template(
#             "dashboard_admin.html", 
#             pending_users=pending_users, 
#             all_users=all_users,
#             all_rank_results=all_rank_results,
#             all_payments=all_payments,
#             now=datetime.utcnow() # Tambahkan now
#         )
#     else:
#         # Data untuk dashboard user
#         user_rank_results = RankResult.query.filter_by(user_id=current_user.id).order_by(RankResult.created_at.desc()).all()
#         return render_template("dashboard_user.html", user_rank_results=user_rank_results, now=datetime.utcnow())

# # Rute untuk menyetujui user (hanya untuk admin)
# @app.route("/approve_user/<int:user_id>")
# @login_required
# def approve_user(user_id):
#     """
#     Menyetujui akun user. Hanya bisa diakses oleh admin.
#     """
#     if current_user.role != "admin":
#         flash("Anda tidak memiliki izin untuk melakukan tindakan ini.", "error")
#         return redirect(url_for("dashboard"))

#     user_to_approve = User.query.get_or_404(user_id)
#     user_to_approve.is_approved = True
#     db.session.commit()
    
#     # Kirim notifikasi WhatsApp ke user yang disetujui
#     if user_to_approve.phone_number:
#         whatsapp_message = (
#             f"Selamat! Akun Anda ({user_to_approve.email}) telah disetujui. "
#             f"Anda sekarang dapat login dan mulai menggunakan fitur cek ranking SERP kami."
#         )
#         send_whatsapp_notification(user_to_approve.phone_number, whatsapp_message)

#     flash(f"User {user_to_approve.email} berhasil disetujui.", "success")
#     return redirect(url_for("dashboard"))

# # Rute untuk menghapus user (hanya untuk admin)
# @app.route("/delete_user/<int:user_id>")
# @login_required
# def delete_user(user_id):
#     """
#     Menghapus akun user. Hanya bisa diakses oleh admin.
#     """
#     if current_user.role != "admin":
#         flash("Anda tidak memiliki izin untuk melakukan tindakan ini.", "error")
#         return redirect(url_for("dashboard"))

#     user_to_delete = User.query.get_or_404(user_id)
#     # Hapus juga semua hasil ranking terkait user ini
#     RankResult.query.filter_by(user_id=user_to_delete.id).delete()
#     Payment.query.filter_by(user_id=user_to_delete.id).delete()
#     db.session.delete(user_to_delete)
#     db.session.commit()
#     flash(f"User {user_to_delete.email} dan semua datanya berhasil dihapus.", "success")
#     return redirect(url_for("dashboard"))

# # Rute untuk menandai pembayaran selesai (hanya untuk admin)
# @app.route("/mark_payment_complete/<int:payment_id>")
# @login_required
# def mark_payment_complete(payment_id):
#     """
#     Menandai pembayaran sebagai selesai. Hanya bisa diakses oleh admin.
#     """
#     if current_user.role != "admin":
#         flash("Anda tidak memiliki izin untuk melakukan tindakan ini.", "error")
#         return redirect(url_for("dashboard"))

#     payment = Payment.query.get_or_404(payment_id)
#     payment.is_completed = True
#     payment.completed_at = datetime.utcnow()
#     db.session.commit()
#     flash(f"Pembayaran {payment.id} berhasil ditandai sebagai selesai.", "success")
#     return redirect(url_for("dashboard"))

# # Rute API untuk konfirmasi pembayaran otomatis (misal dari webhook payment gateway)
# @app.route("/api/confirm_payment", methods=["POST"])
# def api_confirm_payment():
#     """
#     Endpoint API untuk mengkonfirmasi pembayaran.
#     Ini adalah contoh endpoint yang bisa dipanggil oleh sistem pembayaran (misal webhook).
#     """
#     data = request.json
#     transaction_id = data.get("transaction_id")
#     amount_paid = data.get("amount")
#     unique_code_from_payment = data.get("unique_code") # Kode unik dari pembayaran
#     user_email_or_id = data.get("user_identifier") # Email atau ID user dari sistem pembayaran

#     # Cari user berdasarkan email atau ID
#     user = User.query.filter_by(email=user_email_or_id).first()
#     if not user:
#         return jsonify({"message": "User not found"}), 404

#     # Verifikasi kode unik dan jumlah pembayaran
#     # Ini adalah logika sederhana, Anda mungkin perlu logika yang lebih kuat
#     if user.unique_code == unique_code_from_payment and amount_paid >= user.amount_to_pay:
#         # Tandai pembayaran sebagai selesai
#         payment = Payment(
#             user_id=user.id,
#             amount=amount_paid,
#             transaction_id=transaction_id,
#             is_completed=True,
#             completed_at=datetime.utcnow()
#         )
#         db.session.add(payment)
#         # Set is_approved menjadi True jika pembayaran dikonfirmasi otomatis
#         user.is_approved = True 
#         db.session.commit()

#         # Kirim notifikasi WhatsApp ke user
#         if user.phone_number:
#             whatsapp_message = (
#                 f"Pembayaran Anda sebesar Rp {amount_paid:,} telah berhasil dikonfirmasi! "
#                 f"Akun Anda ({user.email}) telah diaktifkan."
#             )
#             send_whatsapp_notification(user.phone_number, whatsapp_message)

#         return jsonify({"message": "Payment confirmed and user approved"}), 200
#     else:
#         return jsonify({"message": "Payment verification failed"}), 400

# # Rute untuk menampilkan detail hasil ranking (dari dashboard user/admin)
# @app.route("/rank_result/<int:result_id>")
# @login_required
# def view_rank_result(result_id):
#     """
#     Menampilkan detail hasil ranking yang disimpan.
#     """
#     rank_result = RankResult.query.get_or_404(result_id)
#     # Pastikan user hanya bisa melihat hasil rankingnya sendiri, kecuali admin
#     if current_user.role != "admin" and rank_result.user_id != current_user.id:
#         flash("Anda tidak memiliki izin untuk melihat hasil ini.", "error")
#         return redirect(url_for("dashboard"))
    
#     # Parse string JSON kembali ke objek Python
#     result_data = json.loads(rank_result.result)
#     return render_template("view_rank_result.html", result=result_data, rank_result_obj=rank_result, now=datetime.utcnow())


# # Error handler untuk halaman 404
# @app.errorhandler(404)
# def page_not_found(e):
#     return render_template("404.html", now=datetime.utcnow()), 404

# # Jalankan aplikasi
# if __name__ == "__main__":
#     # Ini akan membuat database jika belum ada
#     with app.app_context():
#         db.create_all()
#     app.run(debug=True)
