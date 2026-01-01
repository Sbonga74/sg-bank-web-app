import os
from datetime import datetime
from decimal import Decimal
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
# In Pro: Use environment variables for secrets
app.secret_key = os.environ.get("SECRET_KEY", "dev_key_only_123")

# Database
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "bank.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Login Management
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "info"

# --- Models ---

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    
    # Relationship
    transactions = db.relationship("Transaction", backref="owner", lazy="dynamic", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def balance(self):
        """Calculates balance on the fly using high-performance SQL sum."""
        deposits = db.session.query(db.func.sum(Transaction.amount)).filter_by(user_id=self.id, type="deposit").scalar() or 0
        withdraws = db.session.query(db.func.sum(Transaction.amount)).filter_by(user_id=self.id, type="withdraw").scalar() or 0
        return float(deposits - withdraws)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    type = db.Column(db.String(10), nullable=False)  # 'deposit' or 'withdraw'
    amount = db.Column(db.Float, nullable=False)    # Pro tip: Use Integer (cents) in real production
    description = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- Routes ---

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password")
        
        if User.query.filter_by(username=username).first():
            flash("Username already exists.", "danger")
        else:
            new_user = User(username=username)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash("Account created! Please log in.", "success")
            return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form.get("username")).first()
        if user and user.check_password(request.form.get("password")):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Login Unsuccessful. Check username and password", "danger")
    return render_template("login.html")

@app.route("/dashboard")
@login_required
def dashboard():
    # Fetching only the last 10 transactions for performance
    recent = current_user.transactions.order_by(Transaction.timestamp.desc()).limit(10).all()
    return render_template("dashboard.html", balance=current_user.balance, recent=recent)

@app.route("/transaction", methods=["POST"])
@login_required
def create_transaction():
    ttype = request.form.get("type")
    try:
        amount = float(request.form.get("amount", 0))
    except ValueError:
        flash("Invalid amount format.", "danger")
        return redirect(url_for("dashboard"))

    if amount <= 0:
        flash("Amount must be positive.", "warning")
        return redirect(url_for("dashboard"))

    # Logic: Prevent Overdraft
    if ttype == "withdraw" and amount > current_user.balance:
        flash("Transaction declined: Insufficient funds.", "danger")
        return redirect(url_for("dashboard"))

    tx = Transaction(
        user_id=current_user.id, 
        type=ttype, 
        amount=amount, 
        description=request.form.get("description")
    )
    db.session.add(tx)
    db.session.commit()
    flash("Transaction successful!", "success")
    return redirect(url_for("dashboard"))
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/transactions")
@login_required
def view_transactions():
    # Sort by newest first using timestamp
    transactions = current_user.transactions.order_by(Transaction.timestamp.desc()).all()
    return render_template("transactions.html", transactions=transactions)

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login"))

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)