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


def bulk_rack_transfer_management():
    st.title("🚚 Bulk Rack Stock Transfer Hub")
    st.info(
        "Select a source rack, pick specific batches, and transfer them to a new rack location without altering any other item metadata."
    )

    conn = get_db_connection()

    # --- STEP 1: FETCH ACTIVE RACKS FROM DATABASE ---
    query_active = """
        SELECT id, invoice_no, size, finish, material, "type", mica_type, weight, godown, rack 
        FROM stock 
        WHERE status = 'Available' AND weight > 0
        ORDER BY rack ASC, id DESC
    """
    df_active = pd.read_sql(query_active, conn)

    if df_active.empty:
        st.warning("⚠️ No active stock currently available in the warehouse.")
        conn.close()
        return

    # Extract list of available racks that currently hold stock
    available_source_racks = sorted(list(df_active['rack'].dropna().unique()))

    # --- STEP 2: SELECT SOURCE RACK ---
    st.subheader("📍 Step 1: Select Source Rack Location")

    col_src, col_info = st.columns([2, 1])

    with col_src:
        selected_source_rack = st.selectbox(
            "Select Origin Rack",
            options=["-- Select Source Rack --"] + available_source_racks
        )

    if selected_source_rack == "-- Select Source Rack --":
        st.info("Please pick an Origin Rack from the drop-down above to view stored items.")
        conn.close()
        return

    # Filter stock located on the selected source rack
    df_source_stock = df_active[df_active['rack'] == selected_source_rack]
    total_rack_weight = round(df_source_stock['weight'].sum(), 2)

    with col_info:
        st.metric("Total Weight on Rack", f"{total_rack_weight:,.2f} KG", delta=f"{len(df_source_stock)} packets")

    st.divider()

    # --- STEP 3: SELECT BATCHES TO MOVE ---
    st.subheader("📦 Step 2: Select Batches to Transfer")

    # Map human-readable option strings to stock row IDs
    batch_options = {
        f"ID: {row['id']} | Inv: {row['invoice_no']} | Size: {row['size']} | {row['mica_type']} | {row['finish']} ({row['weight']} KG)":
            row['id']
        for _, row in df_source_stock.iterrows()
    }

    col_toggle, _ = st.columns([1, 2])
    select_all = col_toggle.checkbox("Select ALL batches on this rack", value=False)

    if select_all:
        selected_ids = list(df_source_stock['id'].unique())
        st.info(f"Selected all **{len(selected_ids)}** items sitting on Rack `{selected_source_rack}`.")
    else:
        selected_labels = st.multiselect(
            "Choose Specific Batches to Relocate",
            options=list(batch_options.keys()),
            placeholder="Select one or more items to move..."
        )
        selected_ids = [batch_options[lbl] for lbl in selected_labels]

    if not selected_ids:
        st.warning("Please select at least one batch item to execute a transfer.")
        conn.close()
        return

    # Isolate selected target rows for preview
    df_selected_batches = df_source_stock[df_source_stock['id'].isin(selected_ids)]
    moving_weight = round(df_selected_batches['weight'].sum(), 2)

    # Preview dataframe of selected items
    st.write("### 👁️ Preview Items Selected for Transfer:")
    st.dataframe(
        df_selected_batches[
            ['id', 'invoice_no', 'size', 'finish', 'material', 'type', 'mica_type', 'weight', 'godown', 'rack']],
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    # --- STEP 4: CHOOSE DESTINATION RACK & EXECUTE TRANSFER ---
    st.subheader("🎯 Step 3: Choose Destination Rack")

    col_dest, col_action = st.columns([2, 1])

    with col_dest:
        target_rack = st.text_input("Enter New Destination Rack Name / Code",
                                    placeholder="e.g., 6M1, 7B1, RACK-04").strip()

    with col_action:
        st.write("##")  # Alignment spacer
        confirm_btn = st.button("🚀 Transfer Batches", type="primary", use_container_width=True)

    if confirm_btn:
        if not target_rack:
            st.error("❌ Destination Rack field cannot be left blank.")
        elif target_rack.upper() == selected_source_rack.upper():
            st.error("❌ Destination Rack must be different from the Source Rack.")
        else:
            try:
                cursor = conn.cursor()

                # Execute batch update query using parameterized tuple arguments
                cursor.execute("""
                    UPDATE stock 
                    SET rack = %s 
                    WHERE id = ANY(%s)
                """, (target_rack.upper(), selected_ids))

                conn.commit()
                cursor.close()

                st.success(
                    f"🎉 Successfully relocated {len(selected_ids)} batches ({moving_weight:,.2f} KG) "
                    f"from Rack '{selected_source_rack}' to Rack '{target_rack.upper()}'!"
                )
                st.rerun()

            except Exception as ex:
                conn.rollback()
                st.error(f"Critical error executing rack transfer: {ex}")

    conn.close()