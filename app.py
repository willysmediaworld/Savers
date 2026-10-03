import os
import sqlite3
from datetime import datetime, date
from flask import Flask, render_template_string, request, jsonify, g, session
from werkzeug.security import generate_password_hash, check_password_hash

DATABASE_URL = os.environ.get('DATABASE_URL')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'savers_growth_31day_cycle_key_2026_secured')

def add_months(sourcedate, months):
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    return date(year, month, 1)

def get_db():
    if 'db' not in g:
        if DATABASE_URL:
            import psycopg2
            import psycopg2.extras
            url = DATABASE_URL.replace("postgres://", "postgresql://")
            g.db = psycopg2.connect(url, cursor_factory=psycopg2.extras.DictCursor)
        else:
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'savers_growth.db')
            g.db = sqlite3.connect(db_path, timeout=15)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA journal_mode=WAL;")
            g.db.execute("PRAGMA synchronous=NORMAL;")
            g.db.execute("PRAGMA temp_store=MEMORY;")
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

        cursor.execute(f'''CREATE TABLE IF NOT EXISTS members (
            id {pk_type}, member_id TEXT UNIQUE NOT NULL, full_name TEXT NOT NULL,
            phone TEXT DEFAULT '', email TEXT DEFAULT '', username TEXT UNIQUE,
            password_hash TEXT DEFAULT '', daily_target REAL DEFAULT 500.0,
            current_cycle INTEGER DEFAULT 1, cycle_days INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        cursor.execute(f'''CREATE TABLE IF NOT EXISTS savings (
            id {pk_type}, member_id TEXT NOT NULL, amount REAL NOT NULL, date TEXT NOT NULL,
            month_year TEXT NOT NULL, is_service_fee INTEGER DEFAULT 0, days_credited INTEGER DEFAULT 0,
            notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        cursor.execute(f'''CREATE TABLE IF NOT EXISTS withdrawals (
            id {pk_type}, member_id TEXT NOT NULL, amount REAL NOT NULL, withdrawal_type TEXT NOT NULL,
            fee_deducted REAL DEFAULT 0, date TEXT NOT NULL, notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        cursor.execute(f'''CREATE TABLE IF NOT EXISTS loans (
            id {pk_type}, member_id TEXT NOT NULL, amount REAL NOT NULL, interest_rate REAL DEFAULT 0.0,
            repayment_amount REAL NOT NULL, amount_paid REAL DEFAULT 0, status TEXT DEFAULT 'active',
            issue_date TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        cursor.execute(f'''CREATE TABLE IF NOT EXISTS loan_repayments (
            id {pk_type}, loan_id INTEGER NOT NULL, amount REAL NOT NULL, date TEXT NOT NULL,
            notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        cursor.execute(f'''CREATE TABLE IF NOT EXISTS service_fees (
            id {pk_type}, member_id TEXT NOT NULL, amount REAL NOT NULL, month_year TEXT NOT NULL,
            description TEXT, date TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        cursor.execute(f'''CREATE TABLE IF NOT EXISTS admin_users (
            id {pk_type}, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        cursor.execute(f'''CREATE TABLE IF NOT EXISTS transaction_archives (
            id {pk_type}, member_id TEXT NOT NULL, full_name TEXT NOT NULL, tx_type TEXT NOT NULL,
            amount REAL NOT NULL, cycle_no INTEGER DEFAULT 1, date TEXT NOT NULL, notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_members_mid ON members(member_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_members_uname ON members(username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_savings_mid ON savings(member_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_savings_fee ON savings(member_id, is_service_fee)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_withdrawals_mid ON withdrawals(member_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_loans_mid ON loans(member_id, status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_archives_mid ON transaction_archives(member_id)")
        db.commit()

        admin_pass_hash = generate_password_hash('saversrotimi1972')
        cursor.execute(f"SELECT COUNT(*) FROM admin_users WHERE username = {p}", ('Saversadmin',))
        row = cursor.fetchone()
        if not row or row[0] == 0:
            cursor.execute(f"INSERT INTO admin_users (username, password_hash) VALUES ({p}, {p})", ('Saversadmin', admin_pass_hash))
            db.commit()

        cursor.execute(f"SELECT COUNT(*) FROM members WHERE member_id = {p}", ('SVR0001',))
        row_m = cursor.fetchone()
        if not row_m or row_m[0] == 0:
            cursor.execute(f'''INSERT INTO members (member_id, full_name, phone, username, password_hash, daily_target, current_cycle, cycle_days, status)
                VALUES ({p}, {p}, {p}, {p}, {p}, 1000.0, 1, 0, 'Owner/Admin')''',
                ('SVR0001', 'Oladele Rotimi Williams', '09018363715', 'Saversadmin', admin_pass_hash))
            db.commit()

with app.app_context():
    init_db()

def archive_transaction(member_id, full_name, tx_type, amount, cycle_no, date_str, notes):
    try:
        db = get_db()
        cursor = db.cursor()
        p = query_param()
        cursor.execute(f'''INSERT INTO transaction_archives (member_id, full_name, tx_type, amount, cycle_no, date, notes)
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p})''',
            (member_id, full_name, tx_type, amount, cycle_no, date_str, notes))
        db.commit()
    except Exception as e:
        print("Archive error:", e)

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
            'logged_in': True, 'role': session.get('role'), 'member_id': session.get('member_id'),
            'full_name': session.get('full_name'), 'total_members': total_members
        })
    return jsonify({'logged_in': False})

@app.route('/api/stats/overview', methods=['GET'])
def get_wallet_overview():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM savings WHERE is_service_fee = 0')
    net_savings_credited = cursor.fetchone()[0]
    cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM service_fees')
    total_fees = cursor.fetchone()[0]
    cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM withdrawals')
    total_withdrawals = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM members')
    total_members = cursor.fetchone()[0]
    # NEW: total loans stats
    cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM loans')
    total_loans_issued = cursor.fetchone()[0]
    cursor.execute("SELECT COALESCE(SUM(repayment_amount - amount_paid), 0) FROM loans WHERE status = 'active'")
    total_loans_outstanding = cursor.fetchone()[0]

    gross_total_saved = net_savings_credited + total_fees
    net_balance = net_savings_credited - total_withdrawals
    return jsonify({
        'gross_total_saved': gross_total_saved, 'net_savings_credited': net_savings_credited,
        'total_fees': total_fees, 'net_balance': net_balance,
        'total_withdrawals': total_withdrawals, 'total_members': total_members,
        'total_loans_issued': total_loans_issued,
        'total_loans_outstanding': total_loans_outstanding
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
            cursor.execute(f'''INSERT INTO members (member_id, full_name, phone, email, username, password_hash, daily_target, current_cycle, cycle_days, status)
                VALUES ({p}, {p}, '', '', {p}, {p}, {p}, 1, 0, 'active')''',
                (member_id, full_name, default_username, default_pass_hash, daily_target))
            db.commit()
            return jsonify({'success': True, 'message': f'Member registered! ID: {member_id}', 'member_id': member_id})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    else:
        cursor.execute('''
            SELECT m.id, m.member_id, m.full_name, m.phone, m.email, m.username, m.daily_target,
                m.current_cycle, m.cycle_days, m.status, m.created_at,
                COALESCE(s.savings_credited, 0) as savings_credited,
                COALESCE(w.total_withdrawn, 0) as total_withdrawn,
                COALESCE(l.active_loan, 0) as active_loan,
                COALESCE(f.total_service_fees, 0) as total_service_fees
            FROM members m
            LEFT JOIN (SELECT member_id, SUM(amount) as savings_credited FROM savings WHERE is_service_fee = 0 GROUP BY member_id) s ON m.member_id = s.member_id
            LEFT JOIN (SELECT member_id, SUM(amount) as total_withdrawn FROM withdrawals GROUP BY member_id) w ON m.member_id = w.member_id
            LEFT JOIN (SELECT member_id, SUM(repayment_amount - amount_paid) as active_loan FROM loans WHERE status = 'active' GROUP BY member_id) l ON m.member_id = l.member_id
            LEFT JOIN (SELECT member_id, SUM(amount) as total_service_fees FROM service_fees GROUP BY member_id) f ON m.member_id = f.member_id
            ORDER BY m.id ASC''')
        rows = cursor.fetchall()
        members = []
        for r in rows:
            savings_credited = r['savings_credited']
            total_fees = r['total_service_fees']
            gross_saved = savings_credited + total_fees
            net_balance = savings_credited - r['total_withdrawn']
            members.append({
                'id': r['id'], 'member_id': r['member_id'], 'full_name': r['full_name'],
                'phone': r['phone'] or '', 'email': r['email'] or '', 'username': r['username'] or '',
                'daily_target': r['daily_target'], 'current_cycle': r['current_cycle'],
                'cycle_days': r['cycle_days'], 'status': r['status'],
                'gross_saved': gross_saved, 'savings_credited': savings_credited, 'total_saved': gross_saved,
                'total_withdrawn': r['total_withdrawn'], 'net_balance': net_balance,
                'active_loan': r['active_loan'], 'total_service_fees': total_fees,
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
            cursor.execute(f'''UPDATE members SET full_name = {p}, username = {p}, password_hash = {p}, daily_target = {p} WHERE member_id = {p}''',
                (full_name, username, pass_hash, daily_target, member_id))
        else:
            cursor.execute(f'''UPDATE members SET full_name = {p}, username = {p}, daily_target = {p} WHERE member_id = {p}''',
                (full_name, username, daily_target, member_id))
        db.commit()
        return jsonify({'success': True, 'message': 'Member profile updated successfully!'})
    else:
        cursor.execute(f'''SELECT m.*,
            COALESCE((SELECT SUM(amount) FROM savings WHERE member_id = m.member_id AND is_service_fee = 0), 0) as savings_credited,
            COALESCE((SELECT SUM(amount) FROM withdrawals WHERE member_id = m.member_id), 0) as total_withdrawn,
            COALESCE((SELECT SUM(repayment_amount - amount_paid) FROM loans WHERE member_id = m.member_id AND status = 'active'), 0) as active_loan,
            COALESCE((SELECT SUM(amount) FROM service_fees WHERE member_id = m.member_id), 0) as total_service_fees
            FROM members m WHERE m.member_id = {p}''', (member_id,))
        m = cursor.fetchone()
        if not m:
            return jsonify({'success': False, 'message': 'Member not found.'}), 404
        member_id_actual = m['member_id']
        savings_credited = m['savings_credited']
        total_fees = m['total_service_fees']
        gross_saved = savings_credited + total_fees
        net_balance = savings_credited - m['total_withdrawn']
        cursor.execute(f'''SELECT id, amount, date, notes, is_service_fee, days_credited FROM savings WHERE member_id = {p} AND is_service_fee = 0 ORDER BY id DESC LIMIT 10''', (member_id_actual,))
        savings = [dict(s) for s in cursor.fetchall()]
        cursor.execute(f'''SELECT id, amount, repayment_amount, amount_paid, status, issue_date FROM loans WHERE member_id = {p} AND status = 'active' ORDER BY id DESC''', (member_id_actual,))
        active_loans = [dict(l) for l in cursor.fetchall()]
        return jsonify({
            'success': True,
            'member': {
                'id': m['id'], 'member_id': m['member_id'], 'full_name': m['full_name'],
                'username': m['username'] or '', 'daily_target': m['daily_target'],
                'current_cycle': m['current_cycle'], 'cycle_days': m['cycle_days'],
                'status': m['status'], 'gross_saved': gross_saved, 'total_saved': gross_saved,
                'savings_credited': savings_credited, 'total_withdrawn': m['total_withdrawn'],
                'net_balance': net_balance, 'active_loan': m['active_loan'],
                'total_service_fees': total_fees
            },
            'recent_savings': savings, 'active_loans': active_loans
        })

@app.route('/api/member/<member_id>/reset-target', methods=['POST'])
def reset_member_target(member_id):
    db = get_db()
    cursor = db.cursor()
    p = query_param()
    data = request.json or {}
    try:
        new_target = float(data.get('daily_target', 500.0))
    except ValueError:
        new_target = 500.0
    cursor.execute(f'UPDATE members SET daily_target = {p} WHERE member_id = {p}', (new_target, member_id))
    db.commit()
    return jsonify({'success': True, 'message': f'Daily target updated to ₦{new_target:,.2f}!'})

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
        SELECT 'Savings' as category, amount, date, notes, days_credited, created_at FROM savings WHERE member_id = {p} AND is_service_fee = 0
        UNION ALL
        SELECT 'Service Fee' as category, amount, date, description as notes, 0 as days_credited, created_at FROM service_fees WHERE member_id = {p}
        UNION ALL
        SELECT 'Withdrawal' as category, amount, date, notes, 0 as days_credited, created_at FROM withdrawals WHERE member_id = {p}
        UNION ALL
        SELECT tx_type as category, amount, date, notes, 0 as days_credited, created_at FROM transaction_archives WHERE member_id = {p}
        ORDER BY date DESC, created_at DESC''', (member_id, member_id, member_id, member_id))
    rows = cursor.fetchall()
    history = [dict(r) for r in rows]
    return jsonify({'success': True, 'member': dict(m), 'history': history})

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
    cursor.execute(f'DELETE FROM loan_repayments WHERE loan_id IN (SELECT id FROM loans WHERE member_id = {p})', (actual_id,))
    cursor.execute(f'DELETE FROM savings WHERE member_id = {p}', (actual_id,))
    cursor.execute(f'DELETE FROM service_fees WHERE member_id = {p}', (actual_id,))
    cursor.execute(f'DELETE FROM withdrawals WHERE member_id = {p}', (actual_id,))
    cursor.execute(f'DELETE FROM loans WHERE member_id = {p}', (actual_id,))
    cursor.execute(f'UPDATE members SET current_cycle = 1, cycle_days = 0 WHERE member_id = {p}', (actual_id,))
    db.commit()
    return jsonify({'success': True, 'message': f'All financial and savings history for {m["full_name"]} ({actual_id}) reset to zero!'})

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
        raw_date = datetime.strptime(savings_date_str, '%Y-%m-%d').date()
        base_date = raw_date.replace(day=1)
        start_cycle = current_cycle
        remaining_cash = deposit_amount
        total_fees_collected = 0.0
        total_savings_credited = 0.0
        total_days_added = 0
        fee_records = []
        while remaining_cash > 0:
            if cycle_days == 0:
                fee_deducted = min(daily_target, remaining_cash)
                remaining_cash -= fee_deducted
                total_fees_collected += fee_deducted
                cycle_days += 1
                month_offset = current_cycle - start_cycle
                target_fee_date = add_months(base_date, month_offset)
                fee_month_fmt = target_fee_date.strftime('%Y-%m')
                fee_records.append({
                    'amount': fee_deducted, 'cycle': current_cycle, 'date': savings_date_str,
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
        for f in fee_records:
            cursor.execute(f'''INSERT INTO savings (member_id, amount, date, month_year, is_service_fee, days_credited, notes)
                VALUES ({p}, {p}, {p}, {p}, 1, 0, {p})''', (member_id, f['amount'], f['date'], f['month_year'], f['desc']))
            cursor.execute(f'''INSERT INTO service_fees (member_id, amount, month_year, description, date)
                VALUES ({p}, {p}, {p}, {p}, {p})''', (member_id, f['amount'], f['month_year'], f['desc'], f['date']))
            archive_transaction(member_id, full_name, 'Service Fee', f['amount'], f['cycle'], f['date'], f['desc'])
        if total_savings_credited > 0:
            savings_note = notes or f'Bulk Contribution ({total_days_added} days)'
            month_year_base = raw_date.strftime('%Y-%m')
            cursor.execute(f'''INSERT INTO savings (member_id, amount, date, month_year, is_service_fee, days_credited, notes)
                VALUES ({p}, {p}, {p}, {p}, 0, {p}, {p})''',
                (member_id, total_savings_credited, savings_date_str, month_year_base, total_days_added, savings_note))
            archive_transaction(member_id, full_name, 'Savings', total_savings_credited, current_cycle, savings_date_str, savings_note)
        cursor.execute(f'UPDATE members SET current_cycle = {p}, cycle_days = {p} WHERE member_id = {p}',
                       (current_cycle, cycle_days, member_id))
        db.commit()
        msg = f"Processed ₦{deposit_amount:,.2f} for {full_name}! "
        if total_fees_collected > 0:
            msg += f"₦{total_fees_collected:,.2f} fee (Day 1). "
        if total_savings_credited > 0:
            msg += f"₦{total_savings_credited:,.2f} saved ({total_days_added} savings days). "
        msg += f"Now on Cycle {current_cycle} — Day {cycle_days}/31."
        return jsonify({
            'success': True, 'message': msg,
            'breakdown': {
                'member_id': member_id, 'full_name': full_name,
                'deposit_amount': deposit_amount, 'fee_collected': total_fees_collected,
                'savings_credited': total_savings_credited, 'days_added': total_days_added,
                'new_cycle': current_cycle, 'new_cycle_days': cycle_days
            }
        })
    else:
        cursor.execute('''SELECT s.*, m.full_name FROM savings s JOIN members m ON s.member_id = m.member_id ORDER BY s.id DESC LIMIT 50''')
        rows = cursor.fetchall()
        return jsonify([dict(r) for r in rows])

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
    total_saved_credited = cursor.fetchone()[0]
    cursor.execute(f'SELECT COALESCE(SUM(amount), 0) FROM withdrawals WHERE member_id = {p}', (member_id,))
    total_withdrawn = cursor.fetchone()[0]
    current_balance = total_saved_credited - total_withdrawn
    if amount > current_balance:
        return jsonify({'success': False, 'message': f'Insufficient balance! Available Net Balance: ₦{current_balance:,.2f}'}), 400
    cursor.execute(f'''INSERT INTO withdrawals (member_id, amount, withdrawal_type, fee_deducted, date, notes)
        VALUES ({p}, {p}, {p}, 0.0, {p}, {p})''', (member_id, amount, withdrawal_type, w_date, notes))
    archive_transaction(member_id, m_info['full_name'], 'Withdrawal', amount, m_info['current_cycle'], w_date, notes or f'{withdrawal_type} Payout')
    if withdrawal_type == 'reset':
        cursor.execute(f'UPDATE members SET current_cycle = current_cycle + 1, cycle_days = 0 WHERE member_id = {p}', (member_id,))
    db.commit()
    return jsonify({'success': True, 'message': f'Withdrawal of ₦{amount:,.2f} processed for {m_info["full_name"]}!'})

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
        cursor.execute(f'''INSERT INTO loans (member_id, amount, interest_rate, repayment_amount, issue_date)
            VALUES ({p}, {p}, 0.0, {p}, {p})''', (member_id, amount, amount, issue_date))
        if m_info:
            archive_transaction(member_id, m_info['full_name'], 'Loan Disbursed', amount, m_info['current_cycle'], issue_date, 'Loan Issued (Standalone)')
        db.commit()
        return jsonify({'success': True, 'message': f'Standalone loan of ₦{amount:,.2f} issued successfully!'})
    else:
        cursor.execute('''SELECT l.*, m.full_name FROM loans l JOIN members m ON l.member_id = m.member_id ORDER BY l.id DESC''')
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
    cursor.execute(f'INSERT INTO loan_repayments (loan_id, amount, date, notes) VALUES ({p}, {p}, {p}, {p})', (loan_id, amount, repay_date, notes))
    cursor.execute(f'UPDATE loans SET amount_paid = {p}, status = {p} WHERE id = {p}', (new_paid, status, loan_id))
    archive_transaction(loan['member_id'], loan['full_name'], 'Loan Repayment', amount, loan['current_cycle'], repay_date, notes)
    db.commit()
    return jsonify({'success': True, 'message': f'Loan repayment of ₦{amount:,.2f} recorded!'})

@app.route('/api/tracker/daily', methods=['GET'])
def get_daily_tracker():
    db = get_db()
    cursor = db.cursor()
    p = query_param()
    selected_date = request.args.get('date', '').strip()

    if selected_date:
        cursor.execute(f'''SELECT s.id, s.date, s.member_id, m.full_name, s.amount, s.days_credited,
            COALESCE(s.notes, 'Deposit') as notes, s.created_at
            FROM savings s JOIN members m ON s.member_id = m.member_id
            WHERE s.is_service_fee = 0 AND s.date = {p}
            ORDER BY s.created_at DESC, s.id DESC''', (selected_date,))
    else:
        cursor.execute('''SELECT s.id, s.date, s.member_id, m.full_name, s.amount, s.days_credited,
            COALESCE(s.notes, 'Deposit') as notes, s.created_at
            FROM savings s JOIN members m ON s.member_id = m.member_id
            WHERE s.is_service_fee = 0
            ORDER BY s.created_at DESC, s.id DESC''')
    savings_logs = [dict(r) for r in cursor.fetchall()]

    if selected_date:
        cursor.execute(f'''SELECT f.id, f.date, f.member_id, m.full_name, f.amount, f.month_year, f.description, f.created_at
            FROM service_fees f JOIN members m ON f.member_id = m.member_id
            WHERE f.date = {p}
            ORDER BY f.created_at DESC, f.id DESC''', (selected_date,))
    else:
        cursor.execute('''SELECT f.id, f.date, f.member_id, m.full_name, f.amount, f.month_year, f.description, f.created_at
            FROM service_fees f JOIN members m ON f.member_id = m.member_id
            ORDER BY f.created_at DESC, f.id DESC''')
    fee_logs = [dict(r) for r in cursor.fetchall()]

    if selected_date:
        cursor.execute(f'''
            SELECT 'Withdrawal' as tx_type, w.date, w.member_id, m.full_name, w.amount, COALESCE(w.notes, 'Member Withdrawal') as notes, w.created_at
            FROM withdrawals w JOIN members m ON w.member_id = m.member_id WHERE w.date = {p}
            UNION ALL
            SELECT 'Loan Issued' as tx_type, l.issue_date as date, l.member_id, m.full_name, l.amount, 'Standalone Loan' as notes, l.created_at
            FROM loans l JOIN members m ON l.member_id = m.member_id WHERE l.issue_date = {p}
            UNION ALL
            SELECT 'Loan Repayment' as tx_type, lr.date, l.member_id, m.full_name, lr.amount, COALESCE(lr.notes, 'Loan Repayment') as notes, lr.created_at
            FROM loan_repayments lr JOIN loans l ON lr.loan_id = l.id JOIN members m ON l.member_id = m.member_id WHERE lr.date = {p}
            ORDER BY date DESC, created_at DESC''', (selected_date, selected_date, selected_date))
    else:
        cursor.execute('''
            SELECT 'Withdrawal' as tx_type, w.date, w.member_id, m.full_name, w.amount, COALESCE(w.notes, 'Member Withdrawal') as notes, w.created_at
            FROM withdrawals w JOIN members m ON w.member_id = m.member_id
            UNION ALL
            SELECT 'Loan Issued' as tx_type, l.issue_date as date, l.member_id, m.full_name, l.amount, 'Standalone Loan' as notes, l.created_at
            FROM loans l JOIN members m ON l.member_id = m.member_id
            UNION ALL
            SELECT 'Loan Repayment' as tx_type, lr.date, l.member_id, m.full_name, lr.amount, COALESCE(lr.notes, 'Loan Repayment') as notes, lr.created_at
            FROM loan_repayments lr JOIN loans l ON lr.loan_id = l.id JOIN members m ON l.member_id = m.member_id
            ORDER BY date DESC, created_at DESC''')
    other_logs = [dict(r) for r in cursor.fetchall()]

    total_savings = sum(r['amount'] for r in savings_logs)
    total_fees = sum(r['amount'] for r in fee_logs)
    total_withdrawals = sum(r['amount'] for r in other_logs if r['tx_type'] == 'Withdrawal')
    total_loans_issued = sum(r['amount'] for r in other_logs if r['tx_type'] == 'Loan Issued')
    total_repayments = sum(r['amount'] for r in other_logs if r['tx_type'] == 'Loan Repayment')

    total_inflow = total_savings + total_fees + total_repayments
    total_outflow = total_withdrawals + total_loans_issued
    net_cashflow = total_inflow - total_outflow

    return jsonify({
        'savings_logs': savings_logs, 'fee_logs': fee_logs, 'other_logs': other_logs,
        'total_savings': total_savings, 'total_fees': total_fees,
        'total_withdrawals': total_withdrawals, 'total_loans_issued': total_loans_issued,
        'total_repayments': total_repayments,
        'total_inflow': total_inflow, 'total_outflow': total_outflow,
        'net_cashflow': net_cashflow, 'selected_date': selected_date
    })

@app.route('/api/service-fees', methods=['GET'])
def get_service_fees():
    db = get_db()
    cursor = db.cursor()
    p = query_param()
    selected_month = request.args.get('month', '').strip()
    if selected_month:
        cursor.execute(f'''SELECT f.*, m.full_name FROM service_fees f JOIN members m ON f.member_id = m.member_id WHERE f.month_year = {p} ORDER BY f.date DESC, f.id DESC''', (selected_month,))
    else:
        cursor.execute('''SELECT f.*, m.full_name FROM service_fees f JOIN members m ON f.member_id = m.member_id ORDER BY f.date DESC, f.id DESC''')
    rows = cursor.fetchall()
    fees = [dict(r) for r in rows]
    total_fees = sum(f['amount'] for f in fees)
    return jsonify({'fees': fees, 'total_fees': total_fees, 'selected_month': selected_month})

@app.route('/api/archives', methods=['GET'])
def get_past_records():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM transaction_archives ORDER BY date DESC, id DESC')
    rows = cursor.fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/archives/reset', methods=['POST'])
def reset_archives():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('DELETE FROM transaction_archives')
    db.commit()
    return jsonify({'success': True, 'message': 'All past transaction archives have been wiped (records AND totals). Active ledgers and member profiles are unaffected.'})

@app.route('/api/maintenance/resync', methods=['POST'])
def resync_ledger():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE loans SET status = 'cleared' WHERE amount_paid >= repayment_amount AND status = 'active'")
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

@app.route('/api/maintenance/factory-reset', methods=['POST'])
def factory_reset():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('DELETE FROM savings')
    cursor.execute('DELETE FROM withdrawals')
    cursor.execute('DELETE FROM loans')
    cursor.execute('DELETE FROM loan_repayments')
    cursor.execute('DELETE FROM service_fees')
    cursor.execute('DELETE FROM transaction_archives')
    cursor.execute('UPDATE members SET current_cycle = 1, cycle_days = 0')
    db.commit()
    return jsonify({'success': True, 'message': 'FULL FACTORY RESET complete! All ledgers and archives wiped. Member profiles preserved.'})

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

@app.route('/')
def index():
    return render_template_string(INDEX_TEMPLATE)

INDEX_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <title>Savers Growth System</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --bg-body: #f8fafc; --card-bg: #ffffff; --text-dark: #0f172a; --text-muted: #64748b;
            --primary-green: #10b981; --primary-green-dark: #059669; --primary-red: #ef4444;
            --amber-fee: #d97706; --purple-cycle: #9333ea; --purple-bg: #fae8ff;
            --purple-border: #e9d5ff; --border-light: #cbd5e1; --radius-card: 16px;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; -webkit-tap-highlight-color: transparent; }
        body { background-color: var(--bg-body); color: var(--text-dark); display: flex; flex-direction: column; min-height: 100vh; padding-top: calc(112px + env(safe-area-inset-top)); }
        .sticky-header-container { position: fixed; top: 0; left: 0; right: 0; z-index: 1000; background: #ffffff; border-bottom: 1.5px solid var(--border-light); box-shadow: 0 2px 10px rgba(0,0,0,0.04); padding-top: env(safe-area-inset-top); }
        header { padding: 0.75rem 1rem 0.25rem 1rem; display: flex; justify-content: space-between; align-items: center; }
        header .brand-box { display: flex; align-items: center; gap: 10px; cursor: pointer; }
        header .sprout-icon { background: var(--primary-green); color: #ffffff; width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 1.1rem; }
        header .brand-title { font-size: 1.25rem; font-weight: 800; color: var(--text-dark); letter-spacing: -0.3px; }
        .header-controls { display: flex; align-items: center; gap: 10px; }
        .member-count-badge { background: #f1f5f9; border: 1.5px solid var(--border-light); padding: 5px 10px; border-radius: 20px; font-weight: 800; font-size: 0.78rem; color: var(--primary-green-dark); display: flex; align-items: center; gap: 5px; }
        header .btn-logout { background: #ffffff; color: var(--text-dark); border: 1.5px solid var(--text-dark); padding: 6px 14px; border-radius: 20px; font-weight: 700; font-size: 0.82rem; cursor: pointer; min-height: 38px; touch-action: manipulation; }
        .sticky-nav-bar { padding: 0.25rem 1rem 0.6rem 1rem; max-width: 600px; margin: 0 auto; width: 100%; position: relative; display: flex; align-items: center; gap: 8px; }
        .btn-back-sticky { background: #0f172a; color: #ffffff; border: none; padding: 9px 14px; border-radius: 20px; font-weight: 800; font-size: 0.82rem; cursor: pointer; display: none; align-items: center; gap: 6px; white-space: nowrap; flex-shrink: 0; box-shadow: 0 2px 6px rgba(0,0,0,0.12); touch-action: manipulation; }
        .search-wrapper { position: relative; width: 100%; flex: 1; }
        .search-wrapper i { position: absolute; left: 16px; top: 50%; transform: translateY(-50%); color: #94a3b8; font-size: 0.95rem; }
        .search-input { width: 100%; padding: 10px 16px 10px 42px; border-radius: 30px; border: 1.5px solid var(--border-light); font-size: 16px !important; outline: none; background: #ffffff; appearance: none; -webkit-appearance: none; }
        .search-results-dropdown { position: absolute; top: 100%; left: 0; right: 0; background: #ffffff; border: 1.5px solid var(--border-light); border-radius: 16px; box-shadow: 0 12px 25px rgba(0,0,0,0.15); z-index: 2500; max-height: 260px; overflow-y: auto; display: none; margin-top: 6px; -webkit-overflow-scrolling: touch; }
        .search-result-item { padding: 12px 16px; border-bottom: 1px solid var(--border-light); cursor: pointer; display: flex; justify-content: space-between; align-items: center; font-size: 0.88rem; font-weight: 600; }
        .search-result-item:hover, .search-result-item:active { background: #f1f5f9; }
        .member-picker-container { position: relative; width: 100%; }
        .member-picker-dropdown { position: absolute; top: 100%; left: 0; right: 0; background: #ffffff; border: 1.5px solid var(--border-light); border-radius: 14px; box-shadow: 0 10px 25px rgba(0,0,0,0.12); z-index: 2200; max-height: 220px; overflow-y: auto; display: none; margin-top: 4px; -webkit-overflow-scrolling: touch; }
        .member-picker-item { padding: 10px 14px; border-bottom: 1px solid var(--border-light); cursor: pointer; display: flex; justify-content: space-between; align-items: center; font-size: 0.88rem; font-weight: 600; }
        .member-picker-item:hover, .member-picker-item:active { background: #f1f5f9; }
        .member-picker-item:last-child { border-bottom: none; }
        .selected-member-badge { background: #d1fae5; border: 1.5px solid #a7f3d0; color: #065f46; padding: 10px 14px; border-radius: 12px; font-weight: 700; font-size: 0.9rem; display: flex; justify-content: space-between; align-items: center; margin-top: 6px; }
        .selected-member-badge .btn-change-member { background: #ef4444; color: white; border: none; padding: 4px 10px; border-radius: 8px; font-size: 0.75rem; cursor: pointer; font-weight: 800; touch-action: manipulation; }
        .member-preview-card { background: #f0fdf4; border: 1.5px solid #bbf7d0; border-radius: 12px; padding: 12px; margin-top: 10px; animation: fadeIn 0.2s ease-in; }
        .preview-title { font-weight: 800; font-size: 0.92rem; color: var(--text-dark); margin-bottom: 10px; display: flex; align-items: center; gap: 6px; }
        .preview-title small { color: var(--text-muted); font-weight: 700; font-size: 0.75rem; }
        .preview-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
        .preview-item { background: #ffffff; border: 1px solid #d1fae5; border-radius: 8px; padding: 8px 10px; }
        .preview-label { font-size: 0.65rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: 2px; letter-spacing: 0.3px; }
        .preview-value { font-size: 0.88rem; font-weight: 800; color: var(--text-dark); }
        .preview-value.green { color: var(--primary-green-dark); }
        .preview-value.purple { color: var(--purple-cycle); }
        .preview-value.amber { color: var(--amber-fee); }
        .app-container { max-width: 600px; margin: 0 auto; width: 100%; padding: 1rem 1rem 2rem 1rem; flex: 1; }
        .view-section { display: none; }
        .view-section.active { display: block; animation: fadeIn 0.15s ease-in forwards; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(3px); } to { opacity: 1; transform: translateY(0); } }
        .view-header-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.1rem; }
        .view-title-group { display: flex; align-items: center; gap: 8px; font-size: 1.15rem; font-weight: 800; }
        .btn-add-header { background: var(--primary-green); color: #ffffff; border: none; padding: 8px 14px; border-radius: 10px; font-weight: 700; font-size: 0.82rem; cursor: pointer; display: flex; align-items: center; gap: 6px; touch-action: manipulation; }
        .login-card { background: #ffffff; border: 1.5px solid var(--border-light); border-radius: 20px; padding: 1.75rem 1.25rem; max-width: 420px; margin: 1rem auto; box-shadow: 0 4px 12px rgba(0,0,0,0.03); }
        .login-header { text-align: center; margin-bottom: 1.5rem; }
        .login-header .sprout-big { background: var(--primary-green); color: #fff; width: 56px; height: 56px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 1.8rem; margin-bottom: 10px; }
        .grid-3-col { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 0.4rem; }
        .menu-card { background: var(--card-bg); border: 1.5px solid var(--border-light); border-radius: var(--radius-card); padding: 0.85rem 0.3rem; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; cursor: pointer; box-shadow: 0 2px 4px rgba(0,0,0,0.02); transition: transform 0.1s; min-height: 92px; touch-action: manipulation; }
        .menu-card:active { transform: scale(0.96); }
        .menu-card .icon-badge { width: 38px; height: 38px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 1.1rem; margin-bottom: 4px; }
        .icon-badge.pink { background: #ffe4e6; }
        .icon-badge.mint { background: #d1fae5; }
        .icon-badge.blue { background: #e0f2fe; }
        .icon-badge.yellow { background: #fef3c7; }
        .icon-badge.purple { background: #f3e8ff; }
        .icon-badge.teal { background: #ccfbf1; }
        .menu-card .card-heading { font-size: 0.78rem; font-weight: 800; color: var(--text-dark); line-height: 1.15; }
        .grid-row-4-center { display: flex; justify-content: center; gap: 10px; margin-top: 10px; flex-wrap: wrap; }
        .grid-row-4-center .menu-card { width: calc(33.333% - 7px); }
        .overview-box { background: #f0fdf4; border: 1.5px solid #bbf7d0; border-radius: 16px; padding: 1.25rem; margin-bottom: 1.25rem; display: flex; flex-direction: column; gap: 10px; }
        .overview-row { display: flex; justify-content: space-between; align-items: center; font-size: 0.9rem; font-weight: 600; }
        .overview-row .amount-saved { font-size: 1.1rem; font-weight: 800; color: var(--primary-green-dark); }
        .overview-row .amount-fees { font-size: 1.1rem; font-weight: 800; color: var(--amber-fee); }
        .overview-row .amount-net { font-size: 1.2rem; font-weight: 800; color: var(--primary-green-dark); }
        .overview-row .amount-loan { font-size: 1.05rem; font-weight: 800; color: var(--primary-red); }
        .overview-divider { height: 1px; background: #cbd5e1; margin: 2px 0; }
        .action-stack { display: flex; flex-direction: column; gap: 0.75rem; }
        .btn-action-primary { background: var(--primary-red); color: white; border: none; padding: 14px; border-radius: 12px; font-weight: 800; font-size: 0.95rem; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 48px; touch-action: manipulation; }
        .btn-action-secondary { background: #e2e8f0; color: var(--text-dark); border: none; padding: 14px; border-radius: 12px; font-weight: 800; font-size: 0.95rem; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 48px; touch-action: manipulation; }
        .filter-row { display: flex; gap: 8px; margin-bottom: 1rem; flex-wrap: wrap; }
        .filter-row input, .filter-row select { flex: 1; padding: 11px 14px; border-radius: 12px; border: 1.5px solid var(--border-light); font-size: 16px !important; background: #fff; outline: none; min-width: 120px; }
        .member-grid-2col { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        .member-card-item { background: #ffffff; border: 1.5px solid var(--border-light); border-radius: 14px; padding: 0.75rem; cursor: pointer; box-shadow: 0 2px 4px rgba(0,0,0,0.01); display: flex; flex-direction: column; justify-content: space-between; touch-action: manipulation; }
        .member-card-item:active { background: #f8fafc; transform: scale(0.98); }
        .member-card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
        .member-avatar { width: 32px; height: 32px; border-radius: 50%; background: #d1fae5; color: #059669; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 0.95rem; flex-shrink: 0; }
        .member-info .name { font-size: 0.85rem; font-weight: 800; color: var(--text-dark); line-height: 1.2; word-break: break-word; }
        .member-info .code { font-size: 0.72rem; color: #94a3b8; font-weight: 700; }
        .member-stats-box { background: #f8fafc; border-radius: 8px; padding: 6px 8px; display: flex; flex-direction: column; gap: 2px; font-size: 0.75rem; margin-bottom: 6px; }
        .stat-line { font-weight: 600; color: var(--text-dark); display: flex; justify-content: space-between; }
        .stat-line .val-green { color: var(--primary-green-dark); font-weight: 800; }
        .cycle-status-btn { background: var(--purple-bg); border: 1px solid var(--purple-border); color: var(--purple-cycle); padding: 5px; border-radius: 8px; text-align: center; font-weight: 700; font-size: 0.72rem; display: flex; align-items: center; justify-content: center; gap: 4px; }
        .modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(3px); z-index: 3000; display: none; align-items: flex-end; justify-content: center; }
        @media (min-width: 600px) { .modal-overlay { align-items: center; padding: 1rem; } }
        .modal-overlay.active { display: flex; }
        .modal-card { background: #ffffff; border-radius: 24px 24px 0 0; width: 100%; max-width: 520px; max-height: 88vh; overflow-y: auto; padding: 1.25rem; box-shadow: 0 -10px 25px rgba(0,0,0,0.15); animation: slideModal 0.2s cubic-bezier(0.16, 1, 0.3, 1) forwards; -webkit-overflow-scrolling: touch; }
        @media (min-width: 600px) { .modal-card { border-radius: 20px; animation: modalFade 0.2s forwards; } }
        @keyframes slideModal { from { transform: translateY(100%); } to { transform: translateY(0); } }
        @keyframes modalFade { from { transform: scale(0.95); opacity: 0; } to { transform: scale(1); opacity: 1; } }
        .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.85rem; }
        .modal-title { font-size: 1.15rem; font-weight: 800; color: var(--text-dark); }
        .modal-close { background: #f1f5f9; border: none; font-size: 1.2rem; width: 32px; height: 32px; border-radius: 50%; color: var(--text-muted); cursor: pointer; display: flex; align-items: center; justify-content: center; }
        .modal-nav-tabs { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 6px; margin-bottom: 1rem; border-bottom: 1.5px solid var(--border-light); -webkit-overflow-scrolling: touch; }
        .modal-tab { padding: 8px 12px; border-radius: 20px; font-size: 0.78rem; font-weight: 700; border: 1.5px solid var(--border-light); cursor: pointer; white-space: nowrap; color: var(--text-muted); background: #ffffff; touch-action: manipulation; }
        .modal-tab.active { background: #f0fdf4; border-color: #bbf7d0; color: var(--primary-green-dark); }
        .modal-tab-panel { display: none; }
        .modal-tab-panel.active { display: block; }
        .modal-details-list { display: flex; flex-direction: column; gap: 10px; font-size: 0.88rem; margin-bottom: 1rem; }
        .modal-detail-item { display: flex; justify-content: space-between; font-weight: 600; padding: 6px 0; border-bottom: 1px dashed var(--border-light); }
        .modal-detail-item:last-child { border-bottom: none; }
        .modal-cycle-box { background: var(--purple-bg); border: 1.5px solid var(--purple-border); border-radius: 12px; padding: 10px 12px; margin-bottom: 1rem; text-align: center; }
        .modal-cycle-box .lbl { font-size: 0.72rem; font-weight: 800; color: var(--purple-cycle); text-transform: uppercase; margin-bottom: 2px; }
        .modal-cycle-box .val { font-weight: 800; color: var(--purple-cycle); font-size: 0.95rem; }
        .card-form { background: #fff; border: 1.5px solid var(--border-light); border-radius: 16px; padding: 1.1rem; }
        .form-group { display: flex; flex-direction: column; gap: 5px; margin-bottom: 0.85rem; }
        .form-group label { font-size: 0.82rem; font-weight: 700; color: var(--text-dark); }
        .form-control { padding: 11px 12px; border-radius: 10px; border: 1.5px solid var(--border-light); font-size: 16px !important; outline: none; background: #fff; width: 100%; min-height: 46px; appearance: none; -webkit-appearance: none; }
        .btn-submit { background: var(--primary-green); color: white; border: none; padding: 12px; border-radius: 10px; font-weight: 700; font-size: 0.95rem; cursor: pointer; width: 100%; min-height: 48px; touch-action: manipulation; }
        .table-responsive { overflow-x: auto; border-radius: 12px; border: 1.5px solid var(--border-light); -webkit-overflow-scrolling: touch; }
        table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.82rem; white-space: nowrap; }
        th, td { padding: 10px 12px; border-bottom: 1px solid var(--border-light); }
        th { background: #f8fafc; font-weight: 700; color: var(--text-muted); text-transform: uppercase; font-size: 0.68rem; }
        .badge { padding: 3px 6px; border-radius: 6px; font-size: 0.7rem; font-weight: 800; display: inline-block; }
        .badge-savings { background: #d1fae5; color: #065f46; }
        .badge-fee { background: #fef3c7; color: #92400e; }
        .badge-payout { background: #fee2e2; color: #991b1b; }
        .badge-success { background: #d1fae5; color: #065f46; }
        .btn-repay-sm { background: var(--primary-green-dark); color: white; border: none; padding: 6px 12px; border-radius: 6px; font-size: 0.75rem; font-weight: 700; cursor: pointer; touch-action: manipulation; }
        .btn-edit-sm { background: #2563eb; color: white; border: none; padding: 6px 12px; border-radius: 6px; font-size: 0.75rem; font-weight: 700; cursor: pointer; touch-action: manipulation; }
        .tracker-section-header { display: flex; justify-content: space-between; align-items: center; margin: 1rem 0 6px 0; }
        .tracker-section-title { font-weight: 800; font-size: 0.92rem; display: flex; align-items: center; gap: 6px; }
        .tracker-section-total { font-weight: 800; font-size: 0.92rem; }
        .msg-modal-card { background: #ffffff; border-radius: 20px; width: 100%; max-width: 420px; padding: 1.5rem 1.25rem; box-shadow: 0 20px 40px rgba(0,0,0,0.2); animation: modalFade 0.2s forwards; margin: 1rem; }
        .msg-icon-wrap { width: 56px; height: 56px; border-radius: 50%; margin: 0 auto 12px auto; display: flex; align-items: center; justify-content: center; font-size: 1.6rem; }
        .msg-icon-wrap.success { background: #d1fae5; color: var(--primary-green-dark); }
        .msg-icon-wrap.error { background: #fee2e2; color: var(--primary-red); }
        .msg-icon-wrap.info { background: #e0f2fe; color: #2563eb; }
        .msg-title { text-align: center; font-size: 1.15rem; font-weight: 800; margin-bottom: 12px; color: var(--text-dark); }
        .msg-body { font-size: 0.9rem; line-height: 1.6; color: var(--text-dark); margin-bottom: 1.25rem; text-align: left; }
        .msg-actions { display: flex; gap: 8px; }
        .msg-actions button { flex: 1; padding: 12px; border-radius: 10px; font-weight: 800; font-size: 0.92rem; cursor: pointer; border: none; min-height: 46px; touch-action: manipulation; }
        .msg-actions .btn-ok { background: var(--primary-green); color: white; }
        .msg-actions .btn-ok.error-btn { background: var(--primary-red); }
        .msg-actions .btn-cancel { background: #e2e8f0; color: var(--text-dark); }
        footer { background: #ffffff; color: var(--text-dark); text-align: center; padding: 1.25rem 1rem; font-size: 0.85rem; font-weight: 700; border-top: 1.5px solid var(--border-light); margin-top: auto; line-height: 1.4; }
    </style>
</head>
<body>

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
                       placeholder="Search name or digit (e.g. 01, 12, SVR)..." 
                       autocomplete="off" oninput="handleGlobalSearchInput(event)">
            </div>
            <div class="search-results-dropdown" id="search-results-dropdown"></div>
        </div>
    </div>

    <div class="app-container">

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
                        <input type="text" class="form-control" id="login-username" placeholder="Enter username or Member ID" required autocomplete="username">
                    </div>
                    <div class="form-group">
                        <label>Password</label>
                        <input type="password" class="form-control" id="login-password" placeholder="Enter password" required autocomplete="current-password">
                    </div>
                    <button type="submit" class="btn-submit" style="margin-top: 8px;">Login to System</button>
                </form>
            </div>
        </div>

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

        <div id="view-member-portal" class="view-section">
            <div style="background: #ffffff; border: 1.5px solid var(--border-light); border-radius: 20px; padding: 1.25rem;">
                <div style="font-size: 1.2rem; font-weight: 800; color: var(--text-dark);" id="mportal-name">Welcome Member</div>
                <div style="font-size: 0.85rem; color: var(--text-muted);" id="mportal-id">ID: SVR0000</div>
                <div class="overview-box" style="margin-top: 1rem; margin-bottom: 1rem;">
                    <div class="overview-row"><span>Gross Total Saved:</span><span class="amount-saved" id="mportal-gross-saved">₦0.00</span></div>
                    <div class="overview-row"><span>Net Wallet Balance:</span><span class="amount-net" id="mportal-balance">₦0.00</span></div>
                    <div class="overview-row"><span>Daily Target:</span><span id="mportal-target" style="font-weight: 800;">₦0.00</span></div>
                    <div class="overview-row"><span>Service Fees Paid:</span><span id="mportal-fees" style="font-weight: 800; color: var(--amber-fee);">₦0.00</span></div>
                    <div class="overview-divider"></div>
                    <div class="overview-row"><span>Active Loan (Standalone):</span><span style="color: var(--primary-red); font-weight: 800;" id="mportal-loan">₦0.00</span></div>
                </div>
                <div style="font-size: 0.95rem; font-weight: 800; margin-bottom: 8px;">My Savings Contributions</div>
                <div class="table-responsive">
                    <table>
                        <thead><tr><th>DATE</th><th>AMOUNT</th><th>DAYS</th></tr></thead>
                        <tbody id="mportal-savings-table"></tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- WALLET OVERVIEW — WITH LOANS ADDED -->
        <div id="view-overview" class="view-section">
            <div class="view-header-row"><div class="view-title-group">👛 Wallet Overview</div></div>
            <div class="overview-box">
                <div class="overview-row"><span>Gross Total Money Saved:</span><span class="amount-saved" id="stat-total-saved">₦0.00</span></div>
                <div class="overview-row"><span>Total Service Fees Deducted:</span><span class="amount-fees" id="stat-service-fees">₦0.00</span></div>
                <div class="overview-divider"></div>
                <div class="overview-row"><span>Net Wallet Balance:</span><span class="amount-net" id="stat-net-balance">₦0.00</span></div>
                <div class="overview-divider"></div>
                <div class="overview-row"><span>Total Loans Issued:</span><span class="amount-loan" id="stat-loans-issued">₦0.00</span></div>
                <div class="overview-row"><span>Total Loans Outstanding:</span><span class="amount-loan" id="stat-loans-outstanding">₦0.00</span></div>
            </div>
            <div class="action-stack">
                <button class="btn-action-primary" onclick="showSection('withdrawal')"><i class="fa-solid fa-cash-register"></i> Proceed to Withdrawal</button>
                <button class="btn-action-secondary" onclick="showSection('savings')"><i class="fa-solid fa-plus"></i> Record Contribution</button>
            </div>
        </div>

        <div id="view-savings" class="view-section">
            <div class="view-header-row"><div class="view-title-group">➕ Record Contribution</div></div>
            <div class="card-form">
                <form onsubmit="handleSavingsSubmit(event)">
                    <div class="form-group">
                        <label>Search Member (Type 2 digits e.g. 01, 12 or Name)</label>
                        <div class="member-picker-container">
                            <input type="text" class="form-control" id="savings-member-input" placeholder="Type digit (e.g. 01) or name..." autocomplete="off"
                                   oninput="handlePickerSearch('savings-member-input', 'savings-member-id', 'savings-picker-dropdown', 'savings-badge', 'savings-preview')">
                            <input type="hidden" id="savings-member-id" required>
                            <div class="member-picker-dropdown" id="savings-picker-dropdown"></div>
                        </div>
                        <div class="selected-member-badge" id="savings-badge" style="display:none;"></div>
                        <div class="member-preview-card" id="savings-preview" style="display:none;"></div>
                    </div>
                    <div class="form-group"><label>Deposit Amount (₦)</label><input type="number" class="form-control" id="savings-amount" placeholder="e.g. 5000" required></div>
                    <div class="form-group"><label>Deposit Date</label><input type="date" class="form-control" id="savings-date" required></div>
                    <div class="form-group"><label>Notes (Optional)</label><input type="text" class="form-control" id="savings-notes" placeholder="e.g. Cash payment"></div>
                    <button type="submit" class="btn-submit">Record Deposit</button>
                </form>
            </div>
        </div>

        <div id="view-withdrawal" class="view-section">
            <div class="view-header-row"><div class="view-title-group">💸 Process Withdrawal</div></div>
            <div class="card-form">
                <form onsubmit="handleWithdrawalSubmit(event)">
                    <div class="form-group">
                        <label>Search Member (Type 2 digits e.g. 01, 12 or Name)</label>
                        <div class="member-picker-container">
                            <input type="text" class="form-control" id="withdraw-member-input" placeholder="Type digit (e.g. 01) or name..." autocomplete="off"
                                   oninput="handlePickerSearch('withdraw-member-input', 'withdraw-member-id', 'withdraw-picker-dropdown', 'withdraw-badge', 'withdraw-preview')">
                            <input type="hidden" id="withdraw-member-id" required>
                            <div class="member-picker-dropdown" id="withdraw-picker-dropdown"></div>
                        </div>
                        <div class="selected-member-badge" id="withdraw-badge" style="display:none;"></div>
                        <div class="member-preview-card" id="withdraw-preview" style="display:none;"></div>
                    </div>
                    <div class="form-group"><label>Withdrawal Amount (₦)</label><input type="number" class="form-control" id="withdraw-amount" placeholder="e.g. 10000" required></div>
                    <div class="form-group"><label>Withdrawal Date</label><input type="date" class="form-control" id="withdraw-date" required></div>
                    <button type="submit" class="btn-submit" style="background: var(--primary-red);">Process Withdrawal</button>
                </form>
            </div>
        </div>

        <!-- LOAN MANAGEMENT — FORM REMOVED, SUMMARY ADDED -->
        <div id="view-loans" class="view-section">
            <div class="view-header-row"><div class="view-title-group">💳 Standalone Loan Management</div></div>
            <p style="font-size:0.8rem; color:var(--text-muted); margin-bottom:12px;">* Issue new loans from a member's profile (search or click a member card). Loans do not restrict or alter savings wallet balance.</p>

            <div class="overview-box" style="margin-bottom: 1rem; background: #fef3c7; border-color: #fde68a;">
                <div class="overview-row"><span>Total Loans Issued:</span><span id="loan-total-issued" style="font-weight:800; color:var(--primary-red); font-size:1.05rem;">₦0.00</span></div>
                <div class="overview-row"><span>Total Loans Outstanding:</span><span id="loan-total-outstanding" style="font-weight:800; color:var(--primary-red); font-size:1.05rem;">₦0.00</span></div>
                <div class="overview-row"><span>Total Loans Cleared:</span><span id="loan-total-cleared" style="font-weight:800; color:var(--primary-green-dark); font-size:1.05rem;">₦0.00</span></div>
            </div>

            <div style="font-weight:800; font-size:0.95rem; margin-bottom:8px;">All Loan Records</div>
            <div class="table-responsive">
                <table>
                    <thead><tr><th>MEMBER</th><th>LOAN</th><th>PAID</th><th>STATUS</th><th>ACTION</th></tr></thead>
                    <tbody id="loans-table-body"></tbody>
                </table>
            </div>
        </div>

        <div id="view-tracker" class="view-section">
            <div class="view-header-row"><div class="view-title-group">📊 Daily Financial Ledger</div></div>
            <div class="filter-row">
                <input type="date" id="tracker-date-filter">
                <button class="btn-submit" style="width: auto; padding: 0 16px; flex: 0 0 auto;" onclick="loadDailyTracker()">Filter</button>
                <button class="btn-submit" style="width: auto; padding: 0 16px; flex: 0 0 auto; background:#64748b;" onclick="showAllTracker()">Show All</button>
            </div>
            <div class="overview-box" style="margin-bottom: 1rem;">
                <div class="overview-row"><span>Total Inflow:</span><span class="amount-saved" id="tracker-total-inflow">₦0.00</span></div>
                <div class="overview-row"><span>Total Outflow:</span><span style="color:var(--primary-red); font-weight:800;" id="tracker-total-outflow">₦0.00</span></div>
                <div class="overview-divider"></div>
                <div class="overview-row"><span>Net Cashflow:</span><span class="amount-net" id="tracker-net-cashflow">₦0.00</span></div>
            </div>

            <div class="tracker-section-header">
                <div class="tracker-section-title" style="color: var(--primary-green-dark);">💰 Savings Deposits</div>
                <div class="tracker-section-total" style="color: var(--primary-green-dark);" id="tracker-savings-total">₦0.00</div>
            </div>
            <div class="table-responsive" style="margin-bottom: 1.25rem;">
                <table>
                    <thead><tr><th>DATE</th><th>MEMBER</th><th>AMOUNT</th><th>DAYS</th><th>NOTES</th></tr></thead>
                    <tbody id="tracker-savings-body"></tbody>
                </table>
            </div>

            <div class="tracker-section-header">
                <div class="tracker-section-title" style="color: var(--amber-fee);">🏢 Service Fees</div>
                <div class="tracker-section-total" style="color: var(--amber-fee);" id="tracker-fees-total">₦0.00</div>
            </div>
            <div class="table-responsive" style="margin-bottom: 1.25rem;">
                <table>
                    <thead><tr><th>DATE</th><th>MEMBER</th><th>AMOUNT</th><th>DESCRIPTION</th></tr></thead>
                    <tbody id="tracker-fees-body"></tbody>
                </table>
            </div>

            <div class="tracker-section-header">
                <div class="tracker-section-title">📋 Other Transactions</div>
            </div>
            <div class="table-responsive">
                <table>
                    <thead><tr><th>DATE</th><th>MEMBER</th><th>TYPE</th><th>AMOUNT</th><th>NOTES</th></tr></thead>
                    <tbody id="tracker-other-body"></tbody>
                </table>
            </div>
        </div>

        <div id="view-service-fees" class="view-section">
            <div class="view-header-row"><div class="view-title-group">🏢 Monthly Service Fees</div></div>
            <div class="filter-row">
                <input type="month" id="fee-month-filter" onchange="loadMonthlyFees()">
                <button class="btn-submit" style="width: auto; padding: 0 16px;" onclick="loadMonthlyFees()">Filter</button>
            </div>
            <div class="overview-box" style="margin-bottom:1rem;">
                <div class="overview-row"><span>Total Fees Collected:</span><span class="amount-fees" id="fee-total-amount">₦0.00</span></div>
            </div>
            <div class="table-responsive">
                <table>
                    <thead><tr><th>DATE</th><th>MEMBER</th><th>AMOUNT</th><th>DESC</th></tr></thead>
                    <tbody id="service-fees-table-body"></tbody>
                </table>
            </div>
        </div>

        <div id="view-members" class="view-section">
            <div class="view-header-row">
                <div class="view-title-group">👥 Members Directory</div>
                <button class="btn-add-header" onclick="showSection('register')"><i class="fa-solid fa-user-plus"></i> Add</button>
            </div>
            <div class="filter-row">
                <input type="text" id="member-search-dir" placeholder="Search name or digit (e.g. 01, 12)..." onkeyup="filterDirectoryCards()" autocomplete="off">
            </div>
            <div id="members-cards-container" class="member-grid-2col"></div>
            <div style="margin-top: 1.5rem; text-align: center;">
                <button class="btn-submit" style="background: var(--primary-green-dark);" onclick="showSection('register')"><i class="fa-solid fa-user-plus"></i> Register New Member</button>
            </div>
        </div>

        <div id="view-register" class="view-section">
            <div class="view-header-row"><div class="view-title-group">🆔 Register New Member</div></div>
            <div class="card-form">
                <form onsubmit="handleRegisterSubmit(event)">
                    <div class="form-group"><label>Full Name</label><input type="text" class="form-control" id="reg-fullname" placeholder="John Doe" required autocomplete="name"></div>
                    <div class="form-group"><label>Daily Target Amount (₦)</label><input type="number" class="form-control" id="reg-target" placeholder="500" value="500"></div>
                    <button type="submit" class="btn-submit">Register Member</button>
                </form>
            </div>
        </div>

        <div id="view-manage-members" class="view-section">
            <div class="view-header-row"><div class="view-title-group">⚙️ Manage Member Profiles</div></div>
            <div class="overview-box" style="margin-bottom: 1rem; background: #e0f2fe; border-color: #bae6fd;">
                <div class="overview-row"><span>Total Active Members:</span><span id="manage-total-count" style="font-weight:800;">0</span></div>
                <div class="overview-row"><span>Sum of Daily Targets:</span><span id="manage-target-sum" style="font-weight:800; color:var(--primary-green-dark); font-size:1.15rem;">₦0.00</span></div>
            </div>
            <div class="table-responsive">
                <table>
                    <thead><tr><th>MEMBER ID</th><th>FULL NAME</th><th>USERNAME</th><th>DAILY TARGET</th><th>ACTION</th></tr></thead>
                    <tbody id="manage-members-table-body"></tbody>
                </table>
            </div>
        </div>

        <div id="view-member-history" class="view-section">
            <div class="view-header-row"><div class="view-title-group">🔎 Member Search History</div></div>
            <div class="form-group">
                <label>Search Member (Type 2 digits e.g. 01, 12 or Name)</label>
                <div class="member-picker-container">
                    <input type="text" class="form-control" id="history-member-input" placeholder="Type digit (e.g. 01) or name..." autocomplete="off"
                           oninput="handlePickerSearch('history-member-input', 'history-member-id', 'history-picker-dropdown', 'history-badge', '', loadMemberHistoryView)">
                    <input type="hidden" id="history-member-id">
                    <div class="member-picker-dropdown" id="history-picker-dropdown"></div>
                </div>
                <div class="selected-member-badge" id="history-badge" style="display:none;"></div>
            </div>
            <div class="table-responsive" style="margin-top: 1rem;">
                <table>
                    <thead><tr><th>DATE</th><th>TYPE</th><th>AMOUNT</th><th>NOTES</th></tr></thead>
                    <tbody id="member-history-table-body"></tbody>
                </table>
            </div>
        </div>

        <div id="view-past-records" class="view-section">
            <div class="view-header-row"><div class="view-title-group">📦 Past Transaction Archives</div></div>

            <div class="overview-box" style="margin-bottom: 1rem; background: #f1f5f9; border-color: #cbd5e1;">
                <div class="overview-row"><span>Total Archived Records:</span><span id="archive-total-count" style="font-weight:800;">0</span></div>
                <div class="overview-row"><span>Total Archived Amount:</span><span id="archive-total-amount" style="font-weight:800; color:var(--primary-green-dark); font-size:1.15rem;">₦0.00</span></div>
            </div>

            <div class="table-responsive" style="margin-bottom: 1rem;">
                <table>
                    <thead><tr><th>DATE</th><th>MEMBER</th><th>TYPE</th><th>AMOUNT</th><th>CYCLE</th></tr></thead>
                    <tbody id="archives-table-body"></tbody>
                </table>
            </div>

            <div class="card-form" style="border-color: #fca5a5;">
                <div style="font-weight:800; color:var(--primary-red); margin-bottom:6px;"><i class="fa-solid fa-eraser"></i> Reset Past Records</div>
                <p style="font-size:0.8rem; color:var(--text-muted); margin-bottom:10px;">Wipes <strong>ALL</strong> archived transactions (records AND totals). Active ledgers (savings, withdrawals, loans, fees) and member profiles are <strong>not</strong> affected. This cannot be undone.</p>
                <button class="btn-submit" style="background:var(--primary-red);" onclick="resetPastRecords()">Reset All Past Records</button>
            </div>
        </div>

        <div id="view-maintenance" class="view-section">
            <div class="view-header-row"><div class="view-title-group">🛠️ System Maintenance</div></div>
            <div class="card-form" style="margin-bottom: 1rem;">
                <div style="font-weight:800; margin-bottom:6px;"><i class="fa-solid fa-rotate"></i> Synchronize System Counters</div>
                <p style="font-size:0.8rem; color:var(--text-muted); margin-bottom:10px;">Re-evaluates loan status and synchronization counters across tables.</p>
                <button class="btn-submit" onclick="triggerMaintenanceResync()">Resync All Ledgers</button>
            </div>
            <div class="card-form" style="margin-bottom: 1rem; border-color: #fca5a5;">
                <div style="font-weight:800; color:var(--primary-red); margin-bottom:6px;"><i class="fa-solid fa-triangle-exclamation"></i> Reset Active Ledgers</div>
                <p style="font-size:0.8rem; color:var(--text-muted); margin-bottom:10px;">Wipes active financial ledger transactions. Member profiles and past archives are preserved.</p>
                <button class="btn-submit" style="background:var(--primary-red);" onclick="triggerMaintenanceFullReset()">Reset Active Ledgers</button>
            </div>
            <div class="card-form" style="border-color: #7f1d1d; background: #fef2f2;">
                <div style="font-weight:800; color: #7f1d1d; margin-bottom:6px;"><i class="fa-solid fa-bomb"></i> Full Factory Reset</div>
                <p style="font-size:0.8rem; color:#991b1b; margin-bottom:10px;">Wipes <strong>ALL</strong> active ledgers <strong>AND</strong> past archives. Member profiles, usernames, passwords, and daily targets are preserved. Every member is reset to Cycle 1 / Day 0. This cannot be undone.</p>
                <button class="btn-submit" style="background:#7f1d1d;" onclick="triggerFactoryReset()">FULL FACTORY RESET</button>
            </div>
        </div>

        <div id="view-password" class="view-section">
            <div class="view-header-row"><div class="view-title-group">🔐 Update Admin Password</div></div>
            <div class="card-form">
                <form onsubmit="handlePasswordUpdateSubmit(event)">
                    <div class="form-group"><label>Current Password</label><input type="password" class="form-control" id="old-pass" required></div>
                    <div class="form-group"><label>New Password</label><input type="password" class="form-control" id="new-pass" required></div>
                    <button type="submit" class="btn-submit">Update Admin Credentials</button>
                </form>
            </div>
        </div>

    </div>

    <div class="modal-overlay" id="dedicated-edit-modal" onclick="if(event.target===this) closeModal('dedicated-edit-modal')">
        <div class="modal-card">
            <div class="modal-header">
                <div>
                    <div class="modal-title" id="ded-edit-title">Edit Member Profile</div>
                    <div style="font-size:0.78rem; color:var(--text-muted); font-weight:700;" id="ded-edit-subid">SVR0000</div>
                </div>
                <button class="modal-close" onclick="closeModal('dedicated-edit-modal')">&times;</button>
            </div>
            <div class="card-form">
                <form onsubmit="handleDedicatedEditSubmit(event)">
                    <input type="hidden" id="ded-edit-id">
                    <div class="form-group"><label>Full Name</label><input type="text" class="form-control" id="ded-edit-fullname" required></div>
                    <div class="form-group"><label>Username</label><input type="text" class="form-control" id="ded-edit-username" required></div>
                    <div class="form-group"><label>Daily Target Amount (₦)</label><input type="number" class="form-control" id="ded-edit-target" required></div>
                    <div class="form-group"><label>New Password (Optional)</label><input type="password" class="form-control" id="ded-edit-password" placeholder="Leave blank to keep current"></div>
                    <button type="submit" class="btn-submit">Save Member Profile</button>
                </form>
            </div>
        </div>
    </div>

    <div class="modal-overlay" id="member-detail-modal" onclick="if(event.target===this) closeModal('member-detail-modal')">
        <div class="modal-card">
            <div class="modal-header">
                <div>
                    <div class="modal-title" id="md-title">Member Profile</div>
                    <div style="font-size:0.78rem; color:var(--text-muted); font-weight:700;" id="md-subid">SVR0000</div>
                </div>
                <button class="modal-close" onclick="closeModal('member-detail-modal')">&times;</button>
            </div>
            <div class="modal-nav-tabs">
                <button class="modal-tab active" onclick="switchModalTab('md-tab-overview', this)">Overview</button>
                <button class="modal-tab" onclick="switchModalTab('md-tab-savings', this)">Record Save</button>
                <button class="modal-tab" onclick="switchModalTab('md-tab-withdraw', this)">Withdrawal</button>
                <button class="modal-tab" onclick="switchModalTab('md-tab-loans', this)">Loans</button>
                <button class="modal-tab" onclick="switchModalTab('md-tab-edit', this)">Settings & Admin</button>
            </div>
            <div class="modal-tab-panel active" id="md-tab-overview">
                <div class="modal-cycle-box">
                    <div class="lbl">Current Cycle Status</div>
                    <div class="val" id="md-cycle-text">🔄 Cycle 1 (0 / 31 days)</div>
                </div>
                <div class="modal-details-list">
                    <div class="modal-detail-item"><span>Gross Total Saved:</span><span class="val-green" id="md-gross-saved">₦0.00</span></div>
                    <div class="modal-detail-item"><span>Net Wallet Balance:</span><span style="font-weight:800; color:var(--primary-green-dark);" id="md-net-balance">₦0.00</span></div>
                    <div class="modal-detail-item"><span>Total Withdrawn:</span><span id="md-total-withdrawn">₦0.00</span></div>
                    <div class="modal-detail-item"><span>Service Fees Paid:</span><span style="color:var(--amber-fee); font-weight:800;" id="md-service-fees">₦0.00</span></div>
                    <div class="modal-detail-item"><span>Active Loan (Standalone):</span><span style="color:var(--primary-red); font-weight:800;" id="md-active-loan">₦0.00</span></div>
                    <div class="modal-detail-item"><span>Daily Target Amount:</span><span style="font-weight:700;" id="md-daily-target">₦0.00</span></div>
                </div>
                <div style="font-size: 0.88rem; font-weight: 800; margin: 10px 0 6px 0;">Recent Savings History</div>
                <div class="table-responsive">
                    <table>
                        <thead><tr><th>DATE</th><th>AMOUNT</th><th>DAYS</th></tr></thead>
                        <tbody id="md-recent-contributions-body"></tbody>
                    </table>
                </div>
            </div>
            <div class="modal-tab-panel" id="md-tab-savings">
                <div class="card-form">
                    <form onsubmit="handleModalSavingsSubmit(event)">
                        <div class="form-group"><label>Deposit Amount (₦)</label><input type="number" class="form-control" id="mmodal-savings-amount" required placeholder="5000"></div>
                        <div class="form-group"><label>Deposit Date</label><input type="date" class="form-control" id="mmodal-savings-date" required></div>
                        <div class="form-group"><label>Notes</label><input type="text" class="form-control" id="mmodal-savings-notes" placeholder="e.g. Deposit via modal"></div>
                        <button type="submit" class="btn-submit">Record Deposit</button>
                    </form>
                </div>
            </div>
            <div class="modal-tab-panel" id="md-tab-withdraw">
                <div class="card-form">
                    <form onsubmit="handleModalWithdrawSubmit(event)">
                        <div class="form-group"><label>Withdrawal Amount (₦)</label><input type="number" class="form-control" id="mmodal-withdraw-amount" required placeholder="10000"></div>
                        <div class="form-group"><label>Date</label><input type="date" class="form-control" id="mmodal-withdraw-date" required></div>
                        <button type="submit" class="btn-submit" style="background:var(--primary-red);">Process Withdrawal</button>
                    </form>
                </div>
            </div>
            <div class="modal-tab-panel" id="md-tab-loans">
                <div class="card-form" style="margin-bottom: 1rem;">
                    <form onsubmit="handleModalLoanIssueSubmit(event)">
                        <div class="form-group"><label>Disburse Loan Amount (₦)</label><input type="number" class="form-control" id="mmodal-loan-amount" required placeholder="20000"></div>
                        <div class="form-group"><label>Date</label><input type="date" class="form-control" id="mmodal-loan-date" required></div>
                        <button type="submit" class="btn-submit">Issue Standalone Loan</button>
                    </form>
                </div>
                <div style="font-weight:800; font-size:0.85rem; margin-bottom:6px;">Active Loan Records</div>
                <div class="table-responsive">
                    <table>
                        <thead><tr><th>LOAN</th><th>PAID</th><th>ACTION</th></tr></thead>
                        <tbody id="md-active-loans-body"></tbody>
                    </table>
                </div>
            </div>
            <div class="modal-tab-panel" id="md-tab-edit">
                <div class="card-form">
                    <form onsubmit="handleMemberEditSubmit(event)">
                        <input type="hidden" id="edit-member-id">
                        <div class="form-group"><label>Full Name</label><input type="text" class="form-control" id="edit-fullname" required></div>
                        <div class="form-group"><label>Username</label><input type="text" class="form-control" id="edit-username" required></div>
                        <div class="form-group"><label>Daily Target (₦)</label><input type="number" class="form-control" id="edit-target" required></div>
                        <div class="form-group"><label>New Password (Optional)</label><input type="password" class="form-control" id="edit-password" placeholder="Leave blank to keep current"></div>
                        <button type="submit" class="btn-submit">Save Profile Changes</button>
                    </form>
                    <div style="margin-top:14px; display:flex; flex-direction:column; gap:8px;">
                        <button class="btn-submit" style="background:#d97706;" onclick="resetMemberTargetFromModal()">Reset Daily Target (₦500 Default)</button>
                        <button class="btn-submit" style="background:#0f172a;" onclick="resetMemberLedgerFromModal()">Reset Financial History (Including Service Fees)</button>
                        <button class="btn-submit" style="background:var(--primary-red);" onclick="deleteMemberFromModal()">Delete Profile Permanently</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="modal-overlay" id="loan-repay-modal" onclick="if(event.target===this) closeModal('loan-repay-modal')">
        <div class="modal-card">
            <div class="modal-header">
                <div class="modal-title">Record Loan Repayment</div>
                <button class="modal-close" onclick="closeModal('loan-repay-modal')">&times;</button>
            </div>
            <div class="card-form">
                <form onsubmit="handleLoanRepaySubmit(event)">
                    <input type="hidden" id="repay-loan-id">
                    <div class="form-group"><label>Repayment Amount (₦)</label><input type="number" class="form-control" id="repay-amount" required></div>
                    <div class="form-group"><label>Repayment Date</label><input type="date" class="form-control" id="repay-date" required></div>
                    <button type="submit" class="btn-submit">Submit Repayment</button>
                </form>
            </div>
        </div>
    </div>

    <div class="modal-overlay" id="msg-modal">
        <div class="msg-modal-card">
            <div class="msg-icon-wrap info" id="msg-icon"><i class="fa-solid fa-circle-info"></i></div>
            <div class="msg-title" id="msg-title">Notice</div>
            <div class="msg-body" id="msg-body"></div>
            <div class="msg-actions">
                <button class="btn-cancel" id="msg-cancel-btn" style="display:none;" onclick="closeModal('msg-modal')">Cancel</button>
                <button class="btn-ok" id="msg-ok-btn" onclick="msgModalConfirm()">OK</button>
            </div>
        </div>
    </div>

    <footer>
        Savers Growth System &copy; 2026<br>
        <span style="font-size:0.75rem; color:var(--text-muted);">Cycle: 1 Fee Day + 30 Savings Days = 31 Total</span>
    </footer>

    <script>
        let currentUser = null;
        let membersList = [];
        let currentModalMemberId = null;
        let msgModalCallback = null;

        function showMessage(msg, type = 'info', title = null) {
            msgModalCallback = null;
            const iconWrap = document.getElementById('msg-icon');
            iconWrap.className = 'msg-icon-wrap ' + (type === 'error' ? 'error' : type === 'success' ? 'success' : 'info');
            iconWrap.innerHTML = `<i class="fa-solid fa-${type === 'error' ? 'circle-exclamation' : type === 'success' ? 'circle-check' : 'circle-info'}"></i>`;
            const titleEl = document.getElementById('msg-title');
            titleEl.innerText = title || (type === 'error' ? 'Error' : type === 'success' ? 'Success' : 'Notice');
            titleEl.style.color = type === 'error' ? 'var(--primary-red)' : type === 'success' ? 'var(--primary-green-dark)' : 'var(--text-dark)';
            document.getElementById('msg-body').innerHTML = msg;
            document.getElementById('msg-cancel-btn').style.display = 'none';
            const okBtn = document.getElementById('msg-ok-btn');
            okBtn.innerText = 'OK';
            okBtn.className = 'btn-ok' + (type === 'error' ? ' error-btn' : '');
            document.getElementById('msg-modal').classList.add('active');
        }

        function showConfirm(msg, onConfirm, title = 'Please Confirm') {
            msgModalCallback = onConfirm;
            const iconWrap = document.getElementById('msg-icon');
            iconWrap.className = 'msg-icon-wrap info';
            iconWrap.innerHTML = '<i class="fa-solid fa-circle-question"></i>';
            const titleEl = document.getElementById('msg-title');
            titleEl.innerText = title;
            titleEl.style.color = 'var(--text-dark)';
            document.getElementById('msg-body').innerHTML = msg;
            document.getElementById('msg-cancel-btn').style.display = 'inline-block';
            const okBtn = document.getElementById('msg-ok-btn');
            okBtn.innerText = 'Yes, Continue';
            okBtn.className = 'btn-ok';
            document.getElementById('msg-modal').classList.add('active');
        }

        function msgModalConfirm() {
            const cb = msgModalCallback;
            msgModalCallback = null;
            closeModal('msg-modal');
            if (cb) setTimeout(() => cb(), 100);
        }

        function closeModal(id) {
            document.getElementById(id).classList.remove('active');
        }

        function switchModalTab(panelId, btnEl) {
            document.querySelectorAll('.modal-tab-panel').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.modal-tab').forEach(b => b.classList.remove('active'));
            document.getElementById(panelId).classList.add('active');
            btnEl.classList.add('active');
        }

        async function initApp() {
            const today = new Date().toISOString().split('T')[0];
            const currentMonth = new Date().toISOString().slice(0, 7);
            ['savings-date', 'withdraw-date', 'loan-date', 'repay-date', 'tracker-date-filter', 'mmodal-savings-date', 'mmodal-withdraw-date', 'mmodal-loan-date'].forEach(id => {
                if (document.getElementById(id)) document.getElementById(id).value = today;
            });
            if (document.getElementById('fee-month-filter')) document.getElementById('fee-month-filter').value = currentMonth;
            try {
                const res = await fetch('/api/auth/me');
                const data = await res.json();
                if (data.logged_in) {
                    currentUser = data;
                    document.getElementById('header-member-count').innerText = data.total_members || 0;
                    loadMembers();
                    if (data.role === 'admin') showSection('home');
                    else { showSection('member-portal'); loadMemberPortal(data.member_id); }
                } else showSection('login');
            } catch (e) { showSection('login'); }
        }

        function showSection(sectionId) {
            document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));
            const target = document.getElementById(`view-${sectionId}`);
            if (target) target.classList.add('active');
            const backBtn = document.getElementById('global-back-btn');
            if (sectionId === 'home' || sectionId === 'login' || sectionId === 'member-portal') backBtn.style.display = 'none';
            else backBtn.style.display = 'inline-flex';
            if (['savings', 'withdrawal', 'loans', 'members', 'manage-members', 'member-history'].includes(sectionId)) loadMembers();
            if (sectionId === 'overview') loadOverviewStats();
            if (sectionId === 'loans') loadLoans();
            if (sectionId === 'tracker') loadDailyTracker();
            if (sectionId === 'service-fees') loadMonthlyFees();
            if (sectionId === 'past-records') loadPastRecords();
        }

        function goBackHome() {
            if (currentUser && currentUser.role === 'admin') showSection('home');
            else if (currentUser) showSection('member-portal');
            else showSection('login');
        }

        async function handleLoginSubmit(e) {
            e.preventDefault();
            const u = document.getElementById('login-username').value;
            const p = document.getElementById('login-password').value;
            const res = await fetch('/api/auth/login', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username: u, password: p})
            });
            const data = await res.json();
            if (data.success) {
                showMessage('Login successful! Welcome back.', 'success', 'Welcome');
                setTimeout(() => initApp(), 400);
            } else showMessage(data.message, 'error');
        }

        async function handleAuthAction() {
            await fetch('/api/auth/logout', {method: 'POST'});
            currentUser = null;
            showSection('login');
        }

        function filterMembersListByQuery(query) {
            if (!query) return [];
            const cleanQ = query.toLowerCase().trim();
            const numVal = parseInt(cleanQ, 10);
            return membersList.filter(m => {
                const name = (m.full_name || '').toLowerCase();
                const id = (m.member_id || '').toLowerCase();
                const digitsOnly = id.replace(/\D/g, '');
                const intVal = parseInt(digitsOnly, 10);
                return name.includes(cleanQ) || id.includes(cleanQ) || digitsOnly.includes(cleanQ) || (!isNaN(numVal) && intVal === numVal);
            });
        }

        function handlePickerSearch(inputId, hiddenId, dropdownId, badgeId, previewId, callback) {
            const query = document.getElementById(inputId).value;
            const dropdown = document.getElementById(dropdownId);
            if (!query.trim()) { dropdown.style.display = 'none'; return; }
            const results = filterMembersListByQuery(query);
            const cbSuffix = callback ? `, ${callback.name}` : '';
            const previewArg = previewId || '';
            if (results.length > 0) {
                dropdown.innerHTML = results.map(m => `
                    <div class="member-picker-item" onclick="selectPickerMember('${m.member_id}', '${m.full_name.replace(/'/g, "\\'")}', '${inputId}', '${hiddenId}', '${dropdownId}', '${badgeId}', '${previewArg}'${cbSuffix})">
                        <span><strong>${m.full_name}</strong> <small style="color:var(--text-muted);">(${m.member_id})</small></span>
                        <span style="color:var(--primary-green-dark); font-weight:800;">₦${m.net_balance.toLocaleString()}</span>
                    </div>
                `).join('');
                dropdown.style.display = 'block';
            } else {
                dropdown.innerHTML = `<div class="member-picker-item" style="color:var(--text-muted);">No member found</div>`;
                dropdown.style.display = 'block';
            }
        }

        function selectPickerMember(memberId, fullName, inputId, hiddenId, dropdownId, badgeId, previewId, callback) {
            document.getElementById(hiddenId).value = memberId;
            document.getElementById(dropdownId).style.display = 'none';
            document.getElementById(inputId).style.display = 'none';
            const badge = document.getElementById(badgeId);
            badge.innerHTML = `
                <span><i class="fa-solid fa-user-check"></i> <strong>${fullName}</strong> (${memberId})</span>
                <button type="button" class="btn-change-member" onclick="clearPickerSelection('${inputId}', '${hiddenId}', '${badgeId}', '${previewId || ''}')">Change</button>
            `;
            badge.style.display = 'flex';
            if (previewId) populateMemberPreview(memberId, previewId);
            if (callback && typeof callback === 'function') callback();
        }

        function populateMemberPreview(memberId, previewId) {
            const m = membersList.find(x => x.member_id === memberId);
            const el = document.getElementById(previewId);
            if (!m || !el) return;
            el.innerHTML = `
                <div class="preview-title"><i class="fa-solid fa-user-circle" style="color: var(--primary-green-dark);"></i> ${m.full_name} <small>(${m.member_id})</small></div>
                <div class="preview-grid">
                    <div class="preview-item"><div class="preview-label">Gross Saved</div><div class="preview-value green">₦${m.gross_saved.toLocaleString()}</div></div>
                    <div class="preview-item"><div class="preview-label">Net Wallet</div><div class="preview-value">₦${m.net_balance.toLocaleString()}</div></div>
                    <div class="preview-item"><div class="preview-label">Cycle Status</div><div class="preview-value purple">Cycle ${m.current_cycle} — Day ${m.cycle_days}/31</div></div>
                    <div class="preview-item"><div class="preview-label">Daily Target</div><div class="preview-value amber">₦${m.daily_target.toLocaleString()}</div></div>
                </div>
            `;
            el.style.display = 'block';
        }

        function clearPickerSelection(inputId, hiddenId, badgeId, previewId) {
            document.getElementById(hiddenId).value = '';
            document.getElementById(inputId).value = '';
            document.getElementById(inputId).style.display = 'block';
            document.getElementById(badgeId).style.display = 'none';
            if (previewId) { const p = document.getElementById(previewId); if (p) p.style.display = 'none'; }
            document.getElementById(inputId).focus();
        }

        async function loadMembers() {
            const res = await fetch('/api/members');
            membersList = await res.json();
            renderMembersDirectory(membersList);
            const manageTable = document.getElementById('manage-members-table-body');
            let targetSum = 0;
            if (manageTable) {
                manageTable.innerHTML = membersList.map(m => {
                    targetSum += (m.daily_target || 0);
                    return `
                        <tr>
                            <td><strong>${m.member_id}</strong></td>
                            <td>${m.full_name}</td>
                            <td>${m.username}</td>
                            <td style="font-weight:700; color:var(--primary-green-dark);">₦${m.daily_target.toLocaleString()}</td>
                            <td><button class="btn-edit-sm" onclick="openDedicatedEditModal('${m.member_id}')">Edit Profile</button></td>
                        </tr>
                    `;
                }).join('');
                if (document.getElementById('manage-target-sum')) document.getElementById('manage-target-sum').innerText = `₦${targetSum.toLocaleString()}`;
                if (document.getElementById('manage-total-count')) document.getElementById('manage-total-count').innerText = membersList.length;
            }
        }

        function openDedicatedEditModal(memberId) {
            const m = membersList.find(x => x.member_id === memberId);
            if (!m) return;
            document.getElementById('ded-edit-id').value = m.member_id;
            document.getElementById('ded-edit-title').innerText = `Edit ${m.full_name}`;
            document.getElementById('ded-edit-subid').innerText = `Member ID: ${m.member_id}`;
            document.getElementById('ded-edit-fullname').value = m.full_name;
            document.getElementById('ded-edit-username').value = m.username;
            document.getElementById('ded-edit-target').value = m.daily_target;
            document.getElementById('ded-edit-password').value = '';
            document.getElementById('dedicated-edit-modal').classList.add('active');
        }

        async function handleDedicatedEditSubmit(e) {
            e.preventDefault();
            const mid = document.getElementById('ded-edit-id').value;
            const payload = {
                full_name: document.getElementById('ded-edit-fullname').value,
                username: document.getElementById('ded-edit-username').value,
                daily_target: document.getElementById('ded-edit-target').value,
                password: document.getElementById('ded-edit-password').value
            };
            const res = await fetch(`/api/member/${mid}`, {
                method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
            });
            const d = await res.json();
            if (d.success) { closeModal('dedicated-edit-modal'); loadMembers(); showMessage(d.message, 'success'); }
            else showMessage(d.message, 'error');
        }

        function renderMembersDirectory(list) {
            const grid = document.getElementById('members-cards-container');
            if (grid) {
                grid.innerHTML = list.map(m => `
                    <div class="member-card-item" onclick="openMemberEditModal('${m.member_id}')">
                        <div class="member-card-header">
                            <div class="member-avatar">${m.full_name.charAt(0)}</div>
                            <div class="member-info">
                                <div class="name">${m.full_name}</div>
                                <div class="code">${m.member_id}</div>
                            </div>
                        </div>
                        <div class="member-stats-box">
                            <div class="stat-line"><span>Saved:</span> <span class="val-green">₦${m.gross_saved.toLocaleString()}</span></div>
                            <div class="stat-line"><span>Net:</span> <span>₦${m.net_balance.toLocaleString()}</span></div>
                        </div>
                        <div class="cycle-status-btn">🔄 Cycle ${m.current_cycle} (${m.cycle_days}/31d)</div>
                    </div>
                `).join('');
            }
        }

        function filterDirectoryCards() {
            const query = document.getElementById('member-search-dir').value;
            const filtered = filterMembersListByQuery(query);
            renderMembersDirectory(filtered);
        }

        function handleGlobalSearchInput(e) {
            const query = e.target.value;
            const dropdown = document.getElementById('search-results-dropdown');
            if (!query.trim()) { dropdown.style.display = 'none'; return; }
            const filtered = filterMembersListByQuery(query);
            if (filtered.length > 0) {
                dropdown.innerHTML = filtered.map(m => `
                    <div class="search-result-item" onclick="openMemberEditModal('${m.member_id}'); document.getElementById('search-results-dropdown').style.display='none'; document.getElementById('global-search-input').value='';">
                        <span><strong>${m.full_name}</strong> <small style="color:#64748b;">(${m.member_id})</small></span>
                        <span style="color:var(--primary-green-dark); font-weight:800;">₦${m.net_balance.toLocaleString()}</span>
                    </div>
                `).join('');
                dropdown.style.display = 'block';
            } else {
                dropdown.innerHTML = `<div class="search-result-item" style="color:var(--text-muted);">No member found</div>`;
                dropdown.style.display = 'block';
            }
        }

        async function loadOverviewStats() {
            const res = await fetch('/api/stats/overview');
            const d = await res.json();
            document.getElementById('stat-total-saved').innerText = `₦${d.gross_total_saved.toLocaleString()}`;
            document.getElementById('stat-service-fees').innerText = `₦${d.total_fees.toLocaleString()}`;
            document.getElementById('stat-net-balance').innerText = `₦${d.net_balance.toLocaleString()}`;
            document.getElementById('stat-loans-issued').innerText = `₦${(d.total_loans_issued || 0).toLocaleString()}`;
            document.getElementById('stat-loans-outstanding').innerText = `₦${(d.total_loans_outstanding || 0).toLocaleString()}`;
        }

        function showSavingsBreakdown(b) {
            if (!b) { showMessage('Savings recorded.', 'success'); return; }
            const html = `
                <div style="background:#f0fdf4; border:1.5px solid #bbf7d0; border-radius:10px; padding:12px; margin-bottom:12px;">
                    <div style="font-weight:800;">${b.full_name} <small style="color:var(--text-muted); font-weight:700;">(${b.member_id})</small></div>
                </div>
                <div style="display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px dashed var(--border-light);"><span>Amount Deposited:</span><strong>₦${b.deposit_amount.toLocaleString()}</strong></div>
                <div style="display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px dashed var(--border-light);"><span>Service Fee (Day 1):</span><strong style="color:var(--amber-fee);">₦${b.fee_collected.toLocaleString()}</strong></div>
                <div style="display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px dashed var(--border-light);"><span>Savings Credited:</span><strong style="color:var(--primary-green-dark);">₦${b.savings_credited.toLocaleString()}</strong></div>
                <div style="display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px dashed var(--border-light);"><span>Savings Days Added:</span><strong>${b.days_added} days</strong></div>
                <div style="display:flex; justify-content:space-between; padding:6px 0;"><span>New Cycle Position:</span><strong style="color:var(--purple-cycle);">Cycle ${b.new_cycle} — Day ${b.new_cycle_days}/31</strong></div>
            `;
            showMessage(html, 'success', 'Deposit Recorded');
        }

        async function handleSavingsSubmit(e) {
            e.preventDefault();
            const memberId = document.getElementById('savings-member-id').value;
            if (!memberId) { showMessage('Please search and select a member.', 'error'); return; }
            const payload = {
                member_id: memberId, amount: document.getElementById('savings-amount').value,
                date: document.getElementById('savings-date').value, notes: document.getElementById('savings-notes').value
            };
            const res = await fetch('/api/savings', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
            });
            const d = await res.json();
            if (d.success) {
                document.getElementById('savings-amount').value = '';
                document.getElementById('savings-notes').value = '';
                clearPickerSelection('savings-member-input', 'savings-member-id', 'savings-badge', 'savings-preview');
                loadMembers();
                showSavingsBreakdown(d.breakdown);
            } else showMessage(d.message, 'error');
        }

        async function handleWithdrawalSubmit(e) {
            e.preventDefault();
            const memberId = document.getElementById('withdraw-member-id').value;
            if (!memberId) { showMessage('Please search and select a member.', 'error'); return; }
            const payload = {
                member_id: memberId, amount: document.getElementById('withdraw-amount').value,
                date: document.getElementById('withdraw-date').value
            };
            const res = await fetch('/api/withdrawals', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
            });
            const d = await res.json();
            if (d.success) {
                document.getElementById('withdraw-amount').value = '';
                clearPickerSelection('withdraw-member-input', 'withdraw-member-id', 'withdraw-badge', 'withdraw-preview');
                loadMembers();
                showMessage(d.message, 'success');
            } else showMessage(d.message, 'error');
        }

        async function handleRegisterSubmit(e) {
            e.preventDefault();
            const payload = {
                full_name: document.getElementById('reg-fullname').value,
                daily_target: document.getElementById('reg-target').value
            };
            const res = await fetch('/api/members', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
            });
            const d = await res.json();
            if (d.success) {
                document.getElementById('reg-fullname').value = '';
                loadMembers();
                showMessage(d.message, 'success', 'Member Registered');
            } else showMessage(d.message, 'error');
        }

        // ---------------- LOANS (FORM REMOVED, TOTALS ADDED) ----------------
        async function loadLoans() {
            const res = await fetch('/api/loans');
            const loans = await res.json();

            // Compute totals
            let totalIssued = 0;
            let totalOutstanding = 0;
            let totalCleared = 0;
            loans.forEach(l => {
                const amt = l.amount || 0;
                const paid = l.amount_paid || 0;
                const remain = Math.max(0, (l.repayment_amount || amt) - paid);
                totalIssued += amt;
                if (l.status === 'active') totalOutstanding += remain;
                else totalCleared += paid;
            });
            document.getElementById('loan-total-issued').innerText = `₦${totalIssued.toLocaleString()}`;
            document.getElementById('loan-total-outstanding').innerText = `₦${totalOutstanding.toLocaleString()}`;
            document.getElementById('loan-total-cleared').innerText = `₦${totalCleared.toLocaleString()}`;

            const tbody = document.getElementById('loans-table-body');
            if (loans.length === 0) {
                tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding:16px;">No loan records</td></tr>`;
            } else {
                tbody.innerHTML = loans.map(l => `
                    <tr>
                        <td><strong>${l.full_name}</strong> <small style="color:var(--text-muted);">(${l.member_id})</small></td>
                        <td>₦${l.amount.toLocaleString()}</td>
                        <td>₦${l.amount_paid.toLocaleString()}</td>
                        <td><span class="badge ${l.status === 'cleared' ? 'badge-success' : 'badge-fee'}">${l.status}</span></td>
                        <td>${l.status === 'active' ? `<button class="btn-repay-sm" onclick="openLoanRepayModal(${l.id})">Repay</button>` : 'Cleared'}</td>
                    </tr>
                `).join('');
            }
        }

        function openLoanRepayModal(loanId) {
            document.getElementById('repay-loan-id').value = loanId;
            document.getElementById('loan-repay-modal').classList.add('active');
        }

        async function handleLoanRepaySubmit(e) {
            e.preventDefault();
            const payload = {
                loan_id: document.getElementById('repay-loan-id').value,
                amount: document.getElementById('repay-amount').value,
                date: document.getElementById('repay-date').value
            };
            const res = await fetch('/api/loans/repay', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
            });
            const d = await res.json();
            if (d.success) {
                closeModal('loan-repay-modal');
                loadLoans();
                if (currentModalMemberId) openMemberEditModal(currentModalMemberId);
                showMessage(d.message, 'success');
            } else showMessage(d.message, 'error');
        }

        async function openMemberEditModal(memberId) {
            currentModalMemberId = memberId;
            const res = await fetch(`/api/member/${memberId}`);
            const d = await res.json();
            if (d.success) {
                const m = d.member;
                document.getElementById('md-title').innerText = m.full_name;
                document.getElementById('md-subid').innerText = `Member ID: ${m.member_id}`;
                document.getElementById('md-cycle-text').innerText = `🔄 Cycle ${m.current_cycle} (${m.cycle_days} / 31 days)`;
                document.getElementById('md-gross-saved').innerText = `₦${m.gross_saved.toLocaleString()}`;
                document.getElementById('md-total-withdrawn').innerText = `₦${m.total_withdrawn.toLocaleString()}`;
                document.getElementById('md-net-balance').innerText = `₦${m.net_balance.toLocaleString()}`;
                document.getElementById('md-active-loan').innerText = `₦${m.active_loan.toLocaleString()}`;
                document.getElementById('md-service-fees').innerText = `₦${m.total_service_fees.toLocaleString()}`;
                document.getElementById('md-daily-target').innerText = `₦${m.daily_target.toLocaleString()}`;
                const tbodyRec = document.getElementById('md-recent-contributions-body');
                if (d.recent_savings.length === 0) tbodyRec.innerHTML = `<tr><td colspan="3" style="text-align:center; color:var(--text-muted);">No savings history found</td></tr>`;
                else tbodyRec.innerHTML = d.recent_savings.map(s => `
                    <tr><td>${s.date}</td><td style="color:var(--primary-green-dark); font-weight:800;">₦${s.amount.toLocaleString()}</td><td>${s.days_credited} days</td></tr>
                `).join('');
                const tbodyLoans = document.getElementById('md-active-loans-body');
                if (!d.active_loans || d.active_loans.length === 0) tbodyLoans.innerHTML = `<tr><td colspan="3" style="text-align:center; color:var(--text-muted);">No active loans</td></tr>`;
                else tbodyLoans.innerHTML = d.active_loans.map(l => `
                    <tr><td>₦${l.amount.toLocaleString()}</td><td>₦${l.amount_paid.toLocaleString()}</td><td><button class="btn-repay-sm" onclick="openLoanRepayModal(${l.id})">Repay</button></td></tr>
                `).join('');
                document.getElementById('edit-member-id').value = m.member_id;
                document.getElementById('edit-fullname').value = m.full_name;
                document.getElementById('edit-username').value = m.username;
                document.getElementById('edit-target').value = m.daily_target;
                document.getElementById('edit-password').value = '';
                switchModalTab('md-tab-overview', document.querySelector('.modal-nav-tabs .modal-tab'));
                document.getElementById('member-detail-modal').classList.add('active');
            }
        }

        async function handleModalSavingsSubmit(e) {
            e.preventDefault();
            const payload = {
                member_id: currentModalMemberId, amount: document.getElementById('mmodal-savings-amount').value,
                date: document.getElementById('mmodal-savings-date').value, notes: document.getElementById('mmodal-savings-notes').value
            };
            const res = await fetch('/api/savings', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
            });
            const d = await res.json();
            if (d.success) {
                document.getElementById('mmodal-savings-amount').value = '';
                document.getElementById('mmodal-savings-notes').value = '';
                loadMembers();
                openMemberEditModal(currentModalMemberId);
                showSavingsBreakdown(d.breakdown);
            } else showMessage(d.message, 'error');
        }

        async function handleModalWithdrawSubmit(e) {
            e.preventDefault();
            const payload = {
                member_id: currentModalMemberId, amount: document.getElementById('mmodal-withdraw-amount').value,
                date: document.getElementById('mmodal-withdraw-date').value
            };
            const res = await fetch('/api/withdrawals', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
            });
            const d = await res.json();
            if (d.success) {
                document.getElementById('mmodal-withdraw-amount').value = '';
                loadMembers();
                openMemberEditModal(currentModalMemberId);
                showMessage(d.message, 'success');
            } else showMessage(d.message, 'error');
        }

        async function handleModalLoanIssueSubmit(e) {
            e.preventDefault();
            const payload = {
                member_id: currentModalMemberId, amount: document.getElementById('mmodal-loan-amount').value,
                issue_date: document.getElementById('mmodal-loan-date').value
            };
            const res = await fetch('/api/loans', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
            });
            const d = await res.json();
            if (d.success) {
                document.getElementById('mmodal-loan-amount').value = '';
                loadMembers();
                openMemberEditModal(currentModalMemberId);
                showMessage(d.message, 'success');
            } else showMessage(d.message, 'error');
        }

        function resetMemberTargetFromModal() {
            showConfirm(`Reset daily target for <strong>${currentModalMemberId}</strong> to default (₦500)?`, async () => {
                const res = await fetch(`/api/member/${currentModalMemberId}/reset-target`, {
                    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({daily_target: 500.0})
                });
                const d = await res.json();
                if (d.success) { loadMembers(); openMemberEditModal(currentModalMemberId); showMessage(d.message, 'success'); }
                else showMessage(d.message, 'error');
            }, 'Reset Daily Target');
        }

        function resetMemberLedgerFromModal() {
            showConfirm(`Reset <strong>all financial history and service fees to ZERO</strong> for <strong>${currentModalMemberId}</strong>? This cannot be undone.`, async () => {
                const res = await fetch(`/api/member/${currentModalMemberId}/reset-ledger`, {method: 'POST'});
                const d = await res.json();
                if (d.success) { loadMembers(); openMemberEditModal(currentModalMemberId); showMessage(d.message, 'success'); }
                else showMessage(d.message, 'error');
            }, 'Reset Member Ledger');
        }

        function deleteMemberFromModal() {
            showConfirm(`Permanently delete member profile <strong>${currentModalMemberId}</strong> and ALL their ledger data? This cannot be undone.`, async () => {
                const res = await fetch(`/api/member/${currentModalMemberId}`, {method: 'DELETE'});
                const d = await res.json();
                if (d.success) { closeModal('member-detail-modal'); loadMembers(); showMessage(d.message, 'success'); }
                else showMessage(d.message, 'error');
            }, 'Delete Member');
        }

        async function handleMemberEditSubmit(e) {
            e.preventDefault();
            const mid = document.getElementById('edit-member-id').value;
            const payload = {
                full_name: document.getElementById('edit-fullname').value,
                username: document.getElementById('edit-username').value,
                daily_target: document.getElementById('edit-target').value,
                password: document.getElementById('edit-password').value
            };
            const res = await fetch(`/api/member/${mid}`, {
                method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
            });
            const d = await res.json();
            if (d.success) { closeModal('member-detail-modal'); loadMembers(); showMessage(d.message, 'success'); }
            else showMessage(d.message, 'error');
        }

        async function loadDailyTracker() {
            const dateVal = document.getElementById('tracker-date-filter').value;
            const url = dateVal ? `/api/tracker/daily?date=${dateVal}` : '/api/tracker/daily';
            const res = await fetch(url);
            const d = await res.json();
            renderTracker(d);
        }

        function showAllTracker() {
            document.getElementById('tracker-date-filter').value = '';
            loadDailyTracker();
        }

        function renderTracker(d) {
            document.getElementById('tracker-total-inflow').innerText = `₦${d.total_inflow.toLocaleString()}`;
            document.getElementById('tracker-total-outflow').innerText = `₦${d.total_outflow.toLocaleString()}`;
            document.getElementById('tracker-net-cashflow').innerText = `₦${d.net_cashflow.toLocaleString()}`;
            document.getElementById('tracker-savings-total').innerText = `₦${d.total_savings.toLocaleString()}`;
            document.getElementById('tracker-fees-total').innerText = `₦${d.total_fees.toLocaleString()}`;

            const sBody = document.getElementById('tracker-savings-body');
            if (d.savings_logs.length === 0) {
                sBody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding:14px;">No savings records</td></tr>`;
            } else {
                sBody.innerHTML = d.savings_logs.map(s => `
                    <tr>
                        <td>${s.date}</td>
                        <td>${s.full_name} <small style="color:var(--text-muted);">(${s.member_id})</small></td>
                        <td style="color:var(--primary-green-dark); font-weight:800;">₦${s.amount.toLocaleString()}</td>
                        <td>${s.days_credited} days</td>
                        <td>${s.notes || ''}</td>
                    </tr>
                `).join('');
            }

            const fBody = document.getElementById('tracker-fees-body');
            if (d.fee_logs.length === 0) {
                fBody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-muted); padding:14px;">No service fees</td></tr>`;
            } else {
                fBody.innerHTML = d.fee_logs.map(f => `
                    <tr>
                        <td>${f.date}</td>
                        <td>${f.full_name} <small style="color:var(--text-muted);">(${f.member_id})</small></td>
                        <td style="color:var(--amber-fee); font-weight:800;">₦${f.amount.toLocaleString()}</td>
                        <td>${f.description || ''}</td>
                    </tr>
                `).join('');
            }

            const oBody = document.getElementById('tracker-other-body');
            if (d.other_logs.length === 0) {
                oBody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding:14px;">No other transactions</td></tr>`;
            } else {
                oBody.innerHTML = d.other_logs.map(o => {
                    const isOut = (o.tx_type === 'Withdrawal' || o.tx_type === 'Loan Issued');
                    const color = isOut ? 'var(--primary-red)' : 'var(--primary-green-dark)';
                    const badgeClass = o.tx_type === 'Withdrawal' ? 'badge-payout' : (o.tx_type === 'Loan Issued' ? 'badge-fee' : 'badge-savings');
                    return `
                        <tr>
                            <td>${o.date}</td>
                            <td>${o.full_name} <small style="color:var(--text-muted);">(${o.member_id})</small></td>
                            <td><span class="badge ${badgeClass}">${o.tx_type}</span></td>
                            <td style="color:${color}; font-weight:800;">₦${o.amount.toLocaleString()}</td>
                            <td>${o.notes || ''}</td>
                        </tr>
                    `;
                }).join('');
            }
        }

        async function loadMonthlyFees() {
            const monthVal = document.getElementById('fee-month-filter').value;
            const res = await fetch(`/api/service-fees?month=${monthVal}`);
            const d = await res.json();
            document.getElementById('fee-total-amount').innerText = `₦${d.total_fees.toLocaleString()}`;
            const tbody = document.getElementById('service-fees-table-body');
            tbody.innerHTML = d.fees.map(f => `
                <tr>
                    <td>${f.date}</td>
                    <td>${f.full_name}</td>
                    <td style="color:var(--amber-fee); font-weight:800;">₦${f.amount.toLocaleString()}</td>
                    <td>${f.description}</td>
                </tr>
            `).join('');
        }

        async function loadPastRecords() {
            const res = await fetch('/api/archives');
            const records = await res.json();

            const totalAmount = records.reduce((sum, r) => sum + (r.amount || 0), 0);
            document.getElementById('archive-total-count').innerText = records.length.toLocaleString();
            document.getElementById('archive-total-amount').innerText = `₦${totalAmount.toLocaleString()}`;

            const tbody = document.getElementById('archives-table-body');
            if (records.length === 0) {
                tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding:16px;">No archived records found</td></tr>`;
            } else {
                tbody.innerHTML = records.map(r => {
                    let badgeClass = 'badge-payout';
                    if (r.tx_type === 'Savings') badgeClass = 'badge-savings';
                    else if (r.tx_type === 'Service Fee' || r.tx_type.includes('Loan')) badgeClass = 'badge-fee';
                    return `
                        <tr>
                            <td>${r.date}</td>
                            <td>${r.full_name} <small style="color:var(--text-muted);">(${r.member_id})</small></td>
                            <td><span class="badge ${badgeClass}">${r.tx_type}</span></td>
                            <td style="font-weight:800;">₦${r.amount.toLocaleString()}</td>
                            <td>Cycle ${r.cycle_no}</td>
                        </tr>
                    `;
                }).join('');
            }
        }

        function resetPastRecords() {
            showConfirm('<strong style="color:#7f1d1d;">Reset ALL Past Records</strong><br><br>This will permanently wipe every archived transaction <strong>and reset the total archive amount to zero</strong>.<br><br>• Active ledgers (savings, withdrawals, loans, service fees) are <strong>NOT</strong> touched.<br>• Member profiles are <strong>NOT</strong> touched.<br>• Only the archive history and totals are erased.<br><br>This action <strong>cannot be undone</strong>. Continue?', async () => {
                const res = await fetch('/api/archives/reset', {method: 'POST'});
                const d = await res.json();
                if (d.success) {
                    loadPastRecords();
                    showMessage(d.message, 'success', 'Past Records Wiped');
                } else showMessage(d.message, 'error');
            }, '⚠️ Reset Past Records');
        }

        async function loadMemberHistoryView() {
            const mid = document.getElementById('history-member-id').value;
            if (!mid) return;
            const res = await fetch(`/api/member/${mid}/history`);
            const d = await res.json();
            if (d.success) {
                const tbody = document.getElementById('member-history-table-body');
                tbody.innerHTML = d.history.map(h => `
                    <tr>
                        <td>${h.date}</td>
                        <td><span class="badge ${h.category === 'Savings' ? 'badge-savings' : 'badge-fee'}">${h.category}</span></td>
                        <td>₦${h.amount.toLocaleString()}</td>
                        <td>${h.notes}</td>
                    </tr>
                `).join('');
            }
        }

        async function triggerMaintenanceResync() {
            const res = await fetch('/api/maintenance/resync', {method: 'POST'});
            const d = await res.json();
            showMessage(d.message, 'success');
        }

        function triggerMaintenanceFullReset() {
            showConfirm('This will <strong>wipe all active financial ledgers</strong> across all members (savings, withdrawals, loans, repayments, service fees). Member profiles and past archives are preserved. Continue?', async () => {
                const res = await fetch('/api/maintenance/reset-all-ledgers', {method: 'POST'});
                const d = await res.json();
                loadMembers();
                showMessage(d.message, 'success');
            }, 'Reset Active Ledgers');
        }

        function triggerFactoryReset() {
            showConfirm('<strong style="color:#7f1d1d;">FULL FACTORY RESET</strong><br><br>This will permanently delete:<br>• All active ledgers (savings, withdrawals, loans, repayments, fees)<br>• All past archives<br><br>Member profiles, usernames, passwords, and daily targets are preserved. Every member resets to Cycle 1 / Day 0.<br><br>This action <strong>cannot be undone</strong>. Continue?', async () => {
                const res = await fetch('/api/maintenance/factory-reset', {method: 'POST'});
                const d = await res.json();
                loadMembers();
                showMessage(d.message, 'success', 'Factory Reset Complete');
            }, '⚠️ Full Factory Reset');
        }

        async function handlePasswordUpdateSubmit(e) {
            e.preventDefault();
            const payload = {
                old_password: document.getElementById('old-pass').value,
                new_password: document.getElementById('new-pass').value
            };
            const res = await fetch('/api/admin/password', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
            });
            const d = await res.json();
            if (d.success) {
                document.getElementById('old-pass').value = '';
                document.getElementById('new-pass').value = '';
                showMessage(d.message, 'success');
            } else showMessage(d.message, 'error');
        }

        async function loadMemberPortal(memberId) {
            const res = await fetch(`/api/member/${memberId}`);
            const d = await res.json();
            if (d.success) {
                const m = d.member;
                document.getElementById('mportal-name').innerText = m.full_name;
                document.getElementById('mportal-id').innerText = `ID: ${m.member_id}`;
                document.getElementById('mportal-gross-saved').innerText = `₦${m.gross_saved.toLocaleString()}`;
                document.getElementById('mportal-balance').innerText = `₦${m.net_balance.toLocaleString()}`;
                document.getElementById('mportal-target').innerText = `₦${m.daily_target.toLocaleString()}`;
                document.getElementById('mportal-fees').innerText = `₦${m.total_service_fees.toLocaleString()}`;
                document.getElementById('mportal-loan').innerText = `₦${m.active_loan.toLocaleString()}`;
                const table = document.getElementById('mportal-savings-table');
                table.innerHTML = d.recent_savings.map(s => `
                    <tr>
                        <td>${s.date}</td>
                        <td style="color:var(--primary-green-dark); font-weight:800;">₦${s.amount.toLocaleString()}</td>
                        <td>${s.days_credited} days</td>
                    </tr>
                `).join('');
            }
        }

        document.addEventListener('click', function(e) {
            const pickers = ['savings-picker-dropdown', 'withdraw-picker-dropdown', 'loan-picker-dropdown', 'history-picker-dropdown', 'search-results-dropdown'];
            pickers.forEach(id => {
                const el = document.getElementById(id);
                if (el && !el.contains(e.target) && !e.target.classList.contains('form-control') && !e.target.classList.contains('search-input')) {
                    el.style.display = 'none';
                }
            });
        });

        window.onload = initApp;
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
    