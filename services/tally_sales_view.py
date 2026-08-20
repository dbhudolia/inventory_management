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
        st.title("🧾 Tally Sales Hub")
        st.caption("Sales invoices, dispatch registers, and executive sales analytics from Tally 9")

    with refresh_col:
        st.write("")
        if st.button("🔄 Refresh Data", key="refresh_sales_btn", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    v_df, i_df = fetch_sales_register()

    if v_df.empty:
        st.warning("⚠️ No sales records found. Run `sync_sales.bat` on your PC first.")
        return

    # Standardize data types
    v_df['voucher_date'] = pd.to_datetime(v_df['voucher_date']).dt.date
    i_df['unit_of_measure'] = i_df['unit_of_measure'].fillna("").str.strip().str.upper()
    i_df['billed_qty_numeric'] = pd.to_numeric(i_df['billed_qty_numeric'], errors='coerce').fillna(0.0)

    # Recompute invoice-level KG and PCS dynamically from line items
    vch_kg = i_df[i_df['unit_of_measure'].isin(['KG', 'KGS'])].groupby('voucher_id')['billed_qty_numeric'].sum().to_dict()
    vch_pcs = i_df[i_df['unit_of_measure'].isin(['PCS', 'NOS', 'PIECES'])].groupby('voucher_id')['billed_qty_numeric'].sum().to_dict()

    v_df['total_kg'] = v_df['voucher_id'].map(vch_kg).fillna(0.0)
    v_df['total_pcs'] = v_df['voucher_id'].map(vch_pcs).fillna(0.0)

    # --- TOP CONTROLS & DATE FILTER BAR ---
    default_start_fy, default_end_fy = get_current_financial_year_dates()
    today = datetime.date.today()

    f_col1, f_col2, f_col3, f_col4 = st.columns([1.5, 1.8, 2, 2])

    with f_col1:
        date_preset = st.selectbox(
            "📅 Date Preset",
            ["Current Financial Year", "This Month", "Last 30 Days", "All Time", "Custom Range"],
            index=0
        )

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
    else:
        filter_start, filter_end = default_start_fy, default_end_fy

    with f_col2:
        if date_preset == "Custom Range":
            custom_range = st.date_input("Select Date Range", value=(default_start_fy, default_end_fy))
            if isinstance(custom_range, tuple) and len(custom_range) == 2:
                filter_start, filter_end = custom_range
        else:
            st.text_input("Active Period", value=f"{filter_start.strftime('%d/%m/%Y')} - {filter_end.strftime('%d/%m/%Y')}", disabled=True)

    date_filtered_v = v_df[(v_df['voucher_date'] >= filter_start) & (v_df['voucher_date'] <= filter_end)].copy()

    with f_col3:
        party_filter = st.selectbox("🏢 Customer / Party", ["All Parties"] + sorted(date_filtered_v['party_name'].unique().tolist()))

    with f_col4:
        search_txt = st.text_input("🔍 Search Item / Vch No", placeholder="e.g. 0.3 MM, GCF, SAVITA")

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

    # Matching items for filtered vouchers
    filtered_items = i_df[i_df['voucher_id'].isin(filtered_v['voucher_id'])].copy()

    # --- TOP EXECUTIVE KPIS ---
    kg_total = filtered_items[filtered_items['unit_of_measure'].isin(['KG', 'KGS'])]['billed_qty_numeric'].sum()
    pcs_total = filtered_items[filtered_items['unit_of_measure'].isin(['PCS', 'NOS', 'PIECES'])]['billed_qty_numeric'].sum()
    total_invoices = len(filtered_v)

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Invoices", f"{total_invoices:,}")
    k2.metric("Total Weight (KG)", f"{kg_total:,.2f} KG")
    k3.metric("Total Count (PCS)", f"{pcs_total:,.0f} PCS")
    k4.metric("Unique Customers", f"{filtered_v['party_name'].nunique()}")
    k5.metric("Line Items", f"{len(filtered_items):,}")

    st.divider()

    # =========================================================================
    # --- SIDE-BY-SIDE TABS (REGISTER & DRILL-DOWN vs. EXECUTIVE INSIGHTS) ---
    # =========================================================================
    tab_register, tab_insights = st.tabs([
        "📑 Sales Register & Drill-Down",
        "📊 Executive Sales Insights & Analytics"
    ])

    # -------------------------------------------------------------------------
    # TAB 1: SALES REGISTER & INTERACTIVE DRILL-DOWN
    # -------------------------------------------------------------------------
    with tab_register:
        st.subheader(f"Invoices Ledger ({len(filtered_v)} matching records)")
        st.caption("💡 **Tip:** Click on any row below to instantly inspect its line-item breakdown.")

        filtered_v = filtered_v.reset_index(drop=True)

        event = st.dataframe(
            filtered_v[['voucher_date', 'voucher_number', 'party_name', 'buyer_address', 'total_kg', 'total_pcs', 'total_items_count']],
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "voucher_date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                "voucher_number": "Vch No",
                "party_name": "Party / Buyer",
                "buyer_address": "Location",
                "total_kg": st.column_config.NumberColumn("Total Weight (KG)", format="%.3f"),
                "total_pcs": st.column_config.NumberColumn("Total Count (PCS)", format="%.0f"),
                "total_items_count": "Line Items"
            }
        )

        if 'selected_v_id' not in st.session_state:
            st.session_state['selected_v_id'] = filtered_v['voucher_id'].iloc[0] if not filtered_v.empty else None

        if event and event.selection and event.selection.rows:
            selected_row_idx = event.selection.rows[0]
            st.session_state['selected_v_id'] = filtered_v.iloc[selected_row_idx]['voucher_id']

        st.divider()

        st.subheader("🔍 Voucher Item Drill-Down")
        if filtered_v.empty:
            st.info("No matching vouchers found.")
        else:
            vch_options = filtered_v['voucher_id'].tolist()
            vch_lookup = filtered_v.set_index('voucher_id').to_dict('index')

            if st.session_state['selected_v_id'] not in vch_options:
                st.session_state['selected_v_id'] = vch_options[0]

            current_index = vch_options.index(st.session_state['selected_v_id'])

            selected_v_id = st.selectbox(
                "Selected Invoice:",
                options=vch_options,
                index=current_index,
                format_func=lambda x: f"Vch #{vch_lookup[x]['voucher_number']} | Date: {vch_lookup[x]['voucher_date'].strftime('%d-%m-%Y')} | {vch_lookup[x]['party_name']}"
            )

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
                    st.info("No line items found for this voucher.")

    # -------------------------------------------------------------------------
    # TAB 2: EXECUTIVE SALES INSIGHTS & ANALYTICS
    # -------------------------------------------------------------------------
    with tab_insights:
        if not filtered_v.empty and not filtered_items.empty:
            # 1. Party Aggregates strictly for KG
            party_items_kg = filtered_items[filtered_items['unit_of_measure'].isin(['KG', 'KGS'])]
            party_kg_agg = party_items_kg.groupby(
                party_items_kg['voucher_id'].map(filtered_v.set_index('voucher_id')['party_name'])
            )['billed_qty_numeric'].sum().reset_index(name='total_kg').sort_values(by='total_kg', ascending=False)

            top_party_name = party_kg_agg.iloc[0]['voucher_id'] if not party_kg_agg.empty else "N/A"
            top_party_kg = party_kg_agg.iloc[0]['total_kg'] if not party_kg_agg.empty else 0.0
            top_party_share = (top_party_kg / kg_total * 100) if kg_total > 0 else 0.0

            # 2. Item Aggregates (Item + Unit)
            item_agg = filtered_items.groupby(['item_name', 'unit_of_measure']).agg(
                total_sold=('billed_qty_numeric', 'sum'),
                dispatch_count=('voucher_id', 'count')
            ).reset_index().sort_values(by='total_sold', ascending=False)

            top_item = item_agg.iloc[0]

            # Executive Highlight Cards
            c_card1, c_card2 = st.columns(2)
            with c_card1:
                st.info(
                    f"🏆 **Top Buyer (Weight Volume):** **{top_party_name}**\n\n"
                    f"• **Dispatched:** `{top_party_kg:,.2f} KG` ({top_party_share:.1f}% of total weight)\n\n"
                    f"• **Invoices:** `{filtered_v[filtered_v['party_name'] == top_party_name]['voucher_id'].count()}` orders"
                )
            with c_card2:
                st.success(
                    f"📦 **Top Selling Product:** **{top_item['item_name']}**\n\n"
                    f"• **Volume Sold:** `{top_item['total_sold']:,.2f} {top_item['unit_of_measure']}`\n\n"
                    f"• **Dispatch Frequency:** Sold across `{top_item['dispatch_count']}` invoices"
                )

            st.divider()

            # Side-by-side Visual Charts
            chart_col1, chart_col2 = st.columns(2)
            with chart_col1:
                st.markdown("#### 🏢 Top 5 Buyers by Weight (KG)")
                if not party_kg_agg.empty:
                    top5_p = party_kg_agg.head(5).set_index('voucher_id')[['total_kg']]
                    st.bar_chart(top5_p, horizontal=True)

            with chart_col2:
                st.markdown("#### 🏷️ Top 5 Products by Weight (KG)")
                kg_items_agg = item_agg[item_agg['unit_of_measure'].isin(['KG', 'KGS'])].head(5)
                if not kg_items_agg.empty:
                    top5_i = kg_items_agg.set_index('item_name')[['total_sold']]
                    st.bar_chart(top5_i, horizontal=True)

            st.divider()

            # Full Item Analytics Table
            st.markdown("#### 📋 Complete Item Dispatch & Movement Summary")
            item_agg['avg_per_dispatch'] = item_agg['total_sold'] / item_agg['dispatch_count']
            st.dataframe(
                item_agg,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "item_name": st.column_config.TextColumn("Stock Item Description", width="large"),
                    "unit_of_measure": "UOM",
                    "total_sold": st.column_config.NumberColumn("Total Sold", format="%.3f"),
                    "dispatch_count": "Invoices Count",
                    "avg_per_dispatch": st.column_config.NumberColumn("Avg / Dispatch", format="%.2f")
                }
            )
        else:
            st.info("No sufficient data in the selected period to generate insights.")