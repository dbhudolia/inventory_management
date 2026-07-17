import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime


def get_db_connection():
    """Establishes a password-safe connection to Supabase using separate parameters."""
    return psycopg2.connect(
        host=st.secrets["postgres"]["host"],
        database=st.secrets["postgres"]["database"],
        user=st.secrets["postgres"]["user"],
        password=st.secrets["postgres"]["password"],
        port=st.secrets["postgres"]["port"]
    )


def out_order_management():
    st.title("📤 Outward Order (Flexible Batch Dispatch)")
    st.info("Filter stock, select item batches, and process single or multiple orders dynamically.")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sales (
        id SERIAL PRIMARY KEY,
        stock_id INTEGER,
        invoice_no TEXT,
        size TEXT,
        finish TEXT,
        material TEXT,
        "type" TEXT,
        mica_type TEXT,
        company_name TEXT,
        qty_sold REAL,
        price_per_kg REAL,
        total_amount REAL,
        notes TEXT,
        sale_date TIMESTAMP
    )
    """)
    conn.commit()

    query = """
    SELECT id, invoice_no, size, finish, material, "type", mica_type, weight, godown, rack 
    FROM stock 
    WHERE status = 'Available' AND weight > 0
    """
    df_raw = pd.read_sql(query, conn)

    if df_raw.empty:
        st.warning("No active stock currently available in the warehouse.")
        cursor.close()
        conn.close()
        return

    # STEP 1: DYNAMIC FILTER BAR
    st.subheader("🛠️ Step 1: Filter Available Stock")
    with st.container(border=True):
        f_col1, f_col2, f_col3 = st.columns(3)
        selected_size = f_col1.selectbox("Filter by Size", ["All Sizes"] + list(df_raw['size'].unique()))
        selected_mica = f_col2.selectbox("Filter by Mica Type", ["All Mica"] + list(df_raw['mica_type'].unique()))
        selected_material = f_col3.selectbox("Filter by Material",
                                             ["All Materials"] + list(df_raw['material'].unique()))

        f_col4, f_col5, f_col6 = st.columns(3)
        selected_finish = f_col4.selectbox("Filter by Finish", ["All Finishes"] + list(df_raw['finish'].unique()))
        selected_type = f_col5.selectbox("Filter by Stock Type", ["All Types"] + list(df_raw['type'].unique()))
        selected_rack = f_col6.selectbox("Filter by Specific Rack", ["All Racks"] + list(df_raw['rack'].unique()))

    df_filtered = df_raw.copy()
    if selected_size != "All Sizes": df_filtered = df_filtered[df_filtered['size'] == selected_size]
    if selected_mica != "All Mica": df_filtered = df_filtered[df_filtered['mica_type'] == selected_mica]
    if selected_material != "All Materials": df_filtered = df_filtered[df_filtered['material'] == selected_material]
    if selected_finish != "All Finishes": df_filtered = df_filtered[df_filtered['finish'] == selected_finish]
    if selected_type != "All Types": df_filtered = df_filtered[df_filtered['type'] == selected_type]
    if selected_rack != "All Racks": df_filtered = df_filtered[df_filtered['rack'] == selected_rack]

    st.dataframe(df_filtered, use_container_width=True, hide_index=True)
    st.divider()

    # STEP 2: SALES DISPATCH ENTRY
    st.subheader("💼 Step 2: Process Dispatch")
    if df_filtered.empty:
        st.error("❌ No batches match your filters.")
        cursor.close()
        conn.close()
        return

    col_select, col_cust, col_date = st.columns([2.5, 2, 1.5])

    with col_select:
        item_options = {
            f"ID: {row['id']} | Inv: {row['invoice_no']} | Size: {row['size']} | Loc: {row['godown']}-{row['rack']} ({row['weight']} KG)":
                row['id'] for _, row in df_filtered.iterrows()
        }
        selected_labels = st.multiselect("Select Target Batches to Dispatch", list(item_options.keys()),
                                         placeholder="Choose one or more batches")
        selected_ids = [item_options[lbl] for lbl in selected_labels]

    with col_cust:
        cursor.execute(
            "SELECT DISTINCT company_name FROM sales WHERE company_name IS NOT NULL AND company_name != '' ORDER BY company_name ASC")
        known_companies = [row[0] for row in cursor.fetchall()]

        company_dropdown_options = ["[+ Register New Company]"] + known_companies
        selected_company_option = st.selectbox("Select Customer / Company", options=company_dropdown_options,
                                               index=0 if not known_companies else 1)

        if selected_company_option == "[+ Register New Company]":
            company_name = st.text_input("Type New Company Name String", value="")
        else:
            company_name = selected_company_option

    with col_date:
        sales_manual_date = st.date_input("Sales Date", value=datetime.today())

    if not selected_ids:
        st.info("Please select at least one target batch item from the dropdown menu to proceed.")
        cursor.close()
        conn.close()
        return

    # Isolate selected rows
    df_checkout_pool = df_raw[df_raw['id'].isin(selected_ids)]

    # Check if a single batch or multiple batches are highlighted
    is_single_batch = len(selected_ids) == 1

    st.divider()

    # Set up entry parameters based on context rules
    if is_single_batch:
        col_q, col_p, col_n = st.columns([1, 1, 2])
        matched_single_row = df_checkout_pool.iloc[0]
        max_available_weight = float(matched_single_row['weight'])

        with col_q:
            # DYNAMIC INPUT: Shown ONLY when exactly one row is checked
            sell_qty = st.number_input("Weight to Sell (KG)", min_value=0.1, max_value=max_available_weight,
                                       value=max_available_weight, step=0.1)
        with col_p:
            price_per_kg = st.number_input("Price per KG", min_value=0.0, step=5.0, value=0.0)
        with col_n:
            notes = st.text_input("Transaction Notes")
    else:
        col_p, col_n = st.columns([1, 3])
        # AUTOMATIC LOCKIN: Takes the total sum because multiple items are checked
        sell_qty = round(df_checkout_pool['weight'].sum(), 2)

        with col_p:
            price_per_kg = st.number_input("Price per KG", min_value=0.0, step=5.0, value=0.0)
        with col_n:
            notes = st.text_input("Transaction Notes", placeholder="e.g., Combined package contract clearance.")

    total_value = round(sell_qty * price_per_kg, 2)

    # Metric Summary Layout Cards
    m_col1, m_col2 = st.columns(2)
    m_col1.metric("Total Weight Selling (KG)", f"{sell_qty:,.2f} KG",
                  delta=f"{len(selected_ids)} total batches selected")

    if price_per_kg > 0:
        m_col2.metric("Total Deal Value", f"₹ {total_value:,.2f}")
    else:
        st.warning("⚠️ Price is set to 0.0 (Pending Later Update)")

    if st.button("Confirm and Dispatch Selected Batches", type="primary", use_container_width=True):
        if not company_name or company_name.strip() == "":
            st.error("Company Name selection or input string is required.")
        else:
            try:
                sales_date_str = sales_manual_date.strftime("%Y-%m-%d 00:00:00")

                if is_single_batch:
                    # Single execution branch with variable quantity tracking
                    row = df_checkout_pool.iloc[0]
                    p_id = int(row['id'])
                    current_item_weight = float(row['weight'])
                    new_remaining_weight = round(current_item_weight - sell_qty, 2)

                    cursor.execute("""
                        INSERT INTO sales (
                            stock_id, invoice_no, size, finish, material, "type", mica_type, 
                            company_name, qty_sold, price_per_kg, total_amount, notes, sale_date
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (p_id, row['invoice_no'], row['size'], row['finish'], row['material'],
                          row['type'], row['mica_type'], company_name.strip(), sell_qty, price_per_kg,
                          total_value, notes, sales_date_str))

                    if new_remaining_weight <= 0:
                        cursor.execute("UPDATE stock SET weight = 0, status = 'Sold' WHERE id = %s", (p_id,))
                    else:
                        cursor.execute("UPDATE stock SET weight = %s WHERE id = %s", (new_remaining_weight, p_id))
                else:
                    # Multi-batch loop clearing full package totals
                    for _, row in df_checkout_pool.iterrows():
                        p_id = int(row['id'])
                        p_weight = float(row['weight'])
                        packet_amount = round(p_weight * price_per_kg, 2)

                        cursor.execute("""
                            INSERT INTO sales (
                                stock_id, invoice_no, size, finish, material, "type", mica_type, 
                                company_name, qty_sold, price_per_kg, total_amount, notes, sale_date
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (p_id, row['invoice_no'], row['size'], row['finish'], row['material'],
                              row['type'], row['mica_type'], company_name.strip(), p_weight, price_per_kg,
                              packet_amount, notes, sales_date_str))

                        cursor.execute("UPDATE stock SET weight = 0, status = 'Sold' WHERE id = %s", (p_id,))

                conn.commit()
                st.success(f"Successfully processed dispatch of {sell_qty} total KG across {len(selected_ids)} items!")

                cursor.close()
                conn.close()
                st.rerun()

            except Exception as ex:
                conn.rollback()
                st.error(f"Critical transaction rollback triggered by database engine: {ex}")

    try:
        cursor.close()
        conn.close()
    except:
        pass