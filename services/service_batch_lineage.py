import streamlit as st
import psycopg2
import pandas as pd
import warnings

# Suppress pandas DBAPI2 connection warning
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


def extract_thickness(size_str):
    """Extracts gauge/thickness parameter before the '*' symbol."""
    if size_str and '*' in str(size_str):
        return str(size_str).split('*')[0].strip()
    return str(size_str).strip() if size_str else "Unknown"


def sorted_batch_lineage_management():
    st.title("🌳 Sorted Batch Lineage & Genealogy Hub")
    st.info(
        "Trace parent lots to view every child packet created during sorting, including size breakdowns, weights, and real-time inventory statuses."
    )

    conn = get_db_connection()

    # --- FETCH ALL PARENT BATCHES THAT HAVE CHILD RECORDS ---
    query_parents = """
        SELECT DISTINCT 
            p.id AS parent_id, 
            p.invoice_no, 
            p.size AS parent_size, 
            p.type AS parent_type, 
            p.material, 
            p.mica_type, 
            p.finish,
            p.godown, 
            p.rack AS parent_rack, 
            p.status AS parent_status, 
            p.weight AS parent_weight
        FROM stock p
        INNER JOIN stock c ON c.parent_id = p.id
        ORDER BY p.id DESC
    """
    df_parents_raw = pd.read_sql(query_parents, conn)

    if df_parents_raw.empty:
        st.warning(
            "⚠️ No sorting lineage records found. Process mixed lots in the Sorting Hub first to generate child batches.")
        conn.close()
        return

    # Add extracted thickness helper column
    df_parents_raw['Thickness (MM)'] = df_parents_raw['parent_size'].apply(extract_thickness)

    # -----------------------------------------------------------------
    # STEP 1: DYNAMIC PARENT FILTER DECK
    # -----------------------------------------------------------------
    st.subheader("🔍 Step 1: Filter Parent Batches")

    with st.container(border=True):
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)

        # 1. Invoice Number Filter
        avail_invoices = sorted(list(df_parents_raw['invoice_no'].dropna().unique()))
        selected_inv = f_col1.selectbox("Invoice #", ["All Invoices"] + avail_invoices)

        # 2. Thickness Filter
        avail_thick = sorted(list(df_parents_raw['Thickness (MM)'].dropna().unique()))
        selected_thick = f_col2.selectbox("Thickness (MM)", ["All Thicknesses"] + avail_thick)

        # 3. Dynamic Scope for Size Filter
        df_size_scope = df_parents_raw.copy()
        if selected_inv != "All Invoices":
            df_size_scope = df_size_scope[df_size_scope['invoice_no'] == selected_inv]
        if selected_thick != "All Thicknesses":
            df_size_scope = df_size_scope[df_size_scope['Thickness (MM)'] == selected_thick]

        avail_sizes = sorted(list(df_size_scope['parent_size'].dropna().unique()))
        selected_size = f_col3.selectbox("Size (Exact Dimensions)", ["All Sizes"] + avail_sizes)

        # 4. Rack Filter
        avail_racks = sorted(list(df_parents_raw['parent_rack'].dropna().unique()))
        selected_rack = f_col4.selectbox("Rack Location", ["All Racks"] + avail_racks)

        f_col5, f_col6, f_col7, f_col8 = st.columns(4)

        # 5. Mica Type
        avail_micas = sorted(list(df_parents_raw['mica_type'].dropna().unique()))
        selected_mica = f_col5.selectbox("Mica Type", ["All Mica"] + avail_micas)

        # 6. Material
        avail_mats = sorted(list(df_parents_raw['material'].dropna().unique()))
        selected_material = f_col6.selectbox("Material", ["All Materials"] + avail_mats)

        # 7. Finish
        avail_finishes = sorted(list(df_parents_raw['finish'].dropna().unique()))
        selected_finish = f_col7.selectbox("Finish", ["All Finishes"] + avail_finishes)

        # 8. Category Type
        avail_types = sorted(list(df_parents_raw['parent_type'].dropna().unique()))
        selected_type = f_col8.selectbox("Stock Category Group", ["All Types"] + avail_types)

    # --- APPLY FILTERS TO DF_PARENTS ---
    df_parents_filtered = df_parents_raw.copy()

    if selected_inv != "All Invoices":
        df_parents_filtered = df_parents_filtered[df_parents_filtered['invoice_no'] == selected_inv]
    if selected_thick != "All Thicknesses":
        df_parents_filtered = df_parents_filtered[df_parents_filtered['Thickness (MM)'] == selected_thick]
    if selected_size != "All Sizes":
        df_parents_filtered = df_parents_filtered[df_parents_filtered['parent_size'] == selected_size]
    if selected_rack != "All Racks":
        df_parents_filtered = df_parents_filtered[df_parents_filtered['parent_rack'] == selected_rack]
    if selected_mica != "All Mica":
        df_parents_filtered = df_parents_filtered[df_parents_filtered['mica_type'] == selected_mica]
    if selected_material != "All Materials":
        df_parents_filtered = df_parents_filtered[df_parents_filtered['material'] == selected_material]
    if selected_finish != "All Finishes":
        df_parents_filtered = df_parents_filtered[df_parents_filtered['finish'] == selected_finish]
    if selected_type != "All Types":
        df_parents_filtered = df_parents_filtered[df_parents_filtered['parent_type'] == selected_type]

    st.divider()

    if df_parents_filtered.empty:
        st.warning("⚠️ No parent sorting lots match your selected filter criteria.")
        conn.close()
        return

    # -----------------------------------------------------------------
    # STEP 2: SELECT PARENT BATCH FROM FILTERED DROPDOWN
    # -----------------------------------------------------------------
    st.subheader("📦 Step 2: Select Target Parent Batch")

    parent_options = {
        f"Parent ID: {row['parent_id']} | Inv: {row['invoice_no']} | [{row['parent_type']}] | Size: {row['parent_size']} | Loc: {row['godown']}-{row['parent_rack']} | Status: {row['parent_status']}":
            row['parent_id']
        for _, row in df_parents_filtered.iterrows()
    }

    selected_parent_label = st.selectbox(
        f"Choose Parent Lot to Trace ({len(df_parents_filtered)} matching parents found)",
        options=list(parent_options.keys())
    )
    selected_parent_id = parent_options[selected_parent_label]

    parent_row = df_parents_raw[df_parents_raw['parent_id'] == selected_parent_id].iloc[0]

    st.divider()

    # -----------------------------------------------------------------
    # STEP 3: DISPLAY PARENT SPECIFICATION SUMMARY
    # -----------------------------------------------------------------
    st.subheader("📦 Parent Lot Specifications")

    p_col1, p_col2, p_col3, p_col4 = st.columns(4)
    p_col1.metric("Invoice #", parent_row['invoice_no'])
    p_col2.metric("Original Category", parent_row['parent_type'])
    p_col3.metric("Original Size", parent_row['parent_size'])
    p_col4.metric("Current Status", parent_row['parent_status'])

    p_col5, p_col6, p_col7, p_col8 = st.columns(4)
    p_col5.metric("Material", parent_row['material'])
    p_col6.metric("Mica Type", parent_row['mica_type'])
    p_col7.metric("Finish", parent_row['finish'])
    p_col8.metric("Remaining Parent Weight", f"{parent_row['parent_weight']:.2f} KG")

    st.divider()

    # -----------------------------------------------------------------
    # STEP 4: FETCH AND DISPLAY CHILD BATCHES
    # -----------------------------------------------------------------
    query_children = """
        SELECT 
            id AS "Child Stock ID",
            size AS "Extracted Size",
            "type" AS "Stock Type",
            weight AS "Packet Weight (KG)",
            godown AS "Godown",
            rack AS "Rack Location",
            status AS "Current Status",
            received_at AS "Sorting Date",
            invoiced_item_name AS "Origin Note"
        FROM stock
        WHERE parent_id = %s
        ORDER BY id ASC
    """
    df_children = pd.read_sql(query_children, conn, params=[selected_parent_id])

    st.subheader(f"🌱 Extracted Child Batches ({len(df_children)} total packets created)")

    if df_children.empty:
        st.info("No child packets recorded for this parent batch ID.")
        conn.close()
        return

    # Lineage Summary Metrics
    total_child_weight = round(df_children['Packet Weight (KG)'].sum(), 2)
    available_packets = len(df_children[df_children['Current Status'] == 'Available'])
    sold_packets = len(df_children[df_children['Current Status'] == 'Sold'])

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Child Mass Produced", f"{total_child_weight:,.2f} KG")
    m2.metric("Total Packets Created", f"{len(df_children)} packets")
    m3.metric("Available Packets", f"{available_packets} packets")
    m4.metric("Sold Packets", f"{sold_packets} packets")

    st.divider()

    # --- BATCH TYPE BREAKDOWN SUMMARY ---
    st.write("### 📊 Breakdown by Extracted Size Variant:")
    summary_df = df_children.groupby(['Extracted Size', 'Stock Type', 'Rack Location']).agg(
        Packet_Count=('Child Stock ID', 'count'),
        Total_Weight=('Packet Weight (KG)', 'sum')
    ).reset_index().rename(columns={
        'Packet_Count': 'Packets Generated',
        'Total_Weight': 'Subtotal Weight (KG)'
    })

    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    st.divider()

    # --- FULL CHILD PACKET LIST ---
    st.write("### 📋 Complete List of Individual Child Packets:")

    # Format date display
    df_children['Sorting Date'] = pd.to_datetime(df_children['Sorting Date']).dt.strftime('%Y-%m-%d')

    st.dataframe(
        df_children,
        use_container_width=True,
        hide_index=True
    )

    conn.close()