import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, date
import warnings

# Suppress the pandas DBAPI2 connection warning
warnings.filterwarnings("ignore", category=UserWarning, module="pandas")


def get_db_connection():
    """Establishes a password-safe connection to Supabase using separate parameters."""
    return psycopg2.connect(
        host=st.secrets["postgres"]["host"],
        database=st.secrets["postgres"]["database"],
        user=st.secrets["postgres"]["user"],
        password=st.secrets["postgres"]["password"],
        port=st.secrets["postgres"]["port"]
    )


def item_ledger_management():
    st.title("📋 Product Variant Lifecycle Ledger")
    st.info(
        "Select product attributes and a date range to calculate opening balances, periodic transfers, and current warehouse positions.")

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
        # --- PERIOD CALENDAR FILTER CONTROLS ---
        st.subheader("📅 Select Accounting Period")
        date_col1, date_col2 = st.columns(2)
        start_date = date_col1.date_input("Start Date", value=date(2026, 1, 1))
        end_date = date_col2.date_input("End Date", value=datetime.today().date())

    st.divider()

    # --- DYNAMIC SQL WHERE CLAUSES ---
    stock_clauses = []
    sales_clauses = []
    base_params = []

    if selected_size != "All":
        stock_clauses.append("size = %s")
        sales_clauses.append("size = %s")
        base_params.append(selected_size)
    if selected_mica != "All":
        stock_clauses.append("mica_type = %s")
        sales_clauses.append("mica_type = %s")
        base_params.append(selected_mica)
    if selected_finish != "All":
        stock_clauses.append("finish = %s")
        sales_clauses.append("finish = %s")
        base_params.append(selected_finish)
    if selected_material != "All":
        stock_clauses.append("material = %s")
        sales_clauses.append("material = %s")
        base_params.append(selected_material)
    if selected_type != "All":
        stock_clauses.append('"type" = %s')
        sales_clauses.append('"type" = %s')
        base_params.append(selected_type)

    stock_where_str = " AND ".join(stock_clauses) if stock_clauses else "1=1"
    sales_where_str = " AND ".join(sales_clauses) if sales_clauses else "1=1"

    start_date_str = start_date.strftime("%Y-%m-%d 00:00:00")
    end_date_str = end_date.strftime("%Y-%m-%d 23:59:59")

    # Fetch full history datasets for the selected configuration variant
    df_all_stock = pd.read_sql(
        f'SELECT id, invoice_no, weight, godown, status, received_at FROM stock WHERE {stock_where_str}', conn,
        params=base_params)
    df_all_sales = pd.read_sql(
        f'SELECT id, stock_id, invoice_no, company_name, qty_sold, price_per_kg, total_amount, sale_date FROM sales WHERE {sales_where_str}',
        conn, params=base_params)
    conn.close()

    if not df_all_stock.empty:
        df_all_stock['received_at'] = pd.to_datetime(df_all_stock['received_at'])
    if not df_all_sales.empty:
        df_all_sales['sale_date'] = pd.to_datetime(df_all_sales['sale_date'])

    t_start = pd.to_datetime(start_date_str)
    t_end = pd.to_datetime(end_date_str)

    # -----------------------------------------------------------------
    # YOUR BLUEPRINT LOGIC STEP-BY-STEP
    # -----------------------------------------------------------------

    # 1. INITIAL VALUE (OPENING BALANCE)
    initial_at_value = 0.0
    df_prior_stock = df_all_stock[df_all_stock['received_at'] < t_start] if not df_all_stock.empty else pd.DataFrame()

    if not df_prior_stock.empty:
        for _, batch in df_prior_stock.iterrows():
            # Get all sales ever made against this specific packet id
            batch_sales = df_all_sales[
                df_all_sales['stock_id'] == batch['id']] if not df_all_sales.empty else pd.DataFrame()

            # Sum up sales that happened BEFORE our opening start date window
            sales_before_start = batch_sales[batch_sales['sale_date'] < t_start][
                'qty_sold'].sum() if not batch_sales.empty else 0.0
            sales_after_start = batch_sales[batch_sales['sale_date'] >= t_start][
                'qty_sold'].sum() if not batch_sales.empty else 0.0

            # The baseline starting packet weight before sales took place
            original_packet_weight = batch['weight'] + batch_sales['qty_sold'].sum() if not batch_sales.empty else \
            batch['weight']

            # Opening weight = Original weight brought in minus what was sold before the start date
            batch_opening_weight = original_packet_weight - sales_before_start
            initial_at_value += max(0.0, batch_opening_weight)

    # 2. TOTAL RECEIVED (IN PERIOD)
    total_received_in_period = 0.0
    df_period_stock = df_all_stock[(df_all_stock['received_at'] >= t_start) & (
                df_all_stock['received_at'] <= t_end)] if not df_all_stock.empty else pd.DataFrame()

    if not df_period_stock.empty:
        for _, batch in df_period_stock.iterrows():
            # Look up if any sales ever happened against this batch at any point in time
            batch_sales = df_all_sales[
                df_all_sales['stock_id'] == batch['id']] if not df_all_sales.empty else pd.DataFrame()
            total_sales_ever = batch_sales['qty_sold'].sum() if not batch_sales.empty else 0.0

            # Original entry weight = current ledger row value + all tracked dispatches
            total_received_in_period += (batch['weight'] + total_sales_ever)

    # 3. TOTAL SOLD (IN PERIOD)
    if not df_all_sales.empty:
        total_sold_in_period = \
        df_all_sales[(df_all_sales['sale_date'] >= t_start) & (df_all_sales['sale_date'] <= t_end)]['qty_sold'].sum()
    else:
        total_sold_in_period = 0.0

    # 4. NET PHYSICAL STOCK LEFT (BALANCING EQUATION)
    left_value = round(initial_at_value + total_received_in_period - total_sold_in_period, 2)

    # --- DISPLAY METRIC CARDS ---
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"Initial Value (As of {start_date.strftime('%d-%b')})", f"{initial_at_value:,.2f} KG")
    m2.metric("Total Received (In Period)", f"{total_received_in_period:,.2f} KG")
    m3.metric("Total Sold (In Period)", f"{total_sold_in_period:,.2f} KG")
    m4.metric("NET PHYSICAL STOCK LEFT", f"{left_value:,.2f} KG", delta_color="inverse")

    st.divider()

    # -----------------------------------------------------------------
    # COMPILING HISTORICAL DATA TABLES
    # -----------------------------------------------------------------

    # TABLE A: INWARD HISTORY DISPLAY
    st.subheader(f"📥 Periodic Inward Entries ({start_date.strftime('%d-%b-%Y')} to {end_date.strftime('%d-%b-%Y')})")
    if not df_period_stock.empty:
        df_period_stock['Received Date'] = df_period_stock['received_at'].dt.date
        inward_summary_rows = []

        for (inv_no, gdn, stat, r_date), group in df_period_stock.groupby(
                ['invoice_no', 'godown', 'status', 'Received Date']):
            # Current remaining live weight inside the window selection group
            current_bal_left = group[group['status'] == 'Available']['weight'].sum()

            # Sum of original entry weights within this invoice grouping
            group_received_total = 0.0
            for _, row in group.iterrows():
                batch_sales = df_all_sales[
                    df_all_sales['stock_id'] == row['id']] if not df_all_sales.empty else pd.DataFrame()
                total_sales_ever = batch_sales['qty_sold'].sum() if not batch_sales.empty else 0.0
                group_received_total += (row['weight'] + total_sales_ever)

            inward_summary_rows.append({
                "Incoming Invoice #": inv_no,
                "Total Weight Received (KG)": round(group_received_total, 2),
                "Current Balance Left (KG)": round(current_bal_left, 2),
                "Godown": gdn,
                "Current Status": stat,
                "Received Date": r_date
            })

        inward_display_df = pd.DataFrame(inward_summary_rows).sort_values(by="Received Date", ascending=False)
        st.dataframe(inward_display_df, use_container_width=True, hide_index=True)
    else:
        st.info("No inward lot entries found within this date window.")

    st.divider()

    # TABLE B: OUTWARD HISTORY DISPLAY
    st.subheader(f"📤 Periodic Outward Sales ({start_date.strftime('%d-%b-%Y')} to {end_date.strftime('%d-%b-%Y')})")
    df_sales_window = df_all_sales[(df_all_sales['sale_date'] >= t_start) & (
                df_all_sales['sale_date'] <= t_end)].copy() if not df_all_sales.empty else pd.DataFrame()

    if not df_sales_window.empty:
        df_sales_window['Sales Date'] = df_sales_window['sale_date'].dt.date
        sales_display_df = df_sales_window.groupby(['company_name', 'price_per_kg', 'Sales Date']).agg({
            'qty_sold': 'sum',
            'total_amount': 'sum'
        }).reset_index()

        sales_display_df.columns = ["Buyer Company", "Rate/KG", "Sales Date", "Total Quantity Sold (KG)",
                                    "Total Revenue (₹)"]
        sales_display_df = sales_display_df[
            ["Buyer Company", "Total Quantity Sold (KG)", "Rate/KG", "Total Revenue (₹)", "Sales Date"]].sort_values(
            by="Sales Date", ascending=False)
        st.dataframe(sales_display_df, use_container_width=True, hide_index=True)
    else:
        st.info("No customer sales dispatches found within this date window.")