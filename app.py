from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify, flash
import pymysql
import pandas as pd
import joblib
import io
import json
import difflib
import os
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from gtts import gTTS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import matplotlib
matplotlib.use("Agg")
import seaborn as sns
import base64
import matplotlib.pyplot as plt
from config import DB_CONFIG

# --------------------------------------------------
# Flask App Config
# --------------------------------------------------
app = Flask(__name__)
app.secret_key = '9eeedcf6c2befa56780509cfb4b2b43171e0b3c050b16bbd'

# --------------------------------------------------
# Database (PyMySQL – Python 3.11 compatible)
# --------------------------------------------------
def get_db():
    return pymysql.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
        port=DB_CONFIG["port"],
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )

# --------------------------------------------------
# Email Config
# --------------------------------------------------
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "cloudcrypt5@gmail.com")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD", "uvcv ynzg wwau xwnl")

# --------------------------------------------------
# File Upload Config
# --------------------------------------------------
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'csv', 'xlsx', 'xls'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

os.makedirs("static/audio", exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

CHATBOT_RESPONSES_PATH = os.path.join(os.path.dirname(__file__), "chatbot_responses.json")

# --------------------------------------------------
# Helpers
# --------------------------------------------------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def send_otp_email(email, otp):
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = email
        msg['Subject'] = 'OTP Verification'

        body = f"<h2>Your OTP is <b>{otp}</b></h2><p>Valid for 5 minutes</p>"
        msg.attach(MIMEText(body, 'html'))

        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(e)
        return False

# --------------------------------------------------
# Routes
# --------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form['email']
        password = request.form['password']

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, password FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            otp = str(random.randint(100000, 999999))
            expiry = datetime.now() + timedelta(minutes=5)

            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE users SET otp=%s, otp_expiry=%s WHERE id=%s",
                        (otp, expiry, user['id']))
            conn.close()

            send_otp_email(email, otp)
            session['temp_user'] = user['id']
            session['otp_sent'] = True
            flash("OTP sent to your email", "info")
            return redirect(url_for('login'))
        else:
            flash("Invalid credentials", "danger")
            return redirect(url_for('login'))
    
    # Clear otp_sent flag on GET request
    if 'otp_sent' not in session:
        session.pop('temp_user', None)

    return render_template("login.html")

@app.route("/verify_otp", methods=["POST"])
def verify_otp():
    otp = request.form['otp']
    uid = session.get('temp_user')

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT otp, otp_expiry FROM users WHERE id=%s", (uid,))
    user = cur.fetchone()
    conn.close()

    if user and user['otp'] == otp and datetime.now() <= user['otp_expiry']:
        session['user_id'] = uid
        session.pop('temp_user', None)
        session.pop('otp_sent', None)
        flash("Login successful", "success")
        return redirect(url_for("dashboard"))

    flash("Invalid or expired OTP", "danger")
    session['otp_sent'] = True
    return redirect(url_for("login"))

@app.route("/clear_otp_session", methods=["POST"])
def clear_otp_session():
    session.pop('otp_sent', None)
    session.pop('temp_user', None)
    return jsonify({"status": "success"})

@app.route("/register", methods=["POST"])
def register():
    name = request.form['name']
    email = request.form['email']
    password = request.form['password']

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email=%s", (email,))
    if cur.fetchone():
        conn.close()
        flash("Email already exists", "danger")
        return redirect(url_for("login"))

    cur.execute(
        "INSERT INTO users (name, email, password) VALUES (%s,%s,%s)",
        (name, email, generate_password_hash(password))
    )
    conn.close()

    flash("Account created successfully", "success")
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT SUM(amount) AS total FROM transactions WHERE user_id=%s",
                (session['user_id'],))
    total = cur.fetchone()['total'] or 0

    cur.execute("SELECT budgets FROM users WHERE id=%s",
                (session['user_id'],))
    budget = cur.fetchone()['budgets'] or 0
    conn.close()

    return render_template("dashboard.html", total_expense=total, budget=budget)

@app.route("/add_expense", methods=["GET", "POST"])
def add_expense():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        expense_amount = float(request.form['amount'])
        
        conn = get_db()
        cur = conn.cursor()
        
        # Get current budget and total spent before adding
        cur.execute("SELECT budgets FROM users WHERE id=%s", (session['user_id'],))
        current_budget = float(cur.fetchone()['budgets'] or 0)
        
        cur.execute("SELECT SUM(amount) AS total FROM transactions WHERE user_id=%s", (session['user_id'],))
        total_before = float(cur.fetchone()['total'] or 0)
        
        # Insert the transaction
        cur.execute(
            "INSERT INTO transactions (user_id, category, amount, date) VALUES (%s,%s,%s,%s)",
            (session['user_id'],
             request.form['category'],
             expense_amount,
             request.form['date'])
        )
        conn.close()
        
        # Check if budget exceeded
        total_after = total_before + expense_amount
        if current_budget > 0 and total_after > current_budget:
            exceeded_amount = total_after - current_budget
            flash(f"⚠️ Budget Limit Exceeded! You've spent ₹{total_after:.2f}, which is ₹{exceeded_amount:.2f} over your budget of ₹{current_budget:.2f}", "warning")
        else:
            flash("Expense added successfully!", "success")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM transactions WHERE user_id=%s ORDER BY date DESC",
                (session['user_id'],))
    expenses = cur.fetchall()
    
    cur.execute("SELECT SUM(amount) AS total FROM transactions WHERE user_id=%s",
                (session['user_id'],))
    total_spent = float(cur.fetchone()['total'] or 0)
    
    cur.execute("SELECT budgets FROM users WHERE id=%s",
                (session['user_id'],))
    current_budget = float(cur.fetchone()['budgets'] or 0)
    conn.close()
    
    # Check if currently over budget
    budget_exceeded = current_budget > 0 and total_spent > current_budget

    return render_template("add_expense.html", expenses=expenses, total_spent=total_spent, current_budget=current_budget, budget_exceeded=budget_exceeded)

@app.route("/set_budget", methods=["GET", "POST"])
def set_budget():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    if request.method == "POST":
        new_budget = request.form.get("budget")
        
        if not new_budget:
            flash("Please enter a budget amount", "error")
            return redirect(url_for("set_budget"))

        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET budgets = %s WHERE id = %s", (new_budget, session['user_id']))
        conn.close()

        flash("Budget updated successfully!", "success")
        return redirect(url_for("view_transactions"))
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT budgets FROM users WHERE id=%s", (session['user_id'],))
    current_budget = cur.fetchone()['budgets'] or 0
    conn.close()

    return render_template("set_budget.html", current_budget=current_budget)

@app.route("/api/expense_data")
def expense_data():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT category, SUM(amount) AS total FROM transactions WHERE user_id = %s GROUP BY category",
                (session['user_id'],))
    category_expenses = cur.fetchall()
    conn.close()

    if not category_expenses:
        return jsonify({"categories": [], "values": []})

    categories = [row["category"] for row in category_expenses]
    values = [row["total"] for row in category_expenses]

    return jsonify({"categories": categories, "values": values})

@app.route("/expense_analysis")
def expense_analysis():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT category, SUM(amount) AS total FROM transactions WHERE user_id = %s GROUP BY category",
                (session['user_id'],))
    category_expenses = cur.fetchall()
    conn.close()

    if not category_expenses:
        return render_template("spending_chart.html", chart_url=None, message="No transactions found!")

    df = pd.DataFrame(category_expenses)

    plt.figure(figsize=(8, 5))
    sns.barplot(x=df["total"], y=df["category"], palette="coolwarm")
    plt.xlabel("Total Spent")
    plt.ylabel("Category")
    plt.title("Spending by Category")

    img = io.BytesIO()
    plt.savefig(img, format="png")
    img.seek(0)
    graph_url = base64.b64encode(img.getvalue()).decode()
    plt.close()

    return render_template("spending_chart.html", chart_url=f"data:image/png;base64,{graph_url}", message=None)

@app.route("/report", methods=["GET"])
def report():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT category, amount, date FROM transactions WHERE user_id=%s", (session["user_id"],))
    transactions = cur.fetchall()
    conn.close()

    if not transactions:
        return "No transactions to generate a report."

    df = pd.DataFrame(transactions)
    output = io.StringIO()
    df.to_csv(output, index=False, encoding="utf-8")
    output.seek(0)

    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype="text/csv",
        as_attachment=True,
        download_name="financial_report.csv"
    )

@app.route("/view_transactions")
def view_transactions():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, category, amount, date FROM transactions WHERE user_id = %s ORDER BY date DESC", (session['user_id'],))
    transactions = cur.fetchall()
    conn.close()

    return render_template("view_transactions.html", transactions=transactions)

@app.route("/delete_transaction/<int:transaction_id>", methods=["POST"])
def delete_transaction(transaction_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM transactions WHERE id = %s AND user_id = %s", (transaction_id, session["user_id"]))
    conn.close()

    flash("Transaction deleted successfully!", "success")
    return redirect(url_for("view_transactions"))

@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"response": "Please enter a message.", "audio_url": None})

    # Load chatbot responses
    try:
        with open(CHATBOT_RESPONSES_PATH, 'r', encoding='utf-8') as f:
            raw_responses = json.load(f)
            responses = {k.strip().lower(): v for k, v in raw_responses.items()}
    except Exception:
        responses = {}

    response_text = responses.get(user_message.lower(), "I'm not sure how to answer that. Can you rephrase?")
    
    # Generate text-to-speech audio
    try:
        tts = gTTS(text=response_text, lang="en")
        audio_filename = "static/audio/response.mp3"
        tts.save(audio_filename)
        audio_url = "/" + audio_filename
    except:
        audio_url = None

    return jsonify({"response": response_text, "audio_url": audio_url})

@app.route("/upload_document", methods=["GET", "POST"])
def upload_document():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    if request.method == "POST":
        if 'file' not in request.files:
            flash("No file selected", "danger")
            return redirect(url_for("upload_document"))
        
        file = request.files['file']
        if file.filename == '':
            flash("No file selected", "danger")
            return redirect(url_for("upload_document"))
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_filename = f"{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            
            file.save(filepath)
            file_size = os.path.getsize(filepath)
            file_type = filename.rsplit('.', 1)[1].lower()
            
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO documents (user_id, filename, original_filename, file_type, file_path, file_size) VALUES (%s, %s, %s, %s, %s, %s)",
                (session['user_id'], unique_filename, filename, file_type, filepath, file_size)
            )
            doc_id = cur.lastrowid
            
            # Process CSV files
            if file_type == 'csv':
                try:
                    df = pd.read_csv(filepath)
                    for _, row in df.iterrows():
                        cur.execute(
                            "INSERT INTO document_transactions (document_id, user_id, category, amount, date, description) VALUES (%s, %s, %s, %s, %s, %s)",
                            (doc_id, session['user_id'], row.get('category', row.get('Category')), 
                             float(row.get('amount', row.get('Amount', 0))), 
                             row.get('date', row.get('Date')), 
                             row.get('description', row.get('Description', '')))
                        )
                except Exception as e:
                    print(f"Error processing CSV: {e}")
            
            conn.close()
            flash("Document uploaded successfully!", "success")
            return redirect(url_for("view_documents"))
        else:
            flash("Invalid file type. Allowed types: PDF, DOC, DOCX, CSV, XLSX, XLS", "danger")
    
    return render_template("upload_document.html")

@app.route("/view_documents")
def view_documents():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM documents WHERE user_id = %s ORDER BY upload_date DESC", (session['user_id'],))
    documents = cur.fetchall()
    conn.close()
    
    return render_template("view_documents.html", documents=documents)

@app.route("/view_document_transactions/<int:doc_id>")
def view_document_transactions(doc_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM documents WHERE id = %s AND user_id = %s", (doc_id, session['user_id']))
    document = cur.fetchone()
    
    if not document:
        flash("Document not found", "danger")
        conn.close()
        return redirect(url_for("view_documents"))
    
    cur.execute("SELECT * FROM document_transactions WHERE document_id = %s ORDER BY date DESC", (doc_id,))
    transactions = cur.fetchall()
    conn.close()
    
    return render_template("view_document_transactions.html", document=document, transactions=transactions)

@app.route("/delete_document/<int:doc_id>", methods=["POST"])
def delete_document(doc_id):
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT file_path FROM documents WHERE id = %s AND user_id = %s", (doc_id, session['user_id']))
    document = cur.fetchone()
    
    if document:
        # Delete file from filesystem
        try:
            if os.path.exists(document['file_path']):
                os.remove(document['file_path'])
        except Exception as e:
            print(f"Error deleting file: {e}")
        
        # Delete from database
        cur.execute("DELETE FROM documents WHERE id = %s AND user_id = %s", (doc_id, session['user_id']))
        conn.close()
        return jsonify({"success": True, "message": "Document deleted successfully"})
    
    conn.close()
    return jsonify({"success": False, "message": "Document not found"}), 404

@app.route("/download_document/<int:doc_id>")
def download_document(doc_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT file_path, original_filename FROM documents WHERE id = %s AND user_id = %s", (doc_id, session['user_id']))
    document = cur.fetchone()
    conn.close()
    
    if document and os.path.exists(document['file_path']):
        return send_file(document['file_path'], as_attachment=True, download_name=document['original_filename'])
    
    flash("Document not found", "danger")
    return redirect(url_for("view_documents"))

@app.route("/view_expense/<int:expense_id>")
def view_expense(expense_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM transactions WHERE id = %s AND user_id = %s", (expense_id, session['user_id']))
    expense = cur.fetchone()
    conn.close()
    
    if not expense:
        flash("Expense not found", "danger")
        return redirect(url_for("view_transactions"))
    
    return render_template("view_expense.html", expense=expense)

@app.route("/edit_expense/<int:expense_id>", methods=["GET", "POST"])
def edit_expense(expense_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    
    if request.method == "POST":
        cur.execute(
            "UPDATE transactions SET category=%s, amount=%s, date=%s WHERE id=%s AND user_id=%s",
            (request.form['category'], float(request.form['amount']), request.form['date'], expense_id, session['user_id'])
        )
        conn.close()
        flash("Expense updated successfully!", "success")
        return redirect(url_for("view_transactions"))
    
    cur.execute("SELECT * FROM transactions WHERE id = %s AND user_id = %s", (expense_id, session['user_id']))
    expense = cur.fetchone()
    conn.close()
    
    if not expense:
        flash("Expense not found", "danger")
        return redirect(url_for("view_transactions"))
    
    return render_template("edit_expense.html", expense=expense)

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out", "success")
    return redirect(url_for("home"))

# --------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
