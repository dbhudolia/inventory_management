import streamlit as st
import sqlite3
import pandas as pd


def item_ledger_management():
    st.title("📋 Product Variant Lifecycle Ledger")
    st.info(
        "Select specific product attributes or choose 'All' to trace incoming entries, sales logs, and current balances.")

    conn = sqlite3.connect('inventory.db')

    # Fetch unique values to populate search filters dynamically
    setup_df = pd.read_sql("SELECT DISTINCT size, mica_type, finish, material, type FROM stock", conn)

    # --- SPECIFICATION SELECTOR BAR (WITH 'ALL' OPTIONS) ---
    with st.container():
        st.subheader("🔍 Filter Product History")
        col1, col2, col3 = st.columns(3)

        # We append "All" to the front of every unique value array
        selected_size = col1.selectbox("Size", options=["All"] + list(setup_df['size'].unique()))
        selected_mica = col2.selectbox("Mica Type", options=["All"] + list(setup_df['mica_type'].unique()))
        selected_finish = col3.selectbox("Finish", options=["All"] + list(setup_df['finish'].unique()))

        col4, col5 = st.columns(2)
        selected_material = col4.selectbox("Material", options=["All"] + list(setup_df['material'].unique()))
        selected_type = col5.selectbox("Stock Type", options=["All"] + list(setup_df['type'].unique()))

    st.divider()

    # --- BUILD THE DYNAMIC SQL WHERE CLAUSE BASED ON SELECTIONS ---
    where_clauses = []
    params = []

    if selected_size != "All":
        where_clauses.append("size = ?")
        params.append(selected_size)
    if selected_mica != "All":
        where_clauses.append("mica_type = ?")
        params.append(selected_mica)
    if selected_finish != "All":
        where_clauses.append("finish = ?")
        params.append(selected_finish)
    if selected_material != "All":
        where_clauses.append("material = ?")
        params.append(selected_material)
    if selected_type != "All":
        where_clauses.append("type = ?")
        params.append(selected_type)

    # Combine clauses; if all are "All", it grabs everything
    where_string = " AND ".join(where_clauses) if where_clauses else "1=1"

    # --- 1. FETCH ALL INWARD RECORDS (RAW ENTRIES) ---
    inward_query = f"""
    SELECT 
        id AS [Batch ID],
        invoice_no AS [Incoming Invoice #],
        weight AS [Current Weight Left (KG)],
        godown AS [Godown],
        rack AS [Rack],
        status AS [Current Status],
        received_at AS [Received Date]
    FROM stock
    WHERE {where_string}
    ORDER BY id DESC
    """
    inward_df = pd.read_sql(inward_query, conn, params=params)

    # --- 2. FETCH ALL OUTWARD RECORDS (SALES LOGS) ---
    sales_query = f"""
    SELECT 
        id AS [Sales ID],
        company_name AS [Buyer Company],
        qty_sold AS [Qty Sold (KG)],
        price_per_kg AS [Rate/KG],
        total_amount AS [Total Revenue],
        sale_date AS [Sale Date],
        notes AS [Special Notes]
    FROM sales
    WHERE {where_string}
    ORDER BY id DESC
    """
    sales_df = pd.read_sql(sales_query, conn, params=params)

    # --- 3. FIX WEIGHT MATHEMATICS METRICS ---
    # Current available physical warehouse stock remaining right now
    current_stock_query = f"""
    SELECT SUM(weight) FROM stock 
    WHERE {where_string} AND status = 'Available' AND weight > 0
    """
    cursor = conn.cursor()
    cursor.execute(current_stock_query, params)
    total_left = cursor.fetchone()[0]
    total_left = total_left if total_left else 0.0

    # Calculate total weight ever sold from the sales tracking table
    total_sold_weight = sales_df['Qty Sold (KG)'].sum() if not sales_df.empty else 0.0

    # CORE METRIC FIX: Total Ever Received = What is Left Now + What was historically Sold
    total_inward_weight = total_left + total_sold_weight

    # --- DISPLAY LEDGER INTERFACE ---

    # Summary Dashboard Cards
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Ever Received (Fixed)", f"{total_inward_weight:,.2f} KG")
    m2.metric("Total Quantities Sold", f"{total_sold_weight:,.2f} KG")
    m3.metric("NET PHYSICAL STOCK LEFT", f"{total_left:,.2f} KG", delta_color="inverse")

    st.divider()

    # Table A: Inward Log
    st.subheader("📥 Inward Entry History (Warehouse Batches)")
    if not inward_df.empty:
        st.dataframe(inward_df, use_container_width=True, hide_index=True)
    else:
        st.info("No inward lot data logged matching these filters.")

    st.divider()

    # Table B: Sales Log
    st.subheader("📤 Outward Sales History (Customer Dispatches)")
    if not sales_df.empty:
        st.dataframe(sales_df, use_container_width=True, hide_index=True)
    else:
        st.info("No sales or customer dispatches recorded matching these filters.")

    # --- THE CRITICAL SUMMARY BALANCE LINE ---
    st.divider()

    filter_summary_text = "Selected Group" if "All" in [selected_size, selected_mica, selected_finish,
                                                        selected_material,
                                                        selected_type] else f"{selected_size} | {selected_mica} | {selected_finish} | {selected_material} | {selected_type}"

    st.info(f"""
    ### 📦 Final Stock Position Balance

    Total **{filter_summary_text}** left available across warehouse shelves:

    ## `{total_left:,.2f} KG`
    """)

    conn.close()