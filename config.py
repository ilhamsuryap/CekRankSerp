import os

class Config:
    # Flask application secret key for session management
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'super_secret_key_change_me_in_production'

    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///db.sqlite3'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # SerpApi configuration (from your original app.py)
    SERPAPI_API_KEY = "572db24d1b3554570e4013212f0b26160f44709c398abb0a65dee3428e1ed4e6"

    # Quods.id WhatsApp API configuration (Placeholder - replace with your actual details)
    QUODS_ID_API_URL = "https://api.quods.id/v1/send-message" # Example URL, verify with Quods.id docs
    QUODS_ID_API_KEY = "9ZruYR6WpfxC9bF2S25KPfyorDipEu" # Replace with your actual Quods.id API Key
    QUODS_ID_SENDER = "YOUR_QUODS_ID_SENDER_NUMBER" # Replace with your sender number

    # Registration payment settings
    REGISTRATION_BASE_AMOUNT = 50000 # Base amount for registration in your currency (e.g., IDR)
    REGISTRATION_UNIQUE_CODE_MIN = 100 # Minimum for unique 3-digit code
    REGISTRATION_UNIQUE_CODE_MAX = 999 # Maximum for unique 3-digit code

    # Admin email for initial admin user creation (optional, for development)
    ADMIN_EMAIL = "admin@example.com"
    ADMIN_PASSWORD = "admin_password" # Change this in production!

