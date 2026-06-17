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
    st.info(
        "🔒 Secure Admin View. Access consolidated sales positions, dispatch aggregates, and customer ledger analytics.")

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

    # --- TOP LEVEL ADMINISTRATIVE METRICS ---
    st.subheader("📊 Key Performance Metrics")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Gross Revenue", f"₹ {df_raw_sales['Revenue'].sum():,.2f}")
    m2.metric("Total Volume Sold", f"{df_raw_sales['Quantity'].sum():,.2f} KG")
    m3.metric("Average Rate / KG", f"₹ {df_raw_sales['Revenue'].sum() / df_raw_sales['Quantity'].sum():,.2f}")
    m4.metric("Active Clients", df_raw_sales['Company'].nunique())

    st.divider()

    # --- ADMIN WORKSPACE TABS ---
    tab1, tab2 = st.tabs([
        "📋 Consolidated Aggregated Sales Summary",
        "🎯 Client & Variant Performance Insights"
    ])

    # -----------------------------------------------------------------
    # THE MASTER FILTER CONTROL DECK (SCOPES BOTH TABS DYNAMICALLY)
    # -----------------------------------------------------------------
    st.markdown("##### 🔍 Multi-Attribute Selection Filters")

    # Row 1 Filters
    sf1, sf2, sf3 = st.columns(3)
    comp_opts = ["All Companies"] + list(df_raw_sales['Company'].unique())
    selected_comp = sf1.selectbox("Company Name", comp_opts, key="an_comp")

    size_opts = ["All Sizes"] + list(df_raw_sales['Size'].unique())
    selected_size = sf2.selectbox("Sheet Dimensions", size_opts, key="an_size")

    date_range = sf3.date_input("Accounting Range", value=(date(2026, 1, 1), datetime.today().date()), key="an_date")

    # Row 2 Filters
    sf4, sf5, sf6, sf7 = st.columns(4)
    mat_opts = ["All Materials"] + list(df_raw_sales['Material'].dropna().unique())
    selected_mat = sf4.selectbox("Material", mat_opts, key="an_mat")

    fin_opts = ["All Finishes"] + list(df_raw_sales['Finish'].dropna().unique())
    selected_fin = sf5.selectbox("Surface Finish", fin_opts, key="an_fin")

    type_opts = ["All Types"] + list(df_raw_sales['Type'].dropna().unique())
    selected_type = sf6.selectbox("Stock Group", type_opts, key="an_type")

    mica_opts = ["All Mica"] + list(df_raw_sales['Mica Type'].dropna().unique())
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
    # TAB 1: CONSOLIDATED AGGREGATED SUMMARY
    # -----------------------------------------------------------------
    with tab1:
        st.markdown("##### 🧮 Consolidated Order Dispatch Grid")

        if df_filtered.empty:
            st.warning("No historical transactions fall under these explicit metric criteria.")
        else:
            # Grouping entries together to compress packet line noise
            agg_df = df_filtered.groupby(
                ['Company', 'Date', 'Invoice No', 'Size', 'Finish', 'Material', 'Type', 'Mica Type', 'Rate/KG',
                 'Notes'],
                dropna=False
            ).agg({
                'Quantity': 'sum',
                'Revenue': 'sum'
            }).reset_index()

            agg_df = agg_df[[
                'Company', 'Date', 'Invoice No', 'Size', 'Finish', 'Material', 'Type',
                'Mica Type', 'Quantity', 'Rate/KG', 'Revenue', 'Notes'
            ]].sort_values(by="Date", ascending=False)

            st.write(f"Displaying **{len(agg_df)}** aggregated business ledger blocks:")
            st.dataframe(agg_df, use_container_width=True, hide_index=True)

    # -----------------------------------------------------------------
    # TAB 2: MANAGEMENT PORTFOLIO STRATEGIC INSIGHTS
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

            # --- UPDATED PRODUCT DEMAND LEADERBOARD MATRIX ---
            st.markdown("##### 📏 Most Demanded Product Specifications (Variant Matrix Grouping)")

            # Create unique order identifier token pairing
            df_filtered['order_event_token'] = df_filtered['Company'].astype(str) + " | " + df_filtered['Date'].astype(
                str)

            # REMOVED: 'Rate/KG' (Price level) has been completely removed from this grouping layer
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