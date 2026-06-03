import streamlit as st
import psycopg2
import pandas as pd

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

def item_ledger_management():
    st.title("📋 Product Variant Lifecycle Ledger")
    st.info("Select specific product attributes or choose 'All' to trace aggregated inward entries, sales summaries, and current balances.")

    conn = get_db_connection()
    setup_df = pd.read_sql('SELECT DISTINCT size, mica_type, finish, material, "type" AS type FROM stock', conn)

    # --- SPECIFICATION SELECTOR BAR ---
    with st.container():
        st.subheader("🔍 Filter Product History")
        col1, col2, col3 = st.columns(3)
        selected_size = col1.selectbox("Size", options=["All"] + list(setup_df['size'].unique()))
        selected_mica = col2.selectbox("Mica Type", options=["All"] + list(setup_df['mica_type'].unique()))
        selected_finish = col3.selectbox("Finish", options=["All"] + list(setup_df['finish'].unique()))

        col4, col5 = st.columns(2)
        selected_material = col4.selectbox("Material", options=["All"] + list(setup_df['material'].unique()))
        selected_type = col5.selectbox("Stock Type", options=["All"] + list(setup_df['type'].unique()))

    st.divider()

    # --- DYNAMIC SQL CONFIGURATION ---
    where_clauses = []
    params = []

    if selected_size != "All":
        where_clauses.append("size = %s")
        params.append(selected_size)
    if selected_mica != "All":
        where_clauses.append("mica_type = %s")
        params.append(selected_mica)
    if selected_finish != "All":
        where_clauses.append("finish = %s")
        params.append(selected_finish)
    if selected_material != "All":
        where_clauses.append("material = %s")
        params.append(selected_material)
    if selected_type != "All":
        where_clauses.append('"type" = %s')
        params.append(selected_type)

    where_string = " AND ".join(where_clauses) if where_clauses else "1=1"

    # --- 1. COMPRESSED INWARD RECORDS (GROUPED BY INVOICE) ---
    # CHANGED: Consolidated view casting timestamp to a pure DATE string
    inward_query = f"""
    SELECT 
        invoice_no AS "Incoming Invoice #",
        SUM(weight) AS "Total Weight Left (KG)",
        godown AS "Godown",
        status AS "Status",
        CAST(received_at AS DATE) AS "Received Date"
    FROM stock
    WHERE {where_string}
    GROUP BY invoice_no, godown, status, CAST(received_at AS DATE)
    ORDER BY "Received Date" DESC
    """
    inward_df = pd.read_sql(inward_query, conn, params=params)

    # --- 2. COMPRESSED OUTWARD RECORDS (GROUPED BY TRANSACTION BILLS) ---
    # CHANGED: Consolidated sales reporting sum metrics with truncated dates
    sales_query = f"""
    SELECT 
        company_name AS "Buyer Company",
        SUM(qty_sold) AS "Total Quantity Sold (KG)",
        price_per_kg AS "Rate/KG",
        SUM(total_amount) AS "Total Revenue (₹)",
        CAST(sale_date AS DATE) AS "Sales Date"
    FROM sales
    WHERE {where_string}
    GROUP BY company_name, price_per_kg, CAST(sale_date AS DATE)
    ORDER BY "Sales Date" DESC
    """
    sales_df = pd.read_sql(sales_query, conn, params=params)

    # --- 3. STOCK CALCULATIONS ---
    current_stock_query = f"""
    SELECT SUM(weight) FROM stock 
    WHERE {where_string} AND status = 'Available' AND weight > 0
    """
    cursor = conn.cursor()
    cursor.execute(current_stock_query, params)
    total_left = cursor.fetchone()[0]
    total_left = float(total_left) if total_left else 0.0
    cursor.close()

    total_sold_weight = sales_df['Total Quantity Sold (KG)'].sum() if not sales_df.empty else 0.0
    total_inward_weight = total_left + total_sold_weight

    # --- DISPLAY METRICS ---
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Ever Received", f"{total_inward_weight:,.2f} KG")
    m2.metric("Total Quantities Sold", f"{total_sold_weight:,.2f} KG")
    m3.metric("NET PHYSICAL STOCK LEFT", f"{total_left:,.2f} KG", delta_color="inverse")

    st.divider()

    # Table A: Compressed Inward Log
    st.subheader("📥 Aggregated Inward Entry Logs")
    if not inward_df.empty:
        st.dataframe(inward_df, use_container_width=True, hide_index=True)
    else:
        st.info("No inward lot data logged matching these filters.")

    st.divider()

    # Table B: Compressed Sales Log
    st.subheader("📤 Aggregated Outward Sales Logs")
    if not sales_df.empty:
        st.dataframe(sales_df, use_container_width=True, hide_index=True)
    else:
        st.info("No sales or customer dispatches recorded matching these filters.")

    st.divider()
    filter_summary_text = "Selected Group" if "All" in [selected_size, selected_mica, selected_finish, selected_material, selected_type] else f"{selected_size} | {selected_mica} | {selected_finish} | {selected_material} | {selected_type}"

    st.info(f"""
    ### 📦 Final Stock Position Balance

    Total **{filter_summary_text}** left available across warehouse shelves:

    ## `{total_left:,.2f} KG`
    """)

    conn.close()