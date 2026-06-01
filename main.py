import streamlit as st
import sqlite3
import urllib.request
import json

import services.inventory as inventory
import services.inward_stock as inward_stock
import services.inventory_search as inventory_search
import services.helper as helper
import services.out_order as out_order
import services.stock_position as stock_position
import services.item_ledger as item_ledger

# --- MUST BE THE FIRST ST COMMAND ---
st.set_page_config(
    page_title="Mica Inventory System",
    page_icon="📦",
    layout="wide", # This makes it Wide Mode by default
    initial_sidebar_state="expanded"
)

helper.init_db()

def check_network_authorization():
    # 1. Define your authorized office / godown public IP addresses
    ALLOWED_IPS = [
        "49.37.26.239",
    ]

    # 2. Fetch the current visitor's external network IP route safely
    try:
        # Calls a secure plain-text IP echoing endpoint
        current_ip = urllib.request.urlopen('https://api.ipify.org', timeout=3).read().decode('utf8')
    except Exception:
        try:
            # Fallback provider if the primary checker drops offline
            current_ip = urllib.request.urlopen('https://icanhazip.com', timeout=3).read().decode('utf8').strip()
        except Exception:
            st.error("🔒 Security Framework Connection Timeout. Unable to verify network gateway profiles.")
            st.stop()

    # 3. Validation Gateway Gatekeeper Loop
    if current_ip not in ALLOWED_IPS:
        st.error("### 🚫 Access Denied: Unauthorized Network Location")
        st.write(
            f"Your device network routing profile (**{current_ip}**) is not registered on the company access whitelist.")
        st.info(
            "⚠️ Please connect to the official office broadband line or contact administration to register this network point.")
        # Stops execution immediately so no warehouse pages or data connections are rendered
        st.stop()


# TRIGGER THE PROTECTION SUITE IMMEDIATELY BEFORE RENDERING PAGES
# check_network_authorization()

# --- AUTHENTICATION LOGIC ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['user_role'] = None

# --- MAIN APPLICATION ---
def main():
    st.sidebar.title("Warehouse Controls")
    # st.sidebar.title(f"Welcome, {st.session_state['username']}")
    menu_options = ["Dashboard", "Inward Stock Entry", "Out Order (Sales)", "Stock Position",
                    "Inventory Search", "Item History Ledger"]

    # Only show User Management to Admins
    if st.session_state['user_role'] == 'Admin':
        menu_options.append("Manage Users")

    page = st.sidebar.radio("Navigation", menu_options)

    if st.sidebar.button("Logout"):
        st.session_state['logged_in'] = False
        st.rerun()

    conn = sqlite3.connect('inventory.db')

    # --- PAGE 1: DASHBOARD ---
    if page == "Dashboard":
        inventory.inventory_management()

    # --- PAGE 2: INWARD ENTRY ---
    elif page == "Inward Stock Entry":
        inward_stock.inward_stock_management()

    # --- NEW PAGE: OUT ORDER ---
    elif page == "Out Order (Sales)":
        out_order.out_order_management()

    # --- PAGE 4: SEARCH & FILTERS ---
    elif page == "Inventory Search":
        inventory_search.inventory_search_management()

    elif page == "Stock Position":
        stock_position.stock_position_summary()

    elif page == "Item History Ledger":
        item_ledger.item_ledger_management()

    # --- NEW PAGE: MANAGE USERS ---
    elif page == "Manage Users":
        helper.manage_user()
    conn.close()

# --- ROUTER ---
if not st.session_state['logged_in']:
    helper.login()
else:
    main()