import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime
import warnings

# Suppress the pandas DBAPI2 connection warning
warnings.filterwarnings("ignore", category=UserWarning, module="pandas")


def get_db_connection():
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
        "Process unassorted mixed lots. Deduct weight from bulk boxes and split them into precisely measured variations—accounting for processing weight loss or gain.")

    conn = get_db_connection()

    # Fetch only entries marked as Unassorted Bulk that still have physical weight left
    query = """
    SELECT id, invoice_no, size, finish, material, mica_type, weight, godown, rack 
    FROM stock 
    WHERE status = 'Available' AND weight > 0 AND (sorting_status = 'Unassorted Bulk' OR "type" IN ('Seconds', 'Cut'))
    """
    df_bulk = pd.read_sql(query, conn)

    if df_bulk.empty:
        st.success("🎉 All mixed lots are currently sorted! No bulk seconds/cut items require assortment.")
        conn.close()
        return

    # --- STEP 1: SELECT THE BULK PARENT BATCH ---
    st.subheader("📦 Step 1: Select Mixed Parent Batch")
    bulk_options = {
        f"ID: {row['id']} | Size: {row['size']} | Available Book Weight: {row['weight']} KG (Inv: {row['invoice_no']})":
            row['id']
        for _, row in df_bulk.iterrows()
    }
    selected_label = st.selectbox("Choose Mixed Batch to Process", list(bulk_options.keys()))
    parent_id = bulk_options[selected_label]

    parent_row = df_bulk[df_bulk['id'] == parent_id].iloc[0]
    max_book_weight = float(parent_row['weight'])

    st.divider()

    # --- STEP 2: DEFINE THE BOOK VALUE BEING REMOVED ---
    st.subheader("⚖️ Step 2: Book Weight Deducted")
    col_w, col_d = st.columns(2)

    # This is the weight being subtracted from the parent row's ledger balance
    book_weight_to_deduct = col_w.number_input(
        "Book Weight to Deduct from Parent row (KG)",
        min_value=0.1,
        max_value=max_book_weight,
        step=0.1,
        value=max_book_weight,
        help="How much weight should be removed from this parent record's balance? (Usually the full packet weight)"
    )
    sorting_date = col_d.date_input("Processing Date", value=datetime.today())

    st.divider()

    # --- STEP 3: INPUT THE ACTUAL SORTED BREAKDOWN OUTCOMES ---
    st.subheader("📏 Step 3: Actual Physical Breakdown Outputs")
    st.write("Specify the exact physical weights and dimensions actually found upon opening the packet.")

    num_variants = st.number_input("How many different sizes did you find inside?", min_value=1, max_value=6, value=2)

    child_entries = []
    for i in range(int(num_variants)):
        st.markdown(f"**Actual Extracted Variant #{i + 1}**")
        cc1, cc2, cc3, cc4 = st.columns([2, 1.5, 1.5, 1])

        c_size = cc1.text_input(f"Size Details #{i + 1}", placeholder="e.g., 0.45*1000*600", key=f"c_size_{i}")
        c_type = cc2.selectbox("Type", ["Fresh", "Seconds (Assorted)", "Cut (Assorted)", "Damage / Scrap"],
                               key=f"c_type_{i}")
        c_weight = cc3.number_input("Actual Scaled Weight (KG)", min_value=0.0, step=0.1, key=f"c_weight_{i}")
        c_rack = cc4.text_input("Rack Location", value=str(parent_row['rack']), key=f"c_rack_{i}")

        if c_size and c_weight > 0:
            child_entries.append({
                'size': c_size,
                'type': c_type,
                'weight': c_weight,
                'rack': c_rack
            })
        st.markdown("---")

    # Calculate total actual physical weight entered by user
    actual_physical_sum = sum(item['weight'] for item in child_entries)
    weight_variance = round(actual_physical_sum - book_weight_to_deduct, 2)

    # Display dynamic balancing metrics on screen
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

    # --- STEP 4: EXECUTE SAFE DISCREPANCY TRANSACTION ---
    if st.button("Commit Sorting Separation Loop", type="primary", use_container_width=True):
        if actual_physical_sum <= 0:
            st.error("❌ You must log at least one sorted child entry with a weight greater than 0 KG.")
        else:
            try:
                cursor = conn.cursor()

                # A. Deduct the book value from the parent row
                new_parent_weight = round(max_book_weight - book_weight_to_deduct, 2)

                if new_parent_weight <= 0:
                    cursor.execute("UPDATE stock SET weight = 0, status = 'Sorted Out' WHERE id = %s",
                                   (int(parent_id),))
                else:
                    cursor.execute("UPDATE stock SET weight = %s WHERE id = %s", (new_parent_weight, int(parent_id)))

                # B. Insert the actual physical child rows found
                formatted_date_str = sorting_date.strftime("%Y-%m-%d 00:00:00")

                for child in child_entries:
                    cursor.execute("""
                        INSERT INTO stock (
                            invoice_no, invoiced_item_name, size, finish, "type", 
                            material, mica_type, weight, godown, rack, status, received_at, parent_id, sorting_status
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Assorted')
                    """, (
                        parent_row['invoice_no'],
                        f"Sorted from Lot {parent_id}",
                        child['size'],
                        parent_row['finish'],
                        child['type'],
                        parent_row['material'],
                        parent_row['mica_type'],
                        child['weight'],
                        parent_row['godown'],
                        child['rack'],
                        'Available',
                        formatted_date_str,
                        int(parent_id)
                    ))

                conn.commit()
                cursor.close()
                st.success(
                    f"🎉 Processed! Removed {book_weight_to_deduct} KG book value from Parent Box. Registered {actual_physical_sum} KG of precise sorted variants.")
                st.rerun()

            except Exception as e:
                conn.rollback()
                st.error(f"Database error during transaction processing: {e}")

    conn.close()