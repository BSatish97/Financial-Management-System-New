from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify, flash
from flask_mysqldb import MySQL
import MySQLdb.cursors  
import pandas as pd
import joblib
import io
import json
import difflib
import os
from gtts import gTTS  
from werkzeug.security import generate_password_hash, check_password_hash
import matplotlib
matplotlib.use("Agg")
import seaborn as sns
import base64
import matplotlib.pyplot as plt
import os

app = Flask(__name__)
app.secret_key = '9eeedcf6c2befa56780509cfb4b2b43171e0b3c050b16bbd'


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# XAMPP MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'finance_db'

mysql = MySQL(app)

# Ensure 'static/audio' directory exists
if not os.path.exists("static/audio"):
    os.makedirs("static/audio")

CHATBOT_RESPONSES_PATH = os.path.join(os.path.dirname(__file__), "chatbot_responses.json")

# Load chatbot responses
try:
    with open(CHATBOT_RESPONSES_PATH, "r", encoding="utf-8") as f:
        raw_chatbot_data = json.load(f)
        chatbot_data = {k.strip().lower(): v for k, v in raw_chatbot_data.items()}
except Exception as e:
    chatbot_data = {}

def get_chatbot_response(user_message):
    user_message = user_message.lower().strip()
    if user_message in chatbot_data:
        return chatbot_data[user_message]
    closest_match = difflib.get_close_matches(user_message, chatbot_data.keys(), n=1, cutoff=0.5)
    return chatbot_data[closest_match[0]] if closest_match else "Sorry, I don't have an answer for that."

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        cur = mysql.connection.cursor()
        cur.execute("SELECT id, password FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        cur.close()

        if user and check_password_hash(user[1], password):
            session["user_id"] = user[0]
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "danger")

    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO users (name, email, password) VALUES (%s, %s, %s)", (name, email, password))
        mysql.connection.commit()
        cur.close()

        return redirect(url_for("login"))

    return render_template("signup.html")

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("home"))

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get total expenses
    cur.execute("SELECT SUM(amount) AS total_expense FROM transactions WHERE user_id = %s", (session['user_id'],))
    expense_data = cur.fetchone()
    total_expense = expense_data["total_expense"] if expense_data["total_expense"] else 0

    # Get budgets instead of budget
    cur.execute("SELECT budgets FROM users WHERE id = %s", (session['user_id'],))
    budget_data = cur.fetchone()
    budget = budget_data["budgets"] if budget_data and budget_data["budgets"] else 0
    
    cur.close()

    return render_template("dashboard.html", total_expense=total_expense, budget=budget)

@app.route("/add_expense", methods=["GET", "POST"])
def add_expense():
    if "user_id" not in session:
        return redirect(url_for("login"))

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Get total expense
    cur.execute("SELECT SUM(amount) AS total_expense FROM transactions WHERE user_id = %s", (session['user_id'],))
    expense_data = cur.fetchone()
    total_expense = float(expense_data["total_expense"]) if expense_data["total_expense"] else 0  # Convert to float

    # Get current budget
    cur.execute("SELECT budgets FROM users WHERE id = %s", (session['user_id'],))
    budget_data = cur.fetchone()
    budget = float(budget_data["budgets"]) if budget_data and budget_data["budgets"] else 0  # Convert to float

    if request.method == "POST":
        category = request.form["category"]
        amount = float(request.form["amount"])
        date = request.form["date"]

        new_total = total_expense + amount

        if new_total > budget:
            flash(f"Warning: Your total expenses exceed the budget!", "warning")

        # Insert the expense
        cur.execute("INSERT INTO transactions (user_id, category, amount, date) VALUES (%s, %s, %s, %s)",
                    (session["user_id"], category, amount, date))
        mysql.connection.commit()

        return redirect(url_for("add_expense"))

    # Fetch all expenses for the user
    cur.execute("SELECT id, category, amount, date FROM transactions WHERE user_id = %s", (session['user_id'],))
    expense_records = cur.fetchall()
    
    cur.close()

    return render_template("add_expense.html", expenses=expense_records, current_budget=budget, total_spent=total_expense)




@app.route("/set_budget", methods=["GET", "POST"])
def set_budget():
    if request.method == "POST":
        new_budget = request.form.get("budget")
        
        if not new_budget:
            flash("Please enter a budget amount", "error")
            return redirect(url_for("set_budget"))

        cur = mysql.connection.cursor()
        cur.execute("UPDATE users SET budgets = %s WHERE id = %s", (new_budget, session['user_id']))
        mysql.connection.commit()
        cur.close()

        flash("Budget updated successfully!", "success")
        return redirect(url_for("view_transactions")) 

    return render_template("set_budget.html")

@app.route("/api/expense_data")
def expense_data():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT category, SUM(amount) AS total FROM transactions WHERE user_id = %s GROUP BY category",
                (session['user_id'],))
    category_expenses = cur.fetchall()
    cur.close()

    if not category_expenses:
        return jsonify({"categories": [], "values": []})

    categories = [row["category"] for row in category_expenses]
    values = [row["total"] for row in category_expenses]

    return jsonify({"categories": categories, "values": values})


@app.route("/expense_analysis")
def expense_analysis():
    if "user_id" not in session:
        return redirect(url_for("login"))

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT category, SUM(amount) AS total FROM transactions WHERE user_id = %s GROUP BY category",
                (session['user_id'],))
    category_expenses = cur.fetchall()
    cur.close()

    # If no transactions, return a message instead of None
    if not category_expenses:
        return render_template("spending_chart.html", chart_url=None, message="No transactions found!")

    # Convert fetched data to DataFrame
    df = pd.DataFrame(category_expenses)

    # Generate Bar Chart
    plt.figure(figsize=(8, 5))
    sns.barplot(x=df["total"], y=df["category"], palette="coolwarm")
    plt.xlabel("Total Spent")
    plt.ylabel("Category")
    plt.title("Spending by Category")

    # Save plot as base64 string
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

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT category, amount, date FROM transactions WHERE user_id=%s", (session["user_id"],))
    transactions = cur.fetchall()
    cur.close()

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

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT id, category, amount, date FROM transactions WHERE user_id = %s", (session['user_id'],))
    transactions = cur.fetchall()
    cur.close()

    # Debugging: Print transactions to console
    print("Fetched Transactions:", transactions)

    return render_template("view_transactions.html", transactions=transactions)

@app.route("/delete_transaction/<int:transaction_id>", methods=["POST"])
def delete_transaction(transaction_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM transactions WHERE id = %s AND user_id = %s", (transaction_id, session["user_id"]))
    mysql.connection.commit()
    cur.close()

    flash("Transaction deleted successfully!", "success")
    return redirect(url_for("view_transactions"))



@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.get_json()
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"response": "Please enter a message.", "audio_url": None})

    response_text = get_chatbot_response(user_message)
    
    # Generate text-to-speech audio
    tts = gTTS(text=response_text, lang="en")
    audio_filename = "static/audio/response.mp3"  # Fixed file name to always overwrite the last response
    tts.save(audio_filename)

    return jsonify({"response": response_text, "audio_url": "/" + audio_filename})


if __name__ == "__main__":
    app.run(debug=True)
