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


def sales_analysis_management():
    st.title("👑 Executive Sales Analysis Dashboard")
    st.info("🔒 Secure Admin View. Access consolidated sales positions, dispatch aggregates, and customer ledger analytics.")

    conn = get_db_connection()

    # --- FETCH FULL HISTORICAL DATASETS ---
    df_raw_sales = pd.read_sql("""
        SELECT 
            id, 
            CAST(sale_date AS DATE) AS "Date", 
            company_name AS "Company", 
            invoice_no AS "Invoice No", 
            size AS "Size", 
            finish AS "Finish", 
            material AS "Material", 
            "type" AS "Type", 
            mica_type AS "Mica Type",
            qty_sold AS "Quantity", 
            price_per_kg AS "Rate/KG", 
            total_amount AS "Revenue",
            notes AS "Notes"
        FROM sales 
        ORDER BY sale_date DESC
    """, conn)
    conn.close()

    if df_raw_sales.empty:
        st.warning("No sales dispatch records found to analyze in the database.")
        return

    df_raw_sales['Date'] = pd.to_datetime(df_raw_sales['Date']).dt.date

    # -----------------------------------------------------------------
    # MASTER FILTER CONTROL DECK (APPLIED BEFORE KPIS & TABS)
    # -----------------------------------------------------------------
    st.markdown("##### 🔍 Multi-Attribute Selection Filters")

    # Row 1 Filters
    sf1, sf2, sf3 = st.columns(3)
    comp_opts = ["All Companies"] + sorted(df_raw_sales['Company'].dropna().unique().tolist())
    selected_comp = sf1.selectbox("Company Name", comp_opts, key="an_comp")

    size_opts = ["All Sizes"] + sorted(df_raw_sales['Size'].dropna().unique().tolist())
    selected_size = sf2.selectbox("Sheet Dimensions", size_opts, key="an_size")

    # Default date range: current calendar year to today
    default_start_date = date(datetime.today().year, 1, 1)
    date_range = sf3.date_input("Accounting Range", value=(default_start_date, datetime.today().date()), key="an_date")

    # Row 2 Filters
    sf4, sf5, sf6, sf7 = st.columns(4)
    mat_opts = ["All Materials"] + sorted(df_raw_sales['Material'].dropna().unique().tolist())
    selected_mat = sf4.selectbox("Material", mat_opts, key="an_mat")

    fin_opts = ["All Finishes"] + sorted(df_raw_sales['Finish'].dropna().unique().tolist())
    selected_fin = sf5.selectbox("Surface Finish", fin_opts, key="an_fin")

    type_opts = ["All Types"] + sorted(df_raw_sales['Type'].dropna().unique().tolist())
    selected_type = sf6.selectbox("Stock Group", type_opts, key="an_type")

    mica_opts = ["All Mica"] + sorted(df_raw_sales['Mica Type'].dropna().unique().tolist())
    selected_mica = sf7.selectbox("Mica Classification", mica_opts, key="an_mica")

    # Filter Application Layer
    df_filtered = df_raw_sales.copy()

    if selected_comp != "All Companies":
        df_filtered = df_filtered[df_filtered['Company'] == selected_comp]
    if selected_size != "All Sizes":
        df_filtered = df_filtered[df_filtered['Size'] == selected_size]
    if selected_mat != "All Materials":
        df_filtered = df_filtered[df_filtered['Material'] == selected_mat]
    if selected_fin != "All Finishes":
        df_filtered = df_filtered[df_filtered['Finish'] == selected_fin]
    if selected_type != "All Types":
        df_filtered = df_filtered[df_filtered['Type'] == selected_type]
    if selected_mica != "All Mica":
        df_filtered = df_filtered[df_filtered['Mica Type'] == selected_mica]

    if isinstance(date_range, tuple) and len(date_range) == 2:
        df_filtered = df_filtered[(df_filtered['Date'] >= date_range[0]) & (df_filtered['Date'] <= date_range[1])]

    st.divider()

    # -----------------------------------------------------------------
    # DYNAMIC KEY PERFORMANCE METRICS (COMPUTED ON FILTERED DATA)
    # -----------------------------------------------------------------
    st.subheader("📊 Key Performance Metrics")
    m1, m2, m3, m4 = st.columns(4)

    filtered_qty = df_filtered['Quantity'].sum()
    filtered_rev = df_filtered['Revenue'].sum()
    filtered_avg_rate = (filtered_rev / filtered_qty) if filtered_qty > 0 else 0.0
    filtered_clients = df_filtered['Company'].nunique()

    m1.metric("Gross Revenue", f"₹ {filtered_rev:,.2f}")
    m2.metric("Total Volume Sold", f"{filtered_qty:,.2f} KG")
    m3.metric("Average Rate / KG", f"₹ {filtered_avg_rate:,.2f}")
    m4.metric("Active Clients", filtered_clients)

    st.divider()

    # --- ADMIN WORKSPACE TABS ---
    tab1, tab2 = st.tabs([
        "📋 Date-wise Party Sales Summary & Drill-Down",
        "🎯 Client & Variant Performance Insights"
    ])

    # -----------------------------------------------------------------
    # TAB 1: DATE-WISE PARTY SUMMARY + GROUPED BY SIZE DRILL-DOWN
    # -----------------------------------------------------------------
    with tab1:
        st.markdown("##### 📅 Date-wise Party Dispatch Summary")
        st.caption("High-level totals per company and date. Click any row to view the size-wise summary.")

        if df_filtered.empty:
            st.warning("No sales records match the selected filter criteria.")
        else:
            party_date_summary = df_filtered.groupby(
                ['Date', 'Company'],
                as_index=False
            ).agg(
                total_qty=('Quantity', 'sum'),
                total_revenue=('Revenue', 'sum'),
                invoice_count=('Invoice No', 'nunique'),
                packet_count=('id', 'count')
            ).sort_values(by=['Date', 'total_qty'], ascending=[False, False]).reset_index(drop=True)

            party_date_summary['event_token'] = party_date_summary['Date'].astype(str) + " | " + party_date_summary['Company']

            # Interactive DataFrame with Single Row Selection
            event = st.dataframe(
                party_date_summary[['Date', 'Company', 'total_qty', 'total_revenue', 'invoice_count', 'packet_count']],
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                column_config={
                    "Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                    "Company": st.column_config.TextColumn("Company / Buyer Name", width="large"),
                    "total_qty": st.column_config.NumberColumn("Total Weight Sold (KG)", format="%.2f"),
                    "total_revenue": st.column_config.NumberColumn("Total Revenue (₹)", format="₹ %.2f"),
                    "invoice_count": st.column_config.NumberColumn("Invoices"),
                    "packet_count": st.column_config.NumberColumn("Total Packets")
                }
            )

            if 'selected_sales_event' not in st.session_state:
                st.session_state['selected_sales_event'] = party_date_summary['event_token'].iloc[0]

            if event and event.selection and event.selection.rows:
                selected_row_idx = event.selection.rows[0]
                st.session_state['selected_sales_event'] = party_date_summary.iloc[selected_row_idx]['event_token']

            st.divider()

            # --- DRILL DOWN: GROUPED BY SIZE ---
            st.subheader("🔍 Size-Wise Variant Summary Drill-Down")

            available_tokens = party_date_summary['event_token'].tolist()
            if st.session_state['selected_sales_event'] not in available_tokens:
                st.session_state['selected_sales_event'] = available_tokens[0]

            current_idx = available_tokens.index(st.session_state['selected_sales_event'])

            selected_event = st.selectbox(
                "Selected Dispatch Record:",
                options=available_tokens,
                index=current_idx,
                format_func=lambda x: f"📅 Date: {x.split(' | ')[0]}  —  🏢 Buyer: {x.split(' | ')[1]}"
            )

            if selected_event:
                sel_date_str, sel_comp = selected_event.split(" | ")
                sel_date = datetime.strptime(sel_date_str, "%Y-%m-%d").date()

                raw_event_df = df_filtered[
                    (df_filtered['Date'] == sel_date) &
                    (df_filtered['Company'] == sel_comp)
                ]

                # Metric Cards for Selected Dispatch
                d_qty = raw_event_df['Quantity'].sum()
                d_rev = raw_event_df['Revenue'].sum()
                d_avg_rate = (d_rev / d_qty) if d_qty > 0 else 0.0

                dc1, dc2, dc3, dc4 = st.columns(4)
                dc1.metric("Selected Buyer", sel_comp)
                dc2.metric("Dispatch Weight", f"{d_qty:,.2f} KG")
                dc3.metric("Invoice Revenue", f"₹ {d_rev:,.2f}")
                dc4.metric("Avg Rate / KG", f"₹ {d_avg_rate:,.2f}")

                # Group by Size Variants
                size_grouped_df = raw_event_df.groupby(
                    ['Size', 'Finish', 'Material', 'Type', 'Mica Type'],
                    dropna=False,
                    as_index=False
                ).agg(
                    total_qty=('Quantity', 'sum'),
                    total_revenue=('Revenue', 'sum'),
                    packets_packed=('id', 'count'),
                    invoices=('Invoice No', lambda x: ", ".join(sorted(set(str(v) for v in x if pd.notnull(v)))))
                )

                size_grouped_df['avg_rate_per_kg'] = size_grouped_df['total_revenue'] / size_grouped_df['total_qty']
                size_grouped_df = size_grouped_df.sort_values(by="total_qty", ascending=False).reset_index(drop=True)

                st.write(f"Size breakdown for **{sel_comp}** on **{sel_date.strftime('%d %b %Y')}** ({len(size_grouped_df)} distinct size variants):")

                st.dataframe(
                    size_grouped_df[[
                        'Size', 'Finish', 'Material', 'Type', 'Mica Type',
                        'total_qty', 'avg_rate_per_kg', 'total_revenue', 'packets_packed', 'invoices'
                    ]],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Size": st.column_config.TextColumn("Sheet Dimensions (Size)", width="medium"),
                        "Finish": "Finish",
                        "Material": "Material",
                        "Type": "Stock Type",
                        "Mica Type": "Mica Type",
                        "total_qty": st.column_config.NumberColumn("Total Weight (KG)", format="%.2f"),
                        "avg_rate_per_kg": st.column_config.NumberColumn("Avg Rate / KG (₹)", format="₹ %.2f"),
                        "total_revenue": st.column_config.NumberColumn("Total Value (₹)", format="₹ %.2f"),
                        "packets_packed": st.column_config.NumberColumn("Packets (#)"),
                        "invoices": st.column_config.TextColumn("Invoices Included", width="medium")
                    }
                )

    # -----------------------------------------------------------------
    # TAB 2: CLIENT & VARIANT PERFORMANCE INSIGHTS
    # -----------------------------------------------------------------
    with tab2:
        if df_filtered.empty:
            st.warning("No data matches current selections to generate chart insights.")
        else:
            st.markdown("##### 🎯 High-Value Business Demands")
            c1, c2 = st.columns(2)

            with c1:
                st.write("**Top 5 Purchasing Clients (By Volume Dispatched - KG)**")
                client_performance = df_filtered.groupby('Company')['Quantity'].sum().reset_index()
                client_performance = client_performance.sort_values(by='Quantity', ascending=False).head(5)
                st.bar_chart(data=client_performance, x='Company', y='Quantity', color="#FF4B4B")

            with c2:
                st.write("**Mica Types Sales Contribution Balance (KG Volume)**")
                mica_volume = df_filtered.groupby('Mica Type')['Quantity'].sum().reset_index()
                st.bar_chart(data=mica_volume, x='Mica Type', y='Quantity', color="#0068C9")

            st.divider()

            # Product Demand Leaderboard
            st.markdown("##### 📏 Most Demanded Product Specifications (Variant Matrix Grouping)")

            df_filtered['order_event_token'] = df_filtered['Company'].astype(str) + " | " + df_filtered['Date'].astype(str)

            spec_leaderboard = df_filtered.groupby(
                ['Size', 'Finish', 'Material', 'Type', 'Mica Type'],
                dropna=False
            ).agg({
                'Quantity': 'sum',
                'Revenue': 'sum',
                'order_event_token': 'nunique'
            }).reset_index()

            spec_leaderboard.columns = [
                "Size Dimensions", "Surface Finish", "Base Material", "Stock Group",
                "Mica Classification", "Total Mass Sold (KG)", "Total Value Generated (₹)",
                "Unique Orders Issued"
            ]

            spec_leaderboard = spec_leaderboard.sort_values(by="Total Mass Sold (KG)", ascending=False).head(15)
            st.dataframe(spec_leaderboard, use_container_width=True, hide_index=True)