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
import services.tally_sales_view as tally_sales_view

# --- MUST BE THE FIRST ST COMMAND ---
st.set_page_config(
    page_title="Mica Inventory System",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

helper.init_db()

# --- AUTHENTICATION & NAVIGATION STATE ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['user_role'] = None

if 'current_page' not in st.session_state:
    st.session_state['current_page'] = "Dashboard"

# --- MAIN APPLICATION ---
def main():
    st.sidebar.title("Warehouse Controls")
    role = st.session_state.get('user_role', 'User')

    # --- CATEGORIZED NAVIGATION SECTIONS ---
    nav_sections = {
        "📊 Overview & Search": [
            "Dashboard",
            "Stock Position",
            "Inventory Search"
        ],
        "🔄 Operations": [
            "Inward Stock Entry",
            "Out Order (Sales)"
        ],
        "🔗 Tally Live Data": [
            "Tally Stock",
            "Tally Sales"
        ]
    }

    if role in ['Admin', 'Developer']:
        nav_sections["📈 Analytics & History"] = [
            "Item History Ledger",
            "Executive Sales Analysis"
        ]

    if role == 'Developer':
        nav_sections["⚙️ Processing & Transfers"] = [
            "Bulk Variant Sales",
            "Sales Price Editor",
            "Bulk Rack Transfer",
            "Process Stock Sorting",
            "Service Batch Lineage"
        ]

    if role == 'Admin':
        nav_sections["🔐 Administration"] = [
            "Manage Users"
        ]

    # --- RENDER EXPANDABLE SIDEBAR MENUS ---
    for section_title, pages in nav_sections.items():
        # Keep the folder open if the current active page belongs to it
        is_expanded = st.session_state['current_page'] in pages
        with st.sidebar.expander(section_title, expanded=is_expanded):
            for p in pages:
                # Highlight active page button
                btn_type = "primary" if st.session_state['current_page'] == p else "secondary"
                if st.button(p, key=f"btn_{p}", type=btn_type, use_container_width=True):
                    st.session_state['current_page'] = p
                    st.rerun()

    st.sidebar.divider()
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        st.session_state['logged_in'] = False
        st.session_state['current_page'] = "Dashboard"
        st.rerun()

    conn = sqlite3.connect('inventory.db')
    active_page = st.session_state['current_page']

    # --- PAGE ROUTING ---
    # Overview & Search
    if active_page == "Dashboard":
        inventory.inventory_management()
    elif active_page == "Stock Position":
        stock_position.stock_position_summary()
    elif active_page == "Inventory Search":
        inventory_search.inventory_search_management()

    # Operations
    elif active_page == "Inward Stock Entry":
        inward_stock.inward_stock_management()
    elif active_page == "Out Order (Sales)":
        out_order.out_order_management()

    # Tally 9 Integration
    elif active_page == "Tally Stock":
        tally_stock_view.render_tally_stock_page()
    elif active_page == "Tally Sales":
        tally_sales_view.render_tally_sales_page()

    # Analytics & History
    elif active_page == "Item History Ledger":
        item_ledger.item_ledger_management()
    elif active_page == "Executive Sales Analysis":
        sales_analysis_management()

    # Processing & Transfers (Developer)
    elif active_page == "Bulk Variant Sales":
        bulk_sales.rack_liquidation_management()
    elif active_page == "Sales Price Editor":
        sales_price_editor.sales_price_editor_management()
    elif active_page == "Bulk Rack Transfer":
        bulk_rack_transfer.bulk_rack_transfer_management()
    elif active_page == "Process Stock Sorting":
        stock_sorting.stock_sorting_management()
    elif active_page == "Service Batch Lineage":
        service_batch_lineage.sorted_batch_lineage_management()

    # Administration (Admin)
    elif active_page == "Manage Users":
        helper.manage_user()

    conn.close()

# --- ROUTER ---
if not st.session_state['logged_in']:
    helper.login()
else:
    main()