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


def stock_sorting_management():
    st.title("✂️ Seconds & Cut Sorting Hub")
    st.info(
        "Process unassorted mixed lots. Filter down bulk boxes by thickness or rack, deduct material weights, and split them into precisely measured variations."
    )

    conn = get_db_connection()

    # Helper function to extract leading gauge digits before the first asterisk
    def extract_thickness(size_str):
        if size_str and '*' in str(size_str):
            return str(size_str).split('*')[0].strip()
        return str(size_str).strip() if size_str else "Unknown"

    # --- FETCH STRUCTURAL CATEGORY ATTRIBUTES ---
    filter_setup_df = pd.read_sql("""
        SELECT DISTINCT size, finish, material, mica_type, rack 
        FROM stock 
        WHERE status = 'Available' AND weight > 0
    """, conn)

    # Compute valid thickness values present on shelves
    filter_setup_df['thickness_mm'] = filter_setup_df['size'].apply(extract_thickness)
    unique_thicknesses = sorted(list(filter_setup_df['thickness_mm'].unique()))

    # -----------------------------------------------------------------
    # STEP 1: DYNAMIC STRUCTURAL FILTER DECK
    # -----------------------------------------------------------------
    st.subheader("🔍 Filter Available Unassorted Stock")

    f_col1, f_col2, f_col3 = st.columns(3)
    f_thick = f_col1.selectbox("Filter by Thickness (MM)", options=["All"] + unique_thicknesses)

    # Dynamically scope size list choices based on selected thickness coordinate
    if f_thick != "All":
        filtered_sizes = filter_setup_df[filter_setup_df['thickness_mm'] == f_thick]['size'].unique()
    else:
        filtered_sizes = filter_setup_df['size'].unique()

    f_size = f_col2.selectbox("Filter by Size (Exact Dimensions)", options=["All"] + sorted(list(filtered_sizes)))
    f_rack = f_col3.selectbox("Filter by Specific Rack Location",
                              options=["All"] + sorted(list(filter_setup_df['rack'].dropna().unique())))

    f_col4, f_col5, f_col6 = st.columns(3)
    f_mica = f_col4.selectbox("Filter by Mica Type",
                              options=["All"] + list(filter_setup_df['mica_type'].dropna().unique()))
    f_finish = f_col5.selectbox("Filter by Finish", options=["All"] + list(filter_setup_df['finish'].dropna().unique()))
    f_material = f_col6.selectbox("Filter by Material",
                                  options=["All"] + list(filter_setup_df['material'].dropna().unique()))

    f_type = st.selectbox("Filter by Stock Category Group",
                          options=["Seconds & Cut Only", "Seconds Only", "Cut Only", "All Bulk Active"])

    # --- BUILD DATA QUERY ---
    where_clauses = ["status = 'Available'", "weight > 0"]
    params = []

    if f_size != "All":
        where_clauses.append("size = %s")
        params.append(f_size)
    if f_rack != "All":
        where_clauses.append("rack = %s")
        params.append(f_rack)
    if f_mica != "All":
        where_clauses.append("mica_type = %s")
        params.append(f_mica)
    if f_finish != "All":
        where_clauses.append("finish = %s")
        params.append(f_finish)
    if f_material != "All":
        where_clauses.append("material = %s")
        params.append(f_material)

    if f_type == "Seconds & Cut Only":
        where_clauses.append(
            "(\"type\" LIKE '%%Seconds%%' OR \"type\" LIKE '%%Cut%%' OR sorting_status = 'Unassorted Bulk')")
    elif f_type == "Seconds Only":
        where_clauses.append("(\"type\" LIKE '%%Seconds%%')")
    elif f_type == "Cut Only":
        where_clauses.append("(\"type\" LIKE '%%Cut%%')")

    final_query = f"""
        SELECT id, invoice_no, size, finish, material, mica_type, "type", weight, godown, rack 
        FROM stock 
        WHERE {" AND ".join(where_clauses)}
        ORDER BY id DESC
    """

    df_bulk = pd.read_sql(final_query, conn, params=params)

    # Extra layer: In-memory thickness filter if exact dimensions are kept open
    if f_thick != "All" and f_size == "All" and not df_bulk.empty:
        df_bulk['tmp_thick'] = df_bulk['size'].apply(extract_thickness)
        df_bulk = df_bulk[df_bulk['tmp_thick'] == f_thick].drop(columns=['tmp_thick'])

    st.divider()

    if df_bulk.empty:
        st.warning("⚠️ No active unassorted matching lots found with the selected filter criteria.")
        conn.close()
        return

    # --- STEP 2: SELECT PARENT SUBSET (MULTI-SELECT) ---
    st.subheader("📦 Step 2: Select Mixed Parent Batch Rows")

    bulk_options = {
        f"ID: {row['id']} | [{row['type']}] | Size: {row['size']} | Loc: {row['godown']}-{row['rack']} | Weight: {row['weight']} KG (Inv: {row['invoice_no']})":
            row['id']
        for _, row in df_bulk.iterrows()
    }

    selected_labels = st.multiselect("Choose One or More Mixed Batches to Process", list(bulk_options.keys()),
                                     placeholder="Select raw batches to sort out")
    selected_parent_ids = [bulk_options[lbl] for lbl in selected_labels]

    if not selected_parent_ids:
        st.info("Highlight target parent lots from the multiselect menu above to open the processing canvas.")
        conn.close()
        return

    # Isolate parent entries picked by user
    df_selected_parents = df_bulk[df_bulk['id'].isin(selected_parent_ids)]
    total_available_parent_weight = round(df_selected_parents['weight'].sum(), 2)
    is_single_choice = len(selected_parent_ids) == 1

    st.divider()

    # --- STEP 3: DEFINE BOOK VALUE BEING REMOVED ---
    st.subheader("⚖️ Step 3: Book Weight Allocation")
    col_w, col_d = st.columns(2)

    if is_single_choice:
        # Context Mode A: Single line selected -> Allow variable weight inputs
        book_weight_to_deduct = col_w.number_input(
            "Book Weight to Deduct from Parent Row (KG)",
            min_value=0.1,
            max_value=total_available_parent_weight,
            step=0.1,
            value=total_available_parent_weight,
            help="Specify exactly how much mass to draw out from this individual entry record"
        )
    else:
        # Context Mode B: Multiple rows checked -> Hard lock total weights to prevent fractions
        book_weight_to_deduct = total_available_parent_weight
        col_w.number_input("Book Weight to Deduct (Locked on All Selected)", value=book_weight_to_deduct, disabled=True)

    sorting_date = col_d.date_input("Processing Date", value=datetime.today())

    st.divider()

    # --- STEP 4: OUTPUT VARIANT BREAKDOWN COMPOSITION ---
    st.subheader("📏 Step 4: Actual Physical Breakdown Outputs")
    st.write("Specify the size, category, packet count, and unit weight found after sorting.")

    num_variants = st.number_input("How many different sizes/categories were made out of it?", min_value=1,
                                   max_value=10, value=2)

    child_entries = []
    primary_parent = df_selected_parents.iloc[0]

    for i in range(int(num_variants)):
        st.markdown(f"**Actual Extracted Variant #{i + 1}**")
        cc1, cc2, cc3, cc4, cc5, cc6 = st.columns([2, 1.5, 1, 1.2, 1.2, 1])

        c_size = cc1.text_input(f"Size Details #{i + 1}", placeholder="e.g., 0.45*1000*600", key=f"c_size_{i}")
        c_type = cc2.selectbox("Type", ["Seconds (Assorted)", "Cut (Assorted)", "Fresh", "Damage"], key=f"c_type_{i}")
        c_packets = cc3.number_input("Packets", min_value=1, step=1, value=1, key=f"c_packets_{i}")
        c_unit_weight = cc4.number_input("KG / Packet", min_value=0.0, step=0.1, key=f"c_unit_weight_{i}")

        # Calculate subtotal weight for this variant line
        line_total_weight = round(c_packets * c_unit_weight, 2)
        cc5.metric("Line Weight", f"{line_total_weight:,.2f} KG")

        c_rack = cc6.text_input("Rack", value=str(primary_parent['rack']), key=f"c_rack_{i}")

        if c_size and c_unit_weight > 0 and c_packets > 0:
            child_entries.append({
                'size': c_size,
                'type': c_type,
                'packets': int(c_packets),
                'unit_weight': float(c_unit_weight),
                'total_weight': line_total_weight,
                'rack': c_rack
            })
        st.markdown("---")

    # Overall weight sum across all variants
    actual_physical_sum = sum(item['total_weight'] for item in child_entries)
    weight_variance = round(actual_physical_sum - book_weight_to_deduct, 2)

    m_col1, m_col2 = st.columns(2)
    m_col1.metric("Total Actual Physical Weight Found", f"{actual_physical_sum:.2f} KG")

    if weight_variance < 0:
        m_col2.metric("Processing Weight Loss (Discrepancy)", f"{weight_variance:.2f} KG",
                      delta=f"{weight_variance:.2f} KG", delta_color="inverse")
    elif weight_variance > 0:
        m_col2.metric("Processing Weight Gain (Discrepancy)", f"+{weight_variance:.2f} KG",
                      delta=f"+{weight_variance:.2f} KG")
    else:
        m_col2.metric("Weight Balance Status", "Perfect Balance (0.00 KG Change)")

    # --- STEP 5: ATOMIC TRANSACTION CLEARANCE ROUTE ---
    if st.button("Commit Sorting Separation Loop", type="primary", use_container_width=True):
        if actual_physical_sum <= 0:
            st.error(
                "❌ You must log at least one sorted child entry with a valid packet count and weight greater than 0 KG.")
        else:
            try:
                cursor = conn.cursor()
                formatted_date_str = sorting_date.strftime("%Y-%m-%d 00:00:00")

                # A. Handle parent database adjustments based on choice execution scopes
                if is_single_choice:
                    p_id = int(selected_parent_ids[0])
                    old_w = float(primary_parent['weight'])
                    new_parent_w = round(old_w - book_weight_to_deduct, 2)

                    if new_parent_w <= 0:
                        cursor.execute("UPDATE stock SET weight = 0, status = 'Sorted Out' WHERE id = %s", (p_id,))
                    else:
                        cursor.execute("UPDATE stock SET weight = %s WHERE id = %s", (new_parent_w, p_id))
                else:
                    # Clear out all parent balances completely
                    for p_id in selected_parent_ids:
                        cursor.execute("UPDATE stock SET weight = 0, status = 'Sorted Out' WHERE id = %s", (int(p_id),))

                # B. Insert child packet rows into the stock database table
                parent_tracking_label = ", ".join(map(str, selected_parent_ids))
                total_created_packets = 0

                for child in child_entries:
                    # Loop through the packet count to generate individual packet records
                    for p_idx in range(child['packets']):
                        cursor.execute("""
                            INSERT INTO stock (
                                invoice_no, invoiced_item_name, size, finish, "type", 
                                material, mica_type, weight, godown, rack, status, received_at, parent_id, sorting_status
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Assorted')
                        """, (
                            primary_parent['invoice_no'],
                            f"Sorted from Lots [{parent_tracking_label}]",
                            child['size'],
                            primary_parent['finish'],
                            child['type'],
                            primary_parent['material'],
                            primary_parent['mica_type'],
                            child['unit_weight'],  # Stores individual packet weight
                            primary_parent['godown'],
                            child['rack'],
                            'Available',
                            formatted_date_str,
                            int(selected_parent_ids[0])
                        ))
                        total_created_packets += 1

                conn.commit()
                cursor.close()
                st.success(
                    f"🎉 Allocation Successful! Cleaned {book_weight_to_deduct} KG from raw inventories and registered {total_created_packets} individual packets ({actual_physical_sum} KG total)."
                )
                st.rerun()

            except Exception as e:
                conn.rollback()
                st.error(f"Critical Database rollback during transactional routing: {e}")

    conn.close()