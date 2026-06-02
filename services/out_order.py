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

def out_order_management():
    st.title("📤 Outward Order (Sales & Dispatch)")
    st.info("Filter your inventory step-by-step to quickly locate and select the exact batch being sold.")

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. ENSURE SALES TRACKING TABLE EXISTS (PostgreSQL Compatible Schema)
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

    # 2. FETCH ALL AVAILABLE WAREHOUSE STOCK
    # "type" is wrapped in double quotes because it is a reserved keyword in PostgreSQL
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

    # 3. DYNAMIC FILTER BAR (Narrow down choices step-by-step)
    st.subheader("🛠️ Step 1: Filter Available Stock")

    with st.container(border=True):
        f_col1, f_col2, f_col3 = st.columns(3)
        size_opts = ["All Sizes"] + list(df_raw['size'].unique())
        selected_size = f_col1.selectbox("Filter by Size", size_opts)

        mica_opts = ["All Mica"] + list(df_raw['mica_type'].unique())
        selected_mica = f_col2.selectbox("Filter by Mica Type", mica_opts)

        mat_opts = ["All Materials"] + list(df_raw['material'].unique())
        selected_material = f_col3.selectbox("Filter by Material", mat_opts)

        f_col4, f_col5, f_col6 = st.columns(3)
        finish_opts = ["All Finishes"] + list(df_raw['finish'].unique())
        selected_finish = f_col4.selectbox("Filter by Finish", finish_opts)

        type_opts = ["All Types"] + list(df_raw['type'].unique())
        selected_type = f_col5.selectbox("Filter by Stock Type", type_opts)

        rack_opts = ["All Racks"] + list(df_raw['rack'].unique())
        selected_rack = f_col6.selectbox("Filter by Specific Rack", rack_opts)

    # Apply selection criteria to narrow down the dataset
    df_filtered = df_raw.copy()
    if selected_size != "All Sizes":
        df_filtered = df_filtered[df_filtered['size'] == selected_size]
    if selected_mica != "All Mica":
        df_filtered = df_filtered[df_filtered['mica_type'] == selected_mica]
    if selected_material != "All Materials":
        df_filtered = df_filtered[df_filtered['material'] == selected_material]
    if selected_finish != "All Finishes":
        df_filtered = df_filtered[df_filtered['finish'] == selected_finish]
    if selected_type != "All Types":
        df_filtered = df_filtered[df_filtered['type'] == selected_type]
    if selected_rack != "All Racks":
        df_filtered = df_filtered[df_filtered['rack'] == selected_rack]

    st.write(f"Matching Batches Available: **{len(df_filtered)}**")
    st.dataframe(df_filtered, use_container_width=True, hide_index=True)

    st.divider()

    # 4. SALES DISPATCH ENTRY
    st.subheader("💼 Step 2: Process Dispatch")

    if df_filtered.empty:
        st.error("❌ No batches match your filters.")
        cursor.close()
        conn.close()
        return

    col_select, col_cust = st.columns(2)

    with col_select:
        item_options = {
            f"ID: {row['id']} | Inv: {row['invoice_no']} | Loc: {row['godown']}-{row['rack']} ({row['weight']} KG left)":
                row['id']
            for _, row in df_filtered.iterrows()
        }
        selected_label = st.selectbox("Select Target Batch to Dispatch", list(item_options.keys()))
        selected_id = item_options[selected_label]

        matched_row = df_raw[df_raw['id'] == selected_id].iloc[0]
        current_weight = float(matched_row['weight'])

    with col_cust:
        company_name = st.text_input("Customer / Company Name")

    st.divider()
    col_q, col_p, col_n = st.columns([1, 1, 2])
    with col_q:
        sell_qty = st.number_input("Weight to Sell (KG)", min_value=0.1, max_value=current_weight, step=0.1)
    with col_p:
        price_per_kg = st.number_input("Price per KG (Leave 0.0 if unknown)", min_value=0.0, step=5.0, value=0.0)
    with col_n:
        notes = st.text_input("Transaction Notes")

    total_value = round(sell_qty * price_per_kg, 2)
    if price_per_kg > 0:
        st.write(f"### Total Deal Value: ₹ {total_value:,.2f}")
    else:
        st.warning("⚠️ Price is set to 0.0 (Pending Later Update via Search Page)")

    # 5. COMMIT TRANSACTION DATA HANDLERS
    if st.button("Confirm and Dispatch Order", type="primary", use_container_width=True):
        if not company_name:
            st.error("Company Name is required.")
        else:
            new_weight = round(current_weight - sell_qty, 2)
            timestamp = datetime.now()

            # Insert uses %s syntax, and "type" column is double-quoted
            cursor.execute("""
                INSERT INTO sales (
                    stock_id, invoice_no, size, finish, material, "type", mica_type, 
                    company_name, qty_sold, price_per_kg, total_amount, notes, sale_date
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (int(selected_id), matched_row['invoice_no'], matched_row['size'],
                  matched_row['finish'], matched_row['material'], matched_row['type'],
                  matched_row['mica_type'], company_name, sell_qty, price_per_kg,
                  total_value, notes, timestamp))

            if new_weight <= 0:
                cursor.execute("UPDATE stock SET weight = 0, status = 'Sold' WHERE id = %s", (int(selected_id),))
            else:
                cursor.execute("UPDATE stock SET weight = %s WHERE id = %s", (new_weight, int(selected_id)))

            conn.commit()
            cursor.close()
            conn.close()
            st.success(f"Successfully processed dispatch of {sell_qty} KG to {company_name}!")
            st.rerun()

    # General safety fallback close
    try:
        cursor.close()
        conn.close()
    except:
        pass