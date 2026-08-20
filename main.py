import streamlit as st
import sqlite3

import services.inventory as inventory
import services.inward_stock as inward_stock
import services.inventory_search as inventory_search
import services.helper as helper
import services.out_order as out_order
import services.stock_position as stock_position
import services.item_ledger as item_ledger
import services.stock_sorting as stock_sorting
import services.sales_price_editor as sales_price_editor
import services.bulk_rack_transfer as bulk_rack_transfer
import services.service_batch_lineage as service_batch_lineage
from services.sales_analysis import sales_analysis_management
import services.bulk_sales as bulk_sales
import services.tally_stock_view as tally_stock_view

# --- MUST BE THE FIRST ST COMMAND ---
st.set_page_config(
    page_title="Mica Inventory System",
    page_icon="📦",
    layout="wide", # This makes it Wide Mode by default
    initial_sidebar_state="expanded"
)

helper.init_db()

# --- AUTHENTICATION LOGIC ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['user_role'] = None

# --- MAIN APPLICATION ---
def main():
    st.sidebar.title("Warehouse Controls")
    # st.sidebar.title(f"Welcome, {st.session_state['username']}")
    menu_options = ["Dashboard", "Inward Stock Entry", "Out Order (Sales)", "Stock Position",
                    "Inventory Search", "Tally Stock"]

    # Only show User Management to Admins
    if st.session_state['user_role'] == 'Admin':
        menu_options.append("Item History Ledger")
        menu_options.append("Executive Sales Analysis")
        menu_options.append("Manage Users")

    # Only show User Management to Admins
    if st.session_state['user_role'] == 'Developer':
        menu_options.append("Bulk Variant Sales")
        menu_options.append("Sales Price Editor")
        menu_options.append("Item History Ledger")
        menu_options.append("Bulk Rack Transfer")
        menu_options.append("Process Stock Sorting")
        menu_options.append("Service Batch Lineage")
        menu_options.append("Executive Sales Analysis")

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

    elif page == "Bulk Variant Sales":
        bulk_sales.rack_liquidation_management()

    elif page == "Process Stock Sorting":
        stock_sorting.stock_sorting_management()

    # --- PAGE 5: SEARCH & FILTERS ---
    elif page == "Inventory Search":
        inventory_search.inventory_search_management()

    elif page == "Stock Position":
        stock_position.stock_position_summary()

    elif page == "Item History Ledger":
        item_ledger.item_ledger_management()

    elif page == "Executive Sales Analysis":
        sales_analysis_management()

    # --- NEW PAGE: MANAGE USERS ---
    elif page == "Manage Users":
        helper.manage_user()

    # --- NEW PAGE: Sales ---
    elif page == "Sales Price Editor":
        sales_price_editor.sales_price_editor_management()

    # --- NEW PAGE: Rack Transfer ---
    elif page == "Bulk Rack Transfer":
        bulk_rack_transfer.bulk_rack_transfer_management()

    # --- NEW PAGE: Batch Transfer ---
    elif page == "Service Batch Lineage":
        service_batch_lineage.sorted_batch_lineage_management()

    # --- NEW PAGE: Tally Stock ---
    elif page == "Tally Stock":
        tally_stock_view.render_tally_stock_page()
    conn.close()

# --- ROUTER ---
if not st.session_state['logged_in']:
    helper.login()
else:
    main()