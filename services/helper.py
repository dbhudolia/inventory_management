import streamlit as st
import psycopg2
import pandas as pd
import hashlib
from datetime import datetime


# --- CLOUD DATABASE FACTORY CONNECTION ---
def get_db_connection():
    """Establishes a password-safe connection to Supabase using separate parameters."""
    return psycopg2.connect(
        host=st.secrets["postgres"]["host"],
        database=st.secrets["postgres"]["database"],
        user=st.secrets["postgres"]["user"],
        password=st.secrets["postgres"]["password"],
        port=st.secrets["postgres"]["port"]
    )


# --- DATABASE SETUP ---
def init_db():
    """Initializes schema blueprints securely inside the Supabase instance."""
    conn = get_db_connection()
    c = conn.cursor()

    # 1. Table for Physical Stock & Location
    c.execute('''CREATE TABLE IF NOT EXISTS stock (
                        id SERIAL PRIMARY KEY,
                        invoice_no TEXT,
                        invoiced_item_name TEXT,
                        size TEXT,
                        finish TEXT,
                        type TEXT,
                        material TEXT,
                        mica_type TEXT,
                        weight REAL,
                        godown TEXT,
                        rack TEXT,
                        status TEXT,
                        received_at TIMESTAMP)''')

    # 2. Table for Sales Logs
    c.execute('''CREATE TABLE IF NOT EXISTS sales (
                        id SERIAL PRIMARY KEY,
                        stock_id INTEGER,
                        invoice_no TEXT,
                        size TEXT,
                        finish TEXT,
                        material TEXT,
                        type TEXT,
                        mica_type TEXT,
                        company_name TEXT,
                        qty_sold REAL,
                        price_per_kg REAL,
                        total_amount REAL,
                        notes TEXT,
                        sale_date TIMESTAMP)''')

    # 3. Table for User Auth ("role" is double-quoted to prevent PostgreSQL reserved keyword errors)
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                        username TEXT PRIMARY KEY, 
                        password TEXT,
                        "role" TEXT)''')

    # 4. Create default secure administrator profile safely if table is currently empty
    c.execute('SELECT COUNT(*) FROM users')
    if c.fetchone()[0] == 0:
        # Default fallback credentials
        default_username = ""
        default_password_raw = ""
        hashed_password = hashlib.sha256(default_password_raw.encode()).hexdigest()

        c.execute('INSERT INTO users (username, password, "role") VALUES (%s, %s, %s)',
                  (default_username, hashed_password, 'Admin'))

    conn.commit()
    c.close()
    conn.close()


def verify_user(username, password_raw):
    """Safely verifies credentials using parameterized tokens and cryptographic hash signatures."""
    conn = get_db_connection()
    c = conn.cursor()

    # Compute the SHA-256 hash representation of the raw user password string input
    hashed_input = hashlib.sha256(password_raw.encode()).hexdigest()

    # Fully parameterized to block SQL injection vectors entirely
    c.execute('SELECT username, "role" FROM users WHERE username = %s AND password = %s',
              (username.strip(), hashed_input))
    user = c.fetchone()

    c.close()
    conn.close()
    return user  # Returns None if record match fails, or returning (username, role) tuple block


def login():
    """Authenticates corporate sessions cleanly utilizing non-rerun flashing execution forms."""
    st.title("🔐 Inventory Login")

    with st.form("login_form", clear_on_submit=False):
        user = st.text_input("Username").strip()
        pw = st.text_input("Password", type="password")
        submit_btn = st.form_submit_button("Login", use_container_width=True)

    if submit_btn:
        if not user or not pw:
            st.error("⚠️ Username and password fields cannot be left empty.")
        else:
            user_data = verify_user(user, pw)
            if user_data:
                st.session_state['logged_in'] = True
                st.session_state['username'] = user_data[0]
                st.session_state['user_role'] = user_data[1]  # Extracts 'Admin' or 'Staff' profile type cleanly
                st.success("🎉 Login successful! Redirecting...")
                st.rerun()
            else:
                st.error("❌ Invalid Username or Password. Please try again.")


def manage_user():
    """Provides complete CRUD directory registration loops accessible strictly by administrative managers."""
    st.title("👥 User Management")

    # Restrict visibility safety verification layer block
    if st.session_state.get('user_role') != 'Admin':
        st.error(
            "⛔ Access Denied: Staff roles do not possess adequate clearance parameters to view directory frameworks.")
        return

    conn = get_db_connection()

    with st.expander("Add New Staff User Account", expanded=True):
        new_user = st.text_input("New Username").strip()
        new_pw = st.text_input("New Password", type="password").strip()
        new_role = st.selectbox("Assign System Clearance Level", ["Staff", "Admin", "Developer"])

        if st.button("Create User Account & Save to Cloud", type="primary", use_container_width=True):
            if not new_user or not new_pw:
                st.error("❌ Registration parameter files cannot contain empty values.")
            else:
                try:
                    c = conn.cursor()

                    # Convert raw credentials string directly into static SHA-256 hash before pipeline streaming
                    secure_password_hash = hashlib.sha256(new_pw.encode()).hexdigest()

                    c.execute('INSERT INTO users (username, password, "role") VALUES (%s, %s, %s)',
                              (new_user, secure_password_hash, new_role))
                    conn.commit()
                    c.close()

                    st.success(f"🎉 User profile for '{new_user}' registered successfully inside directory logs!")
                    st.rerun()

                except psycopg2.errors.UniqueViolation:
                    conn.rollback()
                    st.error("⚠️ Username compilation conflict: This identifier name already exists.")
                except Exception as e:
                    conn.rollback()
                    st.error(f"Engine routing exception encountered: {e}")

    '''st.subheader("Current Registered Directory Records")
    try:
        # Pull safe tracking overview without exposing sensitive hash values onto screen interfaces
        users_df = pd.read_sql(
            'SELECT username AS "Registered Username", "role" AS "Clearance Level" FROM users ORDER BY username ASC',
            conn)
        st.dataframe(users_df, use_container_width=True, hide_index=True)
    except Exception as read_err:
        st.error(f"Failed to compile operational user list: {read_err}")
    finally:
        conn.close()'''