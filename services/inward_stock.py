import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime


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
    # This selection now triggers an instant rerun of the app
    material = col_mat.selectbox("Material", ["Rigid", "Flexible", "Epoxy"])

    # LOGIC: Instant check
    is_epoxy = (material == "Epoxy")

    # 3. PHYSICAL ENTRY FORM (The rest of the details)
    with st.form("physical_details_form"):
        st.subheader("🔍 Secondary Attributes")

        row2_col1, row2_col2, row2_col3 = st.columns(3)
        with row2_col1:
            # Now properly disables because 'is_epoxy' is calculated before form starts
            finish = st.selectbox("Finish",
                                  ["Glass Cloth", "Steel", "Plain"],
                                  disabled=is_epoxy)
        with row2_col2:
            mica_type = st.selectbox("Mica",
                                     ["Muscovite", "Phlogopite", "Phlogopite(EV)"])
        with row2_col3:
            item_type = st.selectbox("Type", ["Fresh", "Seconds", "Cut", "Open", "Joint", "Damage"])

        st.subheader("📍 Weight & Location")
        row3_col1, row3_col2, row3_col3 = st.columns(3)
        with row3_col1:
            # Note: I moved weight here so it's in the same row
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

                # --- DATABASE SAVING ---
                conn = sqlite3.connect('inventory.db')
                cursor = conn.cursor()

                # Table creation check
                cursor.execute('''CREATE TABLE IF NOT EXISTS stock (
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

                cursor.execute("""
                    INSERT INTO stock 
                    (invoice_no, invoiced_item_name, size, finish, type, material, mica_type, weight, godown, rack, status, received_at) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (invoice_no, invoiced_item_name, size, final_finish, item_type, material, final_mica, weight,
                      godown, rack, "Available", datetime.now()))

                conn.commit()
                conn.close()

                # Discrepancy Alert
                if size not in invoiced_item_name:
                    st.warning(f"⚠️ DISCREPANCY: Measured {size} for invoiced {invoiced_item_name}.")
                else:
                    st.success(f"Successfully logged {size} {material}!")

    # 4. RECENT HISTORY
    st.divider()
    try:
        conn = sqlite3.connect('inventory.db')
        history_df = pd.read_sql(
            "SELECT invoice_no, size, material, finish, weight FROM stock ORDER BY id DESC LIMIT 5", conn)
        st.write("Recent Entries:")
        st.dataframe(history_df, use_container_width=True, hide_index=True)
        conn.close()
    except:
        pass