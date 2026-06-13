import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

import os
import requests

app = Flask(__name__)
app.secret_key = "family_expense_tracker_secret_key_1928"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "family_wealth.db")

def init_db():
    """Initializes the database and seeds starting configurations for users and accounts."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 1. Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL,
            avatar TEXT
        )
    ''')
    
    # Run migration for existing databases to add avatar column if missing
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN avatar TEXT")
    except sqlite3.OperationalError:
        pass
    
    # 2. Accounts Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_name TEXT UNIQUE NOT NULL,
            starting_balance REAL NOT NULL,
            current_balance REAL NOT NULL
        )
    ''')
    
    # 3. Transactions Table (updated with user reference)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            description TEXT,
            amount REAL NOT NULL,
            type TEXT NOT NULL,
            account_name TEXT NOT NULL,
            category TEXT NOT NULL,
            user_id INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    
    # Seed standard operational bank accounts if they don't exist
    accounts_seed = [("Axis Bank", 17032.00), ("Cash", 47000.00)]
    for name, bal in accounts_seed:
        cursor.execute('''
            INSERT OR IGNORE INTO accounts (account_name, starting_balance, current_balance)
            VALUES (?, ?, ?)
        ''', (name, bal, bal))
        
    # Seed default family users if they don't exist
    default_users = [
        ("papa", "Papa", "Parent", "👨"),
        ("mama", "Mama", "Parent", "👩"),
        ("junior", "Junior", "Child", "👦"),
        ("yesha", "Yesha", "Parent", "👩")
    ]
    for username, display_name, role, avatar in default_users:
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if not cursor.fetchone():
            hashed_pw = generate_password_hash("family123")
            cursor.execute('''
                INSERT INTO users (username, password_hash, display_name, role, avatar)
                VALUES (?, ?, ?, ?, ?)
            ''', (username, hashed_pw, display_name, role, avatar))
        
    conn.commit()
    conn.close()

def update_account_balances():
    """Recalculates current balances dynamically based on ledger history."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT account_name, starting_balance FROM accounts")
    accounts = cursor.fetchall()
    
    for name, starting in accounts:
        cursor.execute("SELECT SUM(amount) FROM transactions WHERE account_name = ? AND type = 'Income'", (name,))
        income = cursor.fetchone()[0] or 0.0
        
        cursor.execute("SELECT SUM(amount) FROM transactions WHERE account_name = ? AND type = 'Expense'", (name,))
        expense = cursor.fetchone()[0] or 0.0
        
        current = starting + income - expense
        cursor.execute("UPDATE accounts SET current_balance = ? WHERE account_name = ?", (current, name))
        
    conn.commit()
    conn.close()

# Initialize and seed database on import
init_db()
update_account_balances()

@app.context_processor
def inject_is_localhost():
    is_local = "localhost" in request.host or "127.0.0.1" in request.host or "192.168" in request.host
    return dict(is_localhost=is_local)

# Login Required Decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
        
    error = None
    attempted_username = None
    
    # Load all users dynamically for the grid selector
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT username, display_name, role, avatar FROM users")
    users_raw = cursor.fetchall()
    conn.close()
    
    users = []
    for u_name, disp_name, u_role, u_avatar in users_raw:
        # Fallback avatar
        if not u_avatar:
            if u_name == "papa":
                u_avatar = "👨"
            elif u_name == "mama":
                u_avatar = "👩"
            elif u_name == "junior":
                u_avatar = "👦"
            elif u_role == "Parent":
                u_avatar = "🧑‍💼"
            else:
                u_avatar = "👦"
                
        # Assign gradients
        if u_name == "papa":
            gradient = "from-blue-500 to-indigo-600"
        elif u_name == "mama":
            gradient = "from-pink-500 to-rose-600"
        elif u_name == "junior":
            gradient = "from-amber-400 to-orange-500"
        elif u_role == "Parent":
            if u_avatar in ["👩", "👩‍💼", "👵", "👧"]:
                gradient = "from-fuchsia-500 to-pink-600"
            else:
                gradient = "from-violet-500 to-purple-600"
        else:
            if u_avatar in ["👩", "👩‍💼", "👵", "👧"]:
                gradient = "from-rose-400 to-pink-500"
            else:
                gradient = "from-emerald-400 to-teal-500"
                
        users.append({
            "username": u_name,
            "display_name": disp_name,
            "role": u_role,
            "avatar": u_avatar,
            "gradient": gradient
        })
        
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        attempted_username = username
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, password_hash, display_name, role, avatar FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user[2], password):
            session["user_id"] = user[0]
            session["username"] = user[1]
            session["display_name"] = user[3]
            session["role"] = user[4]
            session["avatar"] = user[5]
            return redirect(url_for("dashboard"))
        else:
            error = "Access Denied: Incorrect password. Please try again."
            
    return render_template("login.html", error=error, attempted_username=attempted_username, users=users)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    init_db()
    update_account_balances()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM accounts")
    accounts = cursor.fetchall()
    total_balance = sum(acc[3] for acc in accounts)
    
    # Calculate overall chart aggregates for dashboard representation
    cursor.execute("SELECT category, SUM(amount) FROM transactions WHERE type='Expense' GROUP BY category")
    chart_raw = cursor.fetchall()
    chart_data = {row[0]: row[1] for row in chart_raw}
    
    # Dynamic Categories extraction
    default_expenses = ["Groceries & Food", "Utilities & Bills", "Fuel & Transport", "Insurance & EMIs", "Entertainment"]
    default_incomes = ["Salary / General Revenue", "Investments Dividend", "Gifts / Pocket Money"]
    
    cursor.execute("SELECT DISTINCT category FROM transactions WHERE type='Expense'")
    db_expenses = [row[0] for row in cursor.fetchall() if row[0]]
    
    cursor.execute("SELECT DISTINCT category FROM transactions WHERE type='Income'")
    db_incomes = [row[0] for row in cursor.fetchall() if row[0]]
    
    expense_categories = list(dict.fromkeys(default_expenses + db_expenses))
    income_categories = list(dict.fromkeys(default_incomes + db_incomes))
    
    conn.close()
    
    current_user = {
        "username": session.get("username"),
        "display_name": session.get("display_name"),
        "role": session.get("role"),
        "avatar": session.get("avatar")
    }
    
    return render_template("dashboard.html", 
                           accounts=accounts, 
                           total_balance=total_balance, 
                           chart_data=chart_data, 
                           current_user=current_user, 
                           expense_categories=expense_categories, 
                           income_categories=income_categories,
                           active_page="dashboard")

@app.route("/ledger")
@login_required
def ledger():
    init_db()
    update_account_balances()
    
    from_date = request.args.get("from_date", "").strip()
    to_date = request.args.get("to_date", "").strip()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Build query for transactions
    query = '''
        SELECT t.id, t.date, t.description, t.amount, t.type, t.account_name, t.category, u.display_name 
        FROM transactions t 
        LEFT JOIN users u ON t.user_id = u.id 
    '''
    params = []
    conditions = []
    
    if from_date:
        conditions.append("date(t.date) >= date(?)")
        params.append(from_date)
    if to_date:
        conditions.append("date(t.date) <= date(?)")
        params.append(to_date)
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    query += " ORDER BY t.date DESC, t.id DESC"
    
    cursor.execute(query, params)
    transactions = cursor.fetchall()
    
    # Filtered Period Summary (Income vs Expense)
    period_summary_query = "SELECT type, SUM(amount) FROM transactions"
    summary_conditions = []
    summary_params = []
    if from_date:
        summary_conditions.append("date(date) >= date(?)")
        summary_params.append(from_date)
    if to_date:
        summary_conditions.append("date(date) <= date(?)")
        summary_params.append(to_date)
    if summary_conditions:
        period_summary_query += " WHERE " + " AND ".join(summary_conditions)
    period_summary_query += " GROUP BY type"
    
    cursor.execute(period_summary_query, summary_params)
    summary_raw = cursor.fetchall()
    period_summary = {"Income": 0.0, "Expense": 0.0}
    for row in summary_raw:
        if row[0] in period_summary:
            period_summary[row[0]] = row[1]
            
    conn.close()
    
    # Group transactions by day for Daily Ledger format
    transactions_by_day = {}
    for tx in transactions:
        try:
            date_obj = datetime.strptime(tx[1].split()[0], "%Y-%m-%d")
            day_str = date_obj.strftime("%A, %b %d, %Y")
        except Exception:
            day_str = tx[1].split()[0]
        if day_str not in transactions_by_day:
            transactions_by_day[day_str] = []
        transactions_by_day[day_str].append(tx)
        
    current_user = {
        "username": session.get("username"),
        "display_name": session.get("display_name"),
        "role": session.get("role"),
        "avatar": session.get("avatar")
    }
    
    return render_template("ledger.html", 
                           transactions_by_day=transactions_by_day, 
                           current_user=current_user, 
                           from_date=from_date,
                           to_date=to_date,
                           period_summary=period_summary,
                           active_page="ledger")


@app.route("/add", methods=["POST"])
@login_required
def add_transaction():
    t_type = request.form["type"]
    acc_name = request.form["account_name"]
    category = request.form.get("category_select")
    if category == "__custom__":
        category = request.form.get("custom_category", "").strip() or "Other"
    amount = float(request.form["amount"])
    desc = request.form["description"] or f"General {t_type}"
    
    # Check if a date was specified in the form
    date_val = request.form.get("date", "").strip()
    time_str = datetime.now().strftime("%H:%M")
    if date_val:
        date_str = f"{date_val} {time_str}"
    else:
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        
    user_id = session.get("user_id")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO transactions (date, description, amount, type, account_name, category, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (date_str, desc, amount, t_type, acc_name, category, user_id))
    conn.commit()
    conn.close()
    
    # Re-calculate balances
    update_account_balances()
    
    return redirect(url_for("dashboard"))

@app.route("/add_account", methods=["POST"])
@login_required
def add_account():
    name = request.form.get("account_name", "").strip()
    starting_balance = request.form.get("starting_balance", "0")
    if not name:
        return redirect(url_for("dashboard"))
    try:
        starting_balance = float(starting_balance)
    except ValueError:
        starting_balance = 0.0
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO accounts (account_name, starting_balance, current_balance)
            VALUES (?, ?, ?)
        ''', (name, starting_balance, starting_balance))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    update_account_balances()
    return redirect(url_for("dashboard"))

@app.route("/delete/<int:tx_id>")
@login_required
def delete_transaction(tx_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    conn.commit()
    conn.close()
    
    # Re-calculate balances
    update_account_balances()
    
    referrer = request.referrer or url_for("dashboard")
    return redirect(referrer)

@app.route("/edit/<int:tx_id>", methods=["GET", "POST"])
@login_required
def edit_transaction(tx_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,))
    tx = cursor.fetchone()
    if not tx:
        conn.close()
        return redirect(url_for("ledger"))
        
    if request.method == "POST":
        t_type = request.form["type"]
        acc_name = request.form["account_name"]
        category = request.form.get("category_select")
        if category == "__custom__":
            category = request.form.get("custom_category", "").strip() or "Other"
        amount = float(request.form["amount"])
        desc = request.form["description"] or f"General {t_type}"
        
        date_val = request.form.get("date", "").strip()
        time_str = datetime.now().strftime("%H:%M")
        existing_time = tx[1].split()[1] if len(tx[1].split()) > 1 else time_str
        if date_val:
            date_str = f"{date_val} {existing_time}"
        else:
            date_str = tx[1]
            
        user_id = int(request.form.get("user_id", tx[7]))
        
        cursor.execute('''
            UPDATE transactions 
            SET date = ?, description = ?, amount = ?, type = ?, account_name = ?, category = ?, user_id = ?
            WHERE id = ?
        ''', (date_str, desc, amount, t_type, acc_name, category, user_id, tx_id))
        conn.commit()
        conn.close()
        
        update_account_balances()
        return redirect(url_for("ledger"))
        
    # GET: Fetch references
    cursor.execute("SELECT * FROM accounts")
    accounts = cursor.fetchall()
    
    cursor.execute("SELECT id, display_name FROM users")
    users = cursor.fetchall()
    
    # Categories
    default_expenses = ["Groceries & Food", "Utilities & Bills", "Fuel & Transport", "Insurance & EMIs", "Entertainment"]
    default_incomes = ["Salary / General Revenue", "Investments Dividend", "Gifts / Pocket Money"]
    
    cursor.execute("SELECT DISTINCT category FROM transactions WHERE type='Expense'")
    db_expenses = [row[0] for row in cursor.fetchall() if row[0]]
    
    cursor.execute("SELECT DISTINCT category FROM transactions WHERE type='Income'")
    db_incomes = [row[0] for row in cursor.fetchall() if row[0]]
    
    expense_categories = list(dict.fromkeys(default_expenses + db_expenses))
    income_categories = list(dict.fromkeys(default_incomes + db_incomes))
    
    conn.close()
    
    # Parse Date value for html5 date input (YYYY-MM-DD)
    date_input_val = tx[1].split()[0] if tx[1] else datetime.now().strftime("%Y-%m-%d")
    
    current_user = {
        "username": session.get("username"),
        "display_name": session.get("display_name"),
        "role": session.get("role"),
        "avatar": session.get("avatar")
    }
    
    return render_template("edit.html",
                           tx=tx,
                           accounts=accounts,
                           users=users,
                           expense_categories=expense_categories,
                           income_categories=income_categories,
                           date_input_val=date_input_val,
                           current_user=current_user)

@app.route("/family", methods=["GET", "POST"])
@login_required
def family():
    error = None
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    if request.method == "POST":
        if session.get("role") != "Parent":
            conn.close()
            return "Access Denied: Only Parent accounts can manage family members.", 403
            
        username = request.form.get("username", "").strip().lower()
        display_name = request.form.get("display_name", "").strip()
        role = request.form.get("role", "Child")
        avatar = request.form.get("avatar", "🧑‍💼")
        password = request.form.get("password", "")
        
        if not username or not display_name or not password:
            error = "Please fill in all fields."
        else:
            # Check if username exists
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            if cursor.fetchone():
                error = f"Username '{username}' already exists. Please choose another one."
            else:
                hashed_pw = generate_password_hash(password)
                cursor.execute('''
                    INSERT INTO users (username, password_hash, display_name, role, avatar)
                    VALUES (?, ?, ?, ?, ?)
                ''', (username, hashed_pw, display_name, role, avatar))
                conn.commit()
                return redirect(url_for("family"))
                
    cursor.execute("SELECT id, username, display_name, role, avatar FROM users")
    users_list = cursor.fetchall()
    conn.close()
    
    current_user = {
        "username": session.get("username"),
        "display_name": session.get("display_name"),
        "role": session.get("role"),
        "user_id": session.get("user_id"),
        "avatar": session.get("avatar")
    }
    
    return render_template("family.html", 
                           users_list=users_list, 
                           error=error, 
                           current_user=current_user,
                           active_page="family")

@app.route("/family/delete/<int:user_id>")
@login_required
def delete_user(user_id):
    if session.get("role") != "Parent":
        return "Access Denied: Only Parent accounts can manage family members.", 403
        
    if user_id == session.get("user_id"):
        return "Access Denied: You cannot delete your own active profile.", 403
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for("family"))

# API endpoints on PythonAnywhere for DB Download / Upload
@app.route("/api/db/download")
def api_db_download():
    token = request.args.get("token")
    if token != app.secret_key:
        return "Access Denied: Invalid sync token.", 403
    if not os.path.exists(DB_FILE):
        return "Error: Database file does not exist.", 404
    return send_file(DB_FILE, as_attachment=True, download_name="family_wealth.db")

@app.route("/api/db/upload", methods=["POST"])
def api_db_upload():
    token = request.args.get("token")
    if token != app.secret_key:
        return "Access Denied: Invalid sync token.", 403
    
    if "file" not in request.files:
        return "Error: No file uploaded.", 400
        
    uploaded_file = request.files["file"]
    if uploaded_file.filename == "":
        return "Error: Empty filename.", 400
        
    # Replace current db file
    try:
        uploaded_file.save(DB_FILE)
        # Re-initialize and update balance mapping just to be safe
        init_db()
        update_account_balances()
        return jsonify({"status": "success", "message": "Database uploaded and loaded successfully."})
    except Exception as e:
        return f"Error saving database: {str(e)}", 500


# Local triggers (only functional on localhost/local network)
LIVE_SYNC_URL = "http://akshat18shah.pythonanywhere.com"

@app.route("/local/sync/pull", methods=["POST"])
@login_required
def local_sync_pull():
    is_local = "localhost" in request.host or "127.0.0.1" in request.host or "192.168" in request.host
    if not is_local:
        return jsonify({"status": "error", "message": "Pull sync can only be initiated from a local running instance."}), 403
        
    try:
        response = requests.get(f"{LIVE_SYNC_URL}/api/db/download", params={"token": app.secret_key}, timeout=15)
        if response.status_code == 200:
            with open(DB_FILE, "wb") as f:
                f.write(response.content)
            update_account_balances()
            # Clear user session if current user no longer exists in downloaded database
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = ?", (session.get("username"),))
            if not cursor.fetchone():
                session.clear()
            conn.close()
            return jsonify({"status": "success", "message": "Successfully pulled live database from PythonAnywhere!"})
        else:
            return jsonify({"status": "error", "message": f"Server error: {response.text}"}), response.status_code
    except Exception as e:
        return jsonify({"status": "error", "message": f"Connection failed: {str(e)}"}), 500

@app.route("/local/sync/push", methods=["POST"])
@login_required
def local_sync_push():
    is_local = "localhost" in request.host or "127.0.0.1" in request.host or "192.168" in request.host
    if not is_local:
        return jsonify({"status": "error", "message": "Push sync can only be initiated from a local running instance."}), 403
        
    if not os.path.exists(DB_FILE):
        return jsonify({"status": "error", "message": "Local database file not found."}), 404
        
    try:
        with open(DB_FILE, "rb") as f:
            files = {"file": ("family_wealth.db", f, "application/x-sqlite3")}
            response = requests.post(f"{LIVE_SYNC_URL}/api/db/upload", params={"token": app.secret_key}, files=files, timeout=15)
            
        if response.status_code == 200:
            return jsonify({"status": "success", "message": "Successfully pushed local database to PythonAnywhere!"})
        else:
            return jsonify({"status": "error", "message": f"Server error: {response.text}"}), response.status_code
    except Exception as e:
        return jsonify({"status": "error", "message": f"Connection failed: {str(e)}"}), 500

if __name__ == "__main__":
    init_db()
    update_account_balances()
    app.run(host="0.0.0.0", port=5000, debug=True)
