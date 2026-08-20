import streamlit as st
import psycopg2
import pandas as pd
import datetime

def get_db_connection():
    return psycopg2.connect(
        host=st.secrets["postgres"]["host"],
        database=st.secrets["postgres"]["database"],
        user=st.secrets["postgres"]["user"],
        password=st.secrets["postgres"]["password"],
        port=st.secrets["postgres"]["port"]
    )

def get_current_financial_year_dates():
    """Calculates the Indian Financial Year (1-Apr to 31-Mar) based on today's date."""
    today = datetime.date.today()
    if today.month >= 4:
        start_date = datetime.date(today.year, 4, 1)
        end_date = datetime.date(today.year + 1, 3, 31)
    else:
        start_date = datetime.date(today.year - 1, 4, 1)
        end_date = datetime.date(today.year, 3, 31)
    return start_date, end_date

@st.cache_data(ttl=30)
def fetch_sales_register():
    conn = get_db_connection()
    v_df = pd.read_sql("SELECT * FROM tally_sales_vouchers ORDER BY voucher_date DESC, voucher_number DESC;", conn)
    i_df = pd.read_sql("SELECT * FROM tally_sales_items;", conn)
    conn.close()
    return v_df, i_df

def render_tally_sales_page():
    # --- HEADER SECTION ---
    header_col, refresh_col = st.columns([5, 1])
    with header_col:
        st.title("🧾 Tally Sales Register")
        st.caption("Sales invoices and item dispatches synchronized from Tally 9")

    with refresh_col:
        st.write("")
        if st.button("🔄 Refresh Data", key="refresh_sales_btn", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    v_df, i_df = fetch_sales_register()

    if v_df.empty:
        st.warning("⚠️ No sales records found. Run `sync_sales.bat` on your PC first.")
        return

    # Ensure date format is date object
    v_df['voucher_date'] = pd.to_datetime(v_df['voucher_date']).dt.date

    # --- MAIN PAGE FILTERS (ROW 1) ---
    default_start_fy, default_end_fy = get_current_financial_year_dates()
    today = datetime.date.today()

    f_col1, f_col2, f_col3, f_col4 = st.columns([1.5, 1.8, 2, 2])

    with f_col1:
        date_preset = st.selectbox(
            "📅 Date Preset",
            ["Current Financial Year", "This Month", "Last 30 Days", "All Time", "Custom Range"],
            index=0
        )

    # Determine Date Range
    if date_preset == "Current Financial Year":
        filter_start, filter_end = default_start_fy, default_end_fy
    elif date_preset == "This Month":
        filter_start = datetime.date(today.year, today.month, 1)
        filter_end = today
    elif date_preset == "Last 30 Days":
        filter_start = today - datetime.timedelta(days=30)
        filter_end = today
    elif date_preset == "All Time":
        filter_start = v_df['voucher_date'].min()
        filter_end = v_df['voucher_date'].max()
    else:  # Custom Range
        filter_start, filter_end = default_start_fy, default_end_fy

    with f_col2:
        if date_preset == "Custom Range":
            custom_range = st.date_input(
                "Select Date Range",
                value=(default_start_fy, default_end_fy)
            )
            if isinstance(custom_range, tuple) and len(custom_range) == 2:
                filter_start, filter_end = custom_range
        else:
            st.text_input(
                "Active Period",
                value=f"{filter_start.strftime('%d/%m/%Y')} - {filter_end.strftime('%d/%m/%Y')}",
                disabled=True
            )

    # Apply date filter first to populate relevant parties
    date_filtered_v = v_df[(v_df['voucher_date'] >= filter_start) & (v_df['voucher_date'] <= filter_end)].copy()

    with f_col3:
        party_filter = st.selectbox(
            "🏢 Customer / Party",
            ["All Parties"] + sorted(date_filtered_v['party_name'].unique().tolist())
        )

    with f_col4:
        search_txt = st.text_input("🔍 Search Item / Vch No", placeholder="e.g. 0.3 MM, GCF, SAVITA")

    # Apply party & text filters
    filtered_v = date_filtered_v.copy()

    if party_filter != "All Parties":
        filtered_v = filtered_v[filtered_v['party_name'] == party_filter]

    if search_txt:
        matching_v_ids = i_df[i_df['item_name'].str.contains(search_txt, case=False, na=False)]['voucher_id'].unique()
        filtered_v = filtered_v[
            filtered_v['party_name'].str.contains(search_txt, case=False, na=False) |
            filtered_v['voucher_number'].str.contains(search_txt, case=False, na=False) |
            filtered_v['voucher_id'].isin(matching_v_ids)
        ]

    # --- TOP KPIS ---
    total_qty = filtered_v['total_qty_kg'].sum()
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Total Invoices", len(filtered_v))
    kpi2.metric("Total Dispatched", f"{total_qty:,.2f} KG")
    kpi3.metric("Unique Customers", filtered_v['party_name'].nunique())
    kpi4.metric("Active Period", f"{filter_start.strftime('%d %b %Y')} - {filter_end.strftime('%d %b %Y')}")

    st.divider()

    # --- INTERACTIVE INVOICE TABLE ---
    st.subheader(f"📑 Sales Invoices ({len(filtered_v)} records)")
    st.caption("💡 **Tip:** Click on any row below to instantly view its item-level dispatches.")

    filtered_v = filtered_v.reset_index(drop=True)

    # Table with Single-Row Selection
    event = st.dataframe(
        filtered_v[['voucher_date', 'voucher_number', 'party_name', 'buyer_address', 'total_qty_kg', 'total_items_count']],
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "voucher_date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
            "voucher_number": "Vch No",
            "party_name": "Party / Buyer",
            "buyer_address": "Location",
            "total_qty_kg": st.column_config.NumberColumn("Total Qty (KG)", format="%.3f"),
            "total_items_count": "Items Count"
        }
    )

    # --- SYNC TABLE SELECTION WITH DROPDOWN ---
    if 'selected_v_id' not in st.session_state:
        st.session_state['selected_v_id'] = filtered_v['voucher_id'].iloc[0] if not filtered_v.empty else None

    # Update selection on row click
    if event and event.selection and event.selection.rows:
        selected_row_idx = event.selection.rows[0]
        st.session_state['selected_v_id'] = filtered_v.iloc[selected_row_idx]['voucher_id']

    st.divider()

    # --- DRILL DOWN SECTION ---
    st.subheader("🔍 Voucher Item Drill-Down")

    if filtered_v.empty:
        st.info("No matching vouchers found in the selected range.")
        return

    vch_options = filtered_v['voucher_id'].tolist()
    vch_lookup = filtered_v.set_index('voucher_id').to_dict('index')

    if st.session_state['selected_v_id'] not in vch_options:
        st.session_state['selected_v_id'] = vch_options[0]

    current_index = vch_options.index(st.session_state['selected_v_id'])

    selected_v_id = st.selectbox(
        "Selected Invoice:",
        options=vch_options,
        index=current_index,
        format_func=lambda x: f"Vch #{vch_lookup[x]['voucher_number']} | Date: {vch_lookup[x]['voucher_date'].strftime('%d-%m-%Y')} | {vch_lookup[x]['party_name']} ({vch_lookup[x]['total_qty_kg']:.2f} KG)"
    )

    # Display line items
    if selected_v_id:
        v_items = i_df[i_df['voucher_id'] == selected_v_id]
        if not v_items.empty:
            st.dataframe(
                v_items[['item_name', 'billed_qty_numeric', 'actual_qty_numeric', 'unit_of_measure', 'godown', 'batch_name']],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "item_name": st.column_config.TextColumn("Stock Item Description", width="large"),
                    "billed_qty_numeric": st.column_config.NumberColumn("Billed Qty", format="%.3f"),
                    "actual_qty_numeric": st.column_config.NumberColumn("Actual Qty", format="%.3f"),
                    "unit_of_measure": "UOM",
                    "godown": "Godown Location",
                    "batch_name": "Batch Name"
                }
            )
        else:
            st.info("No line-item entries found for this voucher.")