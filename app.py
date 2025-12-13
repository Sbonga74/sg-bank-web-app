from flask import Flask, render_template, request, redirect, session, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "change_this_to_a_random_secret_in_prod"  # replace with a secure secret for real deployment

# Database config
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "bank.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    type = db.Column(db.String(10), nullable=False)  # 'deposit' or 'withdraw'
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200), nullable=True)
    date = db.Column(db.String(20), nullable=False)  # YYYY-MM-DD

    user = db.relationship("User", backref=db.backref("transactions", lazy=True))


# Create tables
with app.app_context():
    db.create_all()


# Helpers
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return User.query.get(uid)


# Routes
@app.route("/")
def index():
    user = current_user()
    if user:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        if not username or not password:
            flash("Please fill both fields.")
            return redirect(url_for("register"))

        if User.query.filter_by(username=username).first():
            flash("Username already taken.")
            return redirect(url_for("register"))

        hashed = generate_password_hash(password)
        new_user = User(username=username, password_hash=hashed)
        db.session.add(new_user)
        db.session.commit()
        flash("Registration successful — you can log in now.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session["user_id"] = user.id
            session["username"] = user.username
            flash("Logged in successfully.")
            return redirect(url_for("dashboard"))
        flash("Invalid credentials.")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.")
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    # Current balance: deposits minus withdraws
    deposits = db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0.0)).filter_by(user_id=user.id, type="deposit").scalar()
    withdraws = db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0.0)).filter_by(user_id=user.id, type="withdraw").scalar()
    balance = deposits - withdraws

    # Recent transactions (latest 10)
    recent = Transaction.query.filter_by(user_id=user.id).order_by(Transaction.id.desc()).limit(10).all()

    # Monthly totals for current month (YYYY-MM)
    now = datetime.now()
    month_prefix = f"{now.year}-{now.month:02d}"
    monthly_deposits = db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0.0)).filter(Transaction.user_id == user.id, Transaction.type == "deposit", Transaction.date.like(f"{month_prefix}%")).scalar()
    monthly_withdraws = db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0.0)).filter(Transaction.user_id == user.id, Transaction.type == "withdraw", Transaction.date.like(f"{month_prefix}%")).scalar()
    monthly_total_spent = monthly_withdraws  # total withdraws this month

    return render_template(
        "dashboard.html",
        user=user,
        balance=balance,
        recent=recent,
        monthly_deposits=monthly_deposits,
        monthly_withdraws=monthly_withdraws,
        monthly_total_spent=monthly_total_spent,
    )


@app.route("/transaction", methods=["POST"])
def create_transaction():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    ttype = request.form.get("type")
    amount = request.form.get("amount")
    description = request.form.get("description", "")
    date = request.form.get("date") or datetime.now().strftime("%Y-%m-%d")

    try:
        amount_val = float(amount)
        if amount_val <= 0:
            flash("Amount must be greater than zero.")
            return redirect(url_for("dashboard"))
    except Exception:
        flash("Invalid amount.")
        return redirect(url_for("dashboard"))

    if ttype not in ("deposit", "withdraw"):
        flash("Invalid transaction type.")
        return redirect(url_for("dashboard"))

    tx = Transaction(user_id=user.id, type=ttype, amount=amount_val, description=description, date=date)
    db.session.add(tx)
    db.session.commit()
    flash("Transaction added.")
    return redirect(url_for("dashboard"))


@app.route("/delete_tx/<int:tx_id>", methods=["POST"])
def delete_tx(tx_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    tx = Transaction.query.get(tx_id)
    if tx and tx.user_id == user.id:
        db.session.delete(tx)
        db.session.commit()
        flash("Transaction deleted.")
    else:
        flash("Transaction not found or not allowed.")
    return redirect(url_for("dashboard"))


# Small route to return all transactions - for "view balance / view transactions" button
@app.route("/transactions")
def view_transactions():
    if "user_id" not in session:
        return redirect(url_for("login"))

    transactions = Transaction.query.filter_by(
        user_id=session["user_id"]
    ).all()

    return render_template("transactions.html", transactions=transactions)


if __name__ == "__main__":
    app.run(debug=True)
