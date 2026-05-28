import streamlit as st
import sqlite3
import pandas as pd

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('inventory.db')
    c = conn.cursor()
    # Table for Physical Stock & Location
    c.execute('''CREATE TABLE IF NOT EXISTS stock (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
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

    # Add this to your helper.py init_db function
    c.execute('''CREATE TABLE IF NOT EXISTS sales_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_id INTEGER,
                    customer_name TEXT,
                    qty_sold REAL,
                    sale_date TIMESTAMP)''')

    # Table for simple user auth
    # Users Table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                        username TEXT PRIMARY KEY, 
                        password TEXT,
                        role TEXT)''')

    # Create a default user if the table is empty so you aren't locked out
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users VALUES ('mpmica', 'mpmica@815301', 'Admin')")

    conn.commit()
    conn.close()

def verify_user(username, password):
    conn = sqlite3.connect('inventory.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
    # c.execute("SELECT * FROM users")
    user = c.fetchone()
    # print(user)
    conn.close()
    return user # Returns None if no match, or the user row if found

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
                st.session_state['user_role'] = user_data[2]
                st.rerun()
            else:
                st.error("Invalid Username or Password")

def manage_user():
    conn = sqlite3.connect('inventory.db')
    st.title("👥 User Management")

    with st.expander("Add New Staff User"):
        new_user = st.text_input("New Username")
        new_pw = st.text_input("New Password", type="password")
        new_role = st.selectbox("Role", ["Staff", "Admin"])
        if st.button("Create User"):
            try:
                c = conn.cursor()
                c.execute("INSERT INTO users VALUES (?,?,?)", (new_user, new_pw, new_role))
                conn.commit()
                st.success(f"User {new_user} created successfully!")
            except sqlite3.IntegrityError:
                st.error("Username already exists")

    st.subheader("Current Users")
    users_df = pd.read_sql("SELECT username, role FROM users", conn)
    st.table(users_df)
