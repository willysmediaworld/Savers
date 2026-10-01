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
# HELPER: ACCURATE MONTH-ADDITION FOR BULK SERVICE FEE SPREADING (ANCHORED TO 1st OF MONTH)
# -----------------------------------------------------------------------------
def add_months(sourcedate, months):
    """
    Calculates consecutive month offsets, strictly anchoring the resulting date
    to the 1st of that month (YYYY-MM-01).
    """
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    return date(year, month, 1)

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

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS transaction_archives (
                id {pk_type},
                member_id TEXT NOT NULL,
                full_name TEXT NOT NULL,
                tx_type TEXT NOT NULL,
                amount REAL NOT NULL,
                cycle_no INTEGER DEFAULT 1,
                date TEXT NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # SPEED OPTIMIZATION: Database Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_members_mid ON members(member_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_members_uname ON members(username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_savings_mid ON savings(member_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_loans_mid ON loans(member_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_archives_mid ON transaction_archives(member_id)")

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

def archive_transaction(member_id, full_name, tx_type, amount, cycle_no, date_str, notes):
    try:
        db = get_db()
        cursor = db.cursor()
        p = query_param()
        cursor.execute(f'''
            INSERT INTO transaction_archives (member_id, full_name, tx_type, amount, cycle_no, date, notes)
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p})
        ''', (member_id, full_name, tx_type, amount, cycle_no, date_str, notes))
        db.commit()
    except Exception as e:
        print("Archive error:", e)

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

    cursor.execute(f"SELECT * FROM admin_users WHERE username = {p}", (username,))
    admin = cursor.fetchone()
    if admin and check_password_hash(admin['password_hash'], password):
        session['user_id'] = admin['username']
        session['role'] = 'admin'
        session['member_id'] = 'SVR0001'
        session['full_name'] = 'Oladele Rotimi Williams'
        return jsonify({'success': True, 'role': 'admin', 'name': 'Oladele Rotimi Williams', 'member_id': 'SVR0001'})

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
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT COUNT(*) FROM members')
        total_members = cursor.fetchone()[0]

        return jsonify({
            'logged_in': True,
            'role': session.get('role'),
            'member_id': session.get('member_id'),
            'full_name': session.get('full_name'),
            'total_members': total_members
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

    cursor.execute('SELECT COUNT(*) FROM members')
    total_members = cursor.fetchone()[0]

    net_balance = total_savings - total_withdrawals

    return jsonify({
        'total_savings': total_savings,
        'total_fees': total_fees,
        'net_balance': net_balance,
        'total_withdrawals': total_withdrawals,
        'total_members': total_members
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
            daily_target = float(raw_target) if raw_target not in (None, '', '0') else 500.0
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
                   COALESCE((SELECT SUM(repayment_amount - amount_paid) FROM loans WHERE member_id = m.member_id AND status = 'active'), 0) as active_loan,
                   COALESCE((SELECT SUM(amount) FROM service_fees WHERE member_id = m.member_id), 0) as total_service_fees
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
                'total_service_fees': r['total_service_fees'],
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
                   COALESCE((SELECT SUM(repayment_amount - amount_paid) FROM loans WHERE member_id = m.member_id AND status = 'active'), 0) as active_loan,
                   COALESCE((SELECT SUM(amount) FROM service_fees WHERE member_id = m.member_id), 0) as total_service_fees
            FROM members m WHERE m.member_id = {p}
        ''', (member_id,))
        m = cursor.fetchone()

        if not m:
            return jsonify({'success': False, 'message': 'Member not found.'}), 404

        member_id_actual = m['member_id']

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
                'active_loan': m['active_loan'],
                'total_service_fees': m['total_service_fees']
            },
            'recent_savings': savings
        })

@app.route('/api/member/<member_id>/history', methods=['GET'])
def get_member_full_history(member_id):
    db = get_db()
    cursor = db.cursor()
    p = query_param()

    cursor.execute(f'SELECT full_name, daily_target, current_cycle, cycle_days FROM members WHERE member_id = {p}', (member_id,))
    m = cursor.fetchone()
    if not m:
        return jsonify({'success': False, 'message': 'Member not found.'}), 404

    cursor.execute(f'''
        SELECT 'Savings' as category, amount, date, notes, days_credited, created_at 
        FROM savings WHERE member_id = {p} AND is_service_fee = 0
        UNION ALL
        SELECT 'Service Fee' as category, amount, date, description as notes, 0 as days_credited, created_at 
        FROM service_fees WHERE member_id = {p}
        UNION ALL
        SELECT 'Withdrawal' as category, amount, date, notes, 0 as days_credited, created_at 
        FROM withdrawals WHERE member_id = {p}
        UNION ALL
        SELECT tx_type as category, amount, date, notes, 0 as days_credited, created_at
        FROM transaction_archives WHERE member_id = {p}
        ORDER BY date DESC, created_at DESC
    ''', (member_id, member_id, member_id, member_id))
    
    rows = cursor.fetchall()
    history = [dict(r) for r in rows]

    return jsonify({
        'success': True,
        'member': dict(m),
        'history': history
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

    cursor.execute(f'''
        DELETE FROM loan_repayments 
        WHERE loan_id IN (SELECT id FROM loans WHERE member_id = {p})
    ''', (actual_id,))

    cursor.execute(f'DELETE FROM savings WHERE member_id = {p}', (actual_id,))
    cursor.execute(f'DELETE FROM service_fees WHERE member_id = {p}', (actual_id,))
    cursor.execute(f'DELETE FROM withdrawals WHERE member_id = {p}', (actual_id,))
    cursor.execute(f'DELETE FROM loans WHERE member_id = {p}', (actual_id,))

    cursor.execute(f'UPDATE members SET current_cycle = 1, cycle_days = 0 WHERE member_id = {p}', (actual_id,))

    db.commit()
    return jsonify({'success': True, 'message': f'Financial data for {m["full_name"]} ({actual_id}) reset successfully!'})

# -----------------------------------------------------------------------------
# BULK SAVINGS & MULTI-MONTH SERVICE FEE SPREADING (UPDATED 1st OF MONTH RULE)
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

        savings_date_str = data.get('date') or date.today().isoformat()
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

        # Parse payment date and FORCE baseline start to the 1st of that month
        raw_date = datetime.strptime(savings_date_str, '%Y-%m-%d').date()
        base_date = raw_date.replace(day=1) # Snapped strictly to 1st of month
        
        start_cycle = current_cycle

        remaining_cash = deposit_amount
        total_fees_collected = 0.0
        total_savings_credited = 0.0
        total_days_added = 0
        fee_records = []

        # SPREAD SERVICE FEES ACROSS CONSECUTIVE CALENDAR MONTHS (ALWAYS 1st OF MONTH)
        while remaining_cash > 0:
            if cycle_days == 0:
                fee_deducted = min(daily_target, remaining_cash)
                remaining_cash -= fee_deducted
                total_fees_collected += fee_deducted

                # Calculate target fee date (Always 1st of the target month)
                month_offset = current_cycle - start_cycle
                target_fee_date = add_months(base_date, month_offset)
                fee_date_fmt = target_fee_date.strftime('%Y-%m-01')
                fee_month_fmt = target_fee_date.strftime('%Y-%m')

                fee_records.append({
                    'amount': fee_deducted,
                    'cycle': current_cycle,
                    'date': fee_date_fmt,
                    'month_year': fee_month_fmt,
                    'desc': f'Cycle {current_cycle} Service Fee ({fee_month_fmt})'
                })

                if remaining_cash <= 0:
                    break

            days_needed = 31 - cycle_days
            max_cash_needed = days_needed * daily_target

            cash_for_this_cycle = min(remaining_cash, max_cash_needed)
            days_bought = int(cash_for_this_cycle / daily_target)

            if days_bought > 0:
                cash_spent = days_bought * daily_target
                remaining_cash -= cash_spent
                total_savings_credited += cash_spent
                total_days_added += days_bought
                cycle_days += days_bought

            if days_bought == 0 and remaining_cash < daily_target and cycle_days > 0:
                break

            if cycle_days >= 31:
                current_cycle += 1
                cycle_days = 0

        # INSERT EXTRACTED SERVICE FEES DATED BY CONSECUTIVE MONTHS (1st OF EACH MONTH)
        for f in fee_records:
            cursor.execute(f'''
                INSERT INTO savings (member_id, amount, date, month_year, is_service_fee, days_credited, notes)
                VALUES ({p}, {p}, {p}, {p}, 1, 0, {p})
            ''', (member_id, f['amount'], f['date'], f['month_year'], f['desc']))

            cursor.execute(f'''
                INSERT INTO service_fees (member_id, amount, month_year, description, date)
                VALUES ({p}, {p}, {p}, {p}, {p})
            ''', (member_id, f['amount'], f['month_year'], f['desc'], f['date']))

            archive_transaction(member_id, full_name, 'Service Fee', f['amount'], f['cycle'], f['date'], f['desc'])

        if total_savings_credited > 0:
            savings_note = notes or f'Bulk Contribution ({total_days_added} days)'
            month_year_base = raw_date.strftime('%Y-%m')
            cursor.execute(f'''
                INSERT INTO savings (member_id, amount, date, month_year, is_service_fee, days_credited, notes)
                VALUES ({p}, {p}, {p}, {p}, 0, {p}, {p})
            ''', (member_id, total_savings_credited, savings_date_str, month_year_base, total_days_added, savings_note))

            archive_transaction(member_id, full_name, 'Savings', total_savings_credited, current_cycle, savings_date_str, savings_note)

        cursor.execute(f'UPDATE members SET current_cycle = {p}, cycle_days = {p} WHERE member_id = {p}', 
                       (current_cycle, cycle_days, member_id))
        db.commit()

        msg = f"Processed ₦{deposit_amount:,.2f} for {full_name}! "
        if total_fees_collected > 0:
            msg += f"₦{total_fees_collected:,.2f} extracted in service fees across concerned months. "
        msg += f"₦{total_savings_credited:,.2f} saved in bulk ({total_days_added} days credited). "
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

    cursor.execute(f'SELECT full_name, current_cycle FROM members WHERE member_id = {p}', (member_id,))
    m_info = cursor.fetchone()
    if not m_info:
        return jsonify({'success': False, 'message': 'Member not found.'}), 404

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

    archive_transaction(member_id, m_info['full_name'], 'Withdrawal', amount, m_info['current_cycle'], w_date, notes or f'{withdrawal_type} Payout')

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

        cursor.execute(f'SELECT full_name, current_cycle FROM members WHERE member_id = {p}', (member_id,))
        m_info = cursor.fetchone()

        cursor.execute(f'''
            INSERT INTO loans (member_id, amount, interest_rate, repayment_amount, issue_date)
            VALUES ({p}, {p}, 0.0, {p}, {p})
        ''', (member_id, amount, amount, issue_date))

        if m_info:
            archive_transaction(member_id, m_info['full_name'], 'Loan Disbursed', amount, m_info['current_cycle'], issue_date, 'Loan Issued')

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

    cursor.execute(f'SELECT l.repayment_amount, l.amount_paid, l.member_id, m.full_name, m.current_cycle FROM loans l JOIN members m ON l.member_id = m.member_id WHERE l.id = {p}', (loan_id,))
    loan = cursor.fetchone()
    if not loan:
        return jsonify({'success': False, 'message': 'Loan record not found.'}), 404

    new_paid = loan['amount_paid'] + amount
    status = 'cleared' if new_paid >= loan['repayment_amount'] else 'active'

    cursor.execute(f'INSERT INTO loan_repayments (loan_id, amount, date, notes) VALUES ({p}, {p}, {p}, {p})',
                   (loan_id, amount, repay_date, notes))
    cursor.execute(f'UPDATE loans SET amount_paid = {p}, status = {p} WHERE id = {p}', (new_paid, status, loan_id))

    archive_transaction(loan['member_id'], loan['full_name'], 'Loan Repayment', amount, loan['current_cycle'], repay_date, notes)

    db.commit()
    return jsonify({'success': True, 'message': 'Loan repayment recorded!'})

# -----------------------------------------------------------------------------
# DAILY TRACKER
# -----------------------------------------------------------------------------
@app.route('/api/tracker/daily', methods=['GET'])
def get_daily_tracker():
    db = get_db()
    cursor = db.cursor()
    p = query_param()

    selected_date = request.args.get('date', '').strip()

    where_savings = f"WHERE s.date = {p}" if selected_date else ""
    where_repay = f"WHERE lr.date = {p}" if selected_date else ""
    where_withdraw = f"WHERE w.date = {p}" if selected_date else ""
    where_loans = f"WHERE l.issue_date = {p}" if selected_date else ""

    params = []
    if selected_date:
        params = [selected_date] * 4

    query = f'''
        SELECT 'Savings Deposit' as tx_type, s.date, s.member_id, m.full_name, 
               s.amount as net_amount, s.is_service_fee, COALESCE(s.notes, 'Deposit') as notes, s.created_at, s.id
        FROM savings s JOIN members m ON s.member_id = m.member_id {where_savings}
        UNION ALL
        SELECT 'Loan Repayment' as tx_type, lr.date, l.member_id, m.full_name, 
               lr.amount as net_amount, 0 as is_service_fee, COALESCE(lr.notes, 'Loan Repayment') as notes, lr.created_at, lr.id
        FROM loan_repayments lr JOIN loans l ON lr.loan_id = l.id JOIN members m ON l.member_id = m.member_id {where_repay}
        UNION ALL
        SELECT 'Withdrawal Payout' as tx_type, w.date, w.member_id, m.full_name, 
               w.amount as net_amount, 0 as is_service_fee, COALESCE(w.notes, 'Member Withdrawal') as notes, w.created_at, w.id
        FROM withdrawals w JOIN members m ON w.member_id = m.member_id {where_withdraw}
        UNION ALL
        SELECT 'Loan Disbursement' as tx_type, l.issue_date as date, l.member_id, m.full_name, 
               l.amount as net_amount, 0 as is_service_fee, 'Loan Disbursed' as notes, l.created_at, l.id
        FROM loans l JOIN members m ON l.member_id = m.member_id {where_loans}
        ORDER BY date DESC, id DESC
    '''
    
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()

    logs = []
    grouped_savings = {}

    for r in rows:
        dict_r = dict(r)
        if dict_r['tx_type'] == 'Savings Deposit':
            key = f"{dict_r['member_id']}_{dict_r['date']}_{dict_r['created_at']}"
            if key not in grouped_savings:
                grouped_savings[key] = {
                    'tx_type': 'Savings Deposit',
                    'date': dict_r['date'],
                    'member_id': dict_r['member_id'],
                    'full_name': dict_r['full_name'],
                    'gross_inflow': 0.0,
                    'service_fee': 0.0,
                    'outflow': 0.0,
                    'notes': dict_r['notes']
                }
            
            if dict_r['is_service_fee'] == 1:
                grouped_savings[key]['service_fee'] += dict_r['net_amount']
            else:
                grouped_savings[key]['gross_inflow'] += dict_r['net_amount']
                grouped_savings[key]['notes'] = dict_r['notes']
        else:
            is_outflow = dict_r['tx_type'] in ('Withdrawal Payout', 'Loan Disbursement')
            logs.append({
                'tx_type': dict_r['tx_type'],
                'date': dict_r['date'],
                'member_id': dict_r['member_id'],
                'full_name': dict_r['full_name'],
                'gross_inflow': 0.0 if is_outflow else dict_r['net_amount'],
                'service_fee': 0.0,
                'outflow': dict_r['net_amount'] if is_outflow else 0.0,
                'notes': dict_r['notes']
            })

    for k, grp in grouped_savings.items():
        grp['gross_inflow'] += grp['service_fee']
        logs.append(grp)

    logs.sort(key=lambda x: x['date'], reverse=True)

    total_inflow = sum(r['gross_inflow'] for r in logs)
    total_service_fees = sum(r['service_fee'] for r in logs)
    total_outflow = sum(r['outflow'] for r in logs)
    net_cashflow = total_inflow - total_outflow

    return jsonify({
        'logs': logs,
        'total_inflow': total_inflow,
        'total_service_fees': total_service_fees,
        'total_outflow': total_outflow,
        'net_cashflow': net_cashflow,
        'selected_date': selected_date
    })

@app.route('/api/service-fees', methods=['GET'])
def get_service_fees():
    db = get_db()
    cursor = db.cursor()
    p = query_param()

    selected_month = request.args.get('month', '').strip()

    if selected_month:
        cursor.execute(f'''
            SELECT f.*, m.full_name 
            FROM service_fees f
            JOIN members m ON f.member_id = m.member_id
            WHERE f.month_year = {p}
            ORDER BY f.date DESC, f.id DESC
        ''', (selected_month,))
    else:
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
        'total_fees': total_fees,
        'selected_month': selected_month
    })

@app.route('/api/archives', methods=['GET'])
def get_past_records():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM transaction_archives ORDER BY date DESC, id DESC')
    rows = cursor.fetchall()
    return jsonify([dict(r) for r in rows])

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

    return jsonify({'success': True, 'message': 'ALL active financial ledgers reset to zero! Member profiles & past archive records preserved.'})

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
# FRONTEND ENTRY POINT
# -----------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template_string(INDEX_TEMPLATE)

# -----------------------------------------------------------------------------
# HTML/CSS/JS SINGLE PAGE INTERFACE
# -----------------------------------------------------------------------------
INDEX_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Savers Growth System</title>
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
            padding-top: 112px;
        }

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

        .sticky-header-container {
            position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
            background: #ffffff; border-bottom: 1.5px solid var(--border-light);
            box-shadow: 0 2px 10px rgba(0,0,0,0.04);
        }

        header { padding: 0.75rem 1rem 0.25rem 1rem; display: flex; justify-space-between; align-items: center; }
        header .brand-box { display: flex; align-items: center; gap: 10px; cursor: pointer; }
        header .sprout-icon {
            background: var(--primary-green); color: #ffffff;
            width: 36px; height: 36px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center; font-size: 1.1rem;
        }
        header .brand-title { font-size: 1.25rem; font-weight: 800; color: var(--text-dark); letter-spacing: -0.3px; }
        
        .header-controls { display: flex; align-items: center; gap: 10px; }
        .member-count-badge {
            background: #f1f5f9; border: 1.5px solid var(--border-light);
            padding: 5px 10px; border-radius: 20px; font-weight: 800; font-size: 0.78rem;
            color: var(--primary-green-dark); display: flex; align-items: center; gap: 5px;
        }

        header .btn-logout {
            background: #ffffff; color: var(--text-dark); border: 1.5px solid var(--text-dark);
            padding: 6px 14px; border-radius: 20px; font-weight: 700; font-size: 0.82rem;
            cursor: pointer; min-height: 36px;
        }

        .sticky-nav-bar {
            padding: 0.25rem 1rem 0.6rem 1rem; max-width: 600px; margin: 0 auto;
            width: 100%; position: relative; display: flex; align-items: center; gap: 8px;
        }

        .btn-back-sticky {
            background: #0f172a; color: #ffffff; border: none; padding: 9px 14px;
            border-radius: 20px; font-weight: 800; font-size: 0.82rem; cursor: pointer;
            display: none; align-items: center; gap: 6px; white-space: nowrap; flex-shrink: 0;
            box-shadow: 0 2px 6px rgba(0,0,0,0.12);
        }
        .btn-back-sticky:active { transform: scale(0.96); }

        .search-wrapper { position: relative; width: 100%; flex: 1; }
        .search-wrapper i { position: absolute; left: 16px; top: 50%; transform: translateY(-50%); color: #94a3b8; font-size: 0.95rem; }
        .search-input {
            width: 100%; padding: 9px 16px 9px 42px; border-radius: 30px;
            border: 1.5px solid var(--border-light); font-size: 0.88rem; outline: none; background: #ffffff;
        }
        .search-results-dropdown {
            position: absolute; top: 100%; left: 0; right: 0; background: #ffffff;
            border: 1.5px solid var(--border-light); border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.1);
            z-index: 600; max-height: 240px; overflow-y: auto; display: none; margin-top: 4px;
        }
        .search-result-item {
            padding: 12px 16px; border-bottom: 1px solid var(--border-light); cursor: pointer;
            display: flex; justify-content: space-between; align-items: center; font-size: 0.88rem; font-weight: 600;
        }
        .search-result-item:hover { background: #f8fafc; }

        .app-container { max-width: 600px; margin: 0 auto; width: 100%; padding: 1rem 1rem 2rem 1rem; flex: 1; }

        .view-section { display: none; }
        .view-section.active { display: block; animation: fadeIn 0.2s forwards; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

        .view-header-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.1rem; }
        .view-title-group { display: flex; align-items: center; gap: 8px; font-size: 1.15rem; font-weight: 800; }
        .btn-add-header {
            background: var(--primary-green); color: #ffffff; border: none;
            padding: 8px 14px; border-radius: 10px; font-weight: 700; font-size: 0.82rem; cursor: pointer;
            display: flex; align-items: center; gap: 6px;
        }

        .login-card {
            background: #ffffff; border: 1.5px solid var(--border-light);
            border-radius: 20px; padding: 1.75rem 1.25rem; max-width: 420px; margin: 1rem auto;
            box-shadow: 0 4px 12px rgba(0,0,0,0.03);
        }
        .login-header { text-align: center; margin-bottom: 1.5rem; }
        .login-header .sprout-big {
            background: var(--primary-green); color: #fff; width: 56px; height: 56px;
            border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
            font-size: 1.8rem; margin-bottom: 10px;
        }
        .login-header h2 { font-size: 1.35rem; font-weight: 800; color: var(--text-dark); }

        .grid-3-col { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 0.4rem; }
        .menu-card {
            background: var(--card-bg); border: 1.5px solid var(--border-light);
            border-radius: var(--radius-card); padding: 0.85rem 0.3rem; display: flex;
            flex-direction: column; align-items: center; justify-content: center; text-align: center;
            cursor: pointer; box-shadow: 0 2px 4px rgba(0,0,0,0.02); transition: all 0.15s; min-height: 92px;
        }
        .menu-card:active { transform: scale(0.97); }
        .menu-card .icon-badge {
            width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center;
            font-size: 1.1rem; margin-bottom: 4px;
        }
        .icon-badge.pink { background: #ffe4e6; }
        .icon-badge.mint { background: #d1fae5; }
        .icon-badge.blue { background: #e0f2fe; }
        .icon-badge.yellow { background: #fef3c7; }
        .icon-badge.purple { background: #f3e8ff; }
        .icon-badge.teal { background: #ccfbf1; }

        .menu-card .card-heading { font-size: 0.8rem; font-weight: 800; color: var(--text-dark); line-height: 1.15; }

        .grid-row-4-center { display: flex; justify-content: center; gap: 10px; margin-top: 10px; flex-wrap: wrap; }
        .grid-row-4-center .menu-card { width: calc(33.333% - 7px); }

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
        .filter-row input, .filter-row select { flex: 1; padding: 10px 14px; border-radius: 12px; border: 1.5px solid var(--border-light); font-size: 0.88rem; background: #fff; }

        .member-grid-2col { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        .member-card-item {
            background: #ffffff; border: 1.5px solid var(--border-light);
            border-radius: 14px; padding: 0.75rem; cursor: pointer;
            box-shadow: 0 2px 4px rgba(0,0,0,0.01); display: flex; flex-direction: column; justify-content: space-between;
        }
        .member-card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
        .member-avatar {
            width: 32px; height: 32px; border-radius: 50%; background: #d1fae5; color: #059669;
            display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 0.95rem; flex-shrink: 0;
        }
        .member-info .name { font-size: 0.85rem; font-weight: 800; color: var(--text-dark); line-height: 1.2; word-break: break-word; }
        .member-info .code { font-size: 0.72rem; color: #94a3b8; font-weight: 700; }

        .member-stats-box {
            background: #f8fafc; border-radius: 8px; padding: 6px 8px;
            display: flex; flex-direction: column; gap: 2px; font-size: 0.75rem; margin-bottom: 6px;
        }
        .stat-line { font-weight: 600; color: var(--text-dark); display: flex; justify-content: space-between; }
        .stat-line .val-green { color: var(--primary-green-dark); font-weight: 800; }
        .stat-line .val-red { color: var(--primary-red); font-weight: 800; }

        .cycle-status-btn {
            background: var(--purple-bg); border: 1px solid var(--purple-border); color: var(--purple-cycle);
            padding: 5px; border-radius: 8px; text-align: center; font-weight: 700; font-size: 0.72rem;
            display: flex; align-items: center; justify-content: center; gap: 4px;
        }

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

        .table-responsive { overflow-x: auto; border-radius: 12px; border: 1.5px solid var(--border-light); }
        table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.82rem; }
        th, td { padding: 9px 10px; border-bottom: 1px solid var(--border-light); }
        th { background: #f8fafc; font-weight: 700; color: var(--text-muted); text-transform: uppercase; font-size: 0.68rem; }
        
        .badge { padding: 3px 6px; border-radius: 6px; font-size: 0.7rem; font-weight: 800; display: inline-block; }
        .badge-savings { background: #d1fae5; color: #065f46; }
        .badge-fee { background: #fef3c7; color: #92400e; }
        .badge-payout { background: #fee2e2; color: #991b1b; }
        .badge-success { background: #d1fae5; color: #065f46; }

        footer {
            background: #ffffff; color: var(--text-dark); text-align: center;
            padding: 1.25rem 1rem; font-size: 0.85rem; font-weight: 700;
            border-top: 1.5px solid var(--border-light); margin-top: auto; line-height: 1.4;
        }
    </style>
</head>
<body>

    <div id="toast-container"></div>

    <!-- FIXED STICKY TOP CONTAINER -->
    <div class="sticky-header-container">
        <header>
            <div class="brand-box" onclick="goBackHome()">
                <div class="sprout-icon"><i class="fa-solid fa-leaf"></i></div>
                <div class="brand-title">Savers Growth</div>
            </div>
            <div class="header-controls">
                <div class="member-count-badge" id="header-member-badge">
                    <i class="fa-solid fa-users"></i> <span id="header-member-count">0</span>
                </div>
                <button class="btn-logout" id="header-auth-btn" onclick="handleAuthAction()">Logout</button>
            </div>
        </header>

        <div class="sticky-nav-bar" id="admin-search-container">
            <button class="btn-back-sticky" id="global-back-btn" onclick="goBackHome()">
                <i class="fa-solid fa-arrow-left"></i> Back
            </button>

            <div class="search-wrapper">
                <i class="fa-solid fa-magnifying-glass"></i>
                <input type="text" class="search-input" id="global-search-input" 
                       placeholder="Type member ID or name..." 
                       oninput="handleGlobalSearchInput(event)">
            </div>
            <div class="search-results-dropdown" id="search-results-dropdown"></div>
        </div>
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
                <div class="menu-card" onclick="showSection('member-history')">
                    <div class="icon-badge mint">🔎</div>
                    <div class="card-heading">Member History</div>
                </div>

                <div class="menu-card" onclick="showSection('past-records')">
                    <div class="icon-badge pink">📦</div>
                    <div class="card-heading">Past Records</div>
                </div>

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
            <div style="background: #ffffff; border: 1.5px solid var(--border-light); border-radius: 20px; padding: 1.25rem;">
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
                    <div class="overview-row">
                        <span>Service Fees Paid:</span>
                        <span id="mportal-fees" style="font-weight: 800; color: var(--amber-fee);">₦0.00</span>
                    </div>
                    <div class="overview-divider"></div>
                    <div class="overview-row">
                        <span>Active Loan:</span>
                        <span style="color: var(--primary-red); font-weight: 800;" id="mportal-loan">₦0.00</span>
                    </div>
                </div>

                <div style="font-size: 0.95rem; font-weight: 800; margin-bottom: 8px;">My Recent Savings</div>
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

        <!-- VIEW 2: OVERVIEW -->
        <div id="view-overview" class="view-section">
            <div class="view-header-row"><div class="view-title-group">👛 Wallet Overview</div></div>
            <div class="overview-box">
                <div class="overview-row"><span>Total Money Saved:</span><span class="amount-saved" id="stat-total-saved">₦0.00</span></div>
                <div class="overview-row"><span>Total Service Fees Deducted:</span><span class="amount-fees" id="stat-service-fees">₦0.00</span></div>
                <div class="overview-divider"></div>
                <div class="overview-row"><span>Net Wallet Balance:</span><span class="amount-net" id="stat-net-balance">₦0.00</span></div>
            </div>
        </div>

        <!-- VIEW 3: SAVINGS FORM -->
        <div id="view-savings" class="view-section">
            <div class="view-header-row"><div class="view-title-group">➕ Record Contribution</div></div>
            <div class="card-form">
                <form onsubmit="handleSavingsSubmit(event)">
                    <div class="form-group">
                        <label>Select Member</label>
                        <select class="form-control" id="savings-member-select" required></select>
                    </div>
                    <div class="form-group">
                        <label>Deposit Amount (₦)</label>
                        <input type="number" class="form-control" id="savings-amount" placeholder="e.g. 5000" required>
                    </div>
                    <div class="form-group">
                        <label>Deposit Date</label>
                        <input type="date" class="form-control" id="savings-date" required>
                    </div>
                    <div class="form-group">
                        <label>Notes (Optional)</label>
                        <input type="text" class="form-control" id="savings-notes" placeholder="e.g. Cash payment">
                    </div>
                    <button type="submit" class="btn-submit">Record Deposit</button>
                </form>
            </div>
        </div>

        <!-- VIEW 4: WITHDRAWAL FORM -->
        <div id="view-withdrawal" class="view-section">
            <div class="view-header-row"><div class="view-title-group">💸 Process Withdrawal</div></div>
            <div class="card-form">
                <form onsubmit="handleWithdrawalSubmit(event)">
                    <div class="form-group">
                        <label>Select Member</label>
                        <select class="form-control" id="withdraw-member-select" required></select>
                    </div>
                    <div class="form-group">
                        <label>Withdrawal Amount (₦)</label>
                        <input type="number" class="form-control" id="withdraw-amount" placeholder="e.g. 10000" required>
                    </div>
                    <div class="form-group">
                        <label>Withdrawal Date</label>
                        <input type="date" class="form-control" id="withdraw-date" required>
                    </div>
                    <button type="submit" class="btn-submit" style="background: var(--primary-red);">Process Withdrawal</button>
                </form>
            </div>
        </div>

        <!-- VIEW 5: MEMBERS DIRECTORY -->
        <div id="view-members" class="view-section">
            <div class="view-header-row"><div class="view-title-group">👥 Members Directory</div></div>
            <div id="members-cards-container" class="member-grid-2col"></div>
        </div>

        <!-- VIEW 6: REGISTER MEMBER -->
        <div id="view-register" class="view-section">
            <div class="view-header-row"><div class="view-title-group">🆔 Register New Member</div></div>
            <div class="card-form">
                <form onsubmit="handleRegisterSubmit(event)">
                    <div class="form-group">
                        <label>Full Name</label>
                        <input type="text" class="form-control" id="reg-fullname" placeholder="John Doe" required>
                    </div>
                    <div class="form-group">
                        <label>Daily Target Amount (₦)</label>
                        <input type="number" class="form-control" id="reg-target" placeholder="500" value="500">
                    </div>
                    <button type="submit" class="btn-submit">Register Member</button>
                </form>
            </div>
        </div>

    </div>

    <footer>
        Savers Growth System &copy; 2026<br>
        <span style="font-size:0.75rem; color:var(--text-muted);">Cycle Baseline: 1st of every month</span>
    </footer>

    <script>
        let currentUser = null;
        let membersList = [];

        function showToast(msg, type = 'success') {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            toast.innerHTML = `<i class="fa-solid fa-${type === 'success' ? 'circle-check' : 'circle-exclamation'}"></i> ${msg}`;
            container.appendChild(toast);
            setTimeout(() => toast.remove(), 3500);
        }

        async function initApp() {
            document.getElementById('savings-date').value = new Date().toISOString().split('T')[0];
            document.getElementById('withdraw-date').value = new Date().toISOString().split('T')[0];
            
            try {
                const res = await fetch('/api/auth/me');
                const data = await res.json();
                if (data.logged_in) {
                    currentUser = data;
                    document.getElementById('header-member-count').innerText = data.total_members || 0;
                    if (data.role === 'admin') {
                        showSection('home');
                    } else {
                        showSection('member-portal');
                        loadMemberPortal(data.member_id);
                    }
                } else {
                    showSection('login');
                }
            } catch (e) {
                showSection('login');
            }
        }

        function showSection(sectionId) {
            document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));
            const target = document.getElementById(`view-${sectionId}`);
            if (target) target.classList.add('active');

            const backBtn = document.getElementById('global-back-btn');
            if (sectionId === 'home' || sectionId === 'login' || sectionId === 'member-portal') {
                backBtn.style.display = 'none';
            } else {
                backBtn.style.display = 'inline-flex';
            }

            if (['savings', 'withdrawal', 'members'].includes(sectionId)) {
                loadMembers();
            }
            if (sectionId === 'overview') loadOverviewStats();
        }

        function goBackHome() {
            if (currentUser && currentUser.role === 'admin') {
                showSection('home');
            } else if (currentUser) {
                showSection('member-portal');
            } else {
                showSection('login');
            }
        }

        async function handleLoginSubmit(e) {
            e.preventDefault();
            const u = document.getElementById('login-username').value;
            const p = document.getElementById('login-password').value;

            const res = await fetch('/api/auth/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username: u, password: p})
            });
            const data = await res.json();
            if (data.success) {
                showToast('Login successful!');
                initApp();
            } else {
                showToast(data.message, 'error');
            }
        }

        async function handleAuthAction() {
            await fetch('/api/auth/logout', {method: 'POST'});
            currentUser = null;
            showSection('login');
        }

        async function loadMembers() {
            const res = await fetch('/api/members');
            membersList = await res.json();

            const selects = ['savings-member-select', 'withdraw-member-select'];
            selects.forEach(id => {
                const el = document.getElementById(id);
                if (el) {
                    el.innerHTML = '<option value="">-- Select Member --</option>' +
                        membersList.map(m => `<option value="${m.member_id}">${m.full_name} (${m.member_id})</option>`).join('');
                }
            });

            const grid = document.getElementById('members-cards-container');
            if (grid) {
                grid.innerHTML = membersList.map(m => `
                    <div class="member-card-item">
                        <div class="member-card-header">
                            <div class="member-avatar">${m.full_name.charAt(0)}</div>
                            <div class="member-info">
                                <div class="name">${m.full_name}</div>
                                <div class="code">${m.member_id}</div>
                            </div>
                        </div>
                        <div class="member-stats-box">
                            <div class="stat-line"><span>Saved:</span> <span class="val-green">₦${m.total_saved.toLocaleString()}</span></div>
                            <div class="stat-line"><span>Net:</span> <span>₦${m.net_balance.toLocaleString()}</span></div>
                        </div>
                        <div class="cycle-status-btn">🔄 Cycle ${m.current_cycle} (${m.cycle_days}/31d)</div>
                    </div>
                `).join('');
            }
        }

        async function loadOverviewStats() {
            const res = await fetch('/api/stats/overview');
            const d = await res.json();
            document.getElementById('stat-total-saved').innerText = `₦${d.total_savings.toLocaleString()}`;
            document.getElementById('stat-service-fees').innerText = `₦${d.total_fees.toLocaleString()}`;
            document.getElementById('stat-net-balance').innerText = `₦${d.net_balance.toLocaleString()}`;
        }

        async function handleSavingsSubmit(e) {
            e.preventDefault();
            const payload = {
                member_id: document.getElementById('savings-member-select').value,
                amount: document.getElementById('savings-amount').value,
                date: document.getElementById('savings-date').value,
                notes: document.getElementById('savings-notes').value
            };
            const res = await fetch('/api/savings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            const d = await res.json();
            if (d.success) {
                showToast(d.message);
                document.getElementById('savings-amount').value = '';
                goBackHome();
            } else showToast(d.message, 'error');
        }

        async function handleWithdrawalSubmit(e) {
            e.preventDefault();
            const payload = {
                member_id: document.getElementById('withdraw-member-select').value,
                amount: document.getElementById('withdraw-amount').value,
                date: document.getElementById('withdraw-date').value
            };
            const res = await fetch('/api/withdrawals', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            const d = await res.json();
            if (d.success) {
                showToast(d.message);
                document.getElementById('withdraw-amount').value = '';
                goBackHome();
            } else showToast(d.message, 'error');
        }

        async function handleRegisterSubmit(e) {
            e.preventDefault();
            const payload = {
                full_name: document.getElementById('reg-fullname').value,
                daily_target: document.getElementById('reg-target').value
            };
            const res = await fetch('/api/members', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            const d = await res.json();
            if (d.success) {
                showToast(d.message);
                document.getElementById('reg-fullname').value = '';
                goBackHome();
            } else showToast(d.message, 'error');
        }

        async function loadMemberPortal(memberId) {
            const res = await fetch(`/api/member/${memberId}`);
            const d = await res.json();
            if (d.success) {
                const m = d.member;
                document.getElementById('mportal-name').innerText = m.full_name;
                document.getElementById('mportal-id').innerText = `ID: ${m.member_id}`;
                document.getElementById('mportal-balance').innerText = `₦${m.net_balance.toLocaleString()}`;
                document.getElementById('mportal-target').innerText = `₦${m.daily_target.toLocaleString()}`;
                document.getElementById('mportal-fees').innerText = `₦${m.total_service_fees.toLocaleString()}`;
                document.getElementById('mportal-loan').innerText = `₦${m.active_loan.toLocaleString()}`;

                const table = document.getElementById('mportal-savings-table');
                table.innerHTML = d.recent_savings.map(s => `
                    <tr>
                        <td>${s.date}</td>
                        <td>₦${s.amount.toLocaleString()}</td>
                        <td>${s.days_credited} days</td>
                    </tr>
                `).join('');
            }
        }

        window.onload = initApp;
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
    