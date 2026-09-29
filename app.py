import os
import sqlite3
from datetime import datetime, date
from flask import Flask, render_template_string, request, jsonify, g, session
from werkzeug.security import generate_password_hash, check_password_hash

# Handle PostgreSQL on Render or SQLite locally
DATABASE_URL = os.environ.get('DATABASE_URL')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'savers_growth_31day_cycle_key_2026_secured')

# -----------------------------------------------------------------------------
# DATABASE SETUP & SPEED INDEXING
# -----------------------------------------------------------------------------
def get_db():
    if 'db' not in g:
        if DATABASE_URL:
            import psycopg2
            import psycopg2.extras
            url = DATABASE_URL.replace("postgres://", "postgresql://")
            g.db = psycopg2.connect(url, cursor_factory=psycopg2.extras.DictCursor)
        else:
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'savers_growth.db')
            g.db = sqlite3.connect(db_path)
            g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def query_param():
    return "%s" if DATABASE_URL else "?"

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        p = query_param()

        is_postgres = bool(DATABASE_URL)
        pk_type = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS members (
                id {pk_type},
                member_id TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                phone TEXT DEFAULT '',
                email TEXT DEFAULT '',
                username TEXT UNIQUE,
                password_hash TEXT DEFAULT '',
                daily_target REAL DEFAULT 500.0,
                current_cycle INTEGER DEFAULT 1,
                cycle_days INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS savings (
                id {pk_type},
                member_id TEXT NOT NULL,
                amount REAL NOT NULL,
                date TEXT NOT NULL,
                month_year TEXT NOT NULL,
                is_service_fee INTEGER DEFAULT 0,
                days_credited INTEGER DEFAULT 0,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS withdrawals (
                id {pk_type},
                member_id TEXT NOT NULL,
                amount REAL NOT NULL,
                withdrawal_type TEXT NOT NULL,
                fee_deducted REAL DEFAULT 0,
                date TEXT NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS loans (
                id {pk_type},
                member_id TEXT NOT NULL,
                amount REAL NOT NULL,
                interest_rate REAL DEFAULT 0.0,
                repayment_amount REAL NOT NULL,
                amount_paid REAL DEFAULT 0,
                status TEXT DEFAULT 'active',
                issue_date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS loan_repayments (
                id {pk_type},
                loan_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                date TEXT NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS service_fees (
                id {pk_type},
                member_id TEXT NOT NULL,
                amount REAL NOT NULL,
                month_year TEXT NOT NULL,
                description TEXT,
                date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS admin_users (
                id {pk_type},
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # SPEED OPTIMIZATION: Database Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_members_mid ON members(member_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_members_uname ON members(username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_savings_mid ON savings(member_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_loans_mid ON loans(member_id)")

        db.commit()

        # Seed Primary Admin User (Saversadmin)
        admin_pass_hash = generate_password_hash('saversrotimi1972')
        cursor.execute(f"SELECT COUNT(*) FROM admin_users WHERE username = {p}", ('Saversadmin',))
        row = cursor.fetchone()
        if not row or row[0] == 0:
            cursor.execute(f"INSERT INTO admin_users (username, password_hash) VALUES ({p}, {p})", ('Saversadmin', admin_pass_hash))
            db.commit()

        # Seed Member #1: Oladele Rotimi Williams (SVR0001) as Admin/Owner
        cursor.execute(f"SELECT COUNT(*) FROM members WHERE member_id = {p}", ('SVR0001',))
        row_m = cursor.fetchone()
        if not row_m or row_m[0] == 0:
            cursor.execute(f'''
                INSERT INTO members (member_id, full_name, phone, username, password_hash, daily_target, current_cycle, cycle_days, status)
                VALUES ({p}, {p}, {p}, {p}, {p}, 1000.0, 1, 0, 'Owner/Admin')
            ''', ('SVR0001', 'Oladele Rotimi Williams', '09018363715', 'Saversadmin', admin_pass_hash))
            db.commit()

with app.app_context():
    init_db()

# -----------------------------------------------------------------------------
# AUTHENTICATION API ENDPOINTS
# -----------------------------------------------------------------------------

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password required.'}), 400

    db = get_db()
    cursor = db.cursor()
    p = query_param()

    # 1. Check Admin Account First
    cursor.execute(f"SELECT * FROM admin_users WHERE username = {p}", (username,))
    admin = cursor.fetchone()
    if admin and check_password_hash(admin['password_hash'], password):
        session['user_id'] = admin['username']
        session['role'] = 'admin'
        session['member_id'] = 'SVR0001'
        session['full_name'] = 'Oladele Rotimi Williams'
        return jsonify({'success': True, 'role': 'admin', 'name': 'Oladele Rotimi Williams', 'member_id': 'SVR0001'})

    # 2. Check Member Accounts
    cursor.execute(f"SELECT * FROM members WHERE username = {p} OR member_id = {p}", (username, username))
    member = cursor.fetchone()
    if member and member['password_hash'] and check_password_hash(member['password_hash'], password):
        session['user_id'] = member['username'] or member['member_id']
        session['role'] = 'admin' if member['status'] == 'Owner/Admin' else 'member'
        session['member_id'] = member['member_id']
        session['full_name'] = member['full_name']
        return jsonify({'success': True, 'role': session['role'], 'name': member['full_name'], 'member_id': member['member_id']})

    return jsonify({'success': False, 'message': 'Invalid username or password.'}), 401

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully.'})

@app.route('/api/auth/me', methods=['GET'])
def get_current_user():
    if 'role' in session:
        return jsonify({
            'logged_in': True,
            'role': session.get('role'),
            'member_id': session.get('member_id'),
            'full_name': session.get('full_name')
        })
    return jsonify({'logged_in': False})

# -----------------------------------------------------------------------------
# REST API ENDPOINTS
# -----------------------------------------------------------------------------

@app.route('/api/stats/overview', methods=['GET'])
def get_wallet_overview():
    db = get_db()
    cursor = db.cursor()

    cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM savings WHERE is_service_fee = 0')
    total_savings = cursor.fetchone()[0]

    cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM service_fees')
    total_fees = cursor.fetchone()[0]

    cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM withdrawals')
    total_withdrawals = cursor.fetchone()[0]

    net_balance = total_savings - total_withdrawals

    return jsonify({
        'total_savings': total_savings,
        'total_fees': total_fees,
        'net_balance': net_balance,
        'total_withdrawals': total_withdrawals
    })

@app.route('/api/members', methods=['GET', 'POST'])
def manage_members():
    db = get_db()
    cursor = db.cursor()
    p = query_param()

    if request.method == 'POST':
        data = request.json or {}
        full_name = data.get('full_name', '').strip()
        
        raw_target = data.get('daily_target')
        try:
            daily_target = float(raw_target) if raw_target not in (None, '') else 500.0
        except (ValueError, TypeError):
            daily_target = 500.0

        if not full_name:
            return jsonify({'success': False, 'message': 'Full name is required.'}), 400

        cursor.execute('SELECT COUNT(*) FROM members')
        count = cursor.fetchone()[0] + 1
        member_id = f"SVR{count:04d}"

        while True:
            cursor.execute(f'SELECT id FROM members WHERE member_id = {p}', (member_id,))
            if not cursor.fetchone():
                break
            count += 1
            member_id = f"SVR{count:04d}"

        default_username = f"user_{member_id.lower()}"
        default_pass_hash = generate_password_hash("savers123")

        try:
            cursor.execute(f'''
                INSERT INTO members (member_id, full_name, phone, email, username, password_hash, daily_target, current_cycle, cycle_days, status)
                VALUES ({p}, {p}, '', '', {p}, {p}, {p}, 1, 0, 'active')
            ''', (member_id, full_name, default_username, default_pass_hash, daily_target))
            db.commit()
            return jsonify({'success': True, 'message': f'Member registered! ID: {member_id}', 'member_id': member_id})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500

    else:
        cursor.execute('''
            SELECT m.id, m.member_id, m.full_name, m.phone, m.email, m.username, m.daily_target,
                   m.current_cycle, m.cycle_days, m.status, m.created_at,
                   COALESCE((SELECT SUM(amount) FROM savings WHERE member_id = m.member_id AND is_service_fee = 0), 0) as total_saved,
                   COALESCE((SELECT SUM(amount) FROM withdrawals WHERE member_id = m.member_id), 0) as total_withdrawn,
                   COALESCE((SELECT SUM(repayment_amount - amount_paid) FROM loans WHERE member_id = m.member_id AND status = 'active'), 0) as active_loan
            FROM members m
            ORDER BY m.id ASC
        ''')
        rows = cursor.fetchall()
        members = []
        for r in rows:
            members.append({
                'id': r['id'],
                'member_id': r['member_id'],
                'full_name': r['full_name'],
                'phone': r['phone'] or '',
                'email': r['email'] or '',
                'username': r['username'] or '',
                'daily_target': r['daily_target'],
                'current_cycle': r['current_cycle'],
                'cycle_days': r['cycle_days'],
                'status': r['status'],
                'total_saved': r['total_saved'],
                'total_withdrawn': r['total_withdrawn'],
                'net_balance': r['total_saved'] - r['total_withdrawn'],
                'active_loan': r['active_loan'],
                'created_at': str(r['created_at'])
            })
        return jsonify(members)

@app.route('/api/member/<member_id>', methods=['GET', 'PUT', 'DELETE'])
def member_detail_update_delete(member_id):
    db = get_db()
    cursor = db.cursor()
    p = query_param()

    if request.method == 'DELETE':
        cursor.execute(f'SELECT member_id, full_name FROM members WHERE member_id = {p}', (member_id,))
        m = cursor.fetchone()
        if not m:
            return jsonify({'success': False, 'message': 'Member not found.'}), 404

        actual_id = m['member_id']

        cursor.execute(f'DELETE FROM savings WHERE member_id = {p}', (actual_id,))
        cursor.execute(f'DELETE FROM withdrawals WHERE member_id = {p}', (actual_id,))
        cursor.execute(f'DELETE FROM loans WHERE member_id = {p}', (actual_id,))
        cursor.execute(f'DELETE FROM service_fees WHERE member_id = {p}', (actual_id,))
        cursor.execute(f'DELETE FROM members WHERE member_id = {p}', (actual_id,))
        db.commit()

        return jsonify({'success': True, 'message': f'Member {m["full_name"]} ({actual_id}) deleted successfully!'})

    elif request.method == 'PUT':
        data = request.json or {}
        full_name = data.get('full_name', '').strip()
        username = data.get('username', '').strip()
        new_password = data.get('password', '').strip()
        raw_target = data.get('daily_target')
        
        try:
            daily_target = float(raw_target) if raw_target not in (None, '') else 500.0
        except (ValueError, TypeError):
            daily_target = 500.0

        if new_password:
            pass_hash = generate_password_hash(new_password)
            cursor.execute(f'''
                UPDATE members 
                SET full_name = {p}, username = {p}, password_hash = {p}, daily_target = {p}
                WHERE member_id = {p}
            ''', (full_name, username, pass_hash, daily_target, member_id))
        else:
            cursor.execute(f'''
                UPDATE members 
                SET full_name = {p}, username = {p}, daily_target = {p}
                WHERE member_id = {p}
            ''', (full_name, username, daily_target, member_id))

        db.commit()
        return jsonify({'success': True, 'message': 'Member profile & credentials updated!'})

    else:
        cursor.execute(f'''
            SELECT m.*,
                   COALESCE((SELECT SUM(amount) FROM savings WHERE member_id = m.member_id AND is_service_fee = 0), 0) as total_saved,
                   COALESCE((SELECT SUM(amount) FROM withdrawals WHERE member_id = m.member_id), 0) as total_withdrawn,
                   COALESCE((SELECT SUM(repayment_amount - amount_paid) FROM loans WHERE member_id = m.member_id AND status = 'active'), 0) as active_loan
            FROM members m WHERE m.member_id = {p}
        ''', (member_id,))
        m = cursor.fetchone()

        if not m:
            return jsonify({'success': False, 'message': 'Member not found.'}), 404

        member_id_actual = m['member_id']

        # FETCH LAST 5 CONTRIBUTIONS ONLY
        cursor.execute(f'''
            SELECT id, amount, date, notes, is_service_fee, days_credited 
            FROM savings 
            WHERE member_id = {p} 
            ORDER BY id DESC LIMIT 5
        ''', (member_id_actual,))
        savings = [dict(s) for s in cursor.fetchall()]

        return jsonify({
            'success': True,
            'member': {
                'id': m['id'],
                'member_id': m['member_id'],
                'full_name': m['full_name'],
                'username': m['username'] or '',
                'daily_target': m['daily_target'],
                'current_cycle': m['current_cycle'],
                'cycle_days': m['cycle_days'],
                'status': m['status'],
                'total_saved': m['total_saved'],
                'net_balance': m['total_saved'] - m['total_withdrawn'],
                'active_loan': m['active_loan']
            },
            'recent_savings': savings
        })

@app.route('/api/member/<member_id>/reset-ledger', methods=['POST'])
def reset_single_member_ledger(member_id):
    db = get_db()
    cursor = db.cursor()
    p = query_param()

    cursor.execute(f'SELECT id, full_name, member_id FROM members WHERE member_id = {p}', (member_id,))
    m = cursor.fetchone()
    if not m:
        return jsonify({'success': False, 'message': 'Member not found.'}), 404

    actual_id = m['member_id']

    # Delete loan repayments associated with member's loans
    cursor.execute(f'''
        DELETE FROM loan_repayments 
        WHERE loan_id IN (SELECT id FROM loans WHERE member_id = {p})
    ''', (actual_id,))

    # Delete all transactions for this specific member
    cursor.execute(f'DELETE FROM savings WHERE member_id = {p}', (actual_id,))
    cursor.execute(f'DELETE FROM service_fees WHERE member_id = {p}', (actual_id,))
    cursor.execute(f'DELETE FROM withdrawals WHERE member_id = {p}', (actual_id,))
    cursor.execute(f'DELETE FROM loans WHERE member_id = {p}', (actual_id,))

    # Reset member cycle counters back to Cycle 1, 0 Days
    cursor.execute(f'UPDATE members SET current_cycle = 1, cycle_days = 0 WHERE member_id = {p}', (actual_id,))

    db.commit()
    return jsonify({'success': True, 'message': f'Financial data for {m["full_name"]} ({actual_id}) reset successfully!'})

# -----------------------------------------------------------------------------
# SAVINGS LOGIC
# -----------------------------------------------------------------------------
@app.route('/api/savings', methods=['GET', 'POST'])
def handle_savings():
    db = get_db()
    cursor = db.cursor()
    p = query_param()

    if request.method == 'POST':
        data = request.json or {}
        member_id = data.get('member_id')
        try:
            deposit_amount = float(data.get('amount', 0))
        except ValueError:
            deposit_amount = 0.0

        savings_date = data.get('date') or date.today().isoformat()
        notes = data.get('notes', '').strip()

        if not member_id or deposit_amount <= 0:
            return jsonify({'success': False, 'message': 'Select member and enter a valid amount.'}), 400

        cursor.execute(f'SELECT full_name, current_cycle, cycle_days, daily_target FROM members WHERE member_id = {p}', (member_id,))
        m = cursor.fetchone()
        if not m:
            return jsonify({'success': False, 'message': 'Member not found.'}), 404

        full_name = m['full_name']
        current_cycle = m['current_cycle']
        cycle_days = m['cycle_days']
        daily_target = m['daily_target'] if m['daily_target'] > 0 else 500.0
        month_year = datetime.strptime(savings_date, '%Y-%m-%d').strftime('%Y-%m')

        remaining_cash = deposit_amount
        total_fees_collected = 0.0
        total_savings_credited = 0.0
        total_days_added = 0

        while remaining_cash > 0:
            if cycle_days == 0:
                fee_deducted = min(daily_target, remaining_cash)
                remaining_cash -= fee_deducted
                total_fees_collected += fee_deducted

                cursor.execute(f'''
                    INSERT INTO savings (member_id, amount, date, month_year, is_service_fee, days_credited, notes)
                    VALUES ({p}, {p}, {p}, {p}, 1, 0, {p})
                ''', (member_id, fee_deducted, savings_date, month_year, f'Cycle {current_cycle} Service Fee'))

                cursor.execute(f'''
                    INSERT INTO service_fees (member_id, amount, month_year, description, date)
                    VALUES ({p}, {p}, {p}, {p}, {p})
                ''', (member_id, fee_deducted, month_year, f'Cycle {current_cycle} First Save Fee', savings_date))

                if remaining_cash <= 0:
                    break

            days_needed_in_current_cycle = 31 - cycle_days
            max_cash_needed = days_needed_in_current_cycle * daily_target

            cash_for_this_cycle = min(remaining_cash, max_cash_needed)
            days_bought = int(cash_for_this_cycle / daily_target)

            if days_bought > 0:
                cash_spent = days_bought * daily_target
                remaining_cash -= cash_spent
                total_savings_credited += cash_spent
                total_days_added += days_bought
                cycle_days += days_bought

                cursor.execute(f'''
                    INSERT INTO savings (member_id, amount, date, month_year, is_service_fee, days_credited, notes)
                    VALUES ({p}, {p}, {p}, {p}, 0, {p}, {p})
                ''', (member_id, cash_spent, savings_date, month_year, days_bought, notes or f'Contribution ({days_bought} days)'))

            if cycle_days >= 31:
                current_cycle += 1
                cycle_days = 0
            else:
                break

        cursor.execute(f'UPDATE members SET current_cycle = {p}, cycle_days = {p} WHERE member_id = {p}', 
                       (current_cycle, cycle_days, member_id))
        db.commit()

        msg = f"Processed ₦{deposit_amount:,.2f} for {full_name}! "
        msg += f"₦{total_fees_collected:,.2f} deducted in service fees, ₦{total_savings_credited:,.2f} added to savings ({total_days_added} days). "
        msg += f"Status: Cycle {current_cycle} ({cycle_days} / 31 days)."

        return jsonify({'success': True, 'message': msg})

    else:
        cursor.execute('''
            SELECT s.*, m.full_name 
            FROM savings s
            JOIN members m ON s.member_id = m.member_id
            ORDER BY s.id DESC LIMIT 50
        ''')
        rows = cursor.fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/savings/<int:savings_id>', methods=['DELETE'])
def delete_savings(savings_id):
    db = get_db()
    cursor = db.cursor()
    p = query_param()

    cursor.execute(f'SELECT member_id, amount, is_service_fee, days_credited FROM savings WHERE id = {p}', (savings_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'success': False, 'message': 'Entry not found.'}), 404

    member_id = row['member_id']
    is_fee = row['is_service_fee']
    days_credited = row['days_credited']

    cursor.execute(f'DELETE FROM savings WHERE id = {p}', (savings_id,))

    if is_fee:
        cursor.execute(f'DELETE FROM service_fees WHERE member_id = {p} AND amount = {p}', (member_id, row['amount']))
        cursor.execute(f'UPDATE members SET cycle_days = 0 WHERE member_id = {p}', (member_id,))
    else:
        cursor.execute(f'SELECT cycle_days FROM members WHERE member_id = {p}', (member_id,))
        m = cursor.fetchone()
        if m:
            new_days = max(0, m['cycle_days'] - days_credited)
            cursor.execute(f'UPDATE members SET cycle_days = {p} WHERE member_id = {p}', (new_days, member_id))

    db.commit()
    return jsonify({'success': True, 'message': 'Contribution deleted!'})

# -----------------------------------------------------------------------------
# WITHDRAWAL
# -----------------------------------------------------------------------------
@app.route('/api/withdrawals', methods=['POST'])
def process_withdrawal():
    db = get_db()
    cursor = db.cursor()
    p = query_param()
    data = request.json or {}

    member_id = data.get('member_id')
    try:
        amount = float(data.get('amount', 0))
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid withdrawal amount.'}), 400

    withdrawal_type = data.get('withdrawal_type', 'instant')
    w_date = data.get('date') or date.today().isoformat()
    notes = data.get('notes', '')

    if not member_id or amount <= 0:
        return jsonify({'success': False, 'message': 'Select member and enter withdrawal amount.'}), 400

    cursor.execute(f'SELECT COALESCE(SUM(amount), 0) FROM savings WHERE member_id = {p} AND is_service_fee = 0', (member_id,))
    total_saved = cursor.fetchone()[0]
    cursor.execute(f'SELECT COALESCE(SUM(amount), 0) FROM withdrawals WHERE member_id = {p}', (member_id,))
    total_withdrawn = cursor.fetchone()[0]
    current_balance = total_saved - total_withdrawn

    if amount > current_balance:
        return jsonify({'success': False, 'message': f'Insufficient balance! Available: ₦{current_balance:,.2f}'}), 400

    cursor.execute(f'''
        INSERT INTO withdrawals (member_id, amount, withdrawal_type, fee_deducted, date, notes)
        VALUES ({p}, {p}, {p}, 0.0, {p}, {p})
    ''', (member_id, amount, withdrawal_type, w_date, notes))

    if withdrawal_type == 'reset':
        cursor.execute(f'''
            UPDATE members 
            SET current_cycle = current_cycle + 1, cycle_days = 0 
            WHERE member_id = {p}
        ''', (member_id,))

    db.commit()
    return jsonify({'success': True, 'message': 'Withdrawal processed successfully!'})

# -----------------------------------------------------------------------------
# LOANS API
# -----------------------------------------------------------------------------
@app.route('/api/loans', methods=['GET', 'POST'])
def handle_loans():
    db = get_db()
    cursor = db.cursor()
    p = query_param()

    if request.method == 'POST':
        data = request.json or {}
        member_id = data.get('member_id')
        try:
            amount = float(data.get('amount', 0))
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid amount.'}), 400

        issue_date = data.get('issue_date') or date.today().isoformat()

        if not member_id or amount <= 0:
            return jsonify({'success': False, 'message': 'Select member and enter loan amount.'}), 400

        cursor.execute(f'''
            INSERT INTO loans (member_id, amount, interest_rate, repayment_amount, issue_date)
            VALUES ({p}, {p}, 0.0, {p}, {p})
        ''', (member_id, amount, amount, issue_date))

        db.commit()
        return jsonify({'success': True, 'message': 'Loan issued successfully!'})

    else:
        cursor.execute('''
            SELECT l.*, m.full_name
            FROM loans l
            JOIN members m ON l.member_id = m.member_id
            ORDER BY l.id DESC
        ''')
        rows = cursor.fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/loans/repay', methods=['POST'])
def repay_loan():
    db = get_db()
    cursor = db.cursor()
    p = query_param()
    data = request.json or {}

    loan_id = data.get('loan_id')
    try:
        amount = float(data.get('amount', 0))
    except ValueError:
        amount = 0.0

    repay_date = data.get('date') or date.today().isoformat()
    notes = data.get('notes', 'Loan Repayment')

    if not loan_id or amount <= 0:
        return jsonify({'success': False, 'message': 'Valid Loan ID and Repayment Amount required.'}), 400

    cursor.execute(f'SELECT repayment_amount, amount_paid FROM loans WHERE id = {p}', (loan_id,))
    loan = cursor.fetchone()
    if not loan:
        return jsonify({'success': False, 'message': 'Loan record not found.'}), 404

    new_paid = loan['amount_paid'] + amount
    status = 'cleared' if new_paid >= loan['repayment_amount'] else 'active'

    cursor.execute(f'INSERT INTO loan_repayments (loan_id, amount, date, notes) VALUES ({p}, {p}, {p}, {p})',
                   (loan_id, amount, repay_date, notes))
    cursor.execute(f'UPDATE loans SET amount_paid = {p}, status = {p} WHERE id = {p}', (new_paid, status, loan_id))

    db.commit()
    return jsonify({'success': True, 'message': 'Loan repayment recorded!'})

# -----------------------------------------------------------------------------
# DAILY TRACKER & SERVICE FEES
# -----------------------------------------------------------------------------
@app.route('/api/tracker/daily', methods=['GET'])
def get_daily_tracker():
    db = get_db()
    cursor = db.cursor()

    query = '''
        SELECT 'Savings Contribution' as tx_type, s.date, s.member_id, m.full_name, s.amount as inflow, 0.0 as outflow, COALESCE(s.notes, 'Savings Deposit') as notes, s.created_at, s.id
        FROM savings s JOIN members m ON s.member_id = m.member_id WHERE s.is_service_fee = 0
        UNION ALL
        SELECT 'Service Fee' as tx_type, f.date, f.member_id, m.full_name, f.amount as inflow, 0.0 as outflow, COALESCE(f.description, 'Service Fee') as notes, f.created_at, f.id
        FROM service_fees f JOIN members m ON f.member_id = m.member_id
        UNION ALL
        SELECT 'Loan Repayment' as tx_type, lr.date, l.member_id, m.full_name, lr.amount as inflow, 0.0 as outflow, COALESCE(lr.notes, 'Loan Repayment') as notes, lr.created_at, lr.id
        FROM loan_repayments lr JOIN loans l ON lr.loan_id = l.id JOIN members m ON l.member_id = m.member_id
        UNION ALL
        SELECT 'Withdrawal Payout' as tx_type, w.date, w.member_id, m.full_name, 0.0 as inflow, w.amount as outflow, COALESCE(w.notes, 'Member Withdrawal') as notes, w.created_at, w.id
        FROM withdrawals w JOIN members m ON w.member_id = m.member_id
        UNION ALL
        SELECT 'Loan Disbursement' as tx_type, l.issue_date as date, l.member_id, m.full_name, 0.0 as inflow, l.amount as outflow, 'Loan Disbursed' as notes, l.created_at, l.id
        FROM loans l JOIN members m ON l.member_id = m.member_id
        ORDER BY date DESC, id DESC
    '''
    cursor.execute(query)
    rows = cursor.fetchall()
    logs = [dict(r) for r in rows]

    total_inflow = sum(r['inflow'] for r in logs)
    total_outflow = sum(r['outflow'] for r in logs)
    net_cashflow = total_inflow - total_outflow

    return jsonify({
        'logs': logs,
        'total_inflow': total_inflow,
        'total_outflow': total_outflow,
        'net_cashflow': net_cashflow
    })

@app.route('/api/service-fees', methods=['GET'])
def get_service_fees():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT f.*, m.full_name 
        FROM service_fees f
        JOIN members m ON f.member_id = m.member_id
        ORDER BY f.date DESC, f.id DESC
    ''')
    rows = cursor.fetchall()
    fees = [dict(r) for r in rows]
    total_fees = sum(f['amount'] for f in fees)

    return jsonify({
        'fees': fees,
        'total_fees': total_fees
    })

# -----------------------------------------------------------------------------
# MAINTENANCE
# -----------------------------------------------------------------------------
@app.route('/api/maintenance/resync', methods=['POST'])
def resync_ledger():
    db = get_db()
    cursor = db.cursor()

    cursor.execute('''
        UPDATE loans 
        SET status = 'cleared' 
        WHERE amount_paid >= repayment_amount AND status = 'active'
    ''')
    db.commit()

    return jsonify({'success': True, 'message': 'Financial counters rebuild & ledger synchronization completed!'})

@app.route('/api/maintenance/reset-all-ledgers', methods=['POST'])
def reset_all_ledgers():
    db = get_db()
    cursor = db.cursor()

    cursor.execute('DELETE FROM savings')
    cursor.execute('DELETE FROM withdrawals')
    cursor.execute('DELETE FROM loans')
    cursor.execute('DELETE FROM loan_repayments')
    cursor.execute('DELETE FROM service_fees')

    cursor.execute('UPDATE members SET current_cycle = 1, cycle_days = 0')
    db.commit()

    return jsonify({'success': True, 'message': 'ALL system financial ledgers reset to zero! Member profiles preserved.'})

@app.route('/api/admin/password', methods=['POST'])
def update_password():
    db = get_db()
    cursor = db.cursor()
    p = query_param()
    data = request.json or {}

    old_pass = data.get('old_password', '')
    new_pass = data.get('new_password', '')

    if not old_pass or not new_pass:
        return jsonify({'success': False, 'message': 'Both existing and new password required.'}), 400

    cursor.execute("SELECT password_hash FROM admin_users WHERE username = 'Saversadmin'")
    row = cursor.fetchone()

    if row and check_password_hash(row['password_hash'], old_pass):
        new_hash = generate_password_hash(new_pass)
        cursor.execute(f"UPDATE admin_users SET password_hash = {p} WHERE username = 'Saversadmin'", (new_hash,))
        db.commit()
        return jsonify({'success': True, 'message': 'Admin password updated successfully!'})
    else:
        return jsonify({'success': False, 'message': 'Incorrect current password.'}), 400


# -----------------------------------------------------------------------------
# FRONTEND TEMPLATE
# -----------------------------------------------------------------------------
INDEX_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Savers Growth</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    
    <style>
        :root {
            --bg-body: #f8fafc;
            --card-bg: #ffffff;
            --text-dark: #0f172a;
            --text-muted: #64748b;
            --primary-green: #10b981;
            --primary-green-dark: #059669;
            --primary-red: #ef4444;
            --amber-fee: #d97706;
            --purple-cycle: #9333ea;
            --purple-bg: #fae8ff;
            --purple-border: #e9d5ff;
            --border-light: #cbd5e1;
            --radius-card: 16px;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; -webkit-tap-highlight-color: transparent; }

        body {
            background-color: var(--bg-body);
            color: var(--text-dark);
            display: flex; flex-direction: column; min-height: 100vh;
        }

        /* Toast Notifications */
        #toast-container { position: fixed; top: 16px; right: 16px; z-index: 9999; }
        .toast {
            background: #1e293b; color: #fff; padding: 12px 18px; border-radius: 12px;
            margin-bottom: 8px; box-shadow: 0 8px 20px rgba(0,0,0,0.15);
            display: flex; align-items: center; gap: 8px; animation: slideIn 0.25s forwards;
            font-size: 0.88rem; font-weight: 600;
        }
        .toast.success { background: var(--primary-green-dark); }
        .toast.error { background: var(--primary-red); }
        @keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }

        /* Header */
        header {
            background: #ffffff; padding: 0.85rem 1rem;
            display: flex; justify-content: space-between; align-items: center;
            border-bottom: 1.5px solid var(--border-light);
            position: sticky; top: 0; z-index: 100;
        }
        header .brand-box { display: flex; align-items: center; gap: 10px; cursor: pointer; }
        header .sprout-icon {
            background: var(--primary-green); color: #ffffff;
            width: 36px; height: 36px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center; font-size: 1.1rem;
        }
        header .brand-title { font-size: 1.25rem; font-weight: 800; color: var(--text-dark); letter-spacing: -0.3px; }
        header .btn-logout {
            background: #ffffff; color: var(--text-dark); border: 1.5px solid var(--text-dark);
            padding: 6px 14px; border-radius: 20px; font-weight: 700; font-size: 0.82rem;
            cursor: pointer; min-height: 36px;
        }

        /* Search Bar */
        .search-container { padding: 0.85rem 1rem 0.4rem 1rem; max-width: 600px; margin: 0 auto; width: 100%; position: relative; }
        .search-wrapper { position: relative; width: 100%; }
        .search-wrapper i { position: absolute; left: 16px; top: 50%; transform: translateY(-50%); color: #94a3b8; font-size: 0.95rem; }
        .search-input {
            width: 100%; padding: 10px 16px 10px 42px; border-radius: 30px;
            border: 1.5px solid var(--border-light); font-size: 0.9rem; outline: none; background: #ffffff;
        }
        .search-results-dropdown {
            position: absolute; top: 100%; left: 1rem; right: 1rem; background: #ffffff;
            border: 1.5px solid var(--border-light); border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.1);
            z-index: 500; max-height: 240px; overflow-y: auto; display: none; margin-top: 4px;
        }
        .search-result-item {
            padding: 12px 16px; border-bottom: 1px solid var(--border-light); cursor: pointer;
            display: flex; justify-content: space-between; align-items: center; font-size: 0.88rem; font-weight: 600;
        }

        .app-container { max-width: 600px; margin: 0 auto; width: 100%; padding: 0.5rem 1rem 2rem 1rem; flex: 1; }

        .view-section { display: none; }
        .view-section.active { display: block; animation: fadeIn 0.2s forwards; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

        .view-header-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.1rem; }
        .view-title-group { display: flex; align-items: center; gap: 8px; font-size: 1.15rem; font-weight: 800; }
        .btn-back {
            background: #e2e8f0; color: var(--text-dark); border: none;
            padding: 8px 14px; border-radius: 10px; font-weight: 700; font-size: 0.82rem; cursor: pointer;
        }
        .btn-add-header {
            background: var(--primary-green); color: #ffffff; border: none;
            padding: 8px 14px; border-radius: 10px; font-weight: 700; font-size: 0.82rem; cursor: pointer;
            display: flex; align-items: center; gap: 6px;
        }

        /* Login Screen Card */
        .login-card {
            background: #ffffff; border: 1.5px solid var(--border-light);
            border-radius: 20px; padding: 1.75rem 1.25rem; max-width: 420px; margin: 2rem auto;
            box-shadow: 0 4px 12px rgba(0,0,0,0.03);
        }
        .login-header { text-align: center; margin-bottom: 1.5rem; }
        .login-header .sprout-big {
            background: var(--primary-green); color: #fff; width: 56px; height: 56px;
            border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
            font-size: 1.8rem; margin-bottom: 10px;
        }
        .login-header h2 { font-size: 1.35rem; font-weight: 800; color: var(--text-dark); }

        /* 3-COLUMN HOMEPAGE GRID */
        .grid-3-col {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            margin-top: 0.4rem;
        }

        .menu-card {
            background: var(--card-bg);
            border: 1.5px solid var(--border-light);
            border-radius: var(--radius-card);
            padding: 0.85rem 0.3rem;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            cursor: pointer;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
            transition: all 0.15s;
            min-height: 92px;
        }
        .menu-card:active { transform: scale(0.97); }
        
        .menu-card .icon-badge {
            width: 36px; height: 36px; border-radius: 10px;
            display: flex; align-items: center; justify-content: center;
            font-size: 1.1rem; margin-bottom: 4px;
        }
        .icon-badge.pink { background: #ffe4e6; }
        .icon-badge.mint { background: #d1fae5; }
        .icon-badge.blue { background: #e0f2fe; }
        .icon-badge.yellow { background: #fef3c7; }
        .icon-badge.purple { background: #f3e8ff; }
        .icon-badge.teal { background: #ccfbf1; }

        .menu-card .card-heading {
            font-size: 0.8rem;
            font-weight: 800;
            color: var(--text-dark);
            line-height: 1.15;
        }

        .grid-row-4-center {
            display: flex;
            justify-content: center;
            gap: 10px;
            margin-top: 10px;
        }
        .grid-row-4-center .menu-card {
            width: calc(33.333% - 6px);
        }

        .overview-box {
            background: #f0fdf4; border: 1.5px solid #bbf7d0; border-radius: 16px;
            padding: 1.25rem; margin-bottom: 1.25rem; display: flex; flex-direction: column; gap: 10px;
        }
        .overview-row { display: flex; justify-content: space-between; align-items: center; font-size: 0.9rem; font-weight: 600; }
        .overview-row .amount-saved { font-size: 1.1rem; font-weight: 800; color: var(--primary-green-dark); }
        .overview-row .amount-fees { font-size: 1.1rem; font-weight: 800; color: var(--amber-fee); }
        .overview-row .amount-net { font-size: 1.2rem; font-weight: 800; color: var(--primary-green-dark); }
        .overview-divider { height: 1px; background: #cbd5e1; margin: 2px 0; }

        .action-stack { display: flex; flex-direction: column; gap: 0.75rem; }
        .btn-action-primary {
            background: var(--primary-red); color: white; border: none; padding: 14px;
            border-radius: 12px; font-weight: 800; font-size: 0.95rem; cursor: pointer;
            display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 48px;
        }
        .btn-action-secondary {
            background: #e2e8f0; color: var(--text-dark); border: none; padding: 14px;
            border-radius: 12px; font-weight: 800; font-size: 0.95rem; cursor: pointer;
            display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 48px;
        }

        .filter-row { display: flex; gap: 8px; margin-bottom: 1rem; }
        .filter-row input { flex: 1; padding: 10px 14px; border-radius: 12px; border: 1.5px solid var(--border-light); font-size: 0.88rem; background: #fff; }

        .member-card-item {
            background: #ffffff; border: 1.5px solid var(--border-light);
            border-radius: 18px; padding: 1.1rem; margin-bottom: 0.85rem;
            cursor: pointer; box-shadow: 0 2px 4px rgba(0,0,0,0.01);
        }
        .member-card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
        .member-avatar-group { display: flex; align-items: center; gap: 12px; }
        .member-avatar {
            width: 44px; height: 44px; border-radius: 50%; background: #d1fae5; color: #059669;
            display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 1.2rem;
        }
        .member-info .name { font-size: 1.05rem; font-weight: 800; color: var(--text-dark); margin-bottom: 2px; }
        .member-info .code { font-size: 0.85rem; color: #94a3b8; font-weight: 600; }

        .member-stats-box {
            background: #f8fafc; border-radius: 12px; padding: 10px 14px;
            display: grid; grid-template-columns: 1fr 1fr; gap: 6px;
            font-size: 0.85rem; margin-bottom: 10px;
        }
        .stat-line { font-weight: 600; color: var(--text-dark); }
        .stat-line .val-green { color: var(--primary-green-dark); font-weight: 800; }
        .stat-line .val-red { color: var(--primary-red); font-weight: 800; }

        .cycle-status-btn {
            background: var(--purple-bg); border: 1px solid var(--purple-border); color: var(--purple-cycle);
            padding: 8px; border-radius: 10px; text-align: center; font-weight: 700; font-size: 0.82rem;
            display: flex; align-items: center; justify-content: center; gap: 6px;
        }

        /* Modals */
        .modal-overlay {
            position: fixed; top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(3px);
            z-index: 1000; display: none; align-items: center; justify-content: center; padding: 0.85rem;
        }
        .modal-overlay.active { display: flex; }
        .modal-card {
            background: #ffffff; border-radius: 20px; width: 100%; max-width: 480px;
            max-height: 90vh; overflow-y: auto; padding: 1.25rem; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.1);
            animation: modalUp 0.2s forwards;
        }
        @keyframes modalUp { from { transform: translateY(15px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }

        .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.85rem; }
        .modal-title { font-size: 1.1rem; font-weight: 800; color: var(--text-dark); }
        .modal-close { background: none; border: none; font-size: 1.5rem; color: var(--text-muted); cursor: pointer; }

        .modal-nav-tabs {
            display: flex; gap: 6px; overflow-x: auto; padding-bottom: 6px; margin-bottom: 1rem;
            border-bottom: 1px solid var(--border-light);
        }
        .modal-tab {
            padding: 6px 12px; border-radius: 16px; font-size: 0.8rem; font-weight: 700;
            border: 1px solid var(--border-light); cursor: pointer; white-space: nowrap; color: var(--text-muted);
            background: #ffffff;
        }
        .modal-tab.active { background: #f0fdf4; border-color: #bbf7d0; color: var(--primary-green-dark); }

        .modal-tab-panel { display: none; }
        .modal-tab-panel.active { display: block; }

        .modal-details-list { display: flex; flex-direction: column; gap: 8px; font-size: 0.9rem; margin-bottom: 1rem; }
        .modal-detail-item { display: flex; justify-content: space-between; font-weight: 600; }

        .modal-cycle-box {
            background: var(--purple-bg); border: 1.5px solid var(--purple-border); border-radius: 12px;
            padding: 10px 14px; margin-bottom: 1rem;
        }
        .modal-cycle-box .lbl { font-size: 0.72rem; font-weight: 800; color: var(--purple-cycle); text-transform: uppercase; margin-bottom: 2px; }
        .modal-cycle-box .val { font-weight: 800; color: var(--purple-cycle); font-size: 0.95rem; }

        .card-form { background: #fff; border: 1.5px solid var(--border-light); border-radius: 16px; padding: 1.1rem; }
        .form-group { display: flex; flex-direction: column; gap: 5px; margin-bottom: 0.85rem; }
        .form-group label { font-size: 0.82rem; font-weight: 700; color: var(--text-dark); }
        .form-control {
            padding: 11px 12px; border-radius: 10px; border: 1.5px solid var(--border-light);
            font-size: 0.9rem; outline: none; background: #fff; width: 100%; min-height: 44px;
        }
        .btn-submit {
            background: var(--primary-green); color: white; border: none; padding: 12px;
            border-radius: 10px; font-weight: 700; font-size: 0.9rem; cursor: pointer; width: 100%; min-height: 46px;
        }

        .manage-subcard {
            background: #f8fafc; border: 1.5px solid var(--border-light);
            border-radius: 12px; padding: 0.85rem; margin-bottom: 0.85rem;
        }
        .manage-subcard-title {
            font-size: 0.88rem; font-weight: 800; margin-bottom: 0.6rem; display: flex; align-items: center; gap: 6px;
        }

        .table-responsive { overflow-x: auto; border-radius: 12px; border: 1.5px solid var(--border-light); }
        table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.82rem; }
        th, td { padding: 9px 10px; border-bottom: 1px solid var(--border-light); }
        th { background: #f8fafc; font-weight: 700; color: var(--text-muted); text-transform: uppercase; font-size: 0.68rem; }
        
        .badge { padding: 3px 6px; border-radius: 6px; font-size: 0.7rem; font-weight: 800; display: inline-block; }
        .badge-savings { background: #d1fae5; color: #065f46; }
        .badge-fee { background: #fef3c7; color: #92400e; }
        .badge-payout { background: #fee2e2; color: #991b1b; }
        .badge-success { background: #d1fae5; color: #065f46; }
        .badge-warning { background: #fef3c7; color: #92400e; }

        .btn-delete-sm {
            background: var(--primary-red); color: white; border: none; padding: 5px 10px;
            border-radius: 6px; font-size: 0.72rem; font-weight: 700; cursor: pointer;
        }
        .btn-edit-sm {
            background: #2563eb; color: white; border: none; padding: 5px 10px;
            border-radius: 6px; font-size: 0.72rem; font-weight: 700; cursor: pointer; margin-right: 2px;
        }
        .btn-repay-sm {
            background: var(--primary-green-dark); color: white; border: none; padding: 5px 10px;
            border-radius: 6px; font-size: 0.72rem; font-weight: 700; cursor: pointer;
        }

        footer {
            background: #ffffff; color: var(--text-dark); text-align: center;
            padding: 1.25rem 1rem; font-size: 0.85rem; font-weight: 700;
            border-top: 1.5px solid var(--border-light); margin-top: auto; line-height: 1.4;
        }
    </style>
</head>
<body>

    <div id="toast-container"></div>

    <header>
        <div class="brand-box" onclick="handleHeaderClick()">
            <div class="sprout-icon"><i class="fa-solid fa-leaf"></i></div>
            <div class="brand-title">Savers Growth</div>
        </div>
        <button class="btn-logout" id="header-auth-btn" onclick="handleAuthAction()">
            Logout
        </button>
    </header>

    <!-- Search Container (Admin Only) -->
    <div class="search-container" id="admin-search-container">
        <div class="search-wrapper">
            <i class="fa-solid fa-magnifying-glass"></i>
            <input type="text" class="search-input" id="global-search-input" 
                   placeholder="Type member ID or digits (e.g. 01)..." 
                   oninput="handleGlobalSearchInput(event)">
        </div>
        <div class="search-results-dropdown" id="search-results-dropdown"></div>
    </div>

    <div class="app-container">

        <!-- VIEW 0: LOGIN SCREEN -->
        <div id="view-login" class="view-section">
            <div class="login-card">
                <div class="login-header">
                    <div class="sprout-big"><i class="fa-solid fa-leaf"></i></div>
                    <h2>Savers Growth Login</h2>
                    <p style="font-size: 0.85rem; color: var(--text-muted); margin-top: 4px;">Sign in to access your portal</p>
                </div>
                <form onsubmit="handleLoginSubmit(event)">
                    <div class="form-group">
                        <label>Username / Member ID</label>
                        <input type="text" class="form-control" id="login-username" placeholder="Enter username or Member ID" required>
                    </div>
                    <div class="form-group">
                        <label>Password</label>
                        <input type="password" class="form-control" id="login-password" placeholder="Enter password" required>
                    </div>
                    <button type="submit" class="btn-submit" style="margin-top: 8px;">Login to System</button>
                </form>
            </div>
        </div>

        <!-- VIEW 1: ADMIN HOMEPAGE GRID -->
        <div id="view-home" class="view-section">
            <div class="grid-3-col">
                <div class="menu-card" onclick="showSection('overview')">
                    <div class="icon-badge pink">👛</div>
                    <div class="card-heading">Wallet Overview</div>
                </div>

                <div class="menu-card" onclick="showSection('savings')">
                    <div class="icon-badge mint"><i class="fa-solid fa-plus" style="color:#059669;"></i></div>
                    <div class="card-heading">Record Savings</div>
                </div>

                <div class="menu-card" onclick="showSection('withdrawal')">
                    <div class="icon-badge blue"><i class="fa-solid fa-cash-register" style="color:#2563eb;"></i></div>
                    <div class="card-heading">Process Withdraw</div>
                </div>

                <div class="menu-card" onclick="showSection('loans')">
                    <div class="icon-badge yellow">💳</div>
                    <div class="card-heading">Loans</div>
                </div>

                <div class="menu-card" onclick="showSection('tracker')">
                    <div class="icon-badge teal">📊</div>
                    <div class="card-heading">Daily</div>
                </div>

                <div class="menu-card" onclick="showSection('service-fees')">
                    <div class="icon-badge purple">🏢</div>
                    <div class="card-heading">Monthly</div>
                </div>

                <div class="menu-card" onclick="showSection('members')">
                    <div class="icon-badge mint">👥</div>
                    <div class="card-heading">Member</div>
                </div>

                <div class="menu-card" onclick="showSection('register')">
                    <div class="icon-badge blue">🆔</div>
                    <div class="card-heading">Register</div>
                </div>

                <div class="menu-card" onclick="showSection('manage-members')">
                    <div class="icon-badge pink">⚙️</div>
                    <div class="card-heading">Manage</div>
                </div>
            </div>

            <div class="grid-row-4-center">
                <div class="menu-card" onclick="showSection('maintenance')">
                    <div class="icon-badge yellow">🛠️</div>
                    <div class="card-heading">Maintenance</div>
                </div>

                <div class="menu-card" onclick="showSection('password')">
                    <div class="icon-badge purple">🔐</div>
                    <div class="card-heading">Password</div>
                </div>
            </div>
        </div>

        <!-- VIEW 1B: MEMBER PRIVATE PORTAL -->
        <div id="view-member-portal" class="view-section">
            <div style="background: #ffffff; border: 1.5px solid var(--border-light); border-radius: 20px; padding: 1.25rem; margin-bottom: 1rem;">
                <div style="font-size: 1.2rem; font-weight: 800; color: var(--text-dark);" id="mportal-name">Welcome Member</div>
                <div style="font-size: 0.85rem; color: var(--text-muted);" id="mportal-id">ID: SVR0000</div>

                <div class="overview-box" style="margin-top: 1rem; margin-bottom: 1rem;">
                    <div class="overview-row">
                        <span>Savings Balance:</span>
                        <span class="amount-saved" id="mportal-balance">₦0.00</span>
                    </div>
                    <div class="overview-row">
                        <span>Daily Target:</span>
                        <span id="mportal-target" style="font-weight: 800;">₦0.00</span>
                    </div>
                    <div class="overview-divider"></div>
                    <div class="overview-row">
                        <span>Active Loan:</span>
                        <span style="color: var(--primary-red); font-weight: 800;" id="mportal-loan">₦0.00</span>
                    </div>
                </div>

                <div class="modal-cycle-box" style="margin-bottom: 1rem;">
                    <div class="lbl">YOUR CYCLE STATUS:</div>
                    <div class="val" id="mportal-cycle">🔄 Cycle 1 (0 / 31 days)</div>
                </div>

                <div style="font-size: 0.95rem; font-weight: 800; margin-bottom: 8px;">My Recent Savings (Last 5)</div>
                <div class="table-responsive">
                    <table>
                        <thead>
                            <tr>
                                <th>DATE</th>
                                <th>AMOUNT</th>
                                <th>DAYS</th>
                            </tr>
                        </thead>
                        <tbody id="mportal-savings-table"></tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- VIEW 2: WALLET OVERVIEW -->
        <div id="view-overview" class="view-section">
            <div class="view-header-row">
                <div class="view-title-group">👛 Wallet Overview</div>
                <button class="btn-back" onclick="showSection('home')">← Back</button>
            </div>

            <div class="overview-box">
                <div class="overview-row">
                    <span>Total Money Saved:</span>
                    <span class="amount-saved" id="stat-total-saved">₦0.00</span>
                </div>
                <div class="overview-row">
                    <span>Total Service Fees Deducted:</span>
                    <span class="amount-fees" id="stat-service-fees">₦0.00</span>
                </div>
                <div class="overview-divider"></div>
                <div class="overview-row">
                    <span>Net Wallet Balance:</span>
                    <span class="amount-net" id="stat-net-balance">₦0.00</span>
                </div>
            </div>

            <div class="action-stack">
                <button class="btn-action-primary" onclick="showSection('withdrawal')">
                    <i class="fa-solid fa-cash-register"></i> Proceed to Withdrawal
                </button>
                <button class="btn-action-secondary" onclick="showSection('savings')">
                    <i class="fa-solid fa-plus"></i> Record Contribution
                </button>
            </div>
        </div>

        <!-- VIEW 3: MEMBERS DIRECTORY -->
        <div id="view-members" class="view-section">
            <div class="view-header-row">
                <div class="view-title-group">👥 Members Directory</div>
                <div style="display: flex; gap: 8px; align-items: center;">
                    <button class="btn-add-header" onclick="showSection('register')">
                        <i class="fa-solid fa-user-plus"></i> Add Member
                    </button>
                    <button class="btn-back" onclick="showSection('home')">← Back</button>
                </div>
            </div>

            <div class="filter-row">
                <input type="text" id="member-search-dir" placeholder="Search name or ID..." onkeyup="renderMembersDirectory()">
            </div>

            <div id="members-cards-container"></div>
        </div>

        <!-- VIEW 4: RECORD SAVINGS -->
        <div id="view-savings" class="view-section">
            <div class="view-header-row">
                <div class="view-title-group">➕ Record Savings</div>
                <button class="btn-back" onclick="showSection('home')">← Back</button>
            </div>
            <div class="card-form">
                <form id="form-add-savings" onsubmit="handleSavingsSubmit(event)">
                    <div class="form-group">
                        <label>Select Member</label>
                        <select class="form-control member-select" id="savings-member" required></select>
                    </div>
                    <div class="form-group">
                        <label>Contribution Amount (₦)</label>
                        <input type="number" step="0.01" class="form-control" id="savings-amount" placeholder="e.g. 5000" required>
                    </div>
                    <div class="form-group">
                        <label>Date</label>
                        <input type="date" class="form-control" id="savings-date" required>
                    </div>
                    <div class="form-group">
                        <label>Notes</label>
                        <input type="text" class="form-control" id="savings-notes" placeholder="Optional details">
                    </div>
                    <button type="submit" class="btn-submit">Record Contribution</button>
                </form>
            </div>
        </div>

        <!-- VIEW 5: PROCESS WITHDRAWAL -->
        <div id="view-withdrawal" class="view-section">
            <div class="view-header-row">
                <div class="view-title-group">🏧 Process Withdrawal</div>
                <button class="btn-back" onclick="showSection('home')">← Back</button>
            </div>
            <div class="card-form">
                <form id="form-withdrawal" onsubmit="handleWithdrawalSubmit(event)">
                    <div class="form-group">
                        <label>Select Member</label>
                        <select class="form-control member-select" id="withdrawal-member" required></select>
                    </div>
                    <div class="form-group">
                        <label>Withdrawal Amount (₦)</label>
                        <input type="number" step="0.01" class="form-control" id="withdrawal-amount" placeholder="e.g. 5000" required>
                    </div>
                    <div class="form-group">
                        <label>Withdrawal Type</label>
                        <select class="form-control" id="withdrawal-type">
                            <option value="instant">Instant Partial Payout</option>
                            <option value="reset">Full Cycle Reset Payout</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Date</label>
                        <input type="date" class="form-control" id="withdrawal-date" required>
                    </div>
                    <button type="submit" class="btn-submit" style="background:var(--primary-red);">Execute Withdrawal</button>
                </form>
            </div>
        </div>

        <!-- VIEW 6: LOANS LEDGER -->
        <div id="view-loans" class="view-section">
            <div class="view-header-row">
                <div class="view-title-group">💳 Loans Ledger</div>
                <button class="btn-back" onclick="showSection('home')">← Back</button>
            </div>

            <div class="table-responsive">
                <table>
                    <thead>
                        <tr>
                            <th>Member</th>
                            <th>Principal</th>
                            <th>Repayable</th>
                            <th>Paid</th>
                            <th>Balance</th>
                            <th>Status</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody id="loans-table-body"></tbody>
                </table>
            </div>
        </div>

        <!-- VIEW 7: DAILY TRACKER -->
        <div id="view-tracker" class="view-section">
            <div class="view-header-row">
                <div class="view-title-group">📊 Daily Tracker</div>
                <button class="btn-back" onclick="showSection('home')">← Back</button>
            </div>

            <div class="overview-box" style="margin-bottom: 1.25rem;">
                <div class="overview-row">
                    <span>Total System Inflows:</span>
                    <span class="amount-saved" id="tracker-summary-inflow">₦0.00</span>
                </div>
                <div class="overview-row">
                    <span>Total System Outflows:</span>
                    <span class="amount-fees" id="tracker-summary-outflow" style="color:var(--primary-red);">₦0.00</span>
                </div>
                <div class="overview-divider"></div>
                <div class="overview-row">
                    <span>Net Daily Cashflow:</span>
                    <span class="amount-net" id="tracker-summary-net">₦0.00</span>
                </div>
            </div>

            <div class="table-responsive">
                <table>
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Member</th>
                            <th>Inflow (₦)</th>
                            <th>Outflow (₦)</th>
                            <th>Notes</th>
                        </tr>
                    </thead>
                    <tbody id="tracker-table-body"></tbody>
                </table>
            </div>
        </div>

        <!-- VIEW 8: MONTHLY SERVICE FEES -->
        <div id="view-service-fees" class="view-section">
            <div class="view-header-row">
                <div class="view-title-group">🏢 Monthly Service Fees</div>
                <button class="btn-back" onclick="showSection('home')">← Back</button>
            </div>

            <div class="overview-box" style="margin-bottom: 1.25rem;">
                <div class="overview-row">
                    <span>Total Service Fees Income:</span>
                    <span class="amount-fees" id="fees-summary-total">₦0.00</span>
                </div>
            </div>

            <div class="table-responsive">
                <table>
                    <thead>
                        <tr>
                            <th>Member</th>
                            <th>Amount (₦)</th>
                            <th>Month</th>
                            <th>Date</th>
                            <th>Description</th>
                        </tr>
                    </thead>
                    <tbody id="fees-table-body"></tbody>
                </table>
            </div>
        </div>

        <!-- VIEW 9: REGISTER MEMBER -->
        <div id="view-register" class="view-section">
            <div class="view-header-row">
                <div class="view-title-group">🆔 Register Member</div>
                <button class="btn-back" onclick="showSection('home')">← Back</button>
            </div>
            <div class="card-form">
                <form id="form-register-member" onsubmit="handleMemberRegister(event)">
                    <div class="form-group">
                        <label>Full Name</label>
                        <input type="text" class="form-control" id="reg-fullname" placeholder="e.g. Sunday Adebayo" required>
                    </div>
                    <div class="form-group">
                        <label>Daily Target Amount (₦)</label>
                        <input type="number" step="0.01" class="form-control" id="reg-target" placeholder="e.g. 1000" required>
                    </div>
                    <button type="submit" class="btn-submit">Register Member</button>
                </form>
            </div>
        </div>

        <!-- VIEW 10: MANAGE MEMBERS -->
        <div id="view-manage-members" class="view-section">
            <div class="view-header-row">
                <div class="view-title-group">⚙️ Manage Members</div>
                <button class="btn-back" onclick="showSection('home')">← Back</button>
            </div>

            <div class="table-responsive">
                <table>
                    <thead>
                        <tr>
                            <th>Member ID</th>
                            <th>Full Name</th>
                            <th>Target</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="manage-members-table-body"></tbody>
                </table>
            </div>
        </div>

        <!-- VIEW 11: MAINTENANCE -->
        <div id="view-maintenance" class="view-section">
            <div class="view-header-row">
                <div class="view-title-group">🛠️ System Maintenance</div>
                <button class="btn-back" onclick="showSection('home')">← Back</button>
            </div>

            <div class="manage-subcard" style="margin-bottom: 1.25rem;">
                <div class="manage-subcard-title" style="color:var(--primary-green-dark);">
                    <i class="fa-solid fa-arrows-rotate"></i> 🔄 Rebuild Financial Sync
                </div>
                <p style="font-size:0.85rem; color:var(--text-muted); margin-bottom:1rem;">
                    Audits loan statuses and recalculates system vault balances.
                </p>
                <button class="btn-submit" onclick="resyncLedger()">
                    🔄 Execute Financial Sync
                </button>
            </div>

            <div class="manage-subcard" style="border-color:#fca5a5; background:#fff5f5;">
                <div class="manage-subcard-title" style="color:var(--primary-red);">
                    <i class="fa-solid fa-triangle-exclamation"></i> ⚠️ Reset All Financial Ledgers
                </div>
                <p style="font-size:0.85rem; color:var(--text-muted); margin-bottom:1rem;">
                    Clears ALL financial records. Members will remain preserved.
                </p>
                <button class="btn-submit" style="background:var(--primary-red);" onclick="triggerResetAllSystemLedgers()">
                    ⚠️ Reset All Ledgers
                </button>
            </div>
        </div>

        <!-- VIEW 12: PASSWORD -->
        <div id="view-password" class="view-section">
            <div class="view-header-row">
                <div class="view-title-group">🔐 Update Password</div>
                <button class="btn-back" onclick="showSection('home')">← Back</button>
            </div>
            <div class="card-form">
                <form id="form-password" onsubmit="handlePasswordUpdate(event)">
                    <div class="form-group">
                        <label>Current Password</label>
                        <input type="password" class="form-control" id="pass-old" required>
                    </div>
                    <div class="form-group">
                        <label>New Password</label>
                        <input type="password" class="form-control" id="pass-new" required>
                    </div>
                    <button type="submit" class="btn-submit">Update Admin Password</button>
                </form>
            </div>
        </div>

    </div>

    <!-- MEMBER PROFILE MODAL -->
    <div class="modal-overlay" id="member-profile-modal">
        <div class="modal-card">
            <div class="modal-header">
                <div class="modal-title" id="modal-member-name-title">Member Details</div>
                <button class="modal-close" onclick="closeMemberModal()">×</button>
            </div>

            <div class="modal-nav-tabs">
                <div class="modal-tab active" onclick="switchModalTab('overview')">Overview</div>
                <div class="modal-tab" onclick="switchModalTab('save')">➕ Save</div>
                <div class="modal-tab" onclick="switchModalTab('withdraw')">抓 Withdraw</div>
                <div class="modal-tab" onclick="switchModalTab('loans')">💳 Issue Loan</div>
                <div class="modal-tab" onclick="switchModalTab('manage')">⚙️ Edit / Credentials</div>
            </div>

            <div id="modal-panel-overview" class="modal-tab-panel active">
                <div class="modal-details-list">
                    <div class="modal-detail-item">
                        <span style="color:var(--text-muted);">Daily Target:</span>
                        <span id="modal-target">₦0.00</span>
                    </div>
                    <div class="modal-detail-item">
                        <span style="color:var(--text-muted);">Savings Balance:</span>
                        <span style="color:var(--primary-green-dark); font-weight:800;" id="modal-balance">₦0.00</span>
                    </div>
                    <div class="modal-detail-item">
                        <span style="color:var(--text-muted);">Active Loan:</span>
                        <span style="color:var(--primary-red); font-weight:800;" id="modal-loan">₦0.00</span>
                    </div>
                </div>

                <div class="modal-cycle-box">
                    <div class="lbl">CYCLE STATUS:</div>
                    <div class="val" id="modal-cycle-val">🔄 Cycle 1 (0 / 31 days)</div>
                </div>

                <div style="font-size: 0.95rem; font-weight: 800; margin-bottom: 8px;">Recent Contributions (Last 5)</div>
                <div class="table-responsive">
                    <table>
                        <thead>
                            <tr>
                                <th>DATE</th>
                                <th>GROSS</th>
                                <th>DAYS</th>
                                <th>ACTION</th>
                            </tr>
                        </thead>
                        <tbody id="modal-recent-savings-body"></tbody>
                    </table>
                </div>
            </div>

            <div id="modal-panel-save" class="modal-tab-panel">
                <form onsubmit="handleModalSave(event)">
                    <div class="form-group">
                        <label>Contribution Amount (₦)</label>
                        <input type="number" step="0.01" class="form-control" id="modal-save-amount" placeholder="e.g. 5000" required>
                    </div>
                    <div class="form-group">
                        <label>Date</label>
                        <input type="date" class="form-control" id="modal-save-date" required>
                    </div>
                    <button type="submit" class="btn-submit">Record Contribution</button>
                </form>
            </div>

            <div id="modal-panel-withdraw" class="modal-tab-panel">
                <form onsubmit="handleModalWithdraw(event)">
                    <div class="form-group">
                        <label>Amount (₦)</label>
                        <input type="number" step="0.01" class="form-control" id="modal-withdraw-amount" placeholder="e.g. 2000" required>
                    </div>
                    <div class="form-group">
                        <label>Type</label>
                        <select class="form-control" id="modal-withdraw-type">
                            <option value="instant">Instant Partial Payout</option>
                            <option value="reset">Full Cycle Reset Payout</option>
                        </select>
                    </div>
                    <button type="submit" class="btn-submit" style="background:var(--primary-red);">Process Payout</button>
                </form>
            </div>

            <div id="modal-panel-loans" class="modal-tab-panel">
                <form onsubmit="handleModalLoan(event)">
                    <div class="form-group">
                        <label>Loan Amount (₦)</label>
                        <input type="number" step="0.01" class="form-control" id="modal-loan-amount" placeholder="e.g. 10000" required>
                    </div>
                    <button type="submit" class="btn-submit">Issue Loan (0% Interest)</button>
                </form>
            </div>

            <div id="modal-panel-manage" class="modal-tab-panel">
                <div class="manage-subcard">
                    <div class="manage-subcard-title" style="color:var(--primary-green-dark);">
                        <i class="fa-solid fa-pen-to-square"></i> ✏️ Edit Profile & Login Credentials
                    </div>
                    <form onsubmit="handleModalUpdateMember(event)">
                        <div class="form-group">
                            <label>Full Name</label>
                            <input type="text" class="form-control" id="modal-edit-fullname" required>
                        </div>
                        <div class="form-group">
                            <label>Daily Target Amount (₦)</label>
                            <input type="number" step="0.01" class="form-control" id="modal-edit-target" required>
                        </div>
                        <div class="form-group">
                            <label>Member Username</label>
                            <input type="text" class="form-control" id="modal-edit-username" placeholder="e.g. sunday123">
                        </div>
                        <div class="form-group">
                            <label>New Password (Leave blank to keep unchanged)</label>
                            <input type="password" class="form-control" id="modal-edit-password" placeholder="Enter new password">
                        </div>
                        <button type="submit" class="btn-submit">Save Changes & Credentials</button>
                    </form>
                </div>

                <!-- RESET MEMBER FINANCIAL DATA SUBCARD -->
                <div class="manage-subcard" style="border-color:#fde68a; background:#fffbeb;">
                    <div class="manage-subcard-title" style="color:var(--amber-fee);">
                        <i class="fa-solid fa-rotate-left"></i> 🧹 Reset Member Financial Data
                    </div>
                    <p style="font-size:0.8rem; color:var(--text-muted); margin-bottom:0.75rem;">
                        Clears all savings, withdrawals, loans, and fee logs for this member. Resets cycle back to Cycle 1 (0 days). Member profile and login credentials are preserved.
                    </p>
                    <button class="btn-submit" style="background:var(--amber-fee);" onclick="triggerResetMemberLedger()">
                        Reset Member Financial Data
                    </button>
                </div>

                <div class="manage-subcard" style="border-color:#fca5a5; background:#fff5f5;">
                    <div class="manage-subcard-title" style="color:var(--primary-red);">
                        <i class="fa-solid fa-trash"></i> 🗑️ Delete Member
                    </div>
                    <p style="font-size:0.8rem; color:var(--text-muted); margin-bottom:0.75rem;">
                        Permanently deletes member profile and all recorded transactions.
                    </p>
                    <button class="btn-submit" style="background:var(--primary-red);" onclick="triggerDeleteMemberCurrent()">
                        Delete Member Account
                    </button>
                </div>
            </div>

        </div>
    </div>

    <div class="modal-overlay" id="custom-confirm-modal">
        <div class="modal-card" style="max-width:400px; text-align:center;">
            <div style="font-size:2.5rem; color:var(--amber-fee); margin-bottom:10px;"><i class="fa-solid fa-triangle-exclamation"></i></div>
            <div class="modal-title" id="confirm-modal-title" style="margin-bottom:8px;">Are you sure?</div>
            <p id="confirm-modal-msg" style="font-size:0.9rem; color:var(--text-muted); margin-bottom:1.25rem;"></p>
            <div style="display:flex; gap:10px;">
                <button class="btn-back" style="flex:1; padding:12px;" onclick="resolveConfirmModal(false)">Cancel</button>
                <button class="btn-submit" id="confirm-modal-btn" style="flex:1; background:var(--primary-red);" onclick="resolveConfirmModal(true)">Confirm</button>
            </div>
        </div>
    </div>

    <div class="modal-overlay" id="custom-prompt-modal">
        <div class="modal-card" style="max-width:400px;">
            <div class="modal-title" id="prompt-modal-title" style="margin-bottom:10px;">Repay Loan</div>
            <div class="form-group">
                <label id="prompt-modal-label">Enter Repayment Amount (₦)</label>
                <input type="number" step="0.01" class="form-control" id="prompt-modal-input" placeholder="e.g. 2000">
            </div>
            <div style="display:flex; gap:10px; margin-top:1rem;">
                <button class="btn-back" style="flex:1; padding:12px;" onclick="resolvePromptModal(null)">Cancel</button>
                <button class="btn-submit" style="flex:1;" onclick="submitPromptModal()">Submit</button>
            </div>
        </div>
    </div>

    <footer>
        Savers Growth System ©2026<br>
        Designed by Willys Media World - 09018363715
    </footer>

    <script>
        const todayStr = new Date().toISOString().split('T')[0];
        document.getElementById('savings-date').value = todayStr;
        document.getElementById('withdrawal-date').value = todayStr;
        document.getElementById('modal-save-date').value = todayStr;

        let globalMembers = [];
        let currentModalMember = null;
        let currentUser = null;
        let confirmResolver = null;
        let promptResolver = null;

        function showCustomConfirm(title, message, btnText = "Confirm") {
            return new Promise((resolve) => {
                document.getElementById('confirm-modal-title').innerText = title;
                document.getElementById('confirm-modal-msg').innerText = message;
                document.getElementById('confirm-modal-btn').innerText = btnText;
                document.getElementById('custom-confirm-modal').classList.add('active');
                confirmResolver = resolve;
            });
        }

        function resolveConfirmModal(val) {
            document.getElementById('custom-confirm-modal').classList.remove('active');
            if (confirmResolver) confirmResolver(val);
        }

        function showCustomPrompt(title, labelText) {
            return new Promise((resolve) => {
                document.getElementById('prompt-modal-title').innerText = title;
                document.getElementById('prompt-modal-label').innerText = labelText;
                document.getElementById('prompt-modal-input').value = '';
                document.getElementById('custom-prompt-modal').classList.add('active');
                promptResolver = resolve;
            });
        }

        function submitPromptModal() {
            const val = document.getElementById('prompt-modal-input').value;
            document.getElementById('custom-prompt-modal').classList.remove('active');
            if (promptResolver) promptResolver(val);
        }

        function resolvePromptModal(val) {
            document.getElementById('custom-prompt-modal').classList.remove('active');
            if (promptResolver) promptResolver(val);
        }

        function showToast(message, type = 'success') {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            toast.innerHTML = `<i class="fa-solid fa-${type === 'success' ? 'circle-check' : 'circle-exclamation'}"></i> ${message}`;
            container.appendChild(toast);
            setTimeout(() => toast.remove(), 4000);
        }

        function formatNaira(val) {
            return '₦' + parseFloat(val || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }

        async function checkAuthSession() {
            try {
                const res = await fetch('/api/auth/me');
                const data = await res.json();

                if (data.logged_in) {
                    currentUser = data;
                    document.getElementById('header-auth-btn').innerText = 'Logout';
                    
                    if (data.role === 'admin') {
                        document.getElementById('admin-search-container').style.display = 'block';
                        fetchAndRenderMembers();
                        showSection('home');
                    } else {
                        document.getElementById('admin-search-container').style.display = 'none';
                        loadMemberPrivatePortal(data.member_id);
                    }
                } else {
                    currentUser = null;
                    document.getElementById('header-auth-btn').innerText = 'Login';
                    document.getElementById('admin-search-container').style.display = 'none';
                    showSection('login');
                }
            } catch (err) {
                showSection('login');
            }
        }

        async function handleLoginSubmit(e) {
            e.preventDefault();
            const username = document.getElementById('login-username').value.trim();
            const password = document.getElementById('login-password').value.trim();

            const res = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            const result = await res.json();

            if (result.success) {
                showToast(`Welcome back, ${result.name}!`);
                document.getElementById('login-username').value = '';
                document.getElementById('login-password').value = '';
                checkAuthSession();
            } else {
                showToast(result.message, 'error');
            }
        }

        async function handleAuthAction() {
            if (currentUser) {
                await fetch('/api/auth/logout', { method: 'POST' });
                currentUser = null;
                showToast('Logged out');
                checkAuthSession();
            } else {
                showSection('login');
            }
        }

        function handleHeaderClick() {
            if (currentUser) {
                if (currentUser.role === 'admin') showSection('home');
                else loadMemberPrivatePortal(currentUser.member_id);
            } else {
                showSection('login');
            }
        }

        async function loadMemberPrivatePortal(memberId) {
            const res = await fetch(`/api/member/${memberId}`);
            const data = await res.json();

            if (data.success) {
                const m = data.member;
                document.getElementById('mportal-name').innerText = m.full_name;
                document.getElementById('mportal-id').innerText = `ID: ${m.member_id}`;
                document.getElementById('mportal-balance').innerText = formatNaira(m.net_balance);
                document.getElementById('mportal-target').innerText = formatNaira(m.daily_target);
                document.getElementById('mportal-loan').innerText = formatNaira(m.active_loan);
                document.getElementById('mportal-cycle').innerText = `🔄 Cycle ${m.current_cycle} (${m.cycle_days} / 31 days)`;

                const tbody = document.getElementById('mportal-savings-table');
                tbody.innerHTML = '';

                if (data.recent_savings.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="3" style="text-align:center; color:var(--text-muted);">No savings recorded yet.</td></tr>';
                } else {
                    data.recent_savings.forEach(s => {
                        tbody.innerHTML += `
                            <tr>
                                <td>${s.date}</td>
                                <td style="color:var(--primary-green-dark); font-weight:800;">${formatNaira(s.amount)}</td>
                                <td>${s.days_credited}</td>
                            </tr>
                        `;
                    });
                }

                showSection('member-portal');
            }
        }

        function showSection(sectionId) {
            document.querySelectorAll('.view-section').forEach(sec => sec.classList.remove('active'));
            const target = document.getElementById(`view-${sectionId}`);
            if (target) {
                target.classList.add('active');
                window.scrollTo({ top: 0, behavior: 'smooth' });
            }

            if (sectionId === 'overview') loadOverview();
            if (sectionId === 'members') fetchAndRenderMembers();
            if (sectionId === 'manage-members') renderManageMembersTable();
            if (sectionId === 'loans') loadLoans();
            if (sectionId === 'tracker') loadTracker();
            if (sectionId === 'service-fees') loadServiceFees();
        }

        async function fetchAndRenderMembers() {
            try {
                const res = await fetch('/api/members');
                globalMembers = await res.json();

                const selects = document.querySelectorAll('.member-select');
                selects.forEach(select => {
                    select.innerHTML = '<option value="">-- Select Member --</option>';
                    globalMembers.forEach(m => {
                        select.innerHTML += `<option value="${m.member_id}">${m.full_name} (${m.member_id}) - Bal: ${formatNaira(m.net_balance)}</option>`;
                    });
                });

                renderMembersDirectory();
            } catch (err) {
                console.error("Failed loading members:", err);
            }
        }

        function renderMembersDirectory() {
            const container = document.getElementById('members-cards-container');
            const searchVal = document.getElementById('member-search-dir').value.toLowerCase();
            container.innerHTML = '';

            const filtered = globalMembers.filter(m => 
                m.full_name.toLowerCase().includes(searchVal) || 
                m.member_id.toLowerCase().includes(searchVal)
            );

            if (filtered.length === 0) {
                container.innerHTML = '<div style="text-align:center; padding:2rem; color:var(--text-muted);">No members found. Add your first member!</div>';
                return;
            }

            filtered.forEach(m => {
                const initial = m.full_name.charAt(0).toUpperCase();
                container.innerHTML += `
                    <div class="member-card-item" onclick="openMemberModal('${m.member_id}')">
                        <div class="member-card-header">
                            <div class="member-avatar-group">
                                <div class="member-avatar">${initial}</div>
                                <div class="member-info">
                                    <div class="name">${m.full_name}</div>
                                    <div class="code">${m.member_id}</div>
                                </div>
                            </div>
                        </div>
                        <div class="member-stats-box">
                            <div class="stat-line">Bal: <span class="val-green">${formatNaira(m.net_balance)}</span></div>
                            <div class="stat-line">Target: <span>${formatNaira(m.daily_target)}</span></div>
                            <div class="stat-line">Days: <span>${m.cycle_days}</span></div>
                            <div class="stat-line">Loan: <span class="val-red">${formatNaira(m.active_loan)}</span></div>
                        </div>
                        <div class="cycle-status-btn">
                            🔄 Cycle ${m.current_cycle} (${m.cycle_days} / 31 days)
                        </div>
                    </div>
                `;
            });
        }

        function renderManageMembersTable() {
            const tbody = document.getElementById('manage-members-table-body');
            tbody.innerHTML = '';

            if (globalMembers.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; padding:1.5rem; color:var(--text-muted);">No registered members.</td></tr>';
                return;
            }

            globalMembers.forEach(m => {
                tbody.innerHTML += `
                    <tr>
                        <td><strong>${m.member_id}</strong></td>
                        <td>${m.full_name}</td>
                        <td>${formatNaira(m.daily_target)}</td>
                        <td>
                            <button class="btn-edit-sm" onclick="openMemberModal('${m.member_id}')">✏️ Edit</button>
                            <button class="btn-delete-sm" onclick="deleteMemberDirect('${m.member_id}')">🗑️ Delete</button>
                        </td>
                    </tr>
                `;
            });
        }

        async function openMemberModal(memberId) {
            const res = await fetch(`/api/member/${memberId}`);
            const data = await res.json();

            if (!data.success) {
                showToast("Member details not found.", "error");
                return;
            }

            const m = data.member;
            currentModalMember = m;

            document.getElementById('modal-member-name-title').innerText = `${m.full_name} (${m.member_id})`;
            document.getElementById('modal-target').innerText = formatNaira(m.daily_target);
            document.getElementById('modal-balance').innerText = formatNaira(m.net_balance);
            document.getElementById('modal-loan').innerText = formatNaira(m.active_loan);
            document.getElementById('modal-cycle-val').innerText = `🔄 Cycle ${m.current_cycle} (${m.cycle_days} / 31 days)`;

            document.getElementById('modal-edit-fullname').value = m.full_name;
            document.getElementById('modal-edit-target').value = m.daily_target;
            document.getElementById('modal-edit-username').value = m.username || '';
            document.getElementById('modal-edit-password').value = '';

            const tbody = document.getElementById('modal-recent-savings-body');
            tbody.innerHTML = '';

            if (data.recent_savings.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--text-muted);">No contribution history.</td></tr>';
            } else {
                data.recent_savings.forEach(s => {
                    tbody.innerHTML += `
                        <tr>
                            <td>${s.date}</td>
                            <td style="color:var(--primary-green-dark); font-weight:800;">${formatNaira(s.amount)}</td>
                            <td>${s.days_credited}</td>
                            <td>
                                <button class="btn-delete-sm" onclick="deleteContribution(${s.id})">
                                    🗑️ Delete
                                </button>
                            </td>
                        </tr>
                    `;
                });
            }

            switchModalTab('overview');
            document.getElementById('member-profile-modal').classList.add('active');
        }

        function closeMemberModal() {
            document.getElementById('member-profile-modal').classList.remove('active');
        }

        function switchModalTab(tabName) {
            document.querySelectorAll('.modal-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.modal-tab-panel').forEach(p => p.classList.remove('active'));

            const targetTab = Array.from(document.querySelectorAll('.modal-tab')).find(el => el.innerText.toLowerCase().includes(tabName));
            if (targetTab) targetTab.classList.add('active');

            const panel = document.getElementById(`modal-panel-${tabName}`);
            if (panel) panel.classList.add('active');
        }

        function handleGlobalSearchInput(e) {
            const query = e.target.value.trim().toLowerCase();
            const dropdown = document.getElementById('search-results-dropdown');
            dropdown.innerHTML = '';

            const digitsOnly = query.replace(/\D/g, '');

            if (digitsOnly.length >= 2 || query.length >= 2) {
                const matches = globalMembers.filter(m => 
                    m.member_id.toLowerCase().includes(query) ||
                    m.full_name.toLowerCase().includes(query) ||
                    m.member_id.replace(/\D/g, '').includes(digitsOnly)
                );

                if (matches.length > 0) {
                    dropdown.style.display = 'block';
                    matches.forEach(m => {
                        dropdown.innerHTML += `
                            <div class="search-result-item" onclick="selectSearchMember('${m.member_id}')">
                                <div>
                                    <strong>${m.full_name}</strong> (${m.member_id})
                                </div>
                                <span style="color:var(--primary-green-dark);">${formatNaira(m.net_balance)}</span>
                            </div>
                        `;
                    });
                } else {
                    dropdown.style.display = 'block';
                    dropdown.innerHTML = '<div class="search-result-item" style="color:var(--text-muted);">No matching member found</div>';
                }
            } else {
                dropdown.style.display = 'none';
            }
        }

        function selectSearchMember(memberId) {
            document.getElementById('search-results-dropdown').style.display = 'none';
            document.getElementById('global-search-input').value = '';
            openMemberModal(memberId);
        }

        async function deleteMemberDirect(memberId) {
            const confirmed = await showCustomConfirm("Delete Member", `Are you sure you want to permanently delete member ${memberId}?`);
            if (confirmed) {
                const res = await fetch(`/api/member/${memberId}`, { method: 'DELETE' });
                const result = await res.json();
                if (result.success) {
                    showToast(result.message);
                    await fetchAndRenderMembers();
                    renderManageMembersTable();
                } else {
                    showToast(result.message, 'error');
                }
            }
        }

        async function triggerResetMemberLedger() {
            if (!currentModalMember) return;
            const confirmed = await showCustomConfirm(
                "Reset Member Financial Data", 
                `Are you sure you want to clear all savings, withdrawals, loans, and fee logs for ${currentModalMember.full_name} (${currentModalMember.member_id})? Profile and login credentials will remain intact.`
            );
            if (confirmed) {
                const res = await fetch(`/api/member/${currentModalMember.member_id}/reset-ledger`, { method: 'POST' });
                const result = await res.json();
                if (result.success) {
                    showToast(result.message);
                    await fetchAndRenderMembers();
                    openMemberModal(currentModalMember.member_id);
                } else {
                    showToast(result.message, 'error');
                }
            }
        }

        async function triggerDeleteMemberCurrent() {
            if (!currentModalMember) return;
            const confirmed = await showCustomConfirm("Delete Member Account", `Permanently delete ${currentModalMember.full_name} (${currentModalMember.member_id})?`);
            if (confirmed) {
                const res = await fetch(`/api/member/${currentModalMember.member_id}`, { method: 'DELETE' });
                const result = await res.json();
                if (result.success) {
                    showToast(result.message);
                    closeMemberModal();
                    await fetchAndRenderMembers();
                    renderManageMembersTable();
                } else {
                    showToast(result.message, 'error');
                }
            }
        }

        async function handleModalSave(e) {
            e.preventDefault();
            const payload = {
                member_id: currentModalMember.member_id,
                amount: document.getElementById('modal-save-amount').value,
                date: document.getElementById('modal-save-date').value
            };

            const res = await fetch('/api/savings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await res.json();

            if (result.success) {
                showToast(result.message);
                document.getElementById('modal-save-amount').value = '';
                openMemberModal(currentModalMember.member_id);
                fetchAndRenderMembers();
            } else {
                showToast(result.message, 'error');
            }
        }

        async function handleModalWithdraw(e) {
            e.preventDefault();
            const payload = {
                member_id: currentModalMember.member_id,
                amount: document.getElementById('modal-withdraw-amount').value,
                withdrawal_type: document.getElementById('modal-withdraw-type').value,
                date: todayStr
            };

            const res = await fetch('/api/withdrawals', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await res.json();

            if (result.success) {
                showToast(result.message);
                document.getElementById('modal-withdraw-amount').value = '';
                openMemberModal(currentModalMember.member_id);
                fetchAndRenderMembers();
            } else {
                showToast(result.message, 'error');
            }
        }

        async function handleModalLoan(e) {
            e.preventDefault();
            const payload = {
                member_id: currentModalMember.member_id,
                amount: document.getElementById('modal-loan-amount').value,
                issue_date: todayStr
            };

            const res = await fetch('/api/loans', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await res.json();

            if (result.success) {
                showToast(result.message);
                document.getElementById('modal-loan-amount').value = '';
                openMemberModal(currentModalMember.member_id);
                fetchAndRenderMembers();
            } else {
                showToast(result.message, 'error');
            }
        }

        async function handleModalUpdateMember(e) {
            e.preventDefault();
            const payload = {
                full_name: document.getElementById('modal-edit-fullname').value,
                daily_target: document.getElementById('modal-edit-target').value,
                username: document.getElementById('modal-edit-username').value.trim(),
                password: document.getElementById('modal-edit-password').value.trim()
            };

            const res = await fetch(`/api/member/${currentModalMember.member_id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await res.json();

            if (result.success) {
                showToast(result.message);
                openMemberModal(currentModalMember.member_id);
                fetchAndRenderMembers();
            } else {
                showToast(result.message, 'error');
            }
        }

        async function deleteContribution(savingsId) {
            const confirmed = await showCustomConfirm("Delete Contribution", "Are you sure you want to delete this deposit entry?");
            if (confirmed) {
                const res = await fetch(`/api/savings/${savingsId}`, { method: 'DELETE' });
                const result = await res.json();
                if (result.success) {
                    showToast(result.message);
                    openMemberModal(currentModalMember.member_id);
                    fetchAndRenderMembers();
                }
            }
        }

        async function loadOverview() {
            const res = await fetch('/api/stats/overview');
            const data = await res.json();

            document.getElementById('stat-total-saved').innerText = formatNaira(data.total_savings);
            document.getElementById('stat-service-fees').innerText = formatNaira(data.total_fees);
            document.getElementById('stat-net-balance').innerText = formatNaira(data.net_balance);
        }

        async function handleSavingsSubmit(e) {
            e.preventDefault();
            const payload = {
                member_id: document.getElementById('savings-member').value,
                amount: document.getElementById('savings-amount').value,
                date: document.getElementById('savings-date').value,
                notes: document.getElementById('savings-notes').value
            };

            const res = await fetch('/api/savings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await res.json();

            if (result.success) {
                showToast(result.message);
                document.getElementById('form-add-savings').reset();
                document.getElementById('savings-date').value = todayStr;
                await fetchAndRenderMembers();
                showSection('overview');
            } else {
                showToast(result.message, 'error');
            }
        }

        async function handleWithdrawalSubmit(e) {
            e.preventDefault();
            const payload = {
                member_id: document.getElementById('withdrawal-member').value,
                amount: document.getElementById('withdrawal-amount').value,
                withdrawal_type: document.getElementById('withdrawal-type').value,
                date: document.getElementById('withdrawal-date').value
            };

            const res = await fetch('/api/withdrawals', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await res.json();

            if (result.success) {
                showToast(result.message);
                document.getElementById('form-withdrawal').reset();
                await fetchAndRenderMembers();
                showSection('overview');
            } else {
                showToast(result.message, 'error');
            }
        }

        async function handleMemberRegister(e) {
            e.preventDefault();
            const payload = {
                full_name: document.getElementById('reg-fullname').value.trim(),
                daily_target: document.getElementById('reg-target').value
            };

            try {
                const res = await fetch('/api/members', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const result = await res.json();

                if (result.success) {
                    showToast(result.message);
                    document.getElementById('form-register-member').reset();
                    await fetchAndRenderMembers();
                    showSection('members');
                } else {
                    showToast(result.message, 'error');
                }
            } catch (err) {
                showToast("Connection error while registering member.", "error");
            }
        }

        async function loadLoans() {
            const res = await fetch('/api/loans');
            const loans = await res.json();
            const tbody = document.getElementById('loans-table-body');
            tbody.innerHTML = '';

            if (loans.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:var(--text-muted); padding:1.5rem;">No member loans found.</td></tr>';
                return;
            }

            loans.forEach(l => {
                const balance = l.repayment_amount - l.amount_paid;
                const isCleared = l.status === 'cleared';
                tbody.innerHTML += `
                    <tr>
                        <td>
                            <strong>${l.full_name}</strong><br>
                            <span style="font-size:0.75rem; color:var(--text-muted);">${l.member_id}</span>
                        </td>
                        <td>${formatNaira(l.amount)}</td>
                        <td>${formatNaira(l.repayment_amount)} (0%)</td>
                        <td style="color:var(--primary-green-dark); font-weight:700;">${formatNaira(l.amount_paid)}</td>
                        <td style="color:var(--primary-red); font-weight:800;">${formatNaira(balance)}</td>
                        <td>
                            <span class="badge ${isCleared ? 'badge-success' : 'badge-warning'}">
                                ${l.status.toUpperCase()}
                            </span>
                        </td>
                        <td>
                            ${!isCleared ? `<button class="btn-repay-sm" onclick="promptLoanRepay(${l.id})">Repay</button>` : '-'}
                        </td>
                    </tr>
                `;
            });
        }

        async function promptLoanRepay(loanId) {
            const amount = await showCustomPrompt("Loan Repayment", "Enter Repayment Amount (₦):");
            if (amount && parseFloat(amount) > 0) {
                const res = await fetch('/api/loans/repay', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ loan_id: loanId, amount: amount, date: todayStr })
                });
                const result = await res.json();
                if (result.success) {
                    showToast(result.message);
                    loadLoans();
                    fetchAndRenderMembers();
                } else {
                    showToast(result.message, 'error');
                }
            }
        }

        async function loadTracker() {
            const res = await fetch('/api/tracker/daily');
            const data = await res.json();

            document.getElementById('tracker-summary-inflow').innerText = formatNaira(data.total_inflow);
            document.getElementById('tracker-summary-outflow').innerText = formatNaira(data.total_outflow);
            document.getElementById('tracker-summary-net').innerText = formatNaira(data.net_cashflow);

            const tbody = document.getElementById('tracker-table-body');
            tbody.innerHTML = '';

            if (data.logs.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding:1.5rem;">No daily activity recorded.</td></tr>';
                return;
            }

            data.logs.forEach(r => {
                const isInflow = r.inflow > 0;
                tbody.innerHTML += `
                    <tr>
                        <td><strong>${r.date}</strong></td>
                        <td>${r.full_name} <br><span style="font-size:0.75rem; color:var(--text-muted);">${r.member_id}</span></td>
                        <td style="color:var(--primary-green-dark); font-weight:700;">${r.inflow > 0 ? '+ ' + formatNaira(r.inflow) : '-'}</td>
                        <td style="color:var(--primary-red); font-weight:700;">${r.outflow > 0 ? '- ' + formatNaira(r.outflow) : '-'}</td>
                        <td>
                            <span class="badge ${isInflow ? 'badge-savings' : 'badge-payout'}">${r.tx_type}</span>
                            <div style="font-size:0.75rem; color:var(--text-muted); margin-top:2px;">${r.notes || ''}</div>
                        </td>
                    </tr>
                `;
            });
        }

        async function loadServiceFees() {
            const res = await fetch('/api/service-fees');
            const data = await res.json();

            document.getElementById('fees-summary-total').innerText = formatNaira(data.total_fees);

            const tbody = document.getElementById('fees-table-body');
            tbody.innerHTML = '';

            if (data.fees.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding:1.5rem;">No service fees collected yet.</td></tr>';
                return;
            }

            data.fees.forEach(f => {
                tbody.innerHTML += `
                    <tr>
                        <td>${f.full_name} <br><span style="font-size:0.75rem; color:var(--text-muted);">${f.member_id}</span></td>
                        <td style="color:var(--amber-fee); font-weight:800;">${formatNaira(f.amount)}</td>
                        <td>${f.month_year}</td>
                        <td>${f.date}</td>
                        <td><span class="badge badge-fee">${f.description || 'Service Fee'}</span></td>
                    </tr>
                `;
            });
        }

        async function resyncLedger() {
            const res = await fetch('/api/maintenance/resync', { method: 'POST' });
            const result = await res.json();
            showToast(result.message);
        }

        async function triggerResetAllSystemLedgers() {
            const confirmed = await showCustomConfirm("Reset All System Ledgers", "Clear ALL financial transactions across the system? Profiles will remain preserved.");
            if (confirmed) {
                const res = await fetch('/api/maintenance/reset-all-ledgers', { method: 'POST' });
                const result = await res.json();
                if (result.success) {
                    showToast(result.message);
                    fetchAndRenderMembers();
                    showSection('home');
                } else {
                    showToast(result.message, 'error');
                }
            }
        }

        async function handlePasswordUpdate(e) {
            e.preventDefault();
            const payload = {
                old_password: document.getElementById('pass-old').value,
                new_password: document.getElementById('pass-new').value
            };

            const res = await fetch('/api/admin/password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await res.json();

            if (result.success) {
                showToast(result.message);
                document.getElementById('form-password').reset();
            } else {
                showToast(result.message, 'error');
            }
        }

        window.onload = () => {
            checkAuthSession();
        };
    </script>
</body>
</html>
"""

@app.route('/')
def homepage():
    return render_template_string(INDEX_TEMPLATE)

# -----------------------------------------------------------------------------
# RUN APPLICATION
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
    