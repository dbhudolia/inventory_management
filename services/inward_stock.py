import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime

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

def inward_stock_management():
    st.title("📥 Material-Specific Stock Entry")

    # 1. INVOICE HEADER
    c1, c2 = st.columns(2)
    invoice_no = c1.text_input("Invoice Number")
    invoiced_item_name = c2.text_input("Item Name on Invoice (Nominal)")

    st.divider()

    # 2. THE TRIGGER SECTION (Must be OUTSIDE the form to react instantly)
    st.subheader("📏 Primary Specifications")
    col_size, col_mat = st.columns(2)

    size = col_size.text_input("Size", placeholder="e.g., 0.06 or 35mm")
    material = col_mat.selectbox("Material", ["Rigid", "Flexible", "Epoxy"])

    # LOGIC: Instant conditional check for Epoxy
    is_epoxy = (material == "Epoxy")

    # 3. PHYSICAL ENTRY FORM (The rest of the details)
    with st.form("physical_details_form"):
        st.subheader("🔍 Secondary Attributes")

        row2_col1, row2_col2, row2_col3 = st.columns(3)
        with row2_col1:
            finish = st.selectbox("Finish",
                                  ["Glass Cloth", "Steel", "Plain"],
                                  disabled=is_epoxy)
        with row2_col2:
            mica_type = st.selectbox("Mica",
                                     ["Muscovite", "Phlogopite", "Phlogopite(EV)"],
                                     disabled=is_epoxy)
        with row2_col3:
            item_type = st.selectbox("Type", ["Fresh", "Seconds", "Cut", "Open", "Joint", "Damage"])

        st.subheader("📍 Weight & Location")
        row3_col1, row3_col2, row3_col3 = st.columns(3)
        with row3_col1:
            weight = st.number_input("Weight (KG)", min_value=0.0, step=0.1)
        with row3_col2:
            godown = st.selectbox("Godown", ["Godown 1", "Godown 2"])
        with row3_col3:
            rack = st.text_input("Rack / Row")

        submit = st.form_submit_button("Log Stock Batch")

        if submit:
            if not invoice_no or not size:
                st.error("Invoice # and Size are required!")
            else:
                final_finish = "N/A" if is_epoxy else finish
                final_mica = "N/A" if is_epoxy else mica_type

                # --- DATABASE SAVING (CLOUD POSTGRESQL) ---
                conn = get_db_connection()
                cursor = conn.cursor()

                # Table creation check (Using SERIAL for cloud auto-increment)
                cursor.execute('''CREATE TABLE IF NOT EXISTS stock (
                                    id SERIAL PRIMARY KEY,
                                    invoice_no TEXT,
                                    invoiced_item_name TEXT,
                                    size TEXT,
                                    finish TEXT,
                                    "type" TEXT,
                                    material TEXT,
                                    mica_type TEXT,
                                    weight REAL,
                                    godown TEXT,
                                    rack TEXT,
                                    status TEXT,
                                    received_at TIMESTAMP)''')

                # "type" is wrapped in double quotes for PostgreSQL, placeholders changed to %s
                cursor.execute("""
                    INSERT INTO stock 
                    (invoice_no, invoiced_item_name, size, finish, "type", material, mica_type, weight, godown, rack, status, received_at) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (invoice_no, invoiced_item_name, size, final_finish, item_type, material, final_mica, weight,
                      godown, rack, "Available", datetime.now()))

                conn.commit()
                cursor.close()
                conn.close()

                # Discrepancy Alert
                if size not in invoiced_item_name:
                    st.warning(f"⚠️ DISCREPANCY: Measured {size} for invoiced {invoiced_item_name}.")
                else:
                    st.success(f"Successfully logged {size} {material}!")
                    st.rerun()

    # 4. RECENT HISTORY
    st.divider()
    try:
        conn = get_db_connection()
        # "type" isn't fetched here, but query is fully safe
        history_df = pd.read_sql(
            "SELECT invoice_no, size, material, finish, weight FROM stock ORDER BY id DESC LIMIT 5", conn)
        st.write("Recent Entries:")
        st.dataframe(history_df, use_container_width=True, hide_index=True)
        conn.close()
    except Exception as e:
        pass