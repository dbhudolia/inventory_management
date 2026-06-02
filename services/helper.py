import streamlit as st
import psycopg2
import pandas as pd


# --- CLOUD DATABASE FACTORY CONNECTION ---
def get_db_connection():
    """Establishes a password-safe connection to Supabase using separate parameters."""
    conn = psycopg2.connect(
        host=st.secrets["postgres"]["host"],
        database=st.secrets["postgres"]["database"],
        user=st.secrets["postgres"]["user"],
        password=st.secrets["postgres"]["password"],
        port=st.secrets["postgres"]["port"]
    )
    return conn


# --- DATABASE SETUP ---
def init_db():
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

    # 2. Table for Sales Logs (Synced table name matching previous architecture updates)
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

    # 3. Table for Simple User Auth (Escaping primary key requirements safely)
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                        username TEXT PRIMARY KEY, 
                        password TEXT,
                        "role" TEXT)''')

    # 4. Create default user safely if table is currently empty
    c.execute('SELECT COUNT(*) FROM users')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO users (username, password, "role") VALUES (%s, %s, %s)',
                  ('mpmica', 'mpmica@815301', 'Admin'))

    conn.commit()
    c.close()
    conn.close()


def verify_user(username, password):
    conn = get_db_connection()
    c = conn.cursor()
    # "role" and "users" are double-quoted to comply strictly with PostgreSQL rules
    c.execute('SELECT username, password, "role" FROM users WHERE username = %s AND password = %s',
              (username, password))
    user = c.fetchone()
    c.close()
    conn.close()
    return user  # Returns None if no match, or the user tuple if found


def login():
    st.title("🔐 Inventory Login")
    with st.form("login_form"):
        user = st.text_input("Username")
        pw = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            user_data = verify_user(user, pw)
            if user_data:
                st.session_state['logged_in'] = True
                st.session_state['username'] = user_data[0]
                st.session_state['user_role'] = user_data[2]  # Extracts 'Admin' or 'Staff'
                st.rerun()
            else:
                st.error("Invalid Username or Password")


def manage_user():
    st.title("👥 User Management")
    conn = get_db_connection()

    with st.expander("Add New Staff User"):
        new_user = st.text_input("New Username")
        new_pw = st.text_input("New Password", type="password")
        new_role = st.selectbox("Role", ["Staff", "Admin"])

        if st.button("Create User"):
            if not new_user or not new_pw:
                st.error("Fields cannot be left blank.")
            else:
                try:
                    c = conn.cursor()
                    # Explicit mapping prevents system structural injection exceptions
                    c.execute('INSERT INTO users (username, password, "role") VALUES (%s, %s, %s)',
                              (new_user, new_pw, new_role))
                    conn.commit()
                    c.close()
                    st.success(f"User {new_user} created successfully!")
                    st.rerun()
                except psycopg2.errors.UniqueViolation:
                    conn.rollback()
                    st.error("Username already exists in the cloud directory.")
                except Exception as e:
                    conn.rollback()
                    st.error(f"Error handling entry request: {e}")

    st.subheader("Current Registered Users")
    # Fetch user summary using the cloud connection hook
    users_df = pd.read_sql('SELECT username, "role" AS Role FROM users', conn)
    conn.close()

    st.dataframe(users_df, use_container_width=True, hide_index=True)